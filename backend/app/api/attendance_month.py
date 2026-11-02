"""
The monthly attendance grid (attendance rework, step 3).

Mounted under /api/hr. Loads one month of clock-ins, schedules, holidays and
leave, and hands them to build_month() in app/services/attendance_month.py,
where the status rules live. Read-only: edits go through the existing
attendance endpoints in app/api/hr.py.

  GET /attendance/month      hr:attendance:manage (HR) or hr:attendance:read (Director)
  GET /attendance/me/month   hr:attendance:self, one's own row only

The attendance tracking start date (confirmed 2026-11-02). HR Officer and
Admin change it (hr:manage); the Director sees it on the grid.

  GET /attendance-tracking/impact          what a new date would do, before saving
  PUT /attendance-tracking                 the organisation's date
  PUT /employees/{id}/attendance-tracking  one person's override, or null to follow it

Moving a date earlier is allowed after the impact is shown, but refused when
any day it brings into tracking falls in a month with an Approved payroll
run: once a month is paid, its attendance cannot become absences.
"""

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from supabase import Client

from app.core.audit import log_audit_action
from app.core.security import require_any_permission, require_permission
from app.core.supabase import get_supabase
from app.services.attendance_month import (
    ABSENT,
    HOLIDAY,
    MISSING_CLOCK_OUT,
    NOT_EMPLOYED,
    NOT_TRACKED,
    REST,
    UPCOMING,
    build_month,
    days_brought_into_tracking,
    month_days,
    months_between,
    tracked_from_for,
)
from app.services.work_calendar import COLOMBO

router = APIRouter()


def _bounds(year: int, month: int) -> tuple[date, date]:
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        raise HTTPException(status_code=400, detail="Choose a valid month and year.")
    days = month_days(year, month)
    return days[0], days[-1]


def _tracking_start(supabase: Client) -> Optional[date]:
    rows = supabase.table("attendance_settings").select("tracking_start_date").eq("id", 1).execute().data or []
    return _parse(rows[0].get("tracking_start_date")) if rows else None


def _parse(value) -> Optional[date]:
    return date.fromisoformat(str(value)[:10]) if value else None


def _month(
    supabase: Client,
    year: int,
    month: int,
    employee_id: Optional[int] = None,
    tracking_start: Optional[date] = None,
    tracked_from: Optional[dict[int, date]] = None,
) -> dict:
    """
    `tracking_start` and `tracked_from` (employee id -> date) stand in for
    the stored dates, so the impact preview can see a change before it is
    saved.
    """
    first, last = _bounds(year, month)
    if tracking_start is None:
        tracking_start = _tracking_start(supabase)

    att_q = supabase.table("attendance_log").select("*") \
        .gte("target_date", first.isoformat()).lte("target_date", last.isoformat())
    emp_q = supabase.table("employee_profile") \
        .select("id, first_name, last_name, status, date_joined, user_id, attendance_tracked_from")
    if employee_id is not None:
        att_q = att_q.eq("employee_id", employee_id)
        emp_q = emp_q.eq("id", employee_id)
    attendance = att_q.execute().data or []
    employees = emp_q.order("first_name").execute().data or []

    # Everyone active, plus anyone no longer active who has attendance this
    # month, so a leaver's last weeks still show.
    with_records = {a["employee_id"] for a in attendance}
    employees = [e for e in employees if (e.get("status") or "Active") == "Active" or e["id"] in with_records]
    if tracked_from:
        employees = [{**e, "attendance_tracked_from": tracked_from[e["id"]].isoformat()} if e["id"] in tracked_from else e
                     for e in employees]

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
                       attendance, leave_days, today=now.date(), now=now, tracking_start=tracking_start)


@router.get("/attendance/month")
async def attendance_month(
    year: int,
    month: int,
    user=Depends(require_any_permission("hr:attendance:manage", "hr:attendance:read")),
    supabase: Client = Depends(get_supabase),
):
    return _month(supabase, year, month)


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


