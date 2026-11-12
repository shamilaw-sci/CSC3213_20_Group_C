"""
Work schedules, schedule assignments and the holiday calendar.

Mounted under /api/hr beside app/api/hr.py. Rules live in
app/services/work_calendar.py; this module only reads, validates and writes.
"""

from datetime import date, datetime, time, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from supabase import Client

from app.core.audit import log_audit_action
from app.core.security import get_current_user, require_any_permission, require_permission
from app.core.supabase import get_supabase
from app.services.work_calendar import (
    is_poya,
    load_holiday_file,
    poya_warnings,
    resolve_day,
    schedule_for,
)

router = APIRouter()

SCHEDULE_SELECT = "*, days:work_schedule_days(*)"


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class ScheduleDay(BaseModel):
    weekday: int = Field(ge=1, le=7)  # ISO: 1 = Monday
    start_time: time
    end_time: time
    break_minutes: int = Field(default=60, ge=0, le=600)

    @field_validator("end_time")
    @classmethod
    def _not_zero_length(cls, end, info):
        if info.data.get("start_time") == end:
            raise ValueError("A working day cannot start and end at the same time.")
        return end


class ScheduleIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    grace_minutes: int = Field(default=15, ge=0, le=120)
    observes_holidays: bool = True
    days: List[ScheduleDay] = []

    @field_validator("days")
    @classmethod
    def _one_row_per_weekday(cls, days):
        weekdays = [d.weekday for d in days]
        if len(weekdays) != len(set(weekdays)):
            raise ValueError("Each weekday can appear only once.")
        return days


class AssignmentIn(BaseModel):
    schedule_id: int
    effective_from: date


class HolidayIn(BaseModel):
    holiday_date: date
    name: str = Field(min_length=1, max_length=120)
    is_public: bool = False
    is_bank: bool = False
    is_mercantile: bool = False
    is_day_off: bool = True
    source: Optional[str] = Field(default=None, max_length=200)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _schedule_out(row: dict) -> dict:
    days = sorted(row.pop("days", None) or [], key=lambda d: d["weekday"])
    return {**row, "days": days}


def _get_schedule(supabase: Client, schedule_id: int) -> dict:
    rows = supabase.table("work_schedules").select(SCHEDULE_SELECT).eq("id", schedule_id).execute().data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return _schedule_out(rows[0])


def _day_rows(schedule_id: int, days: List[ScheduleDay]) -> list[dict]:
    return [{
        "schedule_id": schedule_id,
        "weekday": d.weekday,
        "start_time": d.start_time.isoformat(timespec="minutes"),
        "end_time": d.end_time.isoformat(timespec="minutes"),
        "break_minutes": d.break_minutes,
    } for d in days]


def _write_days(supabase: Client, schedule_id: int, days: List[ScheduleDay]) -> None:
    """
    Upsert the given weekdays, then delete the others. In that order, a
    failure part-way leaves extra working days rather than none, which is
    the recoverable mistake: nobody gets marked absent for a day that
    silently stopped being scheduled.
    """
    if days:
        supabase.table("work_schedule_days").upsert(
            _day_rows(schedule_id, days), on_conflict="schedule_id,weekday"
        ).execute()
    keep = {d.weekday for d in days}
    drop = [w for w in range(1, 8) if w not in keep]
    if drop:
        supabase.table("work_schedule_days").delete().eq("schedule_id", schedule_id).in_("weekday", drop).execute()


def _audit_safe(row: dict) -> dict:
    # Times and dates as strings keep the audit hash stable through JSONB.
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}


# --------------------------------------------------------------------------
# Schedules
# --------------------------------------------------------------------------

@router.get("/schedules")
async def list_schedules(
    user=Depends(require_any_permission("hr:manage", "hr:attendance:manage")),
    supabase: Client = Depends(get_supabase),
):
    rows = supabase.table("work_schedules").select(SCHEDULE_SELECT).order("name").execute().data or []
    return [_schedule_out(r) for r in rows]


