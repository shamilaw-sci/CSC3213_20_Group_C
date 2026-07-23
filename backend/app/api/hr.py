from fastapi import APIRouter, HTTPException, Depends
from app.core.supabase import get_supabase
from app.schemas.hr import (
    EmployeeProfile, EmployeeProfileCreate,
    AttendanceLog, AttendanceLogCreate, AttendanceLogUpdate,
    PayrollLedger
)
from typing import List, Optional
from datetime import date, datetime
from supabase import Client
from app.core.security import check_user_role, get_current_user

router = APIRouter()


@router.get("/employees", response_model=List[EmployeeProfile])
async def get_employees(supabase: Client = Depends(get_supabase)):
    response = supabase.table("employee_profile").select("*").execute()
    return response.data

@router.post("/employees", response_model=EmployeeProfile)
async def create_employee(employee: EmployeeProfileCreate, supabase: Client = Depends(get_supabase)):
    response = supabase.table("employee_profile").insert(employee.model_dump()).execute()
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create employee")
    return response.data[0]

@router.put("/employees/{employee_id}", response_model=EmployeeProfile)
async def update_employee(employee_id: int, employee: EmployeeProfileCreate, supabase: Client = Depends(get_supabase)):
    response = supabase.table("employee_profile").update(employee.model_dump()).eq("id", employee_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Employee not found")
    return response.data[0]

@router.get("/attendance", response_model=List[AttendanceLog])
async def get_attendance(target_date: Optional[date] = None, supabase: Client = Depends(get_supabase)):
    query = supabase.table("attendance_log").select("*")
    if target_date:
        query = query.eq("target_date", str(target_date))
    response = query.execute()
    return response.data


def _compute_worked_hours(clock_in, clock_out):
    if clock_in and clock_out:
        if clock_in.tzinfo is not None:
            clock_in = clock_in.replace(tzinfo=None)
        if clock_out.tzinfo is not None:
            clock_out = clock_out.replace(tzinfo=None)
        delta = (clock_out - clock_in).total_seconds() / 3600
        if delta < 0:
            delta += 24  # overnight shift: check-out landed after midnight
        return round(delta, 2)
    return None


@router.post("/attendance", response_model=AttendanceLog)
async def log_attendance(attendance: AttendanceLogCreate, supabase: Client = Depends(get_supabase)):
    existing = supabase.table("attendance_log").select("id") \
        .eq("employee_id", attendance.employee_id) \
        .eq("target_date", str(attendance.target_date)).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="A log already exists for this employee on this date. Edit it instead.")

    payload = attendance.model_dump(mode="json")
    payload["worked_hours"] = _compute_worked_hours(attendance.clock_in, attendance.clock_out)

    response = supabase.table("attendance_log").insert(payload).execute()
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to log attendance")
    return response.data[0]


@router.put("/attendance/{attendance_id}", response_model=AttendanceLog)
async def update_attendance(attendance_id: int, attendance: AttendanceLogUpdate, supabase: Client = Depends(get_supabase)):
    existing = supabase.table("attendance_log").select("*").eq("id", attendance_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    current = existing.data[0]
    if current["is_locked"]:
        raise HTTPException(status_code=400, detail="This record is locked and cannot be edited")

    clock_in = attendance.clock_in or current.get("clock_in")
    clock_out = attendance.clock_out or current.get("clock_out")
    clock_in = datetime.fromisoformat(clock_in) if isinstance(clock_in, str) else clock_in
    clock_out = datetime.fromisoformat(clock_out) if isinstance(clock_out, str) else clock_out

    payload = attendance.model_dump(mode="json", exclude_unset=True)
    payload["worked_hours"] = _compute_worked_hours(clock_in, clock_out)

    response = supabase.table("attendance_log").update(payload).eq("id", attendance_id).execute()
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to update attendance")
    return response.data[0]


@router.post("/attendance/lock")
async def lock_attendance(
    target_date: date,
    user = Depends(check_user_role(["Admin", "HR Officer", "Director"])),
    supabase: Client = Depends(get_supabase)
):
    response = supabase.table("attendance_log").update({"is_locked": True}).eq("target_date", str(target_date)).execute()
    return {"message": "Attendance locked", "data": response.data}


@router.get("/payroll", response_model=List[PayrollLedger])
async def get_payroll(month: int, year: int, supabase: Client = Depends(get_supabase)):
    response = supabase.table("payroll_ledger").select("*").eq("payroll_month", month).eq("payroll_year", year).execute()
    return response.data

@router.post("/payroll/generate", response_model=List[PayrollLedger])
async def generate_monthly_payroll(
    month: int,
    year: int,
    user = Depends(check_user_role(["Admin", "Finance Officer", "Director"])),
    supabase: Client = Depends(get_supabase)
):
    try:
        result = supabase.rpc(
            "generate_monthly_payroll",
            {"p_month": month, "p_year": year}
        ).execute()

        return result.data

    except HTTPException:
        # Re-raise our own HTTPExceptions untouched, don't let
        # the generic handler below swallow and re-wrap them.
        raise

    except Exception as e:
        msg = str(e)

        if "already been processed" in msg:
            raise HTTPException(status_code=400, detail=msg)

        if "No active employees found" in msg:
            raise HTTPException(status_code=404, detail=msg)

        raise HTTPException(
            status_code=500,
            detail=f"Payroll generation failed: {msg}"
        )