from fastapi import APIRouter, HTTPException, Depends
from app.core.supabase import get_supabase
from app.schemas.hr import (EmployeeProfile, EmployeeProfileCreate,AttendanceLog, AttendanceLogCreate, AttendanceLogUpdate,PayrollLedger)
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timezone
from supabase import Client
from app.core.security import require_any_permission, require_permission
from app.core.audit import log_audit_action
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

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="EMPLOYEE_CREATE",
        table_name="employee_profile",
        old_payload=None,
        new_payload=response.data[0],
    )

    return response.data[0]

@router.put("/employees/{employee_id}", response_model=EmployeeProfile)
async def update_employee(employee_id: int, employee: EmployeeProfileCreate, user = Depends(require_permission('hr:manage')), supabase: Client = Depends(get_supabase)):
    # Salary and role live on this row, so the prior values are the point of
    # the audit entry.
    existing = supabase.table("employee_profile").select("*").eq("id", employee_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Employee not found")

    response = supabase.table("employee_profile").update(employee.model_dump()).eq("id", employee_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Employee not found")

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="EMPLOYEE_UPDATE",
        table_name="employee_profile",
        old_payload=existing.data[0],
        new_payload=response.data[0],
    )

    return response.data[0]

# --- SELF SERVICE ATTENDANCE ---

@router.post("/attendance/clock-in")
async def clock_in(user = Depends(require_permission('hr:attendance:self')), supabase: Client = Depends(get_supabase)):
    emp = get_employee_by_user_id(supabase, user['id'])
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

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="ATTENDANCE_CLOCK_IN",
        table_name="attendance_log",
        old_payload=None,
        new_payload=resp.data[0] if resp.data else record,
    )

    return resp.data[0]

@router.post("/attendance/clock-out")
async def clock_out(user = Depends(require_permission('hr:attendance:self')), supabase: Client = Depends(get_supabase)):
    emp = get_employee_by_user_id(supabase, user['id'])
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
    
    # Clocking out does not lock. It used to, which left HR unable to correct
    # a wrong clock-out: update_attendance refuses locked rows and nothing
    # could unlock them. Locking is HR's step, per day, once reviewed.
    update_data = {
        "clock_out": clock_out_time.isoformat(),
        "worked_hours": worked_hours,
    }
    
    resp = supabase.table("attendance_log").update(update_data).eq("id", record['id']).execute()

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="ATTENDANCE_CLOCK_OUT",
        table_name="attendance_log",
        old_payload=record,
        new_payload=resp.data[0] if resp.data else update_data,
    )

    return resp.data[0]

@router.get("/attendance/me")
async def get_my_attendance(month: Optional[int] = None, year: Optional[int] = None, user = Depends(require_permission('hr:attendance:self')), supabase: Client = Depends(get_supabase)):
    emp = get_employee_by_user_id(supabase, user['id'])
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

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="ATTENDANCE_CREATE",
        table_name="attendance_log",
        old_payload=None,
        new_payload=response.data[0],
    )

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

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="ATTENDANCE_UPDATE",
        table_name="attendance_log",
        old_payload=current,
        new_payload=response.data[0],
    )

    return response.data[0]


@router.post("/attendance/lock-day")
async def lock_day_attendance(target_date: date, user = Depends(require_permission('hr:attendance:manage')), supabase: Client = Depends(get_supabase)):
    # Only complete records are locked. Locking a record with no clock-out
    # froze it with blank hours, and with nothing able to unlock it the
    # mistake was permanent. Incomplete ones are reported back instead.
    day = supabase.table("attendance_log").select("id, clock_in, clock_out, is_locked") \
        .eq("target_date", str(target_date)).execute().data or []
    lockable = [r["id"] for r in day if r.get("clock_in") and r.get("clock_out") and not r.get("is_locked")]
    incomplete = [r["id"] for r in day if not (r.get("clock_in") and r.get("clock_out"))]

    updated_count = 0
    if lockable:
        response = supabase.table("attendance_log").update({"is_locked": True}).in_("id", lockable).execute()
        updated_count = len(response.data) if response.data else 0

    # Locking a day is what makes those hours eligible for payroll, so it is a
    # financially meaningful action even though it edits no money directly.
    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="ATTENDANCE_LOCK_DAY",
        table_name="attendance_log",
        old_payload=None,
        new_payload={
            "target_date": str(target_date),
            "updated_count": updated_count,
            "skipped_incomplete": len(incomplete),
        },
    )

    return {
        "message": f"Attendance locked for {target_date}",
        "updated_count": updated_count,
        "skipped_incomplete": len(incomplete),
    }

