# backend/app/api/rescue_cases.py

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from datetime import date, datetime, time, timedelta, timezone
from supabase import Client
from fastapi import UploadFile, File
from pydantic import BaseModel
import logging
from time import monotonic
import uuid
from app.core.ids import UuidPath
from app.core.security import require_permission
from app.core.security import has_permission
from app.core.supabase import get_supabase, get_public_supabase
from app.core.audit import log_audit_action
from app.schemas.rescue_case import (
    RescueCaseGeo, CaseStatus, CaseCreate, CaseOut, CaseStatusUpdate, AssigneeOption,
    OutbreakZoneCreate, OutbreakZoneOut, OptimizedRoute, CaseNoteCreate, CaseEventOut,
    CaseOutcome, CaseReport, OutcomeRecord,
)
from app.schemas.hr import SRI_LANKA
from postgrest.exceptions import APIError
from app.services.board_events import notify_board_changed
from app.services.notifications import notify
from app.services.case_classifier import classify_case_urgency
from app.services.route_optimizer import optimize_route

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/geo", response_model=list[RescueCaseGeo])
async def get_case_geo(
    status: Optional[CaseStatus] = Query(None, description="Filter by case status"),
    days: Optional[int] = Query(None, description="Only cases reported in the last N days"),
    supabase: Client = Depends(get_public_supabase),
):
    query = supabase.table("rescue_cases").select(
        "id, animal_type, status, lat, lng, reported_at"
    )

    if status:
        query = query.eq("status", status.value)

    if days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        query = query.gte("reported_at", cutoff)

    response = query.execute()
    rows = response.data or []

    for row in rows:
        row["lat"] = round(row["lat"], 3)
        row["lng"] = round(row["lng"], 3)

    return rows


@router.post("/cases", response_model=CaseOut)
async def create_case(
    payload: CaseCreate,
    supabase: Client = Depends(get_public_supabase),
):
    classification = await classify_case_urgency(payload.animal_type, payload.description)

    response = supabase.table("rescue_cases").insert({
        **payload.model_dump(exclude_none=True),
        "urgency": classification["urgency"],
        "urgency_reason": classification["reason"],
        "urgency_source": classification["source"],
    }).execute()

    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to create case")

    # Public endpoint: reports come from anonymous members of the public, so a
    # null user_id here is the accurate record, not a missing attribution.
    await log_audit_action(
        supabase,
        user_id=None,
        action_type="RESCUE_CASE_CREATE",
        table_name="rescue_cases",
        old_payload=None,
        new_payload=response.data[0],
    )

    await notify_board_changed()

    return response.data[0]


@router.post("/upload-photo")
async def upload_case_photo(
    file: UploadFile = File(...),
    supabase: Client = Depends(get_public_supabase),
):
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(400, "Only JPEG, PNG, or WebP images are allowed")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:  # 5MB cap
        raise HTTPException(400, "Image must be under 5MB")

    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    path = f"{uuid.uuid4()}.{ext}"

    supabase.storage.from_("case-photos").upload(
        path, contents, {"content-type": file.content_type}
    )

    public_url = supabase.storage.from_("case-photos").get_public_url(path)
    return {"photo_url": public_url}


@router.get("/cases", response_model=list[CaseOut])
async def list_cases(
    status: Optional[CaseStatus] = Query(None, description="Filter by case status"),
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("rescue:read")),
):
    query = supabase.table("rescue_cases").select("*").order("reported_at", desc=True)
    if status:
        query = query.eq("status", status.value)

    cases = query.execute().data or []

    # Joined here rather than embedded by PostgREST: rescue_cases.assigned_to
    # has no foreign key to users, so there is no relationship to embed on.
    # Fetches only the users actually assigned to these cases.
    assigned_ids = sorted({c["assigned_to"] for c in cases if c.get("assigned_to")})
    if assigned_ids:
        by_id = _people(supabase, assigned_ids)
        for c in cases:
            # A deleted user leaves assigned_to pointing at nothing; the card
            # then shows "Assigned" rather than the request failing.
            c["assignee"] = by_id.get(c.get("assigned_to"))

    return cases


