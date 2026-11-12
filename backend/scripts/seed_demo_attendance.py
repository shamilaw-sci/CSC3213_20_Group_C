"""
DEMO DATA ONLY: realistic attendance for September and October 2026.

Not part of the application and never run by it. It exists so the monthly
attendance grid can be demonstrated with every status on it, after the
attendance tracking start date has been set to 1 September 2026.

What it writes, for each active employee, on each working day of their own
schedule in September and October 2026:
  * mostly on-time clock-ins and clock-outs, with a few minutes' jitter
  * a few late arrivals and early departures, at random but repeatably
  * one day each of: late, genuine absence (no record, no leave), left
    early, late and left early, missing clock-out, approved sick leave,
    and a Saturday worked off-schedule
Weekends and holidays come from the schedules and the holiday calendar, so
rest days and Poya days show as they really are.

Safety:
  * Dry run by default: prints the plan and writes nothing. --apply writes.
  * Only dates from 2026-09-01 to 2026-10-31 are ever written; every row is
    checked against that window before anything is sent. July and August
    (approved payroll) are never touched.
  * Refuses to run if payroll for September or October 2026 is approved, or
    if the tracking start date is missing or later than 1 September 2026.
  * Re-runnable: a day that already has an attendance record or leave is
    left alone, so running it twice adds nothing the second time. Choices
    are seeded from the employee and the date, so a re-run plans the same.
  * Demo leave requests carry "[DEMO]" in their reason and decision note.

Usage, from backend/:
  python scripts/seed_demo_attendance.py            # dry run
  python scripts/seed_demo_attendance.py --apply    # write
"""

import argparse
import os
import random
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.attendance_month import tracked_from_for  # noqa: E402
from app.services.work_calendar import COLOMBO, DayPlan, resolve_day, schedule_for  # noqa: E402

DEMO_FIRST = date(2026, 9, 1)
DEMO_LAST = date(2026, 10, 31)
DEMO_MONTHS = ((2026, 9), (2026, 10))
TAG = "[DEMO] Seeded by scripts/seed_demo_attendance.py"

# One of each, handed to employees in turn. Each lands on the employee's
# first working day on or after the target date.
SCENARIOS = (
    (date(2026, 9, 8), "late"),
    (date(2026, 9, 17), "absent"),
    (date(2026, 9, 24), "left_early"),
    (date(2026, 10, 1), "late_and_early"),
    (date(2026, 10, 8), "missing_clock_out"),
    (date(2026, 10, 15), "leave"),
)
# A Saturday: given to the first employee for whom it is not a working day.
WORKED_OFF_DAY = date(2026, 10, 10)

RANDOM_LATE = 0.05    # share of ordinary days with a late arrival
RANDOM_EARLY = 0.03   # and with an early departure


class OutsideDemoWindow(ValueError):
    pass


@dataclass
class Plan:
    attendance: list[dict] = field(default_factory=list)
    leave: list[dict] = field(default_factory=list)          # {employee_id, leave_date}
    scenarios: list[tuple[int, str, str]] = field(default_factory=list)  # (employee_id, date, kind)
    kinds: dict[int, Counter] = field(default_factory=dict)
    skipped_existing: int = 0
    notes: list[str] = field(default_factory=list)


def assert_demo_window(plan: Plan) -> None:
    """Every date in the plan lies in September or October 2026."""
    dates = [r["target_date"] for r in plan.attendance] + [r["leave_date"] for r in plan.leave]
    for iso in dates:
        d = date.fromisoformat(iso)
        if not DEMO_FIRST <= d <= DEMO_LAST:
            raise OutsideDemoWindow(f"Refusing to write {iso}: outside September and October 2026.")
    for r in plan.attendance:
        for key in ("clock_in", "clock_out"):
            if r.get(key) and not r[key].startswith(("2026-09", "2026-10", "2026-11-01")):
                raise OutsideDemoWindow(f"Refusing to write {r[key]}: outside September and October 2026.")


def _days():
    d = DEMO_FIRST
    while d <= DEMO_LAST:
        yield d
        d += timedelta(days=1)