@router.post("/attendance/lock")
async def lock_attendance(target_date: date, user = Depends(require_permission('hr:attendance:manage')), supabase: Client = Depends(get_supabase)):
    # Kept for backward compatibility with older UI if any
    return await lock_day_attendance(target_date, user, supabase)

@router.post("/attendance/{attendance_id}/unlock", response_model=AttendanceLog)
async def unlock_attendance(attendance_id: int, user = Depends(require_permission('hr:attendance:manage')), supabase: Client = Depends(get_supabase)):
    """
    Reopen a locked record for correction.

    Refused once that month's payroll is approved: approved pay was worked
    out from the month as it stood, so its attendance is history from then.
    """
    existing = supabase.table("attendance_log").select("*").eq("id", attendance_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    record = existing.data[0]
    if not record.get("is_locked"):
        raise HTTPException(status_code=400, detail="This record is not locked.")

    record_date = date_cls.fromisoformat(str(record["target_date"])[:10])
    if _approved_run(supabase, record_date.month, record_date.year):
        raise HTTPException(
            status_code=409,
            detail=f"Payroll for {record_date.month}/{record_date.year} is approved; its attendance can no longer be changed.",
        )

    response = supabase.table("attendance_log").update({"is_locked": False}).eq("id", attendance_id).execute()
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to unlock attendance")

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="ATTENDANCE_UNLOCK",
        table_name="attendance_log",
        old_payload=record,
        new_payload=response.data[0],
    )

    return response.data[0]


# --- PAYROLL PIPELINE ---
#
# A month's payroll is a payroll_runs row: Draft when generated, Approved when
# a second person signs it off, and only then posted to the finance ledger.
# The transactional work lives in two SQL functions; see
# db/migrations/007_payroll_runs.sql for why.

# Sentences the SQL functions RAISE, mapped to HTTP statuses. PostgREST wraps
# the message in JSON, so the endpoint matches on these and returns the
# sentence alone rather than the wrapper.
_RPC_ERRORS = (
    ("is already approved", 409),
    ("must be approved by someone other than", 403),
    ("not found", 404),
    ("No active employees found", 404),
    ("has nothing to pay", 400),
)


def _month_bounds(month: int, year: int) -> tuple[str, str]:
    start = f"{year}-{month:02d}-01"
    end = f"{year+1}-01-01" if month == 12 else f"{year}-{month+1:02d}-01"
    return start, end


def _approved_run(supabase: Client, month: int, year: int) -> bool:
    runs = supabase.table("payroll_runs").select("id, status") \
        .eq("payroll_month", month).eq("payroll_year", year).execute().data or []
    return any(r.get("status") == "Approved" for r in runs)


def _validate_month(month: int, year: int) -> None:
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        raise HTTPException(status_code=400, detail="Choose a valid month and year.")


def _audit_run(run: dict) -> dict:
    # total as a decimal string: a whole-number float like 155000.0 comes
    # back from JSONB as 155000 and would make the audit hash unverifiable
    # (see the note in create_transaction in app/api/finance.py).
    return {**run, "total": f"{float(run.get('total') or 0):.2f}"}


def _rpc_error(e: Exception) -> HTTPException:
    """Turn a SQL function's RAISE EXCEPTION into an HTTP error."""
    # postgrest's APIError carries the raised text in .message; fall back to
    # str() for anything else.
    msg = getattr(e, "message", None) or str(e)
    for needle, status in _RPC_ERRORS:
        if needle in msg:
            return HTTPException(status_code=status, detail=msg)
    return HTTPException(status_code=500, detail=f"Payroll operation failed: {msg}")


