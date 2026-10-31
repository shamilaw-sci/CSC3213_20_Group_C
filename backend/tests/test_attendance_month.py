"""The monthly attendance grid (attendance rework, step 3).

Every status and flag, decided by day_cell() against a schedule from step 1
and leave from step 2. Times are written in Sri Lanka time and stored as UTC,
as self-service clock-in stores them.
"""

import os
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.permissions import has_permission
from app.core.supabase import get_supabase
from app.main import app
from app.services.attendance_month import (
    ABSENT, HOLIDAY, IN_PROGRESS, LEAVE, MISSING_CLOCK_OUT, NOT_EMPLOYED, PRESENT, REST, UPCOMING,
    WORKED_OFF_DAY, LeaveOnDay, build_month, day_cell,
)
from app.services.work_calendar import COLOMBO, resolve_day
from tests.test_ledger_integrity import _RecordingSupabase
from tests.test_rbac_matrix import ALL_ROLES, OTHER_USER_ID, _request, acting_as

OFFICE = {"id": 1, "name": "Office hours", "is_default": True, "grace_minutes": 15, "observes_holidays": True,
          "days": [{"weekday": w, "start_time": "08:30:00", "end_time": "17:00:00", "break_minutes": 60} for w in range(1, 6)]}
RESCUE = {"id": 2, "name": "Rescue rota", "is_default": False, "grace_minutes": 15, "observes_holidays": False,
          "days": [{"weekday": w, "start_time": "07:00:00", "end_time": "15:00:00", "break_minutes": 30} for w in range(1, 8)]}
POYA = {"holiday_date": "2026-11-24", "name": "Il Full Moon Poya Day", "is_day_off": True}

WED = date(2026, 10, 28)
TODAY = date(2026, 10, 30)                      # Friday
NOW = datetime(2026, 10, 30, 11, 0, tzinfo=COLOMBO)


def at(d: date, hh: int, mm: int = 0) -> str:
    """A Sri Lanka clock time, stored as UTC like the database returns it."""
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=COLOMBO).astimezone(timezone.utc).isoformat()


def rec(d, start=None, end=None, locked=False):
    return {"id": 5, "employee_id": 7, "target_date": d.isoformat(),
            "clock_in": at(d, *start) if start else None, "clock_out": at(d, *end) if end else None,
            "is_locked": locked}


def cell(d, record=None, approved=None, pending=None, schedule=OFFICE, holidays=(), joined=date(2020, 1, 1),
         today=TODAY, now=NOW):
    return day_cell(d, resolve_day(d, schedule, list(holidays)), record, approved, pending, joined, today, now)


ANNUAL = LeaveOnDay(status="Approved", type_name="Annual leave", type_code="ANNUAL", fraction=1.0)
HALF_AM = LeaveOnDay(status="Approved", type_name="Casual leave", type_code="CASUAL", fraction=0.5, half_day="am")
HALF_PM = LeaveOnDay(status="Approved", type_name="Casual leave", type_code="CASUAL", fraction=0.5, half_day="pm")
PENDING = LeaveOnDay(status="Pending", type_name="Sick leave", type_code="SICK", fraction=1.0)


# --------------------------------------------------------------------------
# Present, late, left early
# --------------------------------------------------------------------------

def test_on_time_is_present():
    c = cell(WED, rec(WED, (8, 30), (17, 0)))
    assert (c.status, c.late_minutes, c.left_early_minutes) == (PRESENT, 0, 0)
    assert c.worked_minutes == 510 and c.expected_minutes == 450


def test_within_grace_is_not_late():
    assert cell(WED, rec(WED, (8, 45), (17, 0))).late_minutes == 0


def test_past_grace_is_late_by_minutes_from_the_scheduled_start():
    c = cell(WED, rec(WED, (8, 46), (17, 0)))
    assert c.status == PRESENT and c.late_minutes == 16
    assert c.needs_attention and "16 min late" in c.reason


def test_left_early_uses_the_same_grace():
    assert cell(WED, rec(WED, (8, 30), (16, 45))).left_early_minutes == 0
    c = cell(WED, rec(WED, (8, 30), (16, 44)))
    assert c.left_early_minutes == 16 and c.needs_attention


def test_late_and_left_early_together():
    c = cell(WED, rec(WED, (9, 30), (16, 0)))
    assert (c.late_minutes, c.left_early_minutes) == (60, 60)
    assert "60 min late and left 60 min early" in c.reason


# --------------------------------------------------------------------------
# Absent, missing clock-out, today
# --------------------------------------------------------------------------

def test_no_clock_in_on_a_working_day_is_absent():
    c = cell(WED)
    assert c.status == ABSENT and c.needs_attention


def test_absent_with_a_pending_request_says_so():
    c = cell(WED, pending=PENDING)
    assert c.status == ABSENT and "awaiting a decision" in c.reason


def test_a_past_day_with_no_clock_out_is_missing_clock_out():
    c = cell(WED, rec(WED, (8, 30)))
    assert c.status == MISSING_CLOCK_OUT and c.needs_attention


def test_today_clocked_in_is_in_progress_not_missing():
    assert cell(TODAY, rec(TODAY, (8, 30))).status == IN_PROGRESS


def test_today_before_the_grace_runs_out_is_not_absent_yet():
    early = datetime(2026, 10, 30, 8, 40, tzinfo=COLOMBO)
    assert cell(TODAY, now=early).status == UPCOMING
    assert cell(TODAY, now=NOW).status == ABSENT


def test_future_working_days_are_upcoming():
    assert cell(date(2026, 11, 2)).status == UPCOMING


# --------------------------------------------------------------------------
# Days off, leave, holidays
# --------------------------------------------------------------------------

def test_weekend_is_a_rest_day():
    assert cell(date(2026, 10, 31), today=date(2026, 11, 2)).status == REST


def test_poya_is_a_holiday_for_the_office():
    c = cell(date(2026, 11, 24), holidays=[POYA], today=date(2026, 11, 30))
    assert c.status == HOLIDAY and "Il Full Moon Poya Day" in c.reason


def test_rescue_staff_working_a_poya_is_an_ordinary_working_day():
    d = date(2026, 11, 24)
    c = cell(d, rec(d, (7, 0), (15, 0)), schedule=RESCUE, holidays=[POYA], today=date(2026, 11, 30))
    assert c.status == PRESENT and c.holidays == ["Il Full Moon Poya Day"]


def test_office_staff_clocking_in_on_a_rest_day_is_flagged_as_worked_off_day():
    d = date(2026, 10, 31)
    c = cell(d, rec(d, (9, 0), (13, 0)), today=date(2026, 11, 2))
    assert c.status == WORKED_OFF_DAY and not c.needs_attention


def test_approved_leave_is_leave_not_absent():
    c = cell(WED, approved=ANNUAL)
    assert c.status == LEAVE and not c.needs_attention


def test_morning_half_day_moves_the_expected_start_to_midday():
    # 08:30-17:00: midday is 12:45. Arriving 12:50 is within grace.
    c = cell(WED, rec(WED, (12, 50), (17, 0)), approved=HALF_AM)
    assert c.status == PRESENT and c.late_minutes == 0
    assert "casual leave for the other half" in c.reason
    assert c.expected_minutes == 225


def test_afternoon_half_day_moves_the_expected_end_to_midday():
    c = cell(WED, rec(WED, (8, 30), (12, 45)), approved=HALF_PM)
    assert c.left_early_minutes == 0


def test_half_day_leave_with_no_clock_in_is_absent_for_the_other_half():
    c = cell(WED, approved=HALF_AM)
    assert c.status == ABSENT and "other half" in c.reason


def test_before_the_join_date_is_not_employed():
    assert cell(WED, joined=date(2026, 10, 29)).status == NOT_EMPLOYED


# --------------------------------------------------------------------------
# The month
# --------------------------------------------------------------------------

def _month(attendance, leave_days=()):
    employees = [{"id": 7, "first_name": "Amal", "last_name": "Silva", "status": "Active", "date_joined": "2020-01-01"}]
    return build_month(2026, 10, employees, [OFFICE], [], [], attendance, list(leave_days), today=TODAY, now=NOW)


def test_month_has_every_day_and_totals():
    result = _month([rec(WED, (9, 0), (17, 0))])
    assert len(result["days"]) == 31
    (row,) = result["employees"]
    t = row["totals"]
    assert t["present"] == 1 and t["late"] == 1
    # October 2026 has 22 weekdays, all on or before today (the 30th, at
    # 11:00, past the grace): one present, so 21 absent.
    assert t["absent"] == 21


def test_attention_lists_problems_oldest_first_and_info_last():
    result = _month(
        [rec(date(2026, 10, 27), (8, 30)), rec(date(2026, 10, 31), (9, 0), (12, 0))],
    )
    kinds = [(a["date"], tuple(a["kinds"])) for a in result["attention"]]
    assert kinds[0] == ("2026-10-01", ("absent",))
    assert ("2026-10-27", ("missing_clock_out",)) in kinds
    assert kinds[-1] == ("2026-10-31", ("worked_off_day",))


def test_leave_days_count_into_totals():
    leave = [{"employee_id": 7, "leave_date": "2026-10-28", "fraction": 1, "status": "Approved",
              "half_day": "none", "type_name": "Annual leave", "type_code": "ANNUAL", "paid": True}]
    (row,) = _month([], leave)["employees"]
    cell_28 = next(c for c in row["cells"] if c["date"] == "2026-10-28")
    assert cell_28["status"] == LEAVE and row["totals"]["leave_days"] == 1.0


# --------------------------------------------------------------------------
# Endpoints and who may see them
# --------------------------------------------------------------------------

def _db():
    return _RecordingSupabase({
        "employee_profile": {"select": [
            {"id": 7, "first_name": "Amal", "last_name": "Silva", "status": "Active", "date_joined": "2020-01-01", "user_id": OTHER_USER_ID},
            {"id": 8, "first_name": "Nimmi", "last_name": "Perera", "status": "Active", "date_joined": "2020-01-01", "user_id": "someone-else"},
        ]},
        "attendance_log": {"select": []},
        "work_schedules": {"select": [OFFICE]},
        "employee_schedule_assignments": {"select": []},
        "holidays": {"select": []},
        "leave_requests": {"select": []},
        "leave_request_days": {"select": []},
    })


@pytest.mark.parametrize("role", ALL_ROLES)
def test_grid_needs_attendance_manage_or_read(role):
    with acting_as(role):
        app.dependency_overrides[get_supabase] = lambda: _db()
        status = _request("GET", "/api/hr/attendance/month?year=2026&month=10").status_code
    allowed = has_permission(role, "hr:attendance:manage") or has_permission(role, "hr:attendance:read")
    assert (status != 403) == allowed, (role, status)


def test_director_reads_the_grid_but_cannot_edit():
    assert has_permission("Director", "hr:attendance:read")
    assert not has_permission("Director", "hr:attendance:manage")


def test_my_month_returns_only_my_row():
    with acting_as("General Staff", user_id=OTHER_USER_ID):
        app.dependency_overrides[get_supabase] = lambda: _db()
        body = _request("GET", "/api/hr/attendance/me/month?year=2026&month=10").json()
    assert body["employee"]["employee_name"] == "Amal Silva"
    assert {e["employee_id"] for e in body["employees"]} == {7}


def test_impossible_month_is_rejected():
    with acting_as("HR Officer"):
        app.dependency_overrides[get_supabase] = lambda: _db()
        assert _request("GET", "/api/hr/attendance/month?year=2026&month=13").status_code == 400
