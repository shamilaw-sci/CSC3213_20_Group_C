# backend/app/api/volunteers.py
#
# Volunteer management. Three public unauthenticated routes and a permission-
# gated staff surface, following the split established in rescue_cases.py.
#
# THE PUBLIC ROUTES USE get_public_supabase, ALWAYS. That helper ignores the
# Authorization header entirely and returns the shared service_role client, so
# a stale or expired staff token sitting in a visitor's browser can never break
# a route that was never meant to require login. api-client.ts attaches any
# token it finds in localStorage to every request, so this is not hypothetical.
#
# It also means these routes bypass RLS. That is the design: there is no anon
# policy on any volunteer table (see db/migrations/004_volunteers.sql), so
# someone holding the public anon key gets nothing from PostgREST even with a
# valid volunteer token. Scoping to one volunteer is an application-layer
# invariant enforced here, by filtering on access_token.

import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from supabase import Client

from app.core.audit import log_audit_action
from app.core.security import require_permission, require_any_permission
from app.core.supabase import get_public_supabase, get_supabase
from app.schemas.volunteer import (
    AssignmentCreate, AssignmentOut, AssignmentRespond, AssignmentResponse,
    MyAssignment, MyAssignmentsOut, ShiftConfirmation, ShiftCreate, ShiftOut,
    ShiftUpdate, ShiftWithConfirmation, VolunteerApply, VolunteerApplyAccepted,
    VolunteerOut, VolunteerReview, VolunteerStatus,
)
from app.services import email as email_service

logger = logging.getLogger(__name__)

router = APIRouter()

# 32 bytes -> 43 url-safe characters, 256 bits of entropy. Enumeration is not a
# practical concern at that width, which is what lets possession of the link
# stand in for authentication.
_TOKEN_BYTES = 32

# Approving is a one-way door out of 'pending'; see VolunteerReview.
_REVIEW_ACTION = {
    VolunteerStatus.approved: "VOLUNTEER_APPROVE",
    VolunteerStatus.rejected: "VOLUNTEER_REJECT",
    VolunteerStatus.inactive: "VOLUNTEER_DEACTIVATE",
}


def _audit_safe(row: dict) -> dict:
    """
    A volunteer row with the access token stripped, for audit payloads.

    The audit log is readable by every role holding audit:read, which is a
    wider set than the roles allowed to see a volunteer's personal link. Writing
    the token into old_payload/new_payload would route it around its own
    permission gate and make it permanent.
    """
    return {k: v for k, v in row.items() if k != "access_token"}


def _format_when(shift: dict) -> Optional[str]:
    """Human-readable wall-clock time for an email. Wall clock is what the
    column stores and what the volunteer will experience; see the migration."""
    if not shift.get("shift_date"):
        return None
    when = str(shift["shift_date"])
    if shift.get("start_time"):
        when += f", {str(shift['start_time'])[:5]}"
        if shift.get("end_time"):
            when += f"–{str(shift['end_time'])[:5]}"
    return when


# ===========================================================================
# Public — application
# ===========================================================================

@router.post("/apply", response_model=VolunteerApplyAccepted)
async def apply(
    payload: VolunteerApply,
    supabase: Client = Depends(get_public_supabase),
):
    """
    Public volunteer application. Lands as 'pending'; not active until reviewed.

    Returns the same body whether the insert succeeded or the partial unique
    index rejected a duplicate live application, so the form cannot be used to
    probe whether an address is already an approved volunteer.
    """
    row = {
        **payload.model_dump(mode="json", exclude_none=True),
        "access_token": secrets.token_urlsafe(_TOKEN_BYTES),
        # Not taken from the caller. VolunteerApply has no status field, but
        # being explicit here means a future edit to that schema cannot
        # accidentally let an applicant approve themselves.
        "status": VolunteerStatus.pending.value,
    }

    try:
        response = supabase.table("volunteers").insert(row).execute()
    except Exception as e:
        # 23505 is the partial unique index on lower(email): this person already
        # has a pending or approved record. That is a no-op, not an error worth
        # showing them — and distinguishing it in the response would leak
        # exactly what the generic message exists to hide.
        if "23505" in str(e) or "duplicate key" in str(e).lower():
            logger.info("Duplicate volunteer application ignored for %s", payload.email)
            return VolunteerApplyAccepted()
        logger.error("Volunteer application failed: %s", e)
        raise HTTPException(status_code=500, detail="Could not submit your application")

    if not response.data:
        raise HTTPException(status_code=500, detail="Could not submit your application")

    # Applications come from anonymous members of the public, so a null user_id
    # is the accurate record rather than a missing attribution — the same
    # reasoning as public rescue case reports.
    await log_audit_action(
        supabase,
        user_id=None,
        action_type="VOLUNTEER_APPLY",
        table_name="volunteers",
        old_payload=None,
        new_payload=_audit_safe(response.data[0]),
    )

    return VolunteerApplyAccepted()


