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
any day it brings into tracking is frozen by an approved payroll: on or
before that month's approval date (2026-11-12; it used to be the whole
month). Once paid, attendance cannot become absences.
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
    absence_days,
    build_month,
    days_brought_into_tracking,
    month_days,
    month_has_tracked_days,
    months_between,
    tracked_from_for,
)
from app.services.payroll_status import frozen_through, month_close, payroll_approved
from app.services.work_calendar import COLOMBO

router = APIRouter()


def _bounds(year: int, month: int) -> tuple[date, date]:
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        raise HTTPException(status_code=400, detail="Choose a valid month and year.")
    days = month_days(year, month)
    return days[0], days[-1]


def _not_migrated(error: Exception) -> bool:
    """A missing table or column: migration 027 isn't applied yet."""
    text = str(error).lower()
    return any(k in text for k in ("42703", "42p01", "pgrst205", "does not exist", "could not find the table"))


def _tracking_start(supabase: Client) -> Optional[date]:
    try:
        rows = supabase.table("attendance_settings").select("tracking_start_date").eq("id", 1).execute().data or []
    except Exception as e:
        # Before 027 there is no start date: everything is tracked, as before.
        if not _not_migrated(e):
            raise
        return None
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
    if employee_id is not None:
        att_q = att_q.eq("employee_id", employee_id)
    attendance = att_q.execute().data or []

    def employees_with(columns: str) -> list[dict]:
        q = supabase.table("employee_profile").select(columns)
        if employee_id is not None:
            q = q.eq("id", employee_id)
        return q.order("first_name").execute().data or []
    try:
        employees = employees_with("id, first_name, last_name, status, date_joined, user_id, attendance_tracked_from")
    except Exception as e:
        # Before 027 there is no override column.
        if not _not_migrated(e):
            raise
        employees = employees_with("id, first_name, last_name, status, date_joined, user_id")

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


def _pending_corrections(supabase: Client, year: int, month: int, employee_id: Optional[int] = None) -> list[dict]:
    """
    The month's correction requests still waiting for HR (migration 028), as
    {id, employee_id, date}; the grid marks those days. Empty before 028.
    """
    first, last = _bounds(year, month)
    try:
        q = supabase.table("attendance_correction_requests").select("id, employee_id, target_date, status")             .eq("status", "Pending").gte("target_date", first.isoformat()).lte("target_date", last.isoformat())
        if employee_id is not None:
            q = q.eq("employee_id", employee_id)
        rows = q.execute().data or []
    except Exception as e:
        if not _not_migrated(e):
            raise
        return []
    return [{"id": r["id"], "employee_id": r["employee_id"], "date": str(r["target_date"])[:10]}
            for r in rows if r.get("status") == "Pending"
            and (employee_id is None or r.get("employee_id") == employee_id)]


def _frozen_through_iso(supabase: Client, year: int, month: int) -> Optional[str]:
    t = frozen_through(supabase, month, year)
    return t.isoformat() if t else None


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
        "payroll_frozen_through": _frozen_through_iso(supabase, year, month),
        "pending_corrections": _pending_corrections(supabase, year, month),
        # Closed, Reopened or None (migration 029): the grid's banner.
        "month_close_status": (_close_row(supabase, year, month) or {}).get("status"),
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
    # One person's own month: the attention list is about them alone. The
    # frozen date and pending requests decide where a correction can be asked.
    return {
        **result,
        "employee": result["employees"][0] if result["employees"] else None,
        "payroll_frozen_through": _frozen_through_iso(supabase, year, month),
        "pending_corrections": _pending_corrections(supabase, year, month, employee_id=me[0]["id"]),
    }


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


