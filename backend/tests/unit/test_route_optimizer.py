# backend/tests/unit/test_route_optimizer.py
#
# The ordering logic is pure and synchronous, so it is tested directly against
# hand-built matrices rather than through the endpoint. No network is touched.

import asyncio

import pytest

from app.services.route_optimizer import (
    FALLBACK_SPEED_KMH,
    haversine_km,
    nearest_neighbour_order,
    optimize_route,
    two_opt,
    _haversine_matrix,
    _path_cost,
)


# --- haversine ---------------------------------------------------------------

def test_haversine_zero_for_same_point():
    assert haversine_km(6.9271, 79.8612, 6.9271, 79.8612) == pytest.approx(0.0)


def test_haversine_colombo_to_kandy():
    # Real-world sanity check: Colombo -> Kandy is ~94 km straight line.
    d = haversine_km(6.9271, 79.8612, 7.2906, 80.6337)
    assert 90 < d < 100


def test_haversine_is_symmetric():
    a = haversine_km(6.9271, 79.8612, 7.2906, 80.6337)
    b = haversine_km(7.2906, 80.6337, 6.9271, 79.8612)
    assert a == pytest.approx(b)


# --- nearest neighbour -------------------------------------------------------

def test_nearest_neighbour_visits_every_stop_exactly_once():
    matrix = _haversine_matrix([
        (6.90, 79.86), (6.95, 79.86), (6.92, 79.90), (7.00, 79.95),
    ])
    order = nearest_neighbour_order(matrix)
    assert sorted(order) == [1, 2, 3]


def test_nearest_neighbour_picks_the_closest_first():
    # Start at 0. Stop 2 is nearest, then 1, then 3.
    matrix = [
        [0, 10, 1, 20],
        [10, 0, 5, 8],
        [1, 5, 0, 15],
        [20, 8, 15, 0],
    ]
    assert nearest_neighbour_order(matrix) == [2, 1, 3]


def test_nearest_neighbour_handles_single_stop():
    assert nearest_neighbour_order([[0, 5], [5, 0]]) == [1]


# --- 2-opt -------------------------------------------------------------------

def test_two_opt_is_a_noop_below_three_stops():
    matrix = [[0, 3, 4], [3, 0, 5], [4, 5, 0]]
    assert two_opt(matrix, [1, 2]) == [1, 2]


def test_two_opt_never_lengthens_the_tour():
    matrix = _haversine_matrix([
        (6.90, 79.86), (6.95, 79.92), (6.88, 79.95), (6.99, 79.88), (6.93, 79.99),
    ])
    initial = nearest_neighbour_order(matrix)
    improved = two_opt(matrix, initial)
    assert _path_cost(matrix, improved) <= _path_cost(matrix, initial) + 1e-9
    assert sorted(improved) == sorted(initial)


def test_two_opt_fixes_the_crossing_nearest_neighbour_leaves():
    # Four points on a line at x = 0, 1, 2, 3, with the start at x = 0.
    # Greedy order is already 1,2,3 here, so instead we hand 2-opt a
    # deliberately crossed tour and check it untangles it.
    points = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0), (0.0, 3.0)]
    matrix = _haversine_matrix(points)
    crossed = [2, 1, 3]  # 0 -> 2 -> 1 -> 3 doubles back on itself
    fixed = two_opt(matrix, crossed)
    assert fixed == [1, 2, 3]
    assert _path_cost(matrix, fixed) < _path_cost(matrix, crossed)


def test_two_opt_result_is_two_optimal():
    """No single segment reversal should improve the returned tour."""
    matrix = _haversine_matrix([
        (6.90, 79.86), (6.95, 79.92), (6.88, 79.95), (6.99, 79.88),
        (6.93, 79.99), (6.85, 79.90),
    ])
    best = two_opt(matrix, nearest_neighbour_order(matrix))
    best_cost = _path_cost(matrix, best)
    n = len(best)
    for i in range(n - 1):
        for j in range(i + 1, n):
            candidate = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
            assert _path_cost(matrix, candidate) >= best_cost - 1e-9


# --- optimize_route ----------------------------------------------------------

def _case(case_id: str, lat: float, lng: float) -> dict:
    return {
        "id": case_id, "animal_type": "Dog", "description": None,
        "status": "Reported", "urgency": "Medium", "lat": lat, "lng": lng,
        "photo_url": None, "reported_by": None, "assigned_to": "staff-1",
        "reported_at": "2026-09-01T00:00:00+00:00",
        "updated_at": "2026-09-01T00:00:00+00:00",
    }