def _people(supabase: Client, user_ids) -> dict[str, dict]:
    """{user_id: CaseAssignee-shaped dict} for the given users. A deleted user
    is simply missing, so callers fall back to None."""
    ids = sorted({str(i) for i in user_ids if i})
    if not ids:
        return {}
    users = supabase.table("users").select("id, email").in_("id", ids).execute().data or []
    names = _display_names(supabase, ids)
    return {u["id"]: {"email": u["email"], "display_name": names.get(u["id"])} for u in users}


def _display_names(supabase: Client, user_ids: list[str]) -> dict[str, str]:
    """first + last name per user, from employee_profile where one exists.

    Names only: employee_profile also holds NIC and base_salary, so the select
    is spelled out rather than "*".
    """
    rows = (
        supabase.table("employee_profile")
        .select("user_id, first_name, last_name")
        .in_("user_id", user_ids)
        .execute()
        .data
        or []
    )
    names = {}
    for r in rows:
        name = " ".join(p for p in (r.get("first_name"), r.get("last_name")) if p)
        if name:
            names[r["user_id"]] = name
    return names


@router.get("/assignees", response_model=list[AssigneeOption])
async def list_assignees(
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("rescue:assign")),
):
    """
    Users the assign dropdown may offer. Gated on rescue:assign, the permission
    to hand a case to someone else, so it is not a directory for every
    rescue:read holder (General Staff is the open-signup role).

    Eligible means the user's role holds rescue:manage, which is what working
    a case through to Resolved requires. Derived from the permission table
    rather than a role list, so it cannot drift from it. In practice: Admin,
    Operations Lead, General Staff — the set the board filtered to before.
    """
    users = supabase.table("users").select("id, email, roles(role_name)").execute().data or []
    eligible = [
        u for u in users
        if has_permission((u.get("roles") or {}).get("role_name") or "", "rescue:manage")
    ]
    names = _display_names(supabase, [u["id"] for u in eligible]) if eligible else {}
    return sorted(
        (
            {
                "id": u["id"],
                "email": u["email"],
                "display_name": names.get(u["id"]),
                "role_name": u["roles"]["role_name"],
            }
            for u in eligible
        ),
        key=lambda a: (a["display_name"] or a["email"]).lower(),
    )


@router.get("/my-route", response_model=OptimizedRoute)
async def get_my_route(
    lat: float = Query(..., ge=-90, le=90, description="Staff member's current latitude"),
    lng: float = Query(..., ge=-180, le=180, description="Staff member's current longitude"),
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("rescue:read")),
):
    """
    An efficient visiting order for the caller's own open cases.

    Gated on rescue:read rather than a dedicated permission: this exposes a
    strict subset of what GET /cases already returns to the same user, so a
    separate permission would be granted to exactly the same roles and add a
    second thing to keep in sync for no access-control gain.

    Scoped to assigned_to = the caller. Not a parameter, deliberately — there is
    no route-for-another-user case, and accepting a user id here would need its
    own authorization check to stop staff enumerating each other's workloads.

    Pure read, so nothing is written to the audit log.
    """
    response = (
        supabase.table("rescue_cases")
        .select("*")
        .eq("assigned_to", str(current_user["id"]))
        .neq("status", CaseStatus.resolved.value)
        .order("reported_at", desc=False)
        .execute()
    )

    cases = response.data or []

    # A case with no coordinates cannot be routed to. Dropping it beats failing
    # the whole request, and beats sending (0, 0) to the routing engine — which
    # would silently anchor the tour in the Atlantic.
    routable = [c for c in cases if c.get("lat") is not None and c.get("lng") is not None]

    result = await optimize_route((lat, lng), routable)
    return result