# ===========================================================================
# Public — tokenized self-service
# ===========================================================================

def _load_volunteer_by_token(supabase: Client, token: str) -> dict:
    """
    Resolve an approved volunteer from a link token, or 404.

    Every rejection path returns the identical 404 — unknown token, pending
    applicant, rejected applicant, deactivated volunteer. Distinguishing them
    would turn this route into an oracle for the status of any token someone
    happens to hold.
    """
    try:
        result = (
            supabase.table("volunteers")
            .select("*")
            .eq("access_token", token)
            .eq("status", VolunteerStatus.approved.value)
            .execute()
        )
    except Exception as e:
        # Note the absence of the token from this message, deliberately.
        logger.error("Volunteer token lookup failed: %s", e)
        raise HTTPException(status_code=404, detail="This link is not valid")

    if not result.data:
        raise HTTPException(status_code=404, detail="This link is not valid")
    return result.data[0]


@router.get("/my-assignments/{token}", response_model=MyAssignmentsOut)
async def my_assignments(
    token: str,
    response: Response,
    supabase: Client = Depends(get_public_supabase),
):
    """
    A volunteer's own assignments. No login; the link is the authorization.

    Scoped by volunteer_id resolved from the token, so it cannot return another
    volunteer's rows regardless of what is asked for.
    """
    # A token in a URL leaks through the Referer header to every external host
    # the page or its subresources touch. The frontend sets this too, but a
    # visitor may hit this endpoint directly, and the header costs nothing.
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store, private"
    # Keep it out of search results if the link is ever pasted somewhere public.
    response.headers["X-Robots-Tag"] = "noindex, nofollow"

    volunteer = _load_volunteer_by_token(supabase, token)

    rows = (
        supabase.table("volunteer_assignments")
        .select(
            "*, volunteer_shifts(title, description, location, shift_date, "
            "start_time, end_time, is_cancelled), programs(program_name), "
            "rescue_cases(animal_type, description)"
        )
        .eq("volunteer_id", volunteer["id"])
        .order("assigned_at", desc=True)
        .execute()
    ).data or []

    assignments: list[MyAssignment] = []
    for row in rows:
        shift = row.get("volunteer_shifts") or {}
        program = row.get("programs") or {}
        case = row.get("rescue_cases") or {}

        if row.get("shift_id"):
            item = MyAssignment(
                id=row["id"], assignment_type="shift",
                title=shift.get("title") or "Shift",
                description=shift.get("description"),
                location=shift.get("location"),
                shift_date=shift.get("shift_date"),
                start_time=shift.get("start_time"),
                end_time=shift.get("end_time"),
                is_cancelled=bool(shift.get("is_cancelled")),
                response=row["response"], decline_reason=row.get("decline_reason"),
                responded_at=row.get("responded_at"), assigned_at=row["assigned_at"],
            )
        elif row.get("rescue_case_id"):
            # Only the animal type and description cross the boundary. The
            # rescue_cases row also carries coordinates and reporter details,
            # which a volunteer assigned to help has no need for — MyAssignment
            # naming its fields explicitly is what keeps that true when someone
            # later adds a column to rescue_cases.
            item = MyAssignment(
                id=row["id"], assignment_type="rescue_case",
                title=f"Rescue case: {case.get('animal_type') or 'animal'}",
                description=case.get("description"),
                response=row["response"], decline_reason=row.get("decline_reason"),
                responded_at=row.get("responded_at"), assigned_at=row["assigned_at"],
            )
        else:
            item = MyAssignment(
                id=row["id"], assignment_type="program",
                title=program.get("program_name") or "Programme",
                response=row["response"], decline_reason=row.get("decline_reason"),
                responded_at=row.get("responded_at"), assigned_at=row["assigned_at"],
            )
        assignments.append(item)

    # Dated things first and soonest-first; undated ones after, newest first.
    assignments.sort(
        key=lambda a: (a.shift_date is None, a.shift_date or a.assigned_at.date())
    )

    first_name = volunteer["full_name"].split()[0] if volunteer["full_name"].split() \
        else volunteer["full_name"]
    return MyAssignmentsOut(volunteer_name=first_name, assignments=assignments)


