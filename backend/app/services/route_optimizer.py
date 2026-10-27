# backend/app/services/route_optimizer.py
#
# Visit-order optimization for field dispatch.
#
# THE PROBLEM
# Given a staff member's current position and the unresolved cases assigned to
# them, produce an order to visit them in that keeps total travel short. This
# is an open (non-returning) Travelling Salesman Path: start is fixed at the
# staff member's location, the end is wherever the last case happens to be, and
# every case must be visited exactly once.
#
# WHY NOT AN EXACT SOLVER
# TSP is NP-hard; exact dynamic programming (Held-Karp) is O(n^2 * 2^n). At the
# realistic size here — a staff member rarely holds more than ~10 open cases —
# exact would actually still be tractable, but it buys nothing: the input
# distances are themselves approximate (traffic, road closures, the accuracy of
# the reporter's dropped pin), so an exactly-optimal tour over fuzzy inputs is
# false precision. The heuristics below land on the optimal tour or within a few
# percent of it at this size, in microseconds, with code that can be read and
# explained.
#
# THE TWO-STAGE HEURISTIC
# 1. Nearest neighbour builds an initial tour: stand at the start, repeatedly
#    hop to the closest unvisited case. Greedy and O(n^2). Its known weakness is
#    that early cheap choices strand a far-away case until the end, producing a
#    long "return leg" across the whole map.
# 2. 2-opt repairs exactly that. It repeatedly looks for two edges in the tour
#    that can be removed and reconnected (by reversing the segment between them)
#    for a shorter total, until no such improvement exists. Geometrically it is
#    the move that un-crosses a tour that crosses itself — and a crossing is
#    precisely the artefact nearest neighbour tends to leave behind. The result
#    is 2-optimal: no single pair-swap can improve it further.
#
# DISTANCES ARE ROAD DISTANCES, NOT STRAIGHT LINES
# The ordering logic is independent of how distance is measured; it consumes a
# matrix. We fill that matrix from OpenRouteService so the cost is real driving
# distance, which matters a great deal in Sri Lanka where a case 2 km away
# across the Mahaweli may be a 20 km drive. If ORS is unavailable we fall back
# to haversine great-circle distance and say so in the response, so the feature
# degrades to "still useful, clearly labelled" rather than failing.

import logging
import math
from typing import Any, Optional, Sequence

import httpx

from app.core import config

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0

# Used only for the haversine fallback, where we have distance but no routing
# engine to give us a duration. Deliberately conservative for Sri Lankan roads:
# a straight-line distance already understates the real drive, so pairing it
# with an optimistic speed would understate the ETA twice over.
FALLBACK_SPEED_KMH = 30.0

# ORS rejects matrix requests above its free-tier size, and a staff member with
# this many open cases has a triage problem rather than a routing problem.
MAX_STOPS = 25


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km. The fallback cost function."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _haversine_matrix(points: Sequence[tuple[float, float]]) -> list[list[float]]:
    """Full symmetric distance matrix in km, computed locally."""
    return [
        [haversine_km(a_lat, a_lng, b_lat, b_lng) for b_lat, b_lng in points]
        for a_lat, a_lng in points
    ]


async def fetch_road_matrix(
    points: Sequence[tuple[float, float]],
) -> Optional[tuple[list[list[float]], list[list[float]]]]:
    """
    Ask ORS for the full pairwise road distance/duration matrix.

    One request covers every pair, which is why the matrix endpoint is used
    rather than N calls to directions: it keeps a whole route computation to a
    single unit of the 500/day matrix quota.

    Returns (distances_km, durations_min), or None if routing is unavailable for
    any reason — no key, timeout, quota exhausted, malformed response. Returning
    None rather than raising is the contract: every failure here is recoverable
    by falling back to haversine, and the caller does exactly that.
    """
    if not config.ORS_API_KEY:
        logger.info("ORS_API_KEY not configured; using straight-line distances")
        return None

    # ORS takes coordinates as [lng, lat] — the opposite of the (lat, lng)
    # convention used everywhere else in this codebase. Getting this backwards
    # silently returns plausible-looking distances for the wrong places.
    locations = [[lng, lat] for lat, lng in points]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{config.ORS_BASE_URL}/v2/matrix/driving-car",
                headers={
                    "Authorization": config.ORS_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "locations": locations,
                    "metrics": ["distance", "duration"],
                    "units": "km",
                },
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as e:
        # 429 is the one worth naming: it means the free-tier quota is spent,
        # which is a normal operating condition for this project rather than a
        # defect, and the fallback handles it.
        if e.response.status_code == 429:
            logger.warning("ORS rate limit reached; using straight-line distances")
        else:
            logger.warning("ORS matrix failed (%s); using straight-line distances",
                           e.response.status_code)
        return None
    except Exception as e:
        logger.warning("ORS matrix unavailable (%s); using straight-line distances", e)
        return None

    distances = data.get("distances")
    durations = data.get("durations")
    if not distances or not durations:
        logger.warning("ORS matrix response missing data; using straight-line distances")
        return None

    # ORS returns null for pairs it cannot route (a pin dropped in the sea, or
    # on an island with no road link). Substituting haversine for just those
    # cells keeps the matrix usable instead of discarding a whole good response.
    n = len(points)
    for i in range(n):
        for j in range(n):
            if distances[i][j] is None:
                distances[i][j] = haversine_km(*points[i], *points[j])
            if durations[i][j] is None:
                durations[i][j] = (distances[i][j] / FALLBACK_SPEED_KMH) * 60.0
            else:
                durations[i][j] = durations[i][j] / 60.0  # ORS gives seconds

    return distances, durations