@router.post("/schedules")
async def create_schedule(
    body: ScheduleIn,
    user=Depends(require_permission("hr:manage")),
    supabase: Client = Depends(get_supabase),
):
    created = supabase.table("work_schedules").insert({
        "name": body.name.strip(),
        "grace_minutes": body.grace_minutes,
        "observes_holidays": body.observes_holidays,
        "created_by": str(user["id"]),
    }).execute().data
    if not created:
        raise HTTPException(status_code=400, detail="Failed to create schedule")

    schedule_id = created[0]["id"]
    _write_days(supabase, schedule_id, body.days)
    schedule = _get_schedule(supabase, schedule_id)

    await log_audit_action(supabase, user_id=user["id"], action_type="SCHEDULE_CREATE",
                           table_name="work_schedules", old_payload=None,
                           new_payload=_audit_safe({**body.model_dump(mode="json"), "id": schedule_id}))
    return schedule


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    body: ScheduleIn,
    user=Depends(require_permission("hr:manage")),
    supabase: Client = Depends(get_supabase),
):
    before = _get_schedule(supabase, schedule_id)
    supabase.table("work_schedules").update({
        "name": body.name.strip(),
        "grace_minutes": body.grace_minutes,
        "observes_holidays": body.observes_holidays,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", schedule_id).execute()
    _write_days(supabase, schedule_id, body.days)
    after = _get_schedule(supabase, schedule_id)

    await log_audit_action(supabase, user_id=user["id"], action_type="SCHEDULE_UPDATE",
                           table_name="work_schedules", old_payload=_audit_safe(before),
                           new_payload=_audit_safe({**body.model_dump(mode="json"), "id": schedule_id}))
    return after


@router.post("/schedules/{schedule_id}/default")
async def make_default(
    schedule_id: int,
    user=Depends(require_permission("hr:manage")),
    supabase: Client = Depends(get_supabase),
):
    """
    The partial unique index allows one default, so the old one is cleared
    first. If setting the new one then fails, the old one is restored rather
    than leaving employees without assignments on no schedule at all.
    """
    target = _get_schedule(supabase, schedule_id)
    if target.get("is_default"):
        return target

    previous = supabase.table("work_schedules").select("id").eq("is_default", True).execute().data or []
    supabase.table("work_schedules").update({"is_default": False}).eq("is_default", True).execute()
    try:
        supabase.table("work_schedules").update({"is_default": True}).eq("id", schedule_id).execute()
    except Exception:
        for p in previous:
            supabase.table("work_schedules").update({"is_default": True}).eq("id", p["id"]).execute()
        raise HTTPException(status_code=500, detail="Could not change the default schedule; the previous default was kept.")

    await log_audit_action(supabase, user_id=user["id"], action_type="SCHEDULE_SET_DEFAULT",
                           table_name="work_schedules",
                           old_payload={"default_schedule_id": previous[0]["id"] if previous else None},
                           new_payload={"default_schedule_id": schedule_id})
    return _get_schedule(supabase, schedule_id)


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: int,
    user=Depends(require_permission("hr:manage")),
    supabase: Client = Depends(get_supabase),
):
    schedule = _get_schedule(supabase, schedule_id)
    if schedule.get("is_default"):
        raise HTTPException(status_code=409, detail="The default schedule cannot be deleted. Make another schedule the default first.")
    used = supabase.table("employee_schedule_assignments").select("id").eq("schedule_id", schedule_id).limit(1).execute().data
    if used:
        raise HTTPException(
            status_code=409,
            detail="This schedule has been assigned to employees, so past attendance depends on it. It cannot be deleted.",
        )

    supabase.table("work_schedules").delete().eq("id", schedule_id).execute()
    await log_audit_action(supabase, user_id=user["id"], action_type="SCHEDULE_DELETE",
                           table_name="work_schedules", old_payload=_audit_safe(schedule), new_payload=None)
    return {"deleted": schedule_id}


# --------------------------------------------------------------------------
# Assignments
# --------------------------------------------------------------------------

@router.get("/schedule-assignments")
async def list_assignments(
    user=Depends(require_any_permission("hr:manage", "hr:attendance:manage")),
    supabase: Client = Depends(get_supabase),
):
    """
    Every employee with the schedule they follow today, their history, and
    the date their attendance is tracked from.
    """
    employees = supabase.table("employee_profile") \
        .select("id, first_name, last_name, status, attendance_tracked_from") \
        .order("first_name").execute().data or []
    assignments = supabase.table("employee_schedule_assignments").select("*") \
        .order("effective_from", desc=True).execute().data or []
    schedules = supabase.table("work_schedules").select("id, name, is_default").execute().data or []

    names = {s["id"]: s["name"] for s in schedules}
    default_id = next((s["id"] for s in schedules if s.get("is_default")), None)
    today = date.today()
    settings = supabase.table("attendance_settings").select("tracking_start_date").eq("id", 1).execute().data or []
    org_start = settings[0].get("tracking_start_date") if settings else None

    out = []
    for e in employees:
        current = schedule_for(e["id"], today, assignments, default_id)
        history = [a for a in assignments if a["employee_id"] == e["id"]]
        out.append({
            "employee_id": e["id"],
            "employee_name": f"{e.get('first_name', '')} {e.get('last_name', '')}".strip(),
            "status": e.get("status"),
            "current_schedule_id": current,
            "current_schedule_name": names.get(current),
            "follows_default": not any(date.fromisoformat(str(a["effective_from"])[:10]) <= today for a in history),
            "history": [{**a, "schedule_name": names.get(a["schedule_id"])} for a in history],
            "tracked_from": e.get("attendance_tracked_from") or org_start,
            "tracking_overridden": bool(e.get("attendance_tracked_from")),
        })
    return out


@router.post("/employees/{employee_id}/schedule")
async def assign_schedule(
    employee_id: int,
    body: AssignmentIn,
    user=Depends(require_permission("hr:manage")),
    supabase: Client = Depends(get_supabase),
):
    if not supabase.table("employee_profile").select("id").eq("id", employee_id).execute().data:
        raise HTTPException(status_code=404, detail="Employee not found")
    _get_schedule(supabase, body.schedule_id)

    row = {
        "employee_id": employee_id,
        "schedule_id": body.schedule_id,
        "effective_from": body.effective_from.isoformat(),
        "created_by": str(user["id"]),
    }
    # Same employee and date: the later decision replaces the earlier one.
    saved = supabase.table("employee_schedule_assignments").upsert(
        row, on_conflict="employee_id,effective_from"
    ).execute().data

    await log_audit_action(supabase, user_id=user["id"], action_type="SCHEDULE_ASSIGN",
                           table_name="employee_schedule_assignments", old_payload=None, new_payload=row)
    return saved[0] if saved else row


@router.delete("/schedule-assignments/{assignment_id}")
async def delete_assignment(
    assignment_id: int,
    user=Depends(require_permission("hr:manage")),
    supabase: Client = Depends(get_supabase),
):
    rows = supabase.table("employee_schedule_assignments").select("*").eq("id", assignment_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Assignment not found")
    supabase.table("employee_schedule_assignments").delete().eq("id", assignment_id).execute()
    await log_audit_action(supabase, user_id=user["id"], action_type="SCHEDULE_UNASSIGN",
                           table_name="employee_schedule_assignments", old_payload=rows[0], new_payload=None)
    return {"deleted": assignment_id}


# --------------------------------------------------------------------------
# Holidays
# --------------------------------------------------------------------------

def _year_bounds(year: int) -> tuple[str, str]:
    if not 2000 <= year <= 2100:
        raise HTTPException(status_code=400, detail="Choose a year between 2000 and 2100.")
    return f"{year}-01-01", f"{year}-12-31"


@router.get("/holidays")
async def list_holidays(
    year: int,
    user=Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Any signed-in staff member: the calendar is not confidential."""
    start, end = _year_bounds(year)
    return supabase.table("holidays").select("*").gte("holiday_date", start).lte("holiday_date", end) \
        .order("holiday_date").execute().data or []


def _import_plan(supabase: Client, year: int) -> dict:
    try:
        rows = load_holiday_file(year)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=422, detail=f"The {year} holiday file is malformed: {e}")

    start, end = _year_bounds(year)
    existing = supabase.table("holidays").select("holiday_date, name") \
        .gte("holiday_date", start).lte("holiday_date", end).execute().data or []
    have = {(str(h["holiday_date"])[:10], h["name"]) for h in existing}
    new = [r for r in rows if (r["holiday_date"], r["name"]) not in have]
    return {"year": year, "rows": rows, "new": new, "warnings": poya_warnings(rows)}


@router.get("/holidays/import-preview")
async def preview_import(
    year: int,
    user=Depends(require_permission("hr:manage")),
    supabase: Client = Depends(get_supabase),
):
    plan = _import_plan(supabase, year)
    return {
        "year": year,
        "rows": plan["rows"],
        "new_count": len(plan["new"]),
        "existing_count": len(plan["rows"]) - len(plan["new"]),
        "warnings": plan["warnings"],
    }


@router.post("/holidays/import")
async def import_holidays(
    year: int,
    user=Depends(require_permission("hr:manage")),
    supabase: Client = Depends(get_supabase),
):
    """
    Adds the year's gazette rows that are not already there. Existing rows,
    including any HR has since edited (e.g. a day-off decision), are left
    alone, so re-importing never undoes a manual change.
    """
    plan = _import_plan(supabase, year)
    if plan["new"]:
        supabase.table("holidays").insert(
            [{**r, "created_by": str(user["id"])} for r in plan["new"]]
        ).execute()

    await log_audit_action(supabase, user_id=user["id"], action_type="HOLIDAY_IMPORT",
                           table_name="holidays", old_payload=None,
                           new_payload={"year": year, "added": len(plan["new"]),
                                        "warnings": plan["warnings"]})
    return {"year": year, "added": len(plan["new"]),
            "skipped_existing": len(plan["rows"]) - len(plan["new"]), "warnings": plan["warnings"]}


@router.post("/holidays")
async def create_holiday(
    body: HolidayIn,
    user=Depends(require_permission("hr:manage")),
    supabase: Client = Depends(get_supabase),
):
    row = {**body.model_dump(mode="json"), "is_poya": is_poya(body.name), "created_by": str(user["id"])}
    if not row.get("source"):
        row["source"] = "Added by HR"
    try:
        saved = supabase.table("holidays").insert(row).execute().data
    except Exception as e:
        if "duplicate" in str(e).lower() or "23505" in str(e):
            raise HTTPException(status_code=409, detail="That holiday is already on the calendar for this date.")
        raise
    await log_audit_action(supabase, user_id=user["id"], action_type="HOLIDAY_CREATE",
                           table_name="holidays", old_payload=None, new_payload=row)
    return saved[0] if saved else row


@router.put("/holidays/{holiday_id}")
async def update_holiday(
    holiday_id: int,
    body: HolidayIn,
    user=Depends(require_permission("hr:manage")),
    supabase: Client = Depends(get_supabase),
):
    rows = supabase.table("holidays").select("*").eq("id", holiday_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Holiday not found")
    update = {**body.model_dump(mode="json"), "is_poya": is_poya(body.name)}
    saved = supabase.table("holidays").update(update).eq("id", holiday_id).execute().data
    await log_audit_action(supabase, user_id=user["id"], action_type="HOLIDAY_UPDATE",
                           table_name="holidays", old_payload=rows[0], new_payload=update)
    return saved[0] if saved else {**rows[0], **update}


@router.delete("/holidays/{holiday_id}")
async def delete_holiday(
    holiday_id: int,
    user=Depends(require_permission("hr:manage")),
    supabase: Client = Depends(get_supabase),
):
    rows = supabase.table("holidays").select("*").eq("id", holiday_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Holiday not found")
    supabase.table("holidays").delete().eq("id", holiday_id).execute()
    await log_audit_action(supabase, user_id=user["id"], action_type="HOLIDAY_DELETE",
                           table_name="holidays", old_payload=rows[0], new_payload=None)
    return {"deleted": holiday_id}


# --------------------------------------------------------------------------
# Self-service: my schedule and the next holidays
# --------------------------------------------------------------------------

@router.get("/schedules/me")
async def my_schedule(
    user=Depends(require_permission("hr:attendance:self")),
    supabase: Client = Depends(get_supabase),
):
    emp = supabase.table("employee_profile").select("id").eq("user_id", str(user["id"])).execute().data
    if not emp:
        raise HTTPException(status_code=404, detail="No linked employee profile found for this user.")
    employee_id = emp[0]["id"]
    today = date.today()

    assignments = supabase.table("employee_schedule_assignments").select("*") \
        .eq("employee_id", employee_id).execute().data or []
    defaults = supabase.table("work_schedules").select("id").eq("is_default", True).execute().data or []
    schedule_id = schedule_for(employee_id, today, assignments, defaults[0]["id"] if defaults else None)
    schedule = _get_schedule(supabase, schedule_id) if schedule_id else None

    upcoming = supabase.table("holidays").select("*").gte("holiday_date", today.isoformat()) \
        .eq("is_day_off", True).order("holiday_date").limit(5).execute().data or []
    todays_holidays = [h for h in upcoming if str(h["holiday_date"])[:10] == today.isoformat()]
    plan = resolve_day(today, schedule, todays_holidays)

    return {
        "schedule": schedule,
        "today": {
            "working": plan.working,
            "reason": plan.reason,
            "start": plan.start.isoformat() if plan.start else None,
            "end": plan.end.isoformat() if plan.end else None,
            "holidays": list(plan.holidays),
        },
        "upcoming_holidays": upcoming if schedule is None or schedule.get("observes_holidays", True) else [],
    }
