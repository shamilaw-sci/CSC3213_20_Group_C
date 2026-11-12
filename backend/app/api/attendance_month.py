"""
The monthly attendance grid (attendance rework, step 3).

Mounted under /api/hr. Loads one month of clock-ins, schedules, holidays and
leave, and hands them to build_month() in app/services/attendance_month.py,
where the status rules live. Read-only: edits go through the existing
attendance endpoints in app/api/hr.py.

  GET /attendance/month      hr:attendance:manage (HR) or hr:attendance:read (Director)
  GET /attendance/me/month   hr:attendance:self, one's own row only
"""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from app.core.security import require_any_permission, require_permission
from app.core.supabase import get_supabase
from app.services.attendance_month import build_month, month_days
from app.services.payroll_status import payroll_approved, payroll_frozen_through
from app.services.work_calendar import COLOMBO

router = APIRouter()


def _bounds(year: int, month: int) -> tuple[date, date]:
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        raise HTTPException(status_code=400, detail="Choose a valid month and year.")
    days = month_days(year, month)
    return days[0], days[-1]


def _month(supabase: Client, year: int, month: int, employee_id: Optional[int] = None) -> dict:
    first, last = _bounds(year, month)

    att_q = supabase.table("attendance_log").select("*") \
        .gte("target_date", first.isoformat()).lte("target_date", last.isoformat())
    emp_q = supabase.table("employee_profile").select("id, first_name, last_name, status, date_joined, user_id")
    if employee_id is not None:
        att_q = att_q.eq("employee_id", employee_id)
        emp_q = emp_q.eq("id", employee_id)
    attendance = att_q.execute().data or []
    employees = emp_q.order("first_name").execute().data or []

    # Everyone active, plus anyone no longer active who has attendance this
    # month, so a leaver's last weeks still show.
    with_records = {a["employee_id"] for a in attendance}
    employees = [e for e in employees if (e.get("status") or "Active") == "Active" or e["id"] in with_records]

    schedules = supabase.table("work_schedules").select("*, days:work_schedule_days(*)").execute().data or []
    assignments = supabase.table("employee_schedule_assignments").select("*").execute().data or []
    holidays = supabase.table("holidays").select("holiday_date, name, is_day_off") \
        .gte("holiday_date", first.isoformat()).lte("holiday_date", last.isoformat()).execute().data or []

    requests = supabase.table("leave_requests") \
        .select("id, employee_id, status, half_day, leave_types(name, code, is_paid)") \
        .in_("status", ["Pending", "Approved"]) \
        .lte("start_date", last.isoformat()).gte("end_date", first.isoformat()).execute().data or []
    requests = [r for r in requests if r.get("status") in ("Pending", "Approved")
                and (employee_id is None or r["employee_id"] == employee_id)]
    by_id = {r["id"]: r for r in requests}
    day_rows = []
    if by_id:
        day_rows = supabase.table("leave_request_days").select("*").in_("request_id", list(by_id)) \
            .gte("leave_date", first.isoformat()).lte("leave_date", last.isoformat()).execute().data or []
    leave_days = []
    for d in day_rows:
        r = by_id.get(d["request_id"])
        if r is None:
            continue
        t = r.get("leave_types") or {}
        leave_days.append({
            "employee_id": r["employee_id"], "leave_date": d["leave_date"], "fraction": d["fraction"],
            "status": r["status"], "half_day": r.get("half_day") or "none",
            "type_name": t.get("name"), "type_code": t.get("code"), "paid": t.get("is_paid", True),
        })

    now = datetime.now(COLOMBO)
    return build_month(year, month, employees, schedules, assignments, holidays,
                       attendance, leave_days, today=now.date(), now=now)


@router.get("/attendance/month")
async def attendance_month(
    year: int,
    month: int,
    user=Depends(require_any_permission("hr:attendance:manage", "hr:attendance:read")),
    supabase: Client = Depends(get_supabase),
):
    result = _month(supabase, year, month)
    # For the grid to show what it can't edit, rather than offer edits the
    # server refuses: the viewer's own row, and a month whose payroll is
    # approved.
    mine = supabase.table("employee_profile").select("id").eq("user_id", str(user["id"])).execute().data or []
    return {
        **result,
        "my_employee_id": mine[0]["id"] if mine else None,
        "payroll_approved": payroll_approved(supabase, month, year),
        # Days up to this date are read-only; later days stay editable.
        "payroll_frozen_through": (lambda t: t.isoformat() if t else None)(
            payroll_frozen_through(supabase, month, year)),
    }


@router.get("/attendance/me/month")
async def my_attendance_month(
    year: int,
    month: int,
    user=Depends(require_permission("hr:attendance:self")),
    supabase: Client = Depends(get_supabase),
):
    me = supabase.table("employee_profile").select("id").eq("user_id", str(user["id"])).execute().data
    if not me:
        raise HTTPException(status_code=404, detail="No linked employee profile found for this user.")
    result = _month(supabase, year, month, employee_id=me[0]["id"])
    # One person's own month: the attention list is about them alone.
    return {**result, "employee": result["employees"][0] if result["employees"] else None}