@router.patch("/cases/{case_id}/status", response_model=CaseOut)
async def update_case_status(
    case_id: UuidPath,
    payload: CaseStatusUpdate,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("rescue:read")),
):
    existing = (
        supabase.table("rescue_cases")
        # Full row rather than just the two fields the permission checks need,
        # so the audit entry records the case as it actually stood beforehand.
        .select("*")
        .eq("id", case_id)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Case not found")

    role_name = (current_user.get("roles", {}).get("role_name") or "")
    current_status = existing.data[0]["status"]
    current_assignee = existing.data[0]["assigned_to"]

    # Claiming a freshly reported case is the act of assigning, so rescue:assign covers
    # it on its own — claiming a case also starts it, moving it straight to In Treatment.
    # Every other status move (including reopening a Resolved case) is case management.
    is_assignment_handoff = (
        current_status == CaseStatus.reported.value
        and payload.new_status == CaseStatus.in_treatment
        and payload.assigned_to is not None
    )
    if payload.new_status.value != current_status and not is_assignment_handoff:
        if not has_permission(role_name, "rescue:manage"):
            raise HTTPException(403, "You do not have permission to change case status")

    if payload.assigned_to is not None:
        is_self_assign = str(payload.assigned_to) == str(current_user["id"])
        if not is_self_assign and not has_permission(role_name, "rescue:assign"):
            raise HTTPException(403, "Only Director/HR Officer/Admin can assign cases to other staff")
        # Claiming a case yourself means working it, and moving it on to
        # Resolved needs rescue:manage. Without this, a rescue:assign-only role
        # (HR Officer, Director) could claim a case through the handoff above
        # and then own one it can never close. Matches the board, which offers
        # those roles neither "Assign to me" nor themselves in the dropdown.
        if is_self_assign and not has_permission(role_name, "rescue:manage"):
            raise HTTPException(403, "Claiming a case requires permission to work it (rescue:manage)")

    # Resolving means saying what happened to the animal (confirmed
    # 2026-11-13), so the outcome is required on the move into Resolved and
    # refused on every other request. Changing a recorded outcome means
    # reopening the case, which the timeline then shows.
    entering_resolved = (
        payload.new_status == CaseStatus.resolved and current_status != CaseStatus.resolved.value
    )
    outcome_note = (payload.outcome_note or "").strip() or None
    if entering_resolved and payload.outcome is None:
        raise HTTPException(400, "Choose an outcome to resolve the case")
    if not entering_resolved and (payload.outcome is not None or outcome_note):
        raise HTTPException(400, "An outcome can only be recorded when resolving a case")

    # Reported is the only stage a case can sit in unclaimed. Leaving it requires
    # an assignee — either one already on the case or one supplied here — so a
    # raw drag or a direct API call can't produce an "In Treatment"/"Resolved"
    # case nobody owns.
    if payload.new_status != CaseStatus.reported:
        if current_assignee is None and payload.assigned_to is None:
            raise HTTPException(400, "A case must have an assignee to move past Reported")

    update_data = {"status": payload.new_status.value}
    if payload.new_status == CaseStatus.reported:
        # Moving back to Reported always releases the claim.
        update_data["assigned_to"] = None
    elif payload.assigned_to is not None:
        update_data["assigned_to"] = str(payload.assigned_to)
    if entering_resolved:
        update_data["outcome"] = payload.outcome.value
        update_data["resolved_at"] = datetime.now(timezone.utc).isoformat()
    elif current_status == CaseStatus.resolved.value and payload.new_status != CaseStatus.resolved:
        # Reopened: the outcome no longer describes the case. The timeline
        # keeps the old one.
        update_data["outcome"] = None
        update_data["resolved_at"] = None

    response = supabase.table("rescue_cases").update(update_data).eq("id", case_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Case not found")

    updated = response.data[0]
    before = existing.data[0]

    # Status change and assignment are gated on different permissions
    # (rescue:manage vs rescue:assign) precisely because they are different
    # kinds of act. The audit trail keeps that distinction rather than
    # flattening one endpoint into one action type. A single request that does
    # both emits both entries.
    if updated.get("status") != before.get("status"):
        await log_audit_action(
            supabase,
            user_id=current_user["id"],
            action_type="RESCUE_CASE_STATUS_UPDATE",
            table_name="rescue_cases",
            old_payload=before,
            new_payload=updated,
        )

    if updated.get("assigned_to") != before.get("assigned_to"):
        await log_audit_action(
            supabase,
            user_id=current_user["id"],
            action_type="RESCUE_CASE_ASSIGN",
            table_name="rescue_cases",
            old_payload={"id": case_id, "assigned_to": before.get("assigned_to")},
            new_payload={"id": case_id, "assigned_to": updated.get("assigned_to")},
        )

    # Someone else handed you the case (migration 032). Claiming it yourself
    # sends nothing: notify() skips the actor.
    new_assignee = updated.get("assigned_to")
    if new_assignee and new_assignee != before.get("assigned_to"):
        actor = _people(supabase, [current_user["id"]]).get(str(current_user["id"])) or {}
        by = actor.get("display_name") or actor.get("email")
        notify(supabase, [new_assignee], actor_id=current_user["id"], kind="case_assigned",
               title=f"You were assigned a {updated.get('animal_type') or 'rescue'} case",
               body=f"{updated.get('urgency') or 'Unknown'} urgency, {updated.get('status')}."
                    + (f" Assigned by {by}." if by else ""),
               href="/case-triage")

    _record_events(
        supabase, case_id, current_user["id"], before, updated,
        outcome=payload.outcome.value if entering_resolved else None,
        outcome_note=outcome_note,
    )

    # Same condition as the audit entries: a no-op request (e.g. Reported ->
    # Reported) changes nothing on the board, so it pings nobody.
    if (updated.get("status") != before.get("status")
            or updated.get("assigned_to") != before.get("assigned_to")):
        await notify_board_changed()

    return updated


def _record_events(supabase: Client, case_id: str, author_id, before: dict, updated: dict,
                   outcome: Optional[str], outcome_note: Optional[str]) -> None:
    """Add this change to the case's timeline: the assignment first, then the
    status move, then the outcome, so a claim reads "assigned to X" before
    "moved to In Treatment".

    Fail-soft. The case has already changed and the audit log has recorded it;
    failing the request now would tell staff that a move they can see on the
    board did not happen.
    """
    # Every row carries every column: PostgREST refuses a bulk insert whose
    # rows have different keys (PGRST102, "All object keys must match").
    base = {
        "case_id": case_id, "author_id": str(author_id), "body": None, "from_status": None,
        "to_status": None, "outcome": None, "assignee_id": None,
    }
    events = []
    if updated.get("assigned_to") != before.get("assigned_to"):
        events.append({**base, "event_type": "assign", "assignee_id": updated.get("assigned_to")})
    if updated.get("status") != before.get("status"):
        events.append({**base, "event_type": "status",
                       "from_status": before.get("status"), "to_status": updated.get("status")})
    if outcome:
        events.append({**base, "event_type": "outcome", "outcome": outcome, "body": outcome_note})
    if not events:
        return
    try:
        supabase.table("rescue_case_events").insert(events).execute()
    except Exception:
        logger.exception("Could not add timeline events for case %s", case_id)


def _get_case(supabase: Client, case_id: str) -> dict:
    rows = supabase.table("rescue_cases").select("*").eq("id", case_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Case not found")
    return rows[0]


@router.get("/cases/{case_id}/timeline", response_model=list[CaseEventOut])
async def get_case_timeline(
    case_id: UuidPath,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("rescue:read")),
):
    """Everything that has happened on a case, oldest first.

    Same gate as the board: whoever can see a case can see its history. Pure
    read, so nothing is written to the audit log.
    """
    case = _get_case(supabase, case_id)
    events = (
        supabase.table("rescue_case_events")
        .select("*")
        .eq("case_id", case_id)
        .order("created_at")
        .order("id")
        .execute()
        .data
        or []
    )
    supplies = _case_movements(supabase, case_id, "*, inventory_items(item_name)")
    people = _people(
        supabase,
        [case.get("reported_by")]
        + [e.get("author_id") for e in events]
        + [e.get("assignee_id") for e in events]
        + [m.get("recorded_by") for m in supplies],
    )

    reported = {
        "id": 0,
        "event_type": "reported",
        "body": case.get("description"),
        "author": people.get(case.get("reported_by")),
        "created_at": case["reported_at"],
    }
    lines = [
        {
            **e,
            "author": people.get(e.get("author_id")),
            "assignee": people.get(e.get("assignee_id")),
        }
        for e in events
    ] + [_supplies_line(m, people) for m in supplies]
    # Stable, so lines saved at the same moment keep their stored order.
    lines.sort(key=lambda line: _as_utc(line["created_at"]))
    return [reported] + lines


def _as_utc(value) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _case_movements(supabase: Client, case_id_or_ids, columns: str) -> list[dict]:
    """The Stock Outs used on one case (or several) and their reversals.
    Empty before migration 031, which adds the column, so the timeline and
    the report still work without it."""
    query = supabase.table("inventory_transactions").select(columns)
    if isinstance(case_id_or_ids, list):
        if not case_id_or_ids:
            return []
        query = query.in_("rescue_case_id", case_id_or_ids)
    else:
        query = query.eq("rescue_case_id", case_id_or_ids)
    try:
        return query.execute().data or []
    except APIError as e:
        if "rescue_case_id" in str(getattr(e, "message", "") or e):
            return []
        raise


def _supplies_line(m: dict, people: dict) -> dict:
    # A reversal of a case's Stock Out is a Return carrying the same case.
    reversed_ = m.get("transaction_type") == "Return"
    # created_at is only on movements saved after 031; the movement's date
    # (midnight, Sri Lanka time) stands in for any older one.
    when = m.get("created_at") or datetime.combine(
        date.fromisoformat(str(m["transaction_date"])[:10]), time(), SRI_LANKA
    ).isoformat()
    return {
        "id": m.get("transaction_id") or m.get("id") or 0,
        "event_type": "supplies_reversed" if reversed_ else "supplies",
        "body": m.get("notes"),
        "item_name": (m.get("inventory_items") or {}).get("item_name"),
        "quantity": m.get("quantity"),
        "cost": round(float(m.get("total_cost") or 0), 2),
        "author": people.get(m.get("recorded_by")),
        "created_at": when,
    }


def _net_supplies_cost(movements: list[dict]) -> dict[str, float]:
    """{case_id: Stock Outs less their reversals}."""
    totals: dict[str, float] = {}
    for m in movements:
        sign = -1 if m.get("transaction_type") == "Return" else 1
        key = str(m["rescue_case_id"])
        totals[key] = totals.get(key, 0.0) + sign * float(m.get("total_cost") or 0)
    return totals


@router.get("/report", response_model=CaseReport)
async def get_case_report(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("rescue:read")),
):
    """Rescue outcomes for one month: cases resolved, by outcome, and what
    their supplies cost. Same gate as the board. Pure read, not audited."""
    return case_report(supabase, year, month)


def case_report(supabase: Client, year: int, month: int) -> dict:
    """GET /report's figures; also the rescue section of the monthly report
    (app/services/monthly_report.py)."""
    start = datetime(year, month, 1, tzinfo=SRI_LANKA)
    end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=SRI_LANKA)
    resolved = (
        supabase.table("rescue_cases")
        .select("id, outcome")
        .eq("status", CaseStatus.resolved.value)
        .gte("resolved_at", start.isoformat())
        .lt("resolved_at", end.isoformat())
        .execute()
        .data
        or []
    )
    costs = _net_supplies_cost(_case_movements(
        supabase, [c["id"] for c in resolved], "rescue_case_id, transaction_type, total_cost",
    ))

    by_outcome = {o: {"outcome": o.value, "cases": 0, "supplies_cost": 0.0} for o in CaseOutcome}
    for c in resolved:
        # resolved_at is only set together with an outcome (030), so a case
        # in a month always has one; guarded anyway.
        line = by_outcome.get(CaseOutcome(c["outcome"])) if c.get("outcome") else None
        if line:
            line["cases"] += 1
            line["supplies_cost"] += costs.get(str(c["id"]), 0.0)
    total = sum(costs.get(str(c["id"]), 0.0) for c in resolved)

    open_cases = (
        supabase.table("rescue_cases").select("id").neq("status", CaseStatus.resolved.value).execute().data or []
    )
    unrecorded = (
        supabase.table("rescue_cases").select("id")
        .eq("status", CaseStatus.resolved.value).is_("outcome", "null")
        .execute().data or []
    )
    reported = (
        supabase.table("rescue_cases").select("id")
        .gte("reported_at", start.isoformat()).lt("reported_at", end.isoformat())
        .execute().data or []
    )
    return {
        "year": year,
        "month": month,
        "reported": len(reported),
        "resolved": len(resolved),
        "by_outcome": [
            {**line, "supplies_cost": round(line["supplies_cost"], 2)} for line in by_outcome.values()
        ],
        "supplies_cost": round(total, 2),
        "average_cost": round(total / len(resolved), 2) if resolved else None,
        "open_cases": len(open_cases),
        "unrecorded_outcomes": len(unrecorded),
    }


