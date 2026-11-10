from datetime import date

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from supabase import Client

from app.core.supabase import get_supabase
from app.core.security import require_permission
from app.core.permissions import has_permission
from app.core.audit import log_audit_action
from app.schemas.inventory import today_in_sri_lanka
from app.schemas.programs import (
    AssignableEmployee, ProgramAssignment, ProgramAssignmentCreate, ProgramDetail,
    ProgramFinancials, ProgramCompleteRequest, ProgramOpenItems, ProgramSummary,
    ProgramUpdate, ProgramVolunteer,
)
from app.services.program_lifecycle import (
    ACTIVE, CANCELLED, COMPLETED, FINISHED, LOCATION_MIGRATION_MESSAGE,
    PROGRAM_FIXES_MIGRATION_MESSAGE, STORED_VALUES, UPCOMING,
    is_cancelled_status_refused, is_missing_location_column, normalize_status,
    transition_error,
)
from app.services.program_volunteers import (
    build_program_volunteers, fetch_program_shifts, shift_belongs_to_program,
)

router = APIRouter()


# ==========================================
# WHO SEES PROGRAM MONEY (P3)
# ==========================================

def _role(user: dict) -> str:
    return (user.get("roles") or {}).get("role_name") or ""


def _can_see_finances(user: dict) -> bool:
    """Revenue and profit come from the finance ledger."""
    return has_permission(_role(user), "finance:read")


def _can_see_costs(user: dict) -> bool:
    """Total cost and cost per animal: finance roles, and the roles that run
    inventory (whose Stock Outs make up most of a program's cost)."""
    return _can_see_finances(user) or has_permission(_role(user), "inventory:read")


def _hide_costs(program: dict, user: dict) -> dict:
    if not _can_see_costs(user):
        program["total_cost"] = None
    return program


# ==========================================
# PROGRAM LIST BY LIFECYCLE STAGE
# ==========================================

def _num(value) -> float:
    return float(value or 0)


# "" rather than "/": see the note on list_volunteers in volunteers.py. Next's
# dev proxy strips the trailing slash, and the resulting 307 drops the token.
@router.get("", response_model=List[ProgramSummary])
async def list_programs(
    status: Optional[str] = Query(None, pattern="^(Upcoming|Active|Completed|Cancelled)$"),
    user=Depends(require_permission("programs:read")),
    supabase: Client = Depends(get_supabase),
):
    """
    Programs for one lifecycle page, each with the figures its card shows.

    A handful of whole-table queries rather than one per program: the pages
    show every program in a stage at once, and N detail calls per page load
    would be slower for no benefit at this scale.
    """
    query = supabase.table("programs").select("*")
    if status:
        # STORED_VALUES, not just `status`: before migration 010 runs, a
        # running program may still be stored as 'In Progress'.
        query = query.in_("status", STORED_VALUES[status])
    programs = query.order("id", desc=False).execute().data or []
    # Re-check in Python so the result is right even when the filter above
    # was not applied (and to normalise the legacy value on the way out).
    for p in programs:
        p["status"] = normalize_status(p.get("status"))
    if status:
        programs = [p for p in programs if p["status"] == status]
    if not programs:
        return []

    ids = [p["id"] for p in programs]

    team = (
        supabase.table("program_assignments").select("program_id")
        .in_("program_id", ids).execute()
    ).data or []
    team_count: dict = {}
    for row in team:
        team_count[row["program_id"]] = team_count.get(row["program_id"], 0) + 1

    # Same revenue rule as /{id}/financials: Income, not Voided. Only read
    # for users who may see it (P3).
    show_finances = _can_see_finances(user)
    show_costs = _can_see_costs(user)
    revenue: dict = {}
    if show_finances:
        txns = (
            supabase.table("financial_transactions")
            .select("program_id, amount, transaction_type, status")
            .in_("program_id", ids).execute()
        ).data or []
        for t in txns:
            if t.get("transaction_type") == "Income" and t.get("status") != "Voided":
                revenue[t["program_id"]] = revenue.get(t["program_id"], 0.0) + _num(t.get("amount"))

    # Volunteer counts use the exact rules of /{id}/volunteers. Only the
    # shifts of these programs, plus older unlinked ones (P8).
    shifts = fetch_program_shifts(supabase, ids)
    accepted = []
    shift_ids = [s["id"] for s in shifts]
    if shift_ids:
        accepted += (
            supabase.table("volunteer_assignments")
            .select("id, volunteer_id, shift_id, program_id, response")
            .in_("shift_id", shift_ids).eq("response", "accepted").execute()
        ).data or []
    accepted += (
        supabase.table("volunteer_assignments")
        .select("id, volunteer_id, shift_id, program_id, response")
        .in_("program_id", ids).eq("response", "accepted").execute()
    ).data or []

    out = []
    for p in programs:
        total_cost = _num(p.get("total_cost"))
        animals = int(p.get("total_animals_treated") or 0)
        rev = revenue.get(p["id"], 0.0)
        out.append({
            **p,
            "total_cost": total_cost if show_costs else None,
            "team_count": team_count.get(p["id"], 0),
            "volunteer_count": len(build_program_volunteers(p, shifts, accepted)),
            "revenue": rev if show_finances else None,
            "profit": (rev - total_cost) if show_finances else None,
            "cost_per_animal": (total_cost / animals) if (animals and show_costs) else None,
        })
    return out