def test_optimize_route_with_no_cases_is_empty_not_an_error():
    result = asyncio.run(optimize_route((6.9271, 79.8612), []))
    assert result["stops"] == []
    assert result["total_distance_km"] == 0.0
    assert result["total_duration_min"] == 0.0


def test_optimize_route_falls_back_without_an_api_key(monkeypatch):
    monkeypatch.setattr("app.services.route_optimizer.config.ORS_API_KEY", None)
    cases = [_case("a", 6.95, 79.90), _case("b", 6.92, 79.87)]
    result = asyncio.run(optimize_route((6.9271, 79.8612), cases))

    assert result["used_road_distances"] is False
    assert result["degraded_reason"] is not None
    # Degraded, but still ordered and still useful.
    assert len(result["stops"]) == 2


def test_optimize_route_orders_nearest_first(monkeypatch):
    monkeypatch.setattr("app.services.route_optimizer.config.ORS_API_KEY", None)
    start = (6.9000, 79.8600)
    far = _case("far", 7.2906, 80.6337)      # Kandy
    near = _case("near", 6.9100, 79.8700)    # a few km away
    mid = _case("mid", 7.0000, 79.9500)

    result = asyncio.run(optimize_route(start, [far, near, mid]))
    visited = [s["case"]["id"] for s in result["stops"]]
    assert visited == ["near", "mid", "far"]
    assert [s["sequence"] for s in result["stops"]] == [1, 2, 3]


def test_optimize_route_cumulative_totals_are_consistent(monkeypatch):
    monkeypatch.setattr("app.services.route_optimizer.config.ORS_API_KEY", None)
    cases = [_case("a", 6.95, 79.90), _case("b", 6.92, 79.87), _case("c", 7.01, 79.95)]
    result = asyncio.run(optimize_route((6.9000, 79.8600), cases))

    running = 0.0
    for stop in result["stops"]:
        running += stop["leg_distance_km"]
        assert stop["cumulative_distance_km"] == pytest.approx(running, abs=0.02)

    assert result["total_distance_km"] == pytest.approx(
        result["stops"][-1]["cumulative_distance_km"], abs=0.02
    )


def test_fallback_duration_matches_the_documented_speed(monkeypatch):
    monkeypatch.setattr("app.services.route_optimizer.config.ORS_API_KEY", None)
    cases = [_case("a", 6.95, 79.90)]
    result = asyncio.run(optimize_route((6.9000, 79.8600), cases))

    stop = result["stops"][0]
    expected = (stop["leg_distance_km"] / FALLBACK_SPEED_KMH) * 60.0
    assert stop["leg_duration_min"] == pytest.approx(expected, abs=0.1)


def test_optimize_route_uses_road_distances_when_ors_answers(monkeypatch):
    """A successful ORS call must drive the ordering, not just decorate it."""
    # Road matrix deliberately contradicts geography: 'b' is closer as the crow
    # flies, but the road to 'a' is far shorter. The road answer must win.
    async def fake_matrix(points):
        distances = [
            [0.0, 2.0, 40.0],
            [2.0, 0.0, 38.0],
            [40.0, 38.0, 0.0],
        ]
        durations = [[d * 2 for d in row] for row in distances]
        return distances, durations

    monkeypatch.setattr("app.services.route_optimizer.fetch_road_matrix", fake_matrix)

    a = _case("a", 7.2906, 80.6337)   # far away geographically
    b = _case("b", 6.9100, 79.8700)   # near geographically
    result = asyncio.run(optimize_route((6.9000, 79.8600), [a, b]))

    assert result["used_road_distances"] is True
    assert result["degraded_reason"] is None
    assert [s["case"]["id"] for s in result["stops"]] == ["a", "b"]
    assert result["total_distance_km"] == pytest.approx(40.0)


def test_optimize_route_survives_an_ors_outage(monkeypatch):
    # fetch_road_matrix returning None is the contract for every failure mode;
    # here we assert the caller honours it rather than propagating.
    async def failing_matrix(points):
        return None

    monkeypatch.setattr("app.services.route_optimizer.fetch_road_matrix", failing_matrix)
    result = asyncio.run(optimize_route((6.9000, 79.8600), [_case("a", 6.95, 79.90)]))

    assert result["used_road_distances"] is False
    assert len(result["stops"]) == 1