def _frozen_months(supabase: Client, first: date, last: date) -> list[dict]:
    """
    Months in first..last with frozen days in the span: days on or before the
    month's payroll approval date (the whole month if approved after it), or
    the whole of a closed month.
    """
    out = []
    for y, m in months_between(first, last):
        through = frozen_through(supabase, m, y)
        if through and through >= date(y, m, 1) and first <= through:
            out.append({"year": y, "month": m, "frozen_through": through.isoformat(),
                        "closed": month_close(supabase, m, y) is not None})
    return out


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
    # Months with frozen days in the span, and which of them would actually
    # turn a frozen day into an absence or a missing clock-out. Only those
    # block: a rest day, holiday, leave or present day brought into tracking
    # changes nothing that was paid (2026-11-12: 1 Nov, a Sunday frozen by
    # November's approval on the 3rd, was blocking a 1 September start).
    frozen = {}
    hits = set()
    if earlier:
        out["direction"], (first, last) = "earlier", earlier
        frozen = {(f["year"], f["month"]): f for f in _frozen_months(supabase, first, last)}
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
                    f = frozen.get((y, m))
                    if f and c["date"] <= f["frozen_through"] and c["status"] in (ABSENT, MISSING_CLOCK_OUT):
                        hits.add((y, m))
    out["employees"] = len(people)
    out["blocked_months"] = [f for key, f in sorted(frozen.items()) if key in hits]
    return out


def _refuse_if_paid(impact: dict) -> None:
    blocked = impact["blocked_months"]
    if blocked:
        names = ", ".join(date(b["year"], b["month"], 1).strftime("%B %Y") for b in blocked)
        after = date.fromisoformat(max(b["frozen_through"] for b in blocked)) + timedelta(days=1)
        if all(b.get("closed") for b in blocked):
            detail = (f"{names} is closed, and this would turn its days into absences. "
                      f"Choose {after.day} {after.strftime('%B %Y')} or later, or reopen the month.")
        else:
            detail = (f"Payroll for {names} is already approved, and this would turn days up to its approval "
                      f"into absences. Choose {after.day} {after.strftime('%B %Y')} or later.")
        raise HTTPException(status_code=409, detail=detail)


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


# --------------------------------------------------------------------------
# Month close (attendance rework, step 5; migration 029)
# --------------------------------------------------------------------------
#
# HR closes a past month once nothing is loose. The close records each
# employee's payable absences, freezes the month, and the next payroll
# generated deducts those absences in arrears (confirmed 2026-11-12).

_MONTH_NAMES = ("January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December")


def _close_row(supabase: Client, year: int, month: int) -> Optional[dict]:
    """The month's close row, Closed or Reopened, or None (also before 029)."""
    try:
        rows = supabase.table("attendance_month_closes").select("*") \
            .eq("close_month", month).eq("close_year", year).execute().data or []
    except Exception as e:
        if not _not_migrated(e):
            raise
        return None
    return next((r for r in rows if r.get("close_month") == month and r.get("close_year") == year), None)


def _close_preview(supabase: Client, year: int, month: int) -> dict:
    """What closing the month would record, and what stops it."""
    first, last = _bounds(year, month)
    period = f"{_MONTH_NAMES[month - 1]} {year}"
    result = _month(supabase, year, month)
    rows = result["employees"]

    missing, absences = [], []
    for r in rows:
        for c in r["cells"]:
            if c["status"] == MISSING_CLOCK_OUT:
                missing.append({"employee_id": r["employee_id"], "employee_name": r["employee_name"], "date": c["date"]})
        days = absence_days(r["cells"])
        if days:
            absences.append({
                "employee_id": r["employee_id"], "employee_name": r["employee_name"],
                "absent_days": sum(f for _, f in days), "absent_dates": [d for d, _ in days],
            })
    names = {r["employee_id"]: r["employee_name"] for r in rows}
    waiting = [{**p, "employee_name": names.get(p["employee_id"], f"Employee {p['employee_id']}")}
               for p in _pending_corrections(supabase, year, month)]

    close = _close_row(supabase, year, month)
    status = close["status"] if close else "Open"
    blocks = []
    if status == "Closed":
        blocks.append(f"{period} is already closed.")
    if last >= datetime.now(COLOMBO).date():
        blocks.append(f"{period} can be closed once it has ended.")
    tracked = [date.fromisoformat(r["tracked_from"]) if r.get("tracked_from") else None for r in rows]
    if rows and not month_has_tracked_days(year, month, tracked):
        blocks.append(f"Attendance wasn't tracked in {period}, so there is nothing to close.")
    if missing:
        blocks.append(f"{len(missing)} day{'s are' if len(missing) != 1 else ' is'} missing a clock-out.")
    if waiting:
        blocks.append(f"{len(waiting)} correction request{'s are' if len(waiting) != 1 else ' is'} still waiting.")

    reopen_block = None
    if status == "Closed" and close.get("deducted_in_run_id"):
        reopen_block = "Its absences are in an approved payroll, so it can no longer be reopened."
    return {
        "year": year, "month": month, "status": status, "close": close,
        "can_close": not blocks, "blocks": blocks,
        "can_reopen": status == "Closed" and reopen_block is None, "reopen_block": reopen_block,
        "missing_clock_outs": missing, "pending_corrections": waiting,
        "absences": sorted(absences, key=lambda a: a["employee_name"].lower()),
        "absent_days_total": sum(a["absent_days"] for a in absences),
    }