@router.post("/cases/{case_id}/outcome", response_model=CaseOut)
async def record_older_outcome(
    case_id: UuidPath,
    payload: OutcomeRecord,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("rescue:manage")),
):
    """Give an outcome to a case resolved before outcomes were recorded
    (confirmed 2026-11-13), without reopening it.

    Only for a Resolved case with no outcome: a recorded outcome is changed by
    reopening, as before. Its resolve date was never stored, so the case's
    last update stands in for it (for a case nobody touched after resolving,
    that is when it was resolved) and the timeline says it is an estimate.
    """
    case = _get_case(supabase, case_id)
    if case.get("status") != CaseStatus.resolved.value:
        raise HTTPException(400, "Only a resolved case can be given an outcome this way. Resolve it instead.")
    if case.get("outcome"):
        raise HTTPException(409, "This case already has an outcome. Reopen it to change the outcome.")

    estimated = case.get("updated_at") or case.get("reported_at")
    update = {"outcome": payload.outcome.value, "resolved_at": estimated}
    updated = supabase.table("rescue_cases").update(update).eq("id", case_id).execute().data
    if not updated:
        raise HTTPException(status_code=404, detail="Case not found")

    note = (payload.outcome_note or "").strip()
    when = _as_utc(estimated).astimezone(SRI_LANKA).date()
    body = f"Recorded later. Resolve date estimated from the case's last update: {when.day} {when.strftime('%b')} {when.year}."
    if note:
        body = f"{note} ({body})"
    try:
        supabase.table("rescue_case_events").insert({
            "case_id": case_id, "event_type": "outcome", "outcome": payload.outcome.value, "body": body,
            "author_id": str(current_user["id"]), "from_status": None, "to_status": None, "assignee_id": None,
        }).execute()
    except Exception:
        logger.exception("Could not add the outcome line to the timeline of case %s", case_id)

    await log_audit_action(
        supabase,
        user_id=current_user["id"],
        action_type="RESCUE_CASE_OUTCOME_RECORDED",
        table_name="rescue_cases",
        old_payload={"id": case_id, "outcome": None, "resolved_at": case.get("resolved_at")},
        new_payload={"id": case_id, **update},
    )
    await notify_board_changed()
    return updated[0]