@router.post("/my-assignments/{token}/{assignment_id}/respond",
             response_model=MyAssignment)
async def respond_to_assignment(
    token: str,
    assignment_id: str,
    payload: AssignmentRespond,
    response: Response,
    supabase: Client = Depends(get_public_supabase),
):
    """
    Accept or decline. Volunteers may change their answer later; the row holds
    the latest state and the audit log preserves the history.
    """
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store, private"

    volunteer = _load_volunteer_by_token(supabase, token)

    # Scoped by BOTH id and volunteer_id. Without the second filter, a volunteer
    # holding a valid token could respond on behalf of anyone else by guessing
    # an assignment id.
    existing = (
        supabase.table("volunteer_assignments")
        .select("*")
        .eq("id", assignment_id)
        .eq("volunteer_id", volunteer["id"])
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Assignment not found")

    before = existing.data[0]
    update = {
        "response": payload.response.value,
        "responded_at": datetime.now(timezone.utc).isoformat(),
        # Clearing this on the way out of 'declined' is required by the
        # reason_only_on_decline CHECK, not merely tidy.
        "decline_reason": payload.decline_reason
        if payload.response == AssignmentResponse.declined else None,
    }

    updated = (
        supabase.table("volunteer_assignments")
        .update(update)
        .eq("id", assignment_id)
        .eq("volunteer_id", volunteer["id"])
        .execute()
    )
    if not updated.data:
        raise HTTPException(status_code=404, detail="Assignment not found")

    # user_id is null: there is no authenticated user, and inventing one would
    # misattribute the act. The volunteer is identified by the row's
    # volunteer_id in the payload instead.
    await log_audit_action(
        supabase,
        user_id=None,
        action_type="VOLUNTEER_RESPOND",
        table_name="volunteer_assignments",
        old_payload=before,
        new_payload=updated.data[0],
    )

    # Re-read through the same shaping the GET uses, so the UI gets a row it can
    # drop straight into its list rather than a second, subtly different shape.
    fresh = await my_assignments(token, Response(), supabase)
    for item in fresh.assignments:
        if str(item.id) == str(assignment_id):
            return item
    raise HTTPException(status_code=404, detail="Assignment not found")


# ===========================================================================
# Staff — roster
# ===========================================================================

@router.get("/", response_model=list[VolunteerOut])
async def list_volunteers(
    status: Optional[VolunteerStatus] = Query(None),
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("volunteers:read")),
):
    query = supabase.table("volunteers").select("*")
    if status:
        query = query.eq("status", status.value)
    # Pending first so applications awaiting review surface without filtering.
    result = query.order("applied_at", desc=True).execute()
    return result.data or []