# Before /{program_id}, so "assignable-employees" is not read as an id.
@router.get("/assignable-employees", response_model=List[AssignableEmployee])
async def list_assignable_employees(
    user=Depends(require_permission("programs:manage")),
    supabase: Client = Depends(get_supabase),
):
    """Active employees for the program team picker (P1). Only names, so
    programs:manage is enough: the full employee list (salaries, NICs) stays
    behind hr:manage."""
    rows = (
        supabase.table("employee_profile")
        .select("id, first_name, last_name, status")
        .execute()
    ).data or []
    active = [r for r in rows if str(r.get("status") or "Active").strip().lower() == "active"]
    return sorted(
        ({"id": r["id"], "first_name": r.get("first_name") or "", "last_name": r.get("last_name") or ""}
         for r in active),
        key=lambda r: (r["first_name"].lower(), r["last_name"].lower()),
    )


# ==========================================
# PROGRAM DETAIL (basic info, including fields
# not present in finance.py's list/create endpoints)
# ==========================================

@router.get("/{program_id}", response_model=ProgramDetail)
async def get_program_detail(
    program_id: int,
    user=Depends(require_permission("programs:read")),
    supabase: Client = Depends(get_supabase),
):
    response = (
        supabase.table("programs")
        .select("*")
        .eq("id", program_id)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Program not found")
    return _hide_costs(
        {**response.data[0], "status": normalize_status(response.data[0].get("status"))}, user
    )


# ==========================================
# PROGRAM LIFECYCLE (Upcoming -> Active -> Completed)
# ==========================================

async def _transition(
    supabase: Client, user: dict, program_id: int, target: str, extra: Optional[dict] = None,
) -> dict:
    existing = supabase.table("programs").select("*").eq("id", program_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Program not found")
    before = existing.data[0]

    error = transition_error(before.get("status"), target)
    if error:
        raise HTTPException(status_code=409, detail=error)

    # Sri Lanka's date, not the server's (X3): a UTC server is still on
    # yesterday until 05:30.
    today = today_in_sri_lanka()
    update = {"status": target}
    if target == ACTIVE:
        # The day it actually started. A planned date still in the future is
        # replaced, so a program started early never ends before it began.
        planned = before.get("start_date")
        if not planned or str(planned) > today.isoformat():
            update["start_date"] = today.isoformat()
    elif target == COMPLETED:
        # The day it ended: today unless an earlier day was given (P6).
        end = (extra or {}).pop("end_date", None) or today
        if end > today:
            raise HTTPException(status_code=400, detail="The end date cannot be in the future.")
        started = before.get("start_date")
        if started and end.isoformat() < str(started):
            raise HTTPException(
                status_code=400,
                detail=f"The end date cannot be before the start date ({started}).",
            )
        update["end_date"] = end.isoformat()
        if not started:
            update["start_date"] = end.isoformat()
    # Written in the same update as the status, so a program is never
    # Completed without its final animal count.
    update.update(extra or {})

    # Conditional on the status read above, so two people pressing the button
    # at once cannot both succeed.
    try:
        result = (
            supabase.table("programs").update(update)
            .eq("id", program_id).eq("status", before.get("status"))
            .execute()
        )
    except Exception as e:
        if target == CANCELLED and is_cancelled_status_refused(e):
            raise HTTPException(status_code=503, detail=PROGRAM_FIXES_MIGRATION_MESSAGE)
        raise
    if not result.data:
        raise HTTPException(
            status_code=409,
            detail="This program changed while you were looking at it. Refresh and try again.",
        )
    after = result.data[0]

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type={ACTIVE: "PROGRAM_START", COMPLETED: "PROGRAM_COMPLETE"}.get(target, "PROGRAM_CANCEL"),
        table_name="programs",
        old_payload=before,
        new_payload=after,
    )
    return _hide_costs({**after, "status": normalize_status(after.get("status"))}, user)


def _open_items(supabase: Client, program: dict, after: date) -> dict:
    """What a program still has out: stock issued and not returned, and
    non-cancelled shifts after `after` (P4)."""
    movements = (
        supabase.table("inventory_transactions")
        .select("item_id, quantity, transaction_type, inventory_items(item_name)")
        .eq("program_id", program["id"])
        .execute()
    ).data or []
    held: dict = {}
    for m in movements:
        sign = {"Issue": 1, "Return": -1}.get(m.get("transaction_type"), 0)
        if not sign:
            continue
        entry = held.setdefault(m["item_id"], {
            "item_id": m["item_id"],
            "item_name": (m.get("inventory_items") or {}).get("item_name"),
            "outstanding": 0,
        })
        entry["outstanding"] += sign * int(m.get("quantity") or 0)
    stock_held = sorted(
        (h for h in held.values() if h["outstanding"] > 0),
        key=lambda h: (h["item_name"] or "").lower(),
    )

    shifts = [
        s for s in fetch_program_shifts(supabase, [program["id"]])
        if shift_belongs_to_program(s, program) and str(s.get("shift_date")) > after.isoformat()
    ]
    shifts_after = sorted(
        ({"shift_id": str(s["id"]), "title": s.get("title") or "", "shift_date": s["shift_date"]}
         for s in shifts),
        key=lambda s: str(s["shift_date"]),
    )
    return {"stock_held": stock_held, "shifts_after": shifts_after}


@router.get("/{program_id}/open-items", response_model=ProgramOpenItems)
async def get_open_items(
    program_id: int,
    end_date: Optional[date] = None,
    user=Depends(require_permission("programs:manage")),
    supabase: Client = Depends(get_supabase),
):
    """Shown before completing a program: stock it still holds, and shifts
    after the end date (today if not given)."""
    program = supabase.table("programs").select("*").eq("id", program_id).execute()
    if not program.data:
        raise HTTPException(status_code=404, detail="Program not found")
    return _open_items(supabase, program.data[0], end_date or today_in_sri_lanka())


@router.post("/{program_id}/start", response_model=ProgramDetail)
async def start_program(
    program_id: int,
    user=Depends(require_permission("programs:manage")),
    supabase: Client = Depends(get_supabase),
):
    """Upcoming -> Active. Sets start_date to today unless already in the past."""
    return await _transition(supabase, user, program_id, ACTIVE)


@router.post("/{program_id}/complete", response_model=ProgramDetail)
async def complete_program(
    program_id: int,
    payload: ProgramCompleteRequest,
    user=Depends(require_permission("programs:manage")),
    supabase: Client = Depends(get_supabase),
):
    """Active -> Completed. Sets end_date (today unless given) and records how
    many animals were treated, which the Completed page's cost per animal
    uses. Refused while the program still holds stock or has shifts after the
    end date, unless confirm_open_items is sent (P4)."""
    if not payload.confirm_open_items:
        program = supabase.table("programs").select("*").eq("id", program_id).execute()
        if program.data and normalize_status(program.data[0].get("status")) == ACTIVE:
            items = _open_items(supabase, program.data[0], payload.end_date or today_in_sri_lanka())
            problems = []
            if items["stock_held"]:
                problems.append("it still holds " + ", ".join(
                    f"{h['outstanding']} x {h['item_name'] or 'item #' + str(h['item_id'])}"
                    for h in items["stock_held"]
                ))
            if items["shifts_after"]:
                n = len(items["shifts_after"])
                problems.append(f"it has {n} volunteer shift{'s' if n != 1 else ''} after the end date")
            if problems:
                raise HTTPException(
                    status_code=409,
                    detail="This program " + " and ".join(problems)
                    + ". Return the stock and cancel the shifts first, or confirm to complete anyway.",
                )
    return await _transition(
        supabase, user, program_id, COMPLETED,
        extra={"total_animals_treated": payload.total_animals_treated, "end_date": payload.end_date},
    )


@router.post("/{program_id}/cancel", response_model=ProgramDetail)
async def cancel_program(
    program_id: int,
    user=Depends(require_permission("programs:manage")),
    supabase: Client = Depends(get_supabase),
):
    """Upcoming -> Cancelled, for a program created by mistake or called off
    before it began (P5). Kept, not deleted, so the audit trail stays whole."""
    return await _transition(supabase, user, program_id, CANCELLED)


@router.patch("/{program_id}", response_model=ProgramDetail)
async def update_program(
    program_id: int,
    payload: ProgramUpdate,
    user=Depends(require_permission("programs:manage")),
    supabase: Client = Depends(get_supabase),
):
    """
    Set or change a program's location (any stage, so programs created before
    locations were recorded can be filled in), correct its name or planned
    start date while it is Upcoming (P5), or correct a completed program's
    animal count (Completed only: before that it is not recorded).
    """
    existing = supabase.table("programs").select("*").eq("id", program_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Program not found")
    before = existing.data[0]
    status = normalize_status(before.get("status"))

    update = payload.model_dump(mode="json", exclude_none=True)
    if "total_animals_treated" in update and status != COMPLETED:
        raise HTTPException(
            status_code=409,
            detail="Animals treated is recorded when the program is marked as completed.",
        )
    if ("program_name" in update or "start_date" in update) and status != UPCOMING:
        raise HTTPException(
            status_code=409,
            detail="The name and start date can only be changed while the program is Upcoming.",
        )
    try:
        result = supabase.table("programs").update(update).eq("id", program_id).execute()
    except Exception as e:
        if is_missing_location_column(e):
            raise HTTPException(status_code=503, detail=LOCATION_MIGRATION_MESSAGE)
        raise
    if not result.data:
        raise HTTPException(status_code=404, detail="Program not found")
    after = result.data[0]

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="PROGRAM_UPDATE",
        table_name="programs",
        old_payload=before,
        new_payload=after,
    )
    return _hide_costs({**after, "status": normalize_status(after.get("status"))}, user)


def _ensure_not_completed(supabase: Client, program_id: int) -> None:
    """404 for an unknown program; 409 once it is completed or cancelled,
    because a finished program's team is a historical record, not a roster."""
    program = supabase.table("programs").select("id, status").eq("id", program_id).execute()
    if not program.data:
        raise HTTPException(status_code=404, detail="Program not found")
    status = normalize_status(program.data[0].get("status"))
    if status in FINISHED:
        raise HTTPException(
            status_code=409, detail=f"This program is {status.lower()}; its team can no longer change."
        )


# ==========================================
# PROGRAM FINANCIALS (Revenue vs. total_cost -> Profit)
# ==========================================

@router.get("/{program_id}/financials", response_model=ProgramFinancials)
async def get_program_financials(
    program_id: int,
    # Revenue and profit are finance figures (P3).
    user=Depends(require_permission("finance:read")),
    supabase: Client = Depends(get_supabase),
):
    # Confirm the program exists and grab its trigger-maintained total_cost
    program = (
        supabase.table("programs")
        .select("id, total_cost")
        .eq("id", program_id)
        .execute()
    )
    if not program.data:
        raise HTTPException(status_code=404, detail="Program not found")

    total_cost = float(program.data[0].get("total_cost") or 0)

    # Revenue = sum of Income transactions tied to this program.
    # Excludes Voided transactions on purpose - a voided entry shouldn't
    # count as real income.
    txns = (
        supabase.table("financial_transactions")
        .select("amount, transaction_type, status")
        .eq("program_id", program_id)
        .execute()
    )

    revenue = sum(
        float(t["amount"])
        for t in (txns.data or [])
        if t["transaction_type"] == "Income" and t.get("status") != "Voided"
    )

    return {
        "program_id": program_id,
        "revenue": revenue,
        "total_cost": total_cost,
        "profit": revenue - total_cost,
    }


# ==========================================
# PROGRAM VOLUNTEERS (accepted shifts / assignments)
# ==========================================

@router.get("/{program_id}/volunteers", response_model=List[ProgramVolunteer])
async def get_program_volunteers(
    program_id: int,
    user=Depends(require_permission("programs:read")),
    supabase: Client = Depends(get_supabase),
):
    """
    Volunteers who ACCEPTED a non-cancelled shift for this program, or a
    direct assignment to the program. Which shifts count as this program's,
    and every other rule, is decided in app/services/program_volunteers.py.
    """
    program = (
        supabase.table("programs").select("id, program_name")
        .eq("id", program_id).execute()
    )
    if not program.data:
        raise HTTPException(status_code=404, detail="Program not found")
    program = program.data[0]

    shifts = fetch_program_shifts(supabase, [program_id])

    # Only the volunteer columns the response needs: never the email, phone or
    # access_token.
    columns = "*, volunteers(full_name, skills, skills_other)"
    assignments = (
        supabase.table("volunteer_assignments").select(columns)
        .eq("program_id", program_id).eq("response", "accepted").execute()
    ).data or []

    shift_ids = [s["id"] for s in shifts if shift_belongs_to_program(s, program)]
    if shift_ids:
        assignments += (
            supabase.table("volunteer_assignments").select(columns)
            .in_("shift_id", shift_ids).eq("response", "accepted").execute()
        ).data or []

    return build_program_volunteers(program, shifts, assignments)


# ==========================================
# PROGRAM TEAM / WORKER ASSIGNMENTS
# ==========================================

@router.get("/{program_id}/team", response_model=List[ProgramAssignment])
async def get_program_team(
    program_id: int,
    user=Depends(require_permission("programs:read")),
    supabase: Client = Depends(get_supabase),
):
    # Confirm the program actually exists first, so a bad ID gives a clear 404
    # instead of silently returning an empty team list.
    program = supabase.table("programs").select("id").eq("id", program_id).execute()
    if not program.data:
        raise HTTPException(status_code=404, detail="Program not found")

    response = (
        supabase.table("program_assignments")
        .select("*, employee_profile(id, first_name, last_name)")
        .eq("program_id", program_id)
        .order("assigned_at", desc=False)
        .execute()
    )
    return response.data or []


@router.post("/{program_id}/team", response_model=ProgramAssignment)
async def assign_worker_to_program(
    program_id: int,
    assignment: ProgramAssignmentCreate,
    user=Depends(require_permission("programs:manage")),
    supabase: Client = Depends(get_supabase),
):
    # Validate the program exists and is not completed
    _ensure_not_completed(supabase, program_id)

    # Validate the employee exists
    employee = (
        supabase.table("employee_profile")
        .select("id")
        .eq("id", assignment.employee_id)
        .execute()
    )
    if not employee.data:
        raise HTTPException(status_code=404, detail="Employee not found")

    data = {
        "program_id": program_id,
        "employee_id": assignment.employee_id,
        "role_on_program": assignment.role_on_program,
    }

    try:
        response = supabase.table("program_assignments").insert(data).execute()
    except Exception as e:
        # Most likely cause: the UNIQUE(program_id, employee_id) constraint
        # firing because this worker is already assigned to this program.
        msg = str(e)
        if "duplicate" in msg.lower() or "unique" in msg.lower():
            raise HTTPException(
                status_code=400,
                detail="This employee is already assigned to this program.",
            )
        raise HTTPException(status_code=400, detail=f"Failed to assign worker: {msg}")

    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to assign worker")

    # Re-fetch with the employee join so the response matches GET /team's shape
    created_id = response.data[0]["id"]
    refreshed = (
        supabase.table("program_assignments")
        .select("*, employee_profile(id, first_name, last_name)")
        .eq("id", created_id)
        .single()
        .execute()
    )

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="PROGRAM_TEAM_ASSIGN",
        table_name="program_assignments",
        old_payload=None,
        new_payload=refreshed.data,
    )

    return refreshed.data


@router.delete("/{program_id}/team/{assignment_id}")
async def remove_worker_from_program(
    program_id: int,
    assignment_id: int,
    user=Depends(require_permission("programs:manage")),
    supabase: Client = Depends(get_supabase),
):
    _ensure_not_completed(supabase, program_id)

    existing = (
        supabase.table("program_assignments")
        # Full row, not just the id: after the delete this audit entry is the
        # only remaining record of who was on the program and in what role.
        .select("*")
        .eq("id", assignment_id)
        .eq("program_id", program_id)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Assignment not found")

    supabase.table("program_assignments").delete().eq("id", assignment_id).execute()

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="PROGRAM_TEAM_REMOVE",
        table_name="program_assignments",
        old_payload=existing.data[0],
        new_payload=None,
    )

    return {"message": "Worker removed from program"}