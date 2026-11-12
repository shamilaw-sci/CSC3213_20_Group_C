"""
The monthly attendance grid: what each employee's day was, and what needs
attention (attendance rework, step 3).

Pure, over rows already fetched: clock-ins (attendance_log), schedules and
holidays via resolve_day (step 1), and leave days (step 2). Nothing is stored;
month close (step 5) will freeze these statuses when a month is closed.

Days before a person's tracked-from date (the organisation's attendance
tracking start, or their own override) are NOT_TRACKED: nobody clocked in
then, so the grid does not judge them. They count towards no total except
leave, never need attention, and are never sent to payroll. Approved
full-day leave still shows as leave on those days, because leave is its own
record and no-pay leave is paid through payroll whatever the date
(confirmed 2026-11-02).

Rules (confirmed 2026-10-31):
  * Late: clocked in after the scheduled start plus the schedule's grace.
  * Left early: clocked out before the scheduled end minus the same grace.
  * No separate short-day flag; overtime is worked out with payroll.
  * A morning half day of leave moves the expected start to the middle of
    the scheduled day; an afternoon half day moves the expected end there.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from app.services.work_calendar import COLOMBO, DayPlan, resolve_day, schedule_for

# Statuses, in the order they are decided.
NOT_EMPLOYED = "not_employed"
NOT_TRACKED = "not_tracked"
UPCOMING = "upcoming"
LEAVE = "leave"
HOLIDAY = "holiday"
REST = "rest"
WORKED_OFF_DAY = "worked_off_day"
ABSENT = "absent"
MISSING_CLOCK_OUT = "missing_clock_out"
IN_PROGRESS = "in_progress"
PRESENT = "present"


def _parse_ts(value) -> Optional[datetime]:
    """A stored clock time as Colombo time. Naive values are taken as UTC,
    which is how Postgres stores a timestamptz written without an offset."""
    if not value:
        return None
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(COLOMBO)


def _minutes(delta: timedelta) -> int:
    return int(delta.total_seconds() // 60)


@dataclass
class LeaveOnDay:
    status: str                 # 'Approved' | 'Pending'
    type_name: str
    type_code: str
    fraction: float             # 1.0 or 0.5
    half_day: str = "none"      # 'am' | 'pm' when fraction is 0.5
    paid: bool = True


@dataclass
class DayCell:
    date: str
    status: str
    late_minutes: int = 0
    left_early_minutes: int = 0
    worked_minutes: int = 0
    expected_minutes: int = 0
    clock_in: Optional[str] = None      # Colombo, ISO
    clock_out: Optional[str] = None
    record_id: Optional[int] = None
    locked: bool = False
    expected_start: Optional[str] = None
    expected_end: Optional[str] = None
    schedule_name: Optional[str] = None
    holidays: list[str] = field(default_factory=list)
    leave: Optional[dict] = None        # approved leave on the day
    leave_pending: Optional[dict] = None  # a pending request covering the day
    reason: str = ""                     # one sentence explaining the status

    @property
    def needs_attention(self) -> bool:
        return self.status in (ABSENT, MISSING_CLOCK_OUT) or self.late_minutes > 0 or self.left_early_minutes > 0


def _expected_window(plan: DayPlan, half: Optional[LeaveOnDay]) -> tuple[Optional[datetime], Optional[datetime]]:
    start, end = plan.start, plan.end
    if start and end and half and half.fraction < 1:
        middle = start + (end - start) / 2
        if half.half_day == "am":
            start = middle
        elif half.half_day == "pm":
            end = middle
    return start, end


def day_cell(
    d: date,
    plan: DayPlan,
    record: Optional[dict],
    approved: Optional[LeaveOnDay],
    pending: Optional[LeaveOnDay],
    joined: Optional[date],
    today: date,
    now: datetime,
    tracked_from: Optional[date] = None,
) -> DayCell:
    """One employee-day. `now` is Colombo time, for days still in progress."""
    clock_in = _parse_ts(record.get("clock_in")) if record else None
    clock_out = _parse_ts(record.get("clock_out")) if record else None

    cell = DayCell(
        date=d.isoformat(),
        status=PRESENT,
        expected_minutes=plan.expected_minutes,
        clock_in=clock_in.isoformat() if clock_in else None,
        clock_out=clock_out.isoformat() if clock_out else None,
        record_id=record.get("id") if record else None,
        locked=bool(record.get("is_locked")) if record else False,
        schedule_name=plan.schedule_name,
        holidays=list(plan.holidays),
        leave=None if approved is None else vars(approved).copy(),
        leave_pending=None if pending is None else vars(pending).copy(),
    )
    if clock_in and clock_out:
        cell.worked_minutes = max(_minutes(clock_out - clock_in), 0)

    if joined and d < joined:
        cell.status, cell.reason = NOT_EMPLOYED, "Before their join date."
        return cell

    full_leave = approved is not None and approved.fraction >= 1
    half_leave = approved if approved is not None and approved.fraction < 1 else None

    if full_leave:
        cell.status, cell.reason = LEAVE, f"{approved.type_name}."
        return cell

    if tracked_from and d < tracked_from:
        cell.status, cell.reason = NOT_TRACKED, "Before attendance tracking started."
        return cell

    if not plan.working:
        if clock_in:
            cell.status = WORKED_OFF_DAY
            cell.reason = (f"Worked on a holiday ({', '.join(plan.holidays)})." if plan.reason == "holiday"
                           else "Worked on a rest day.")
        elif plan.reason == "holiday":
            cell.status, cell.reason = HOLIDAY, ", ".join(plan.holidays) + "."
        else:
            cell.status, cell.reason = REST, "Not a working day on their schedule."
        return cell

    start, end = _expected_window(plan, half_leave)
    cell.expected_start = start.isoformat() if start else None
    cell.expected_end = end.isoformat() if end else None
    if half_leave:
        cell.expected_minutes = max(plan.expected_minutes // 2, 0)

    if d > today:
        cell.status, cell.reason = UPCOMING, "Working day ahead."
        return cell

    if not clock_in:
        if d == today and start and now < start + timedelta(minutes=plan.grace_minutes):
            cell.status, cell.reason = UPCOMING, "Not due in yet."
            return cell
        cell.status = ABSENT
        cell.reason = ("No clock-in, and no approved leave"
                       + (f" ({pending.type_name} is awaiting a decision)." if pending else "."))
        if half_leave:
            cell.reason = f"{half_leave.type_name} for half the day, and no clock-in for the other half."
        return cell

    grace = timedelta(minutes=plan.grace_minutes)
    if start and clock_in > start + grace:
        cell.late_minutes = _minutes(clock_in - start)

    if not clock_out:
        if d == today:
            cell.status, cell.reason = IN_PROGRESS, "Clocked in, not out yet."
        else:
            cell.status, cell.reason = MISSING_CLOCK_OUT, "Clocked in but never clocked out."
        return cell

    if end and clock_out < end - grace:
        cell.left_early_minutes = _minutes(end - clock_out)

    parts = []
    if cell.late_minutes:
        parts.append(f"{cell.late_minutes} min late")
    if cell.left_early_minutes:
        parts.append(f"left {cell.left_early_minutes} min early")
    cell.status = PRESENT
    cell.reason = ("Present, " + " and ".join(parts) + ".") if parts else "Present."
    if half_leave:
        cell.reason = cell.reason[:-1] + f"; {half_leave.type_name.lower()} for the other half."
    return cell


# --------------------------------------------------------------------------
# The month
# --------------------------------------------------------------------------

def tracked_from_for(employee: dict, org_start: Optional[date]) -> Optional[date]:
    """The employee's override if set, otherwise the organisation's date."""
    own = employee.get("attendance_tracked_from")
    return date.fromisoformat(str(own)[:10]) if own else org_start


def month_has_tracked_days(year: int, month: int, tracked_from: list[Optional[date]]) -> bool:
    """
    Whether anyone is tracked on any day of the month. Month close (step 5)
    refuses a month where nobody is: with no overrides that is every month
    ending before the organisation's tracking start. A missing date means
    tracked throughout.
    """
    last = month_days(year, month)[-1]
    return any(t is None or t <= last for t in tracked_from)


def payable_absences(cells: list[dict]) -> list[str]:
    """
    The dates month close (step 5) may send to payroll as unpaid absences.
    Only ABSENT counts, so a not-tracked day can never be one.
    """
    return [c["date"] for c in cells if c["status"] == ABSENT]


def days_brought_into_tracking(old: Optional[date], new: date) -> Optional[tuple[date, date]]:
    """
    The span of days a change of tracked-from date starts tracking, as
    (first, last), or None when the change only stops tracking days (or
    changes nothing). `old` None means everything was already tracked.
    """
    if old is None or new >= old:
        return None
    return (new, old - timedelta(days=1))


def months_between(first: date, last: date) -> list[tuple[int, int]]:
    out, y, m = [], first.year, first.month
    while (y, m) <= (last.year, last.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def month_days(year: int, month: int) -> list[date]:
    first = date(year, month, 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return [first + timedelta(days=i) for i in range((nxt - first).days)]


ATTENTION_ORDER = {ABSENT: 0, MISSING_CLOCK_OUT: 1}


def build_month(
    year: int,
    month: int,
    employees: list[dict],
    schedules: list[dict],
    assignments: list[dict],
    holidays: list[dict],
    attendance: list[dict],
    leave_days: list[dict],
    today: date,
    now: datetime,
    tracking_start: Optional[date] = None,
) -> dict:
    """
    `leave_days` rows: {employee_id, leave_date, fraction, status, half_day,
    type_name, type_code, paid}, for Pending and Approved requests only.
    `tracking_start` is the organisation's date; an employee's
    `attendance_tracked_from` overrides it.
    """
    days = month_days(year, month)
    by_schedule = {s["id"]: s for s in schedules}
    default_id = next((s["id"] for s in schedules if s.get("is_default")), None)

    holidays_on: dict[str, list[dict]] = {}
    for h in holidays:
        holidays_on.setdefault(str(h["holiday_date"])[:10], []).append(h)

    records = {(a["employee_id"], str(a["target_date"])[:10]): a for a in attendance}
    approved: dict[tuple, LeaveOnDay] = {}
    pending: dict[tuple, LeaveOnDay] = {}
    for row in leave_days:
        key = (row["employee_id"], str(row["leave_date"])[:10])
        item = LeaveOnDay(status=row["status"], type_name=row.get("type_name") or "Leave",
                          type_code=row.get("type_code") or "", fraction=float(row["fraction"]),
                          half_day=row.get("half_day") or "none", paid=bool(row.get("paid", True)))
        (approved if row["status"] == "Approved" else pending)[key] = item

    out_employees, attention = [], []
    for e in employees:
        joined = date.fromisoformat(str(e["date_joined"])[:10]) if e.get("date_joined") else None
        tracked_from = tracked_from_for(e, tracking_start)
        cells = []
        totals = dict(present=0, absent=0, late=0, left_early=0, missing_clock_out=0,
                      leave_days=0.0, worked_off_days=0, worked_minutes=0, expected_minutes=0)
        name = f"{e.get('first_name', '')} {e.get('last_name', '')}".strip()

        for d in days:
            iso = d.isoformat()
            schedule = by_schedule.get(schedule_for(e["id"], d, assignments, default_id))
            plan = resolve_day(d, schedule, holidays_on.get(iso, []))
            cell = day_cell(d, plan, records.get((e["id"], iso)), approved.get((e["id"], iso)),
                            pending.get((e["id"], iso)), joined, today, now, tracked_from)
            cells.append(cell)

            if cell.leave and cell.status != NOT_EMPLOYED:
                totals["leave_days"] += cell.leave["fraction"]
            if cell.status in (NOT_TRACKED, NOT_EMPLOYED):
                continue

            if cell.status == PRESENT:
                totals["present"] += 1
            totals["absent"] += cell.status == ABSENT
            totals["missing_clock_out"] += cell.status == MISSING_CLOCK_OUT
            totals["late"] += cell.late_minutes > 0
            totals["left_early"] += cell.left_early_minutes > 0
            totals["worked_off_days"] += cell.status == WORKED_OFF_DAY
            totals["worked_minutes"] += cell.worked_minutes
            if cell.status != UPCOMING:
                totals["expected_minutes"] += cell.expected_minutes

            if cell.needs_attention:
                kinds = []
                if cell.status in (ABSENT, MISSING_CLOCK_OUT):
                    kinds.append(cell.status)
                if cell.late_minutes:
                    kinds.append("late")
                if cell.left_early_minutes:
                    kinds.append("left_early")
                attention.append({
                    "employee_id": e["id"], "employee_name": name, "date": iso,
                    "kinds": kinds, "reason": cell.reason,
                    "leave_pending": cell.leave_pending is not None,
                })
            elif cell.status == WORKED_OFF_DAY:
                attention.append({
                    "employee_id": e["id"], "employee_name": name, "date": iso,
                    "kinds": ["worked_off_day"], "reason": cell.reason, "leave_pending": False,
                    "info": True,  # for overtime / lieu leave later, not a problem
                })

        out_employees.append({
            "employee_id": e["id"],
            "employee_name": name,
            "status": e.get("status"),
            "date_joined": e.get("date_joined"),
            "tracked_from": tracked_from.isoformat() if tracked_from else None,
            "tracking_overridden": bool(e.get("attendance_tracked_from")),
            "cells": [vars(c) for c in cells],
            "totals": totals,
        })

    # Problems before information, then oldest first: the oldest gap is the
    # one most likely to be forgotten.
    attention.sort(key=lambda a: (a.get("info", False), a["date"], a["employee_name"]))

    return {
        "year": year,
        "month": month,
        "days": [{
            "date": d.isoformat(),
            "weekday": d.isoweekday(),
            "holidays": [h["name"] for h in holidays_on.get(d.isoformat(), []) if h.get("is_day_off")],
        } for d in days],
        "employees": out_employees,
        "attention": attention,
        "today": today.isoformat(),
        "tracking_start_date": tracking_start.isoformat() if tracking_start else None,
    }