@router.get("/attendance/close")
async def month_close_preview(year: int, month: int, user=Depends(require_permission("hr:attendance:manage")),
                              supabase: Client = Depends(get_supabase)):
    _bounds(year, month)
    return _close_preview(supabase, year, month)


@router.post("/attendance/close")
async def close_month(year: int, month: int, user=Depends(require_permission("hr:attendance:manage")),
                      supabase: Client = Depends(get_supabase)):
    """Close a past month, recording its payable absences for the next payroll."""
    _bounds(year, month)
    preview = _close_preview(supabase, year, month)
    if not preview["can_close"]:
        raise HTTPException(status_code=409, detail=" ".join(preview["blocks"]))
    lines = [{"employee_id": a["employee_id"], "absent_days": a["absent_days"], "absent_dates": a["absent_dates"]}
             for a in preview["absences"]]
    try:
        result = supabase.rpc("close_attendance_month",
                              {"p_month": month, "p_year": year, "p_user": str(user["id"]), "p_lines": lines}).execute()
    except Exception as e:
        msg = getattr(e, "message", None) or str(e)
        if "already closed" in msg:
            raise HTTPException(status_code=409, detail=msg)
        if "Could not find the function" in msg:
            raise HTTPException(status_code=503, detail="Month close isn't set up yet (database migration 029).")
        raise
    close = result.data[0] if isinstance(result.data, list) and result.data else result.data
    await log_audit_action(supabase, user_id=user["id"], action_type="ATTENDANCE_MONTH_CLOSE",
                           table_name="attendance_month_closes", old_payload=None,
                           new_payload={"year": year, "month": month, "absent_days_total": str(preview["absent_days_total"]),
                                        "employees_with_absences": len(lines)})
    return {**preview, "status": "Closed", "close": close, "can_close": False}


@router.post("/attendance/close/reopen")
async def reopen_month(year: int, month: int, user=Depends(require_permission("hr:attendance:manage")),
                       supabase: Client = Depends(get_supabase)):
    """Reopen a closed month, until a payroll that took its absences is approved."""
    _bounds(year, month)
    close = _close_row(supabase, year, month)
    period = f"{_MONTH_NAMES[month - 1]} {year}"
    if not close or close.get("status") != "Closed":
        raise HTTPException(status_code=409, detail=f"{period} isn't closed.")
    if close.get("deducted_in_run_id"):
        raise HTTPException(status_code=409, detail=f"{period}'s absences are in an approved payroll, so it can no longer be reopened.")
    # Guarded in the update too: a payroll approved in between wins.
    updated = supabase.table("attendance_month_closes") \
        .update({"status": "Reopened", "reopened_by": str(user["id"]),
                 "reopened_at": datetime.now(COLOMBO).isoformat()}) \
        .eq("id", close["id"]).eq("status", "Closed").is_("deducted_in_run_id", "null").execute().data or []
    if not updated:
        raise HTTPException(status_code=409, detail=f"{period} could not be reopened; reload and try again.")
    await log_audit_action(supabase, user_id=user["id"], action_type="ATTENDANCE_MONTH_REOPEN",
                           table_name="attendance_month_closes", old_payload=close,
                           new_payload={"status": "Reopened"})
    return _close_preview(supabase, year, month)
