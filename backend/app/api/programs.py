from fastapi import APIRouter, HTTPException, Depends
from typing import List
from supabase import Client

from app.core.supabase import get_supabase
from app.core.security import require_permission
from app.core.audit import log_audit_action
from app.schemas.programs import (
    ProgramAssignment, ProgramAssignmentCreate, ProgramDetail, ProgramFinancials,
    ProgramVolunteer,
)
from app.services.program_volunteers import (
    build_program_volunteers, shift_belongs_to_program,
)

router = APIRouter()


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
    return response.data[0]


# ==========================================
# PROGRAM FINANCIALS (Revenue vs. total_cost -> Profit)
# ==========================================

@router.get("/{program_id}/financials", response_model=ProgramFinancials)
async def get_program_financials(
    program_id: int,
    user=Depends(require_permission("programs:read")),
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

    shifts = (
        supabase.table("volunteer_shifts").select("*")
        .eq("is_cancelled", False).execute()
    ).data or []

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
    # Validate the program exists
    program = supabase.table("programs").select("id").eq("id", program_id).execute()
    if not program.data:
        raise HTTPException(status_code=404, detail="Program not found")

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