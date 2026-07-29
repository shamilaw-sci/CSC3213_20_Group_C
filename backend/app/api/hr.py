from fastapi import APIRouter, HTTPException, Depends
from app.core.supabase import get_supabase
from app.schemas.hr import (EmployeeProfile, EmployeeProfileCreate,AttendanceLog, AttendanceLogCreate, AttendanceLogUpdate,PayrollLedger)
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timezone
from supabase import Client
from app.core.security import require_permission
from fastapi.responses import StreamingResponse
from datetime import date as date_cls
from fastapi import HTTPException
import io
import csv

router = APIRouter()

def get_employee_by_user_id(supabase: Client, user_id: str):
    response = supabase.table("employee_profile").select("*").eq("user_id", user_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="No linked employee profile found for this user.")
    return response.data[0]

@router.get("/employees", response_model=List[EmployeeProfile])
async def get_employees(user = Depends(require_permission('hr:manage')), supabase: Client = Depends(get_supabase)):
    response = supabase.table("employee_profile").select("*").execute()
    return response.data

@router.post("/employees", response_model=EmployeeProfile)
async def create_employee(employee: EmployeeProfileCreate, user = Depends(require_permission('hr:manage')), supabase: Client = Depends(get_supabase)):
    response = supabase.table("employee_profile").insert(employee.model_dump()).execute()
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create employee")
    return response.data[0]

@router.put("/employees/{employee_id}", response_model=EmployeeProfile)
async def update_employee(employee_id: int, employee: EmployeeProfileCreate, user = Depends(require_permission('hr:manage')), supabase: Client = Depends(get_supabase)):
    response = supabase.table("employee_profile").update(employee.model_dump()).eq("id", employee_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Employee not found")
    return response.data[0]

# --- SELF SERVICE ATTENDANCE ---

@router.post("/attendance/clock-in")
async def clock_in(user = Depends(require_permission('hr:attendance:self')), supabase: Client = Depends(get_supabase)):
    emp = get_employee_by_user_id(supabase, user['sub'])
    today = str(date.today())
    
    existing = supabase.table("attendance_log").select("*").eq("employee_id", emp['id']).eq("target_date", today).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="Already clocked in for today.")
    
    record = {
        "employee_id": emp['id'],
        "target_date": today,
        "clock_in": datetime.now(timezone.utc).isoformat(),
        "is_locked": False
    }
    resp = supabase.table("attendance_log").insert(record).execute()
    return resp.data[0]

@router.post("/attendance/clock-out")
async def clock_out(user = Depends(require_permission('hr:attendance:self')), supabase: Client = Depends(get_supabase)):
    emp = get_employee_by_user_id(supabase, user['sub'])
    today = str(date.today())
    
    existing = supabase.table("attendance_log").select("*").eq("employee_id", emp['id']).eq("target_date", today).execute()
    if not existing.data:
        raise HTTPException(status_code=400, detail="No active clock-in record found for today.")
    
    record = existing.data[0]
    if record['is_locked']:
        raise HTTPException(status_code=403, detail="Attendance record is already locked.")
    if record['clock_out']:
        raise HTTPException(status_code=400, detail="Already clocked out.")
        
    clock_out_time = datetime.now(timezone.utc)
    clock_in_time = datetime.fromisoformat(record['clock_in'].replace('Z', '+00:00'))
    diff = clock_out_time - clock_in_time
    worked_hours = round(diff.total_seconds() / 3600.0, 2)
    
    update_data = {
        "clock_out": clock_out_time.isoformat(),
        "worked_hours": worked_hours,
        "is_locked": True
    }
    
    resp = supabase.table("attendance_log").update(update_data).eq("id", record['id']).execute()
    return resp.data[0]

@router.get("/attendance/me")
async def get_my_attendance(month: Optional[int] = None, year: Optional[int] = None, user = Depends(require_permission('hr:attendance:self')), supabase: Client = Depends(get_supabase)):
    emp = get_employee_by_user_id(supabase, user['sub'])
    query = supabase.table("attendance_log").select("*").eq("employee_id", emp['id']).order("target_date", desc=True)
    
    if month and year:
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year+1}-01-01" if month == 12 else f"{year}-{month+1:02d}-01"
        query = query.gte("target_date", start_date).lt("target_date", end_date)
        
    resp = query.execute()
    return resp.data

# --- HR ATTENDANCE MANAGEMENT ---

@router.get("/attendance")
async def get_attendance(target_date: Optional[date] = None, month: Optional[int] = None, year: Optional[int] = None, user = Depends(require_permission('hr:attendance:manage')), supabase: Client = Depends(get_supabase)):
    query = supabase.table("attendance_log").select("*, employee_profile(*)")
    if target_date:
        query = query.eq("target_date", str(target_date))
    if month and year:
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year+1}-01-01" if month == 12 else f"{year}-{month+1:02d}-01"
        query = query.gte("target_date", start_date).lt("target_date", end_date)
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
async def log_attendance(attendance: AttendanceLogCreate, user = Depends(require_permission('hr:attendance:manage')), supabase: Client = Depends(get_supabase)):
    existing = supabase.table("attendance_log").select("*") \
        .eq("employee_id", attendance.employee_id) \
        .eq("target_date", str(attendance.target_date)).execute()
    if existing.data:
        if existing.data[0]['is_locked']:
            raise HTTPException(status_code=403, detail="Record is locked and cannot be modified.")
        raise HTTPException(status_code=400, detail="A log already exists for this employee on this date. Edit it instead.")

    payload = attendance.model_dump(mode="json")
    payload["worked_hours"] = _compute_worked_hours(attendance.clock_in, attendance.clock_out)

    response = supabase.table("attendance_log").insert(payload).execute()
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to log attendance")
    return response.data[0]

@router.get("/attendance/export")
async def export_attendance(
    target_date: str,
    user = Depends(require_permission('hr:attendance:manage')),
    supabase: Client = Depends(get_supabase),
):
    try:
        parsed_date = date_cls.fromisoformat(target_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="target_date must be in YYYY-MM-DD format")

    logs = (
        supabase.table("attendance_log")
        .select("*, employee_profile(first_name, last_name)")
        .eq("target_date", parsed_date.isoformat())
        .execute()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Employee", "Check In", "Check Out", "Worked Hours"])

    for log in logs.data or []:
        profile = log.get("employee_profile") or {}
        full_name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
        writer.writerow([
            full_name,
            log.get("clock_in"),
            log.get("clock_out"),
            log.get("worked_hours"),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=attendance_{parsed_date.isoformat()}.csv"}
    )

@router.put("/attendance/{attendance_id}", response_model=AttendanceLog)
async def update_attendance(attendance_id: int, attendance: AttendanceLogUpdate, user = Depends(require_permission('hr:attendance:manage')), supabase: Client = Depends(get_supabase)):
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


@router.post("/attendance/lock-day")
async def lock_day_attendance(target_date: date, user = Depends(require_permission('hr:attendance:manage')), supabase: Client = Depends(get_supabase)):
    response = supabase.table("attendance_log").update({"is_locked": True}).eq("target_date", str(target_date)).execute()
    return {"message": f"Attendance locked for {target_date}", "updated_count": len(response.data) if response.data else 0}

@router.post("/attendance/lock")
async def lock_attendance(target_date: date, user = Depends(require_permission('hr:attendance:manage')), supabase: Client = Depends(get_supabase)):
    # Kept for backward compatibility with older UI if any
    return await lock_day_attendance(target_date, user, supabase)

# --- PAYROLL PIPELINE ---


@router.get("/payroll", response_model=List[PayrollLedger])
async def get_payroll(month: int, year: int, user = Depends(require_permission('finance:read')), supabase: Client = Depends(get_supabase)):
    response = supabase.table("payroll_ledger").select("*").eq("payroll_month", month).eq("payroll_year", year).execute()
    return response.data

@router.post("/payroll/generate", response_model=List[PayrollLedger])
async def generate_monthly_payroll(
    month: int,
    year: int,
    user = Depends(require_permission('payroll:generate')),
    supabase: Client = Depends(get_supabase)
):
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year+1}-01-01" if month == 12 else f"{year}-{month+1:02d}-01"
    
    unlocked = supabase.table("attendance_log").select("id, employee_id, target_date").gte("target_date", start_date).lt("target_date", end_date).eq("is_locked", False).execute()
    if unlocked.data:
        raise HTTPException(status_code=422, detail=f"Cannot generate payroll: {len(unlocked.data)} attendance records are unlocked/incomplete in this period. Lock them first.")
        
    try:
        result = supabase.rpc(
            "generate_monthly_payroll",
            {"p_month": month, "p_year": year}
        ).execute()

        return result.data

    except HTTPException:
        raise
    except Exception as e:
        msg = str(e)
        if "already been processed" in msg:
            raise HTTPException(status_code=400, detail=msg)
        if "No active employees found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=500, detail=f"Payroll generation failed: {msg}")