def _row(employee_id: int, d: date, clock_in: datetime, clock_out: Optional[datetime]) -> dict:
    hours = round((clock_out - clock_in).total_seconds() / 3600, 2) if clock_out else None
    return {
        "employee_id": employee_id,
        "target_date": d.isoformat(),
        "clock_in": clock_in.isoformat(),
        "clock_out": clock_out.isoformat() if clock_out else None,
        "worked_hours": hours,
        "is_locked": False,
    }


def plan_demo(
    employees: list[dict],
    schedules: list[dict],
    assignments: list[dict],
    holidays: list[dict],
    existing_attendance: list[dict],
    existing_leave_days: list[dict],
    tracking_start: Optional[date],
    today: date,
) -> Plan:
    """
    Pure: decides every row from what is already there. `existing_leave_days`
    are {employee_id, leave_date} for Pending and Approved requests.
    """
    plan = Plan()
    by_schedule = {s["id"]: s for s in schedules}
    default_id = next((s["id"] for s in schedules if s.get("is_default")), None)
    holidays_on: dict[str, list[dict]] = {}
    for h in holidays:
        holidays_on.setdefault(str(h["holiday_date"])[:10], []).append(h)
    have_record = {(a["employee_id"], str(a["target_date"])[:10]) for a in existing_attendance}
    have_leave = {(r["employee_id"], str(r["leave_date"])[:10]) for r in existing_leave_days}

    people = sorted((e for e in employees if (e.get("status") or "Active") == "Active"), key=lambda e: e["id"])
    if not people:
        plan.notes.append("No active employees: nothing to seed.")
        return plan

    def day_plan(e: dict, d: date) -> DayPlan:
        schedule = by_schedule.get(schedule_for(e["id"], d, assignments, default_id))
        return resolve_day(d, schedule, holidays_on.get(d.isoformat(), []))

    def eligible(e: dict, d: date) -> bool:
        joined = date.fromisoformat(str(e["date_joined"])[:10]) if e.get("date_joined") else None
        tracked = tracked_from_for(e, tracking_start)
        return (DEMO_FIRST <= d <= DEMO_LAST and d < today
                and (joined is None or d >= joined) and (tracked is None or d >= tracked))

    def first_working(e: dict, target: date) -> Optional[date]:
        d = target
        while d <= DEMO_LAST:
            if eligible(e, d) and day_plan(e, d).working:
                return d
            d += timedelta(days=1)
        return None

    # Scenario days depend only on schedules, never on what is already
    # stored, so a re-run picks the same days and finds them filled.
    special: dict[tuple[int, str], str] = {}
    for i, (target, kind) in enumerate(SCENARIOS):
        e = people[i % len(people)]
        d = first_working(e, target)
        if d is None or (e["id"], d.isoformat()) in special:
            plan.notes.append(f"No working day for the '{kind}' example; it was left out.")
            continue
        special[(e["id"], d.isoformat())] = kind
    start = len(SCENARIOS) % len(people)
    for e in people[start:] + people[:start]:
        if eligible(e, WORKED_OFF_DAY) and not day_plan(e, WORKED_OFF_DAY).working:
            special[(e["id"], WORKED_OFF_DAY.isoformat())] = "worked_off_day"
            break
    else:
        plan.notes.append("Everyone works on 10 October, so the 'worked a day off' example was left out.")

    for e in people:
        kinds = plan.kinds.setdefault(e["id"], Counter())
        for d in _days():
            if not eligible(e, d):
                continue
            iso = d.isoformat()
            key = (e["id"], iso)
            kind = special.get(key)
            p = day_plan(e, d)
            if not p.working and kind != "worked_off_day":
                continue
            if key in have_record or key in have_leave:
                plan.skipped_existing += 1
                if kind:
                    plan.notes.append(f"Employee {e['id']} already has a record or leave on {iso}; "
                                      f"the '{kind}' example there was left as it is.")
                continue
            if kind:
                plan.scenarios.append((e["id"], iso, kind))

            if kind == "absent":
                kinds["absent"] += 1
                continue
            if kind == "leave":
                plan.leave.append({"employee_id": e["id"], "leave_date": iso})
                kinds["leave"] += 1
                continue

            rng = random.Random(f"vff-demo:{e['id']}:{iso}")
            if kind == "worked_off_day":
                clock_in = datetime.combine(d, datetime.min.time(), COLOMBO) + timedelta(hours=9, minutes=rng.randint(0, 10))
                plan.attendance.append(_row(e["id"], d, clock_in, clock_in + timedelta(hours=4)))
                kinds["worked_off_day"] += 1
                continue

            grace = p.grace_minutes
            clock_in = p.start + timedelta(minutes=rng.randint(-15, min(8, max(grace - 1, 0))))
            clock_out: Optional[datetime] = p.end + timedelta(minutes=rng.randint(0, 25))
            label = "present"
            if kind == "late":
                clock_in, label = p.start + timedelta(minutes=grace + 20), "late"
            elif kind == "left_early":
                clock_out, label = p.end - timedelta(minutes=grace + 60), "left_early"
            elif kind == "late_and_early":
                clock_in = p.start + timedelta(minutes=grace + 10)
                clock_out, label = p.end - timedelta(minutes=grace + 25), "late_and_early"
            elif kind == "missing_clock_out":
                clock_out, label = None, "missing_clock_out"
            else:
                roll = rng.random()
                if roll < RANDOM_LATE:
                    clock_in, label = p.start + timedelta(minutes=rng.randint(grace + 5, grace + 45)), "late"
                elif roll < RANDOM_LATE + RANDOM_EARLY:
                    clock_out, label = p.end - timedelta(minutes=rng.randint(grace + 10, grace + 80)), "left_early"
            plan.attendance.append(_row(e["id"], d, clock_in, clock_out))
            kinds[label] += 1

    assert_demo_window(plan)
    return plan