@router.post("/cases/{case_id}/notes", response_model=CaseEventOut)
async def add_case_note(
    case_id: UuidPath,
    payload: CaseNoteCreate,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("rescue:manage")),
):
    """A note on the case's timeline, from the staff who work cases.

    Append-only (confirmed 2026-11-13): there is no edit or delete, here or in
    the database, so a mistake is corrected with a follow-up note. Allowed on a
    resolved case too, for follow-ups after release or rehoming.
    """
    body = payload.body.strip()
    if not body:
        raise HTTPException(400, "A note cannot be empty")
    _get_case(supabase, case_id)

    response = supabase.table("rescue_case_events").insert({
        "case_id": case_id,
        "event_type": "note",
        "body": body,
        "author_id": str(current_user["id"]),
    }).execute()
    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to add the note")
    note = response.data[0]

    await log_audit_action(
        supabase,
        user_id=current_user["id"],
        action_type="RESCUE_CASE_NOTE",
        table_name="rescue_case_events",
        old_payload=None,
        new_payload=note,
    )

    author = _people(supabase, [current_user["id"]]).get(str(current_user["id"]))
    return {**note, "author": author}


# --------------------------------------------------------------------------
# Public impact numbers (confirmed 2026-11-13)
# --------------------------------------------------------------------------
#
# Live totals for the homepage and the donate page, for anyone, signed in or
# not. Totals only: no case, place, person or date below the year ever leaves
# this route, and PublicImpact is the whole response, so adding a field is a
# deliberate change the tests see. Died and Not found stay in the staff
# reports; donation totals stay private.
#
# Read with get_public_supabase, which is service_role (RLS does not apply),
# which is why the selects below name only the columns the totals need.
#
# Cached per year for IMPACT_CACHE_SECONDS: a busy homepage should not query
# the database on every visit, and these numbers move slowly.