# --------------------------------------------------------------------------
# Attendance tracking start
# --------------------------------------------------------------------------

_EARLIEST = date(2000, 1, 1)


def _check_date(value: date) -> date:
    if value < _EARLIEST or value > datetime.now(COLOMBO).date() + timedelta(days=366):
        raise ValueError("Choose a date from 2000 onwards and no more than a year ahead.")
    return value


class TrackingIn(BaseModel):
    tracking_start_date: date

    @field_validator("tracking_start_date")
    @classmethod
    def _valid(cls, v):
        return _check_date(v)


class OverrideIn(BaseModel):
    # None: follow the organisation date again.
    tracked_from: Optional[date] = None

    @field_validator("tracked_from")
    @classmethod
    def _valid(cls, v):
        return None if v is None else _check_date(v)


def _approved_months(supabase: Client, months: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not months:
        return []
    runs = supabase.table("payroll_runs").select("payroll_month, payroll_year, status") \
        .eq("status", "Approved").execute().data or []
    paid = {(r["payroll_year"], r["payroll_month"]) for r in runs if r.get("status") == "Approved"}
    return [m for m in months if m in paid]


def _employee(supabase: Client, employee_id: int) -> dict:
    rows = supabase.table("employee_profile") \
        .select("id, first_name, last_name, attendance_tracked_from").eq("id", employee_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Employee not found")
    return rows[0]


def _history_floor(supabase: Client) -> Optional[date]:
    """
    The earliest join date or clock-in. Nobody can be judged before it, so
    the impact never walks years of empty months.
    """
    joined = supabase.table("employee_profile").select("date_joined").execute().data or []
    clocked = supabase.table("attendance_log").select("target_date").order("target_date").limit(1).execute().data or []
    found = [_parse(r.get("date_joined")) for r in joined] + [_parse(r.get("target_date")) for r in clocked]
    found = [d for d in found if d]
    return min(found) if found else None


def _impact(
    supabase: Client,
    org_old: Optional[date],
    org_new: Optional[date],
    employee_id: Optional[int] = None,
    override_new: Optional[date] = None,
) -> dict:
    """
    What a change would do. Either the organisation date changes (org_new),
    and with it everyone who has no override, or one employee's override
    does (employee_id, override_new; None clears it).

    The days that change hands lie between the old and the new effective
    date. They are judged as if tracked, so the counts say how many
    absences and missing clock-outs would appear (moving earlier) or stop
    showing (moving later). Days after today are not counted.
    """
    if employee_id is None:
        old, new = org_old, org_new
        everyone = supabase.table("employee_profile").select("id, attendance_tracked_from").execute().data or []
        affected = {e["id"] for e in everyone if not e.get("attendance_tracked_from")}
    else:
        old = tracked_from_for(_employee(supabase, employee_id), org_old)
        new = override_new or org_old
        affected = {employee_id}

    out = {
        "old_date": old.isoformat() if old else None,
        "new_date": new.isoformat() if new else None,
        "direction": "same", "first": None, "last": None,
        "employees": 0, "working_days": 0, "absences": 0, "missing_clock_outs": 0,
        "blocked_months": [],
    }
    if new is None or old == new:
        return out

    earlier = days_brought_into_tracking(old, new)
    if earlier:
        out["direction"], (first, last) = "earlier", earlier
        out["blocked_months"] = [{"year": y, "month": m}
                                 for y, m in _approved_months(supabase, months_between(first, last))]
    else:
        # Everything before `new` that was tracked stops being tracked.
        out["direction"], first, last = "later", old or _EARLIEST, new - timedelta(days=1)
    out["first"], out["last"] = first.isoformat(), last.isoformat()

    floor = _history_floor(supabase)
    judged_from = max(first, floor) if floor else first
    judged_to = min(last, datetime.now(COLOMBO).date())
    people: set[int] = set()
    if judged_from <= judged_to:
        for y, m in months_between(judged_from, judged_to):
            # Judge the span as if tracked from its first day.
            if employee_id is None:
                result = _month(supabase, y, m, tracking_start=first)
            else:
                result = _month(supabase, y, m, employee_id=employee_id, tracked_from={employee_id: first})
            for row in result["employees"]:
                if row["employee_id"] not in affected:
                    continue
                for c in row["cells"]:
                    if not judged_from.isoformat() <= c["date"] <= judged_to.isoformat():
                        continue
                    if c["status"] in (NOT_EMPLOYED, NOT_TRACKED, UPCOMING, REST, HOLIDAY):
                        continue
                    people.add(row["employee_id"])
                    out["working_days"] += 1
                    out["absences"] += c["status"] == ABSENT
                    out["missing_clock_outs"] += c["status"] == MISSING_CLOCK_OUT
    out["employees"] = len(people)
    return out


def _refuse_if_paid(impact: dict) -> None:
    if impact["blocked_months"]:
        names = ", ".join(date(b["year"], b["month"], 1).strftime("%B %Y") for b in impact["blocked_months"])
        raise HTTPException(
            status_code=409,
            detail=f"Payroll for {names} is already approved, so its attendance cannot be brought into "
                   f"tracking. Choose a date after that month.",
        )


@router.get("/attendance-tracking/impact")
async def tracking_impact(
    start: Optional[date] = None,
    employee_id: Optional[int] = None,
    user=Depends(require_permission("hr:manage")),
    supabase: Client = Depends(get_supabase),
):
    """
    `start` alone: the organisation date would become `start`. With
    `employee_id`: that person's override would become `start`, or be
    cleared when `start` is left out.
    """
    if employee_id is None and start is None:
        raise HTTPException(status_code=400, detail="Choose a date.")
    if start is not None:
        try:
            _check_date(start)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    org = _tracking_start(supabase)
    if employee_id is None:
        return _impact(supabase, org, start)
    return _impact(supabase, org, None, employee_id=employee_id, override_new=start)


@router.put("/attendance-tracking")
async def set_tracking_start(
    body: TrackingIn,
    user=Depends(require_permission("hr:manage")),
    supabase: Client = Depends(get_supabase),
):
    org = _tracking_start(supabase)
    impact = _impact(supabase, org, body.tracking_start_date)
    _refuse_if_paid(impact)

    row = {
        "id": 1,
        "tracking_start_date": body.tracking_start_date.isoformat(),
        "updated_by": str(user["id"]),
        "updated_at": datetime.now(COLOMBO).isoformat(),
    }
    supabase.table("attendance_settings").upsert(row, on_conflict="id").execute()
    await log_audit_action(
        supabase, user_id=user["id"], action_type="ATTENDANCE_TRACKING_START",
        table_name="attendance_settings",
        old_payload={"tracking_start_date": org.isoformat() if org else None},
        new_payload={"tracking_start_date": row["tracking_start_date"]},
    )
    return {"tracking_start_date": row["tracking_start_date"], "impact": impact}


@router.put("/employees/{employee_id}/attendance-tracking")
async def set_employee_tracking(
    employee_id: int,
    body: OverrideIn,
    user=Depends(require_permission("hr:manage")),
    supabase: Client = Depends(get_supabase),
):
    current = _employee(supabase, employee_id)
    impact = _impact(supabase, _tracking_start(supabase), None,
                     employee_id=employee_id, override_new=body.tracked_from)
    _refuse_if_paid(impact)

    value = body.tracked_from.isoformat() if body.tracked_from else None
    supabase.table("employee_profile").update({"attendance_tracked_from": value}).eq("id", employee_id).execute()
    await log_audit_action(
        supabase, user_id=user["id"], action_type="ATTENDANCE_TRACKING_OVERRIDE",
        table_name="employee_profile",
        old_payload={"employee_id": employee_id, "attendance_tracked_from": current.get("attendance_tracked_from")},
        new_payload={"employee_id": employee_id, "attendance_tracked_from": value},
    )
    return {"employee_id": employee_id, "attendance_tracked_from": value, "impact": impact}