# --------------------------------------------------------------------------
# Running it
# --------------------------------------------------------------------------

def _fail(message: str) -> None:
    print(f"\nREFUSED: {message}")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="DEMO DATA ONLY: seed September and October 2026 attendance.")
    parser.add_argument("--apply", action="store_true", help="write the rows (default: dry run, writes nothing)")
    args = parser.parse_args()

    from dotenv import load_dotenv
    from supabase import create_client

    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        _fail("SUPABASE_URL and SUPABASE_KEY must be set (backend/.env).")
    db = create_client(url, key)

    print("=" * 72)
    print("DEMO DATA ONLY: attendance for September and October 2026")
    print("Mode:", "APPLY (writing)" if args.apply else "DRY RUN (nothing is written)")
    print("=" * 72)

    try:
        settings = db.table("attendance_settings").select("tracking_start_date").eq("id", 1).execute().data or []
    except Exception:
        settings = []
    if not settings:
        _fail("No attendance tracking start date. Apply migration 012 and set the date to 1 September 2026 first.")
    tracking_start = date.fromisoformat(str(settings[0]["tracking_start_date"])[:10])
    if tracking_start > DEMO_FIRST:
        _fail(f"Tracking starts {tracking_start}, after 1 September 2026, so the seeded days would show as "
              f"Not tracked. Set the tracking date to 1 September 2026 first.")
    print(f"Tracking start date: {tracking_start}")

    runs = db.table("payroll_runs").select("payroll_month, payroll_year, status").eq("payroll_year", 2026).execute().data or []
    for r in runs:
        if (r["payroll_year"], r["payroll_month"]) in DEMO_MONTHS and r.get("status") == "Approved":
            _fail(f"Payroll for {r['payroll_month']}/2026 is approved; its attendance must not change.")
        if (r["payroll_year"], r["payroll_month"]) in DEMO_MONTHS:
            print(f"Note: payroll for {r['payroll_month']}/2026 is a Draft. Pay is a fixed salary, so it is unaffected.")

    first, last = DEMO_FIRST.isoformat(), DEMO_LAST.isoformat()
    employees = db.table("employee_profile") \
        .select("id, first_name, last_name, status, date_joined, attendance_tracked_from").execute().data or []
    schedules = db.table("work_schedules").select("*, days:work_schedule_days(*)").execute().data or []
    if not any(s.get("is_default") for s in schedules):
        _fail("No default work schedule. Set one on the Schedules page first.")
    assignments = db.table("employee_schedule_assignments").select("*").execute().data or []
    holidays = db.table("holidays").select("holiday_date, name, is_day_off") \
        .gte("holiday_date", first).lte("holiday_date", last).execute().data or []
    attendance = db.table("attendance_log").select("employee_id, target_date") \
        .gte("target_date", first).lte("target_date", last).execute().data or []
    requests = db.table("leave_requests").select("id, employee_id, status") \
        .in_("status", ["Pending", "Approved"]).lte("start_date", last).gte("end_date", first).execute().data or []
    owner = {r["id"]: r["employee_id"] for r in requests}
    leave_days = []
    if owner:
        rows = db.table("leave_request_days").select("request_id, leave_date").in_("request_id", list(owner)).execute().data or []
        leave_days = [{"employee_id": owner[r["request_id"]], "leave_date": r["leave_date"]} for r in rows]

    sick = db.table("leave_types").select("id").eq("code", "SICK").execute().data or []
    if not sick:
        _fail("No SICK leave type. Apply migration 009 first.")

    plan = plan_demo(employees, schedules, assignments, holidays, attendance, leave_days,
                     tracking_start, today=datetime.now(COLOMBO).date())

    names = {e["id"]: f"{e.get('first_name', '')} {e.get('last_name', '')}".strip() for e in employees}
    print(f"\nHolidays in the window: {', '.join(sorted({h['name'] for h in holidays})) or 'none'}")
    if not holidays:
        print("  (Import the 2026 holidays on the Schedules page for Poya days to show as H.)")
    print(f"\n{'Employee':<28}{'present':>8}{'late':>6}{'early':>7}{'L+E':>5}{'noOut':>7}{'absent':>8}{'leave':>7}{'W':>4}")
    for eid, c in plan.kinds.items():
        if not sum(c.values()):
            continue
        print(f"{names.get(eid, eid):<28}{c['present']:>8}{c['late']:>6}{c['left_early']:>7}{c['late_and_early']:>5}"
              f"{c['missing_clock_out']:>7}{c['absent']:>8}{c['leave']:>7}{c['worked_off_day']:>4}")
    print("\nExamples placed:")
    for eid, iso, kind in plan.scenarios:
        print(f"  {iso}  {kind:<18} {names.get(eid, eid)}")
    for note in plan.notes:
        print(f"Note: {note}")
    print(f"\nAttendance rows to add: {len(plan.attendance)}")
    print(f"Approved leave requests to add: {len(plan.leave)}")
    print(f"Days left alone because a record or leave already exists: {plan.skipped_existing}")

    if not args.apply:
        print("\nDry run: nothing was written. Re-run with --apply to write.")
        return

    assert_demo_window(plan)
    for i in range(0, len(plan.attendance), 200):
        db.table("attendance_log").insert(plan.attendance[i:i + 200]).execute()
    for item in plan.leave:
        request = db.table("leave_requests").insert({
            "employee_id": item["employee_id"],
            "leave_type_id": sick[0]["id"],
            "start_date": item["leave_date"],
            "end_date": item["leave_date"],
            "half_day": "none",
            "days": 1,
            "reason": TAG,
            "status": "Approved",
            "decided_at": datetime.now(COLOMBO).isoformat(),
            "decision_note": TAG,
        }).execute().data
        try:
            db.table("leave_request_days").insert(
                {"request_id": request[0]["id"], "leave_date": item["leave_date"], "fraction": 1.0}).execute()
        except Exception:
            # A request without its day would never show; take it back.
            db.table("leave_requests").delete().eq("id", request[0]["id"]).execute()
            raise
    print(f"\nWritten: {len(plan.attendance)} attendance rows, {len(plan.leave)} leave requests.")


if __name__ == "__main__":
    main()