@router.patch("/{volunteer_id}/review", response_model=VolunteerOut)
async def review_volunteer(
    volunteer_id: str,
    payload: VolunteerReview,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("volunteers:approve")),
):
    """Approve, reject or deactivate. Approval sends the welcome email."""
    existing = (
        supabase.table("volunteers").select("*").eq("id", volunteer_id).execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Volunteer not found")
    before = existing.data[0]

    update = {
        "status": payload.status.value,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_by": str(current_user["id"]),
    }
    if payload.staff_notes is not None:
        update["staff_notes"] = payload.staff_notes

    result = (
        supabase.table("volunteers").update(update).eq("id", volunteer_id).execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Volunteer not found")
    after = result.data[0]

    await log_audit_action(
        supabase,
        user_id=current_user["id"],
        action_type=_REVIEW_ACTION[payload.status],
        table_name="volunteers",
        old_payload=_audit_safe(before),
        new_payload=_audit_safe(after),
    )

    # Fail-soft: the approval above is the act, and it has already happened.
    # A Brevo outage must not turn an approved volunteer into a 500.
    if payload.status == VolunteerStatus.approved:
        await email_service.send_volunteer_approved(
            after["email"], after["full_name"], after["access_token"]
        )

    return after


@router.post("/{volunteer_id}/link-shared", response_model=VolunteerOut)
async def mark_link_shared(
    volunteer_id: str,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(
        require_any_permission("volunteers:approve", "volunteers:assign")
    ),
):
    """
    Record that a coordinator copied this volunteer's link to send manually.

    Gated on approve OR assign: sharing a link is contact, not a vetting or a
    scheduling decision, and gating on either alone strands one of the two roles
    — an HR Officer who just approved someone, or an Operations Lead who just
    rostered them. See require_any_permission.

    The roster surfaces this as "Link shared 3 days ago" / "Never shared" so
    coordinators can see who has actually been contacted, which matters more
    here than it would elsewhere: Brevo's free-tier deliverability means the
    email may well never have arrived.
    """
    existing = (
        supabase.table("volunteers").select("*").eq("id", volunteer_id).execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Volunteer not found")

    result = (
        supabase.table("volunteers")
        .update({"link_shared_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", volunteer_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Volunteer not found")

    await log_audit_action(
        supabase,
        user_id=current_user["id"],
        action_type="VOLUNTEER_LINK_SHARE",
        table_name="volunteers",
        old_payload={"id": volunteer_id,
                     "link_shared_at": existing.data[0].get("link_shared_at")},
        new_payload={"id": volunteer_id,
                     "link_shared_at": result.data[0].get("link_shared_at")},
    )

    return result.data[0]


# ===========================================================================
# Staff — shifts
# ===========================================================================

@router.get("/shifts", response_model=list[ShiftWithConfirmation])
async def list_shifts(
    include_past: bool = Query(False),
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("volunteers:read")),
):
    """
    Shifts with their confirmation breakdown.

    The counts are computed here rather than left to the UI because "6 assigned:
    4 accepted, 1 declined, 1 awaiting" is the number the whole feature exists
    to surface, and a client that counts rows itself will eventually disagree
    with one that does not.
    """
    query = supabase.table("volunteer_shifts").select("*")
    if not include_past:
        query = query.gte("shift_date", datetime.now(timezone.utc).date().isoformat())
    shifts = query.order("shift_date", desc=False).execute().data or []

    if not shifts:
        return []

    # One query for every shift's assignments rather than one per shift.
    assignments = (
        supabase.table("volunteer_assignments")
        .select("shift_id, response")
        .in_("shift_id", [s["id"] for s in shifts])
        .execute()
    ).data or []

    by_shift: dict[str, list[str]] = {}
    for a in assignments:
        by_shift.setdefault(a["shift_id"], []).append(a["response"])

    out = []
    for shift in shifts:
        responses = by_shift.get(shift["id"], [])
        out.append(ShiftWithConfirmation(
            **shift,
            confirmation=ShiftConfirmation(
                assigned=len(responses),
                accepted=responses.count(AssignmentResponse.accepted.value),
                declined=responses.count(AssignmentResponse.declined.value),
                awaiting=responses.count(AssignmentResponse.pending.value),
                needed=shift["volunteers_needed"],
            ),
        ))
    return out


@router.post("/shifts", response_model=ShiftOut)
async def create_shift(
    payload: ShiftCreate,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("volunteers:assign")),
):
    result = supabase.table("volunteer_shifts").insert({
        **payload.model_dump(mode="json"),
        "created_by": str(current_user["id"]),
    }).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Could not create shift")

    await log_audit_action(
        supabase,
        user_id=current_user["id"],
        action_type="VOLUNTEER_SHIFT_CREATE",
        table_name="volunteer_shifts",
        old_payload=None,
        new_payload=result.data[0],
    )
    return result.data[0]


@router.patch("/shifts/{shift_id}", response_model=ShiftOut)
async def update_shift(
    shift_id: str,
    payload: ShiftUpdate,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("volunteers:assign")),
):
    existing = (
        supabase.table("volunteer_shifts").select("*").eq("id", shift_id).execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Shift not found")
    before = existing.data[0]

    update = payload.model_dump(mode="json", exclude_none=True)
    if not update:
        return before

    # The merged start/end must still satisfy the ends_after_start CHECK when
    # only one of the pair is being changed.
    start = update.get("start_time", before["start_time"])
    end = update.get("end_time", before["end_time"])
    if str(end) <= str(start):
        raise HTTPException(400, "A shift must end after it starts")

    result = (
        supabase.table("volunteer_shifts").update(update).eq("id", shift_id).execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Shift not found")

    # Cancelling is a different act from editing — volunteers who already
    # accepted need to be told — so the audit trail keeps them distinct rather
    # than flattening both into one action type.
    cancelled = (not before.get("is_cancelled")) and result.data[0].get("is_cancelled")
    await log_audit_action(
        supabase,
        user_id=current_user["id"],
        action_type="VOLUNTEER_SHIFT_CANCEL" if cancelled else "VOLUNTEER_SHIFT_UPDATE",
        table_name="volunteer_shifts",
        old_payload=before,
        new_payload=result.data[0],
    )
    return result.data[0]


# ===========================================================================
# Staff — assignments
# ===========================================================================

@router.get("/assignments", response_model=list[AssignmentOut])
async def list_assignments(
    shift_id: Optional[str] = Query(None),
    volunteer_id: Optional[str] = Query(None),
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("volunteers:read")),
):
    query = supabase.table("volunteer_assignments").select("*")
    if shift_id:
        query = query.eq("shift_id", shift_id)
    if volunteer_id:
        query = query.eq("volunteer_id", volunteer_id)
    return query.order("assigned_at", desc=True).execute().data or []


@router.post("/assignments", response_model=AssignmentOut)
async def create_assignment(
    payload: AssignmentCreate,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("volunteers:assign")),
):
    """Assign a volunteer to a shift, rescue case or programme, and tell them."""
    volunteer = (
        supabase.table("volunteers").select("*")
        .eq("id", str(payload.volunteer_id)).execute()
    )
    if not volunteer.data:
        raise HTTPException(status_code=404, detail="Volunteer not found")
    volunteer = volunteer.data[0]

    # An unapproved volunteer has an inert token, so assigning one would create
    # work nobody can see or respond to.
    if volunteer["status"] != VolunteerStatus.approved.value:
        raise HTTPException(400, "Only approved volunteers can be assigned")

    row = payload.model_dump(mode="json", exclude_none=True)
    row["assigned_by"] = str(current_user["id"])

    try:
        result = supabase.table("volunteer_assignments").insert(row).execute()
    except Exception as e:
        if "23505" in str(e) or "duplicate key" in str(e).lower():
            raise HTTPException(409, "This volunteer is already assigned to that")
        logger.error("Assignment failed: %s", e)
        raise HTTPException(status_code=500, detail="Could not create assignment")

    if not result.data:
        raise HTTPException(status_code=500, detail="Could not create assignment")
    created = result.data[0]

    # The payload is the assignment row alone. It must never embed the joined
    # rescue_cases row: that carries lat/lng floats, and JSONB coerces a whole
    # float to an int, which permanently breaks hash verification for this row
    # and every row after it. See the warning in app/core/audit.py.
    await log_audit_action(
        supabase,
        user_id=current_user["id"],
        action_type="VOLUNTEER_ASSIGN",
        table_name="volunteer_assignments",
        old_payload=None,
        new_payload=created,
    )

    # Fail-soft, and after the audit entry: the assignment exists regardless of
    # whether the notification does.
    title, when, location = "a new assignment", None, None
    if created.get("shift_id"):
        shift = (
            supabase.table("volunteer_shifts").select("*")
            .eq("id", created["shift_id"]).execute()
        ).data
        if shift:
            title = shift[0]["title"]
            when = _format_when(shift[0])
            location = shift[0].get("location")
    elif created.get("program_id"):
        program = (
            supabase.table("programs").select("program_name")
            .eq("id", created["program_id"]).execute()
        ).data
        if program:
            title = program[0]["program_name"]
    else:
        case = (
            supabase.table("rescue_cases").select("animal_type")
            .eq("id", created["rescue_case_id"]).execute()
        ).data
        if case:
            title = f"Rescue case: {case[0]['animal_type']}"

    await email_service.send_assignment_notice(
        volunteer["email"], volunteer["full_name"], volunteer["access_token"],
        title, when, location,
    )

    return created


@router.delete("/assignments/{assignment_id}")
async def delete_assignment(
    assignment_id: str,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("volunteers:assign")),
):
    existing = (
        supabase.table("volunteer_assignments").select("*")
        .eq("id", assignment_id).execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Assignment not found")

    supabase.table("volunteer_assignments").delete().eq("id", assignment_id).execute()

    await log_audit_action(
        supabase,
        user_id=current_user["id"],
        action_type="VOLUNTEER_UNASSIGN",
        table_name="volunteer_assignments",
        old_payload=existing.data[0],
        new_payload=None,
    )
    return {"status": "removed"}