IMPACT_CACHE_SECONDS = 600
_impact_cache: dict[int, tuple[float, dict]] = {}


class PublicImpact(BaseModel):
    year: int
    reported: int            # cases reported to us this year
    cared_for: int           # of those, taken on by staff (Not found excluded)
    rehomed: int             # resolved this year with this outcome
    released: int
    transferred: int
    supplies_cost: float     # net cost of supplies used on rescue cases this year
    as_of: datetime


def _public_impact(supabase: Client, year: int) -> dict:
    start = datetime(year, 1, 1, tzinfo=SRI_LANKA)
    end = datetime(year + 1, 1, 1, tzinfo=SRI_LANKA)
    reported = (
        supabase.table("rescue_cases").select("status, outcome")
        .gte("reported_at", start.isoformat()).lt("reported_at", end.isoformat())
        .execute().data or []
    )
    resolved = (
        supabase.table("rescue_cases").select("outcome")
        .eq("status", CaseStatus.resolved.value)
        .gte("resolved_at", start.isoformat()).lt("resolved_at", end.isoformat())
        .execute().data or []
    )
    movements = _case_movements_in_year(supabase, year)
    outcomes = [c.get("outcome") for c in resolved]
    return {
        "year": year,
        "reported": len(reported),
        "cared_for": sum(
            1 for c in reported
            if c.get("status") != CaseStatus.reported.value and c.get("outcome") != CaseOutcome.not_found.value
        ),
        "rehomed": outcomes.count(CaseOutcome.rehomed.value),
        "released": outcomes.count(CaseOutcome.released.value),
        "transferred": outcomes.count(CaseOutcome.transferred.value),
        "supplies_cost": round(sum(
            (-1 if m.get("transaction_type") == "Return" else 1) * float(m.get("total_cost") or 0)
            for m in movements
        ), 2),
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


def _case_movements_in_year(supabase: Client, year: int) -> list[dict]:
    """Stock Outs on rescue cases and their reversals, dated this year."""
    try:
        return (
            supabase.table("inventory_transactions").select("transaction_type, total_cost")
            .not_.is_("rescue_case_id", "null")
            .gte("transaction_date", f"{year}-01-01").lte("transaction_date", f"{year}-12-31")
            .execute().data or []
        )
    except APIError as e:
        if "rescue_case_id" in str(getattr(e, "message", "") or e):
            return []  # before migration 031
        raise


@router.get("/impact", response_model=PublicImpact)
async def get_public_impact(supabase: Client = Depends(get_public_supabase)):
    """This year's rescue totals for the public site. No sign-in."""
    year = datetime.now(SRI_LANKA).year
    hit = _impact_cache.get(year)
    if hit and monotonic() - hit[0] < IMPACT_CACHE_SECONDS:
        return hit[1]
    result = _public_impact(supabase, year)
    _impact_cache[year] = (monotonic(), result)
    return result


@router.get("/outbreak-zones", response_model=list[OutbreakZoneOut])
async def get_outbreak_zones(
    supabase: Client = Depends(get_public_supabase),
):
    """Public — active outbreak zones only. No individual case data exposed."""
    response = (
        supabase.table("outbreak_zones")
        .select("*")
        .eq("is_active", True)
        .order("declared_at", desc=True)
        .execute()
    )
    return response.data or []


@router.post("/outbreak-zones", response_model=OutbreakZoneOut)
async def declare_outbreak_zone(
    payload: OutbreakZoneCreate,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("rescue:assign")),
):
    response = supabase.table("outbreak_zones").insert({
        **payload.model_dump(),
        "declared_by": current_user["id"],
    }).execute()

    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to declare outbreak zone")

    # Declaring a zone publishes it to the public map, so it is a public-facing
    # act worth attributing.
    await log_audit_action(
        supabase,
        user_id=current_user["id"],
        action_type="OUTBREAK_ZONE_DECLARE",
        table_name="outbreak_zones",
        old_payload=None,
        new_payload=response.data[0],
    )

    return response.data[0]


@router.patch("/outbreak-zones/{zone_id}/resolve", response_model=OutbreakZoneOut)
async def resolve_outbreak_zone(
    zone_id: UuidPath,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("rescue:assign")),
):
    existing = (
        supabase.table("outbreak_zones")
        .select("*")
        .eq("id", zone_id)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Zone not found")

    response = (
        supabase.table("outbreak_zones")
        .update({"is_active": False, "resolved_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", zone_id)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Zone not found")

    await log_audit_action(
        supabase,
        user_id=current_user["id"],
        action_type="OUTBREAK_ZONE_RESOLVE",
        table_name="outbreak_zones",
        old_payload=existing.data[0],
        new_payload=response.data[0],
    )

    return response.data[0]