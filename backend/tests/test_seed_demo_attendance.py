"""
The demo attendance seed (scripts/seed_demo_attendance.py): only September
and October 2026, re-runnable without duplicates, and every grid status
appears once it is applied.
"""

from datetime import date, datetime

import pytest

from app.services.attendance_month import (
    ABSENT, HOLIDAY, LEAVE, MISSING_CLOCK_OUT, NOT_TRACKED, PRESENT, REST, WORKED_OFF_DAY, build_month,
)
from app.services.work_calendar import COLOMBO
from scripts.seed_demo_attendance import (
    OutsideDemoWindow, Plan, assert_demo_window, plan_demo,
)
from tests.test_attendance_month import OFFICE, RESCUE

TODAY = date(2026, 11, 2)
NOW = datetime(2026, 11, 2, 10, 0, tzinfo=COLOMBO)
SEPT_1 = date(2026, 9, 1)
HOLIDAYS = [
    {"holiday_date": "2026-09-26", "name": "Binara Full Moon Poya Day", "is_day_off": True},
    {"holiday_date": "2026-10-25", "name": "Vap Full Moon Poya Day", "is_day_off": True},
]


def _people(n=8):
    return [{"id": i, "first_name": "Emp", "last_name": str(i), "status": "Active",
             "date_joined": "2024-01-01", "attendance_tracked_from": None} for i in range(1, n + 1)]


def _plan(employees=None, attendance=(), leave_days=(), assignments=(), tracking=SEPT_1):
    return plan_demo(employees or _people(), [OFFICE, RESCUE], list(assignments), HOLIDAYS,
                     list(attendance), list(leave_days), tracking, TODAY)


def test_only_september_and_october_are_planned():
    plan = _plan()
    dates = {r["target_date"] for r in plan.attendance} | {r["leave_date"] for r in plan.leave}
    assert dates and all("2026-09-01" <= d <= "2026-10-31" for d in dates)


def test_a_row_outside_the_window_is_refused():
    plan = Plan(attendance=[{"target_date": "2026-08-31", "clock_in": "2026-08-31T08:30:00+05:30"}])
    with pytest.raises(OutsideDemoWindow):
        assert_demo_window(plan)
    with pytest.raises(OutsideDemoWindow):
        assert_demo_window(Plan(leave=[{"employee_id": 1, "leave_date": "2026-07-15"}]))


def test_the_plan_is_the_same_every_time():
    assert _plan().attendance == _plan().attendance


def test_running_it_again_adds_nothing():
    first = _plan()
    again = _plan(attendance=first.attendance,
                  leave_days=[{"employee_id": r["employee_id"], "leave_date": r["leave_date"]} for r in first.leave])
    assert again.attendance == [] and again.leave == []
    assert again.skipped_existing == len(first.attendance) + len(first.leave)


def test_existing_records_and_leave_are_left_alone():
    real = {"employee_id": 1, "target_date": "2026-09-02"}
    leave = {"employee_id": 2, "leave_date": "2026-09-03"}
    plan = _plan(attendance=[real], leave_days=[leave])
    keys = {(r["employee_id"], r["target_date"]) for r in plan.attendance}
    assert (1, "2026-09-02") not in keys and (2, "2026-09-03") not in keys


def test_nobody_is_seeded_before_joining_or_before_their_tracked_from():
    people = _people(2)
    people[0]["date_joined"] = "2026-10-01"
    people[1]["attendance_tracked_from"] = "2026-10-12"
    plan = _plan(employees=people)
    assert min(r["target_date"] for r in plan.attendance if r["employee_id"] == 1) >= "2026-10-01"
    assert min(r["target_date"] for r in plan.attendance if r["employee_id"] == 2) >= "2026-10-12"


def test_rescue_staff_are_seeded_on_their_own_weekends():
    plan = _plan(assignments=[{"id": 1, "employee_id": 3, "schedule_id": 2, "effective_from": "2026-01-01"}])
    saturdays = {r["target_date"] for r in plan.attendance if r["employee_id"] == 3}
    assert "2026-09-05" in saturdays  # a Saturday on the rescue rota


def test_every_grid_status_appears():
    people = _people()
    plan = _plan(employees=people)
    leave_days = [{"employee_id": r["employee_id"], "leave_date": r["leave_date"], "fraction": 1,
                   "status": "Approved", "half_day": "none", "type_name": "Sick leave", "type_code": "SICK",
                   "paid": True} for r in plan.leave]
    seen, late, early = set(), 0, 0
    for month in (9, 10):
        result = build_month(2026, month, people, [OFFICE, RESCUE], [], HOLIDAYS, plan.attendance, leave_days,
                             today=TODAY, now=NOW, tracking_start=SEPT_1)
        for row in result["employees"]:
            for c in row["cells"]:
                seen.add(c["status"])
                late += c["late_minutes"] > 0
                early += c["left_early_minutes"] > 0
    assert {PRESENT, ABSENT, MISSING_CLOCK_OUT, LEAVE, HOLIDAY, REST, WORKED_OFF_DAY} <= seen
    assert late and early
    assert NOT_TRACKED not in seen
    # Mostly present: the deliberate absence is the only one.
    assert sum(c == "absent" for c in [s for _, _, s in plan.scenarios]) == 1


def test_august_shows_as_not_tracked_after_seeding():
    people = _people(1)
    plan = _plan(employees=people)
    result = build_month(2026, 8, people, [OFFICE], [], [], plan.attendance, [],
                         today=TODAY, now=NOW, tracking_start=SEPT_1)
    statuses = {c["status"] for c in result["employees"][0]["cells"]}
    assert statuses == {NOT_TRACKED}