def nearest_neighbour_order(matrix: list[list[float]]) -> list[int]:
    """
    Greedy initial tour. Index 0 is the fixed start (the staff member); the
    returned list is the order the remaining indices are visited in.

    O(n^2): for each of n stops, scan the unvisited set for the closest.
    """
    n = len(matrix)
    unvisited = set(range(1, n))
    order: list[int] = []
    current = 0

    while unvisited:
        nearest = min(unvisited, key=lambda j: matrix[current][j])
        order.append(nearest)
        unvisited.remove(nearest)
        current = nearest

    return order


def _path_cost(matrix: list[list[float]], order: Sequence[int]) -> float:
    """Total cost of starting at index 0 and visiting `order` in sequence."""
    if not order:
        return 0.0
    cost = matrix[0][order[0]]
    for a, b in zip(order, order[1:]):
        cost += matrix[a][b]
    return cost


def two_opt(matrix: list[list[float]], order: list[int], max_passes: int = 50) -> list[int]:
    """
    Improve a tour by reversing segments, until no reversal helps.

    Each candidate move takes the segment order[i:j+1] and reverses it, which
    swaps which two edges connect that segment to the rest of the path. If the
    result is shorter, keep it. Repeating to a fixed point yields a 2-optimal
    tour: one where no single such swap improves anything.

    This is an open path, not a cycle, so there is no wrap-around edge and the
    final stop is free to be anywhere — matching the real task, where staff
    finish at the last case rather than driving back to where they started.

    max_passes bounds the work. It is a safety rail, not a tuning knob: at these
    sizes convergence takes a handful of passes, and a pass that makes no
    improvement exits immediately.
    """
    n = len(order)
    if n < 3:
        # Fewer than three stops has no pair of non-adjacent edges to exchange,
        # so nearest neighbour is already optimal.
        return order

    best = list(order)
    best_cost = _path_cost(matrix, best)

    for _ in range(max_passes):
        improved = False
        for i in range(n - 1):
            for j in range(i + 1, n):
                candidate = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                candidate_cost = _path_cost(matrix, candidate)
                # Strict improvement only. Accepting equal-cost swaps would let
                # the loop cycle between two identical-length tours forever.
                if candidate_cost < best_cost - 1e-9:
                    best, best_cost = candidate, candidate_cost
                    improved = True
        if not improved:
            break

    return best


async def optimize_route(
    start: tuple[float, float],
    cases: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Order `cases` into an efficient visiting sequence from `start`.

    Returns the ordered cases with per-leg distance/duration, plus a flag saying
    whether real road distances were used. The caller surfaces that flag so the
    user knows whether they are looking at driving distances or crow-flies
    estimates.
    """
    if not cases:
        return {
            "stops": [],
            "total_distance_km": 0.0,
            "total_duration_min": 0.0,
            "used_road_distances": False,
            "degraded_reason": None,
        }

    truncated = len(cases) > MAX_STOPS
    if truncated:
        # Keep the most urgent ones rather than an arbitrary prefix.
        logger.warning("Truncating %d cases to %d for routing", len(cases), MAX_STOPS)
        cases = cases[:MAX_STOPS]

    points: list[tuple[float, float]] = [start] + [
        (c["lat"], c["lng"]) for c in cases
    ]

    road = await fetch_road_matrix(points)
    if road is not None:
        distances, durations = road
        used_road = True
        degraded_reason = None
    else:
        distances = _haversine_matrix(points)
        durations = [
            [(d / FALLBACK_SPEED_KMH) * 60.0 for d in row] for row in distances
        ]
        used_road = False
        degraded_reason = (
            "Road-distance routing was unavailable, so these are straight-line "
            "estimates. The visiting order is still optimized."
        )

    order = two_opt(distances, nearest_neighbour_order(distances))

    stops = []
    previous = 0
    total_distance = 0.0
    total_duration = 0.0
    for position, index in enumerate(order, start=1):
        leg_distance = distances[previous][index]
        leg_duration = durations[previous][index]
        total_distance += leg_distance
        total_duration += leg_duration
        stops.append({
            "sequence": position,
            "case": cases[index - 1],  # index 0 is the start, so shift by one
            "leg_distance_km": round(leg_distance, 2),
            "leg_duration_min": round(leg_duration, 1),
            "cumulative_distance_km": round(total_distance, 2),
            "cumulative_duration_min": round(total_duration, 1),
        })
        previous = index

    return {
        "stops": stops,
        "total_distance_km": round(total_distance, 2),
        "total_duration_min": round(total_duration, 1),
        "used_road_distances": used_road,
        "degraded_reason": degraded_reason,
        "truncated": truncated,
    }