def _single(data):
    """An RPC returning one composite row may come back as a dict or a list."""
    if isinstance(data, list):
        return data[0] if data else None
    return data


@router.get("/payroll", response_model=List[PayrollLedger])
async def get_payroll(month: int, year: int, user = Depends(require_permission('finance:read')), supabase: Client = Depends(get_supabase)):
    response = supabase.table("payroll_ledger").select("*").eq("payroll_month", month).eq("payroll_year", year).execute()
    return response.data


@router.get("/payroll/run")
async def get_payroll_run(
    month: int,
    year: int,
    user = Depends(require_any_permission('payroll:generate', 'payroll:approve')),
    supabase: Client = Depends(get_supabase),
):
    """
    The month's run, its lines with employee names, and how many attendance
    records in the month are still incomplete (a warning, not a gate: pay is a
    fixed monthly salary).
    """
    _validate_month(month, year)

    runs = supabase.table("payroll_runs") \
        .select(
            "*, generator:users!payroll_runs_generated_by_fkey(email), "
            "approver:users!payroll_runs_approved_by_fkey(email)"
        ) \
        .eq("payroll_month", month).eq("payroll_year", year).execute().data or []
    run = runs[0] if runs else None

    lines = []
    if run:
        rows = supabase.table("payroll_ledger") \
            .select("*, employee_profile(first_name, last_name, nic)") \
            .eq("run_id", run["id"]).execute().data or []
        for r in rows:
            profile = r.get("employee_profile") or {}
            name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
            lines.append({
                "id": r.get("id"),
                "employee_id": r.get("employee_id"),
                "employee_name": name or f"Employee {r.get('employee_id')}",
                "nic": profile.get("nic"),
                "net_payable": float(r.get("net_payable") or 0),
            })
        lines.sort(key=lambda line: line["employee_name"].lower())

    start, end = _month_bounds(month, year)
    logs = supabase.table("attendance_log").select("id, clock_in, clock_out") \
        .gte("target_date", start).lt("target_date", end).execute().data or []
    incomplete = sum(1 for log in logs if not (log.get("clock_in") and log.get("clock_out")))

    return {"run": run, "lines": lines, "incomplete_attendance": incomplete}


@router.post("/payroll/generate")
async def generate_monthly_payroll(
    month: int,
    year: int,
    user = Depends(require_permission('payroll:generate')),
    supabase: Client = Depends(get_supabase)
):
    """
    Create or refresh the month's Draft. Nothing reaches the finance ledger
    until approve_payroll.

    Attendance no longer blocks this. Pay is a fixed monthly salary, so an
    unlocked or incomplete record does not change it; it used to stop the
    whole organisation's payroll over one forgotten clock-out.
    """
    _validate_month(month, year)
    try:
        result = supabase.rpc(
            "generate_payroll_draft",
            {"p_month": month, "p_year": year, "p_user": str(user["id"])},
        ).execute()
    except Exception as e:
        raise _rpc_error(e)

    run = _single(result.data)
    if not run:
        raise HTTPException(status_code=500, detail="Payroll generation returned no run.")

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="PAYROLL_DRAFT_GENERATE",
        table_name="payroll_runs",
        old_payload=None,
        new_payload=_audit_run(run),
    )
    return run


@router.post("/payroll/runs/{run_id}/approve")
async def approve_payroll(
    run_id: int,
    user = Depends(require_permission('payroll:approve')),
    supabase: Client = Depends(get_supabase),
):
    """
    Approve a Draft: freezes it and posts its total to the ledger as a payable
    dated the last day of the month. The SQL function refuses an approval by
    whoever generated the run.
    """
    try:
        result = supabase.rpc(
            "approve_payroll_run",
            {"p_run_id": run_id, "p_user": str(user["id"])},
        ).execute()
    except Exception as e:
        raise _rpc_error(e)

    run = _single(result.data)
    if not run:
        raise HTTPException(status_code=500, detail="Payroll approval returned no run.")

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="PAYROLL_APPROVE",
        table_name="payroll_runs",
        old_payload=None,
        new_payload=_audit_run(run),
    )
    return run
