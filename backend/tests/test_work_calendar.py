"""Work schedules and the holiday calendar (attendance rework, step 1).

The pure rules run against the real gazette files in db/holidays, so a
transcription mistake there fails here too.
"""

import os
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.permissions import has_permission
from app.core.supabase import get_supabase
from app.main import app
from app.services.work_calendar import (
    COLOMBO,
    full_moons,
    is_poya,
    load_holiday_file,
    poya_warnings,
    resolve_day,
    schedule_for,
    vff_day_off,
)
from tests.test_ledger_integrity import _RecordingSupabase
from tests.test_rbac_matrix import ALL_ROLES, _request, acting_as


def _days(weekdays, start="08:30:00", end="17:00:00", brk=60):
    return [{"weekday": w, "start_time": start, "end_time": end, "break_minutes": brk} for w in weekdays]


OFFICE = {"id": 1, "name": "Office hours", "is_default": True, "grace_minutes": 15,
          "observes_holidays": True, "days": _days(range(1, 6))}
RESCUE = {"id": 2, "name": "Rescue rota", "is_default": False, "grace_minutes": 15,
          "observes_holidays": False, "days": _days([3, 4, 5, 6, 7], "07:00:00", "15:00:00", 30)}
NIGHT = {"id": 3, "name": "Night clinic", "is_default": False, "grace_minutes": 10,
         "observes_holidays": True, "days": _days([1], "20:00:00", "04:00:00", 0)}

POYA = {"name": "Il Full Moon Poya Day", "is_day_off": True}           # Tue 24 Nov 2026
GOOD_FRIDAY = {"name": "Good Friday", "is_day_off": False}             # Fri 3 Apr 2026


# --------------------------------------------------------------------------
# Holiday policy and the gazette files
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name, expected", [
    ("Duruthu Full Moon Poya Day", True),
    ("Adhi Poson Full Moon Poya Day", True),
    ("Day Following Vesak Full Moon Poya Day", False),   # mercantile in its own right
    ("Independence Day", False),
])
def test_is_poya(name, expected):
    assert is_poya(name) is expected


def test_day_off_policy_is_mercantile_plus_poya():
    assert vff_day_off(is_mercantile=True, poya=False)
    assert vff_day_off(is_mercantile=False, poya=True)
    assert not vff_day_off(is_mercantile=False, poya=False)   # e.g. Good Friday


@pytest.mark.parametrize("year, rows, poya, mercantile, days_off", [
    (2026, 26, 13, 8, 21),   # Adhi Poson makes 13 Poya days
    (2027, 25, 12, 8, 20),
])
def test_gazette_files(year, rows, poya, mercantile, days_off):
    data = load_holiday_file(year)
    assert len(data) == rows
    assert sum(r["is_poya"] for r in data) == poya
    assert sum(r["is_mercantile"] for r in data) == mercantile
    assert sum(r["is_day_off"] for r in data) == days_off
    assert all(r["is_public"] and r["is_bank"] for r in data)   # the gazette marks every row both


def test_poya_days_are_never_mercantile_and_always_off():
    for year in (2026, 2027):
        for r in load_holiday_file(year):
            if r["is_poya"]:
                assert not r["is_mercantile"] and r["is_day_off"], r


def test_other_public_holidays_are_working_days():
    good_friday = next(r for r in load_holiday_file(2026) if r["name"] == "Good Friday")
    assert not good_friday["is_day_off"]


def test_missing_year_says_how_to_add_it():
    with pytest.raises(FileNotFoundError, match="gazette"):
        load_holiday_file(2031)


# --------------------------------------------------------------------------
# Full-moon cross-check
# --------------------------------------------------------------------------

def test_full_moon_calculation_is_accurate():
    # Published: 3 Jan 2026, 10:03 UTC.
    moon = min(full_moons(2026), key=lambda m: abs(m - datetime(2026, 1, 3, 10, 3, tzinfo=timezone.utc)))
    assert abs(moon - datetime(2026, 1, 3, 10, 3, tzinfo=timezone.utc)) < timedelta(minutes=30)


@pytest.mark.parametrize("year", [2026, 2027])
def test_every_gazette_poya_is_within_a_day_of_a_full_moon(year):
    assert poya_warnings(load_holiday_file(year)) == []


def test_a_mistyped_poya_is_flagged():
    typo = [{"holiday_date": "2026-11-14", "name": "Il Full Moon Poya Day", "is_poya": True}]
    (warning,) = poya_warnings(typo)
    assert "2026-11-14" in warning


# --------------------------------------------------------------------------
# Which schedule applies
# --------------------------------------------------------------------------

ASSIGNMENTS = [
    {"employee_id": 7, "schedule_id": 2, "effective_from": "2026-11-01"},
    {"employee_id": 7, "schedule_id": 3, "effective_from": "2027-01-01"},
    {"employee_id": 8, "schedule_id": 2, "effective_from": "2026-06-01"},
]


@pytest.mark.parametrize("employee, on, expected", [
    (7, date(2026, 10, 31), 1),   # before any assignment: the default
    (7, date(2026, 11, 1), 2),    # effective that day
    (7, date(2026, 12, 31), 2),
    (7, date(2027, 1, 5), 3),     # the later assignment wins
    (9, date(2026, 11, 5), 1),    # never assigned
])
def test_schedule_for(employee, on, expected):
    assert schedule_for(employee, on, ASSIGNMENTS, default_schedule_id=1) == expected


# --------------------------------------------------------------------------
# Resolving a day
# --------------------------------------------------------------------------

def test_office_weekday():
    plan = resolve_day(date(2026, 10, 28), OFFICE, [])   # Wednesday
    assert plan.working and plan.reason == "scheduled"
    assert plan.start == datetime(2026, 10, 28, 8, 30, tzinfo=COLOMBO)
    assert plan.end == datetime(2026, 10, 28, 17, 0, tzinfo=COLOMBO)
    assert plan.expected_minutes == 450                     # 8.5 h less a 1 h break
    assert plan.late_after == datetime(2026, 10, 28, 8, 45, tzinfo=COLOMBO)


def test_office_weekend_is_a_rest_day():
    plan = resolve_day(date(2026, 10, 31), OFFICE, [])   # Saturday
    assert not plan.working and plan.reason == "rest_day"


def test_poya_is_a_holiday_for_the_office():
    plan = resolve_day(date(2026, 11, 24), OFFICE, [POYA])
    assert not plan.working and plan.reason == "holiday"
    assert plan.holidays == ("Il Full Moon Poya Day",)


def test_rescue_rota_works_through_poya_but_knows_it_is_one():
    plan = resolve_day(date(2026, 11, 25), RESCUE, [POYA])   # Wednesday, a rota day
    assert plan.working and plan.reason == "scheduled"
    assert plan.holidays == ("Il Full Moon Poya Day",)       # kept for holiday pay later


def test_a_public_holiday_that_is_not_a_day_off_is_a_working_day():
    plan = resolve_day(date(2026, 4, 3), OFFICE, [GOOD_FRIDAY])
    assert plan.working and plan.holidays == ()


def test_overnight_shift_ends_the_next_morning():
    plan = resolve_day(date(2026, 11, 2), NIGHT, [])   # Monday
    assert plan.end == datetime(2026, 11, 3, 4, 0, tzinfo=COLOMBO)
    assert plan.expected_minutes == 480


def test_no_schedule_at_all_is_not_a_working_day():
    assert not resolve_day(date(2026, 11, 2), None, []).working


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------

def _send(role, supabase, method, path, json=None):
    with acting_as(role):
        app.dependency_overrides[get_supabase] = lambda: supabase
        return _request(method, path, json=json)


def test_import_preview_counts_new_rows_and_reports_no_warnings():
    supabase = _RecordingSupabase({"holidays": {"select": [
        {"holiday_date": "2026-01-03", "name": "Duruthu Full Moon Poya Day"},
    ]}})
    body = _send("HR Officer", supabase, "GET", "/api/hr/holidays/import-preview?year=2026").json()
    assert (body["new_count"], body["existing_count"], body["warnings"]) == (25, 1, [])


def test_import_adds_only_missing_rows_with_the_day_off_policy_applied():
    supabase = _RecordingSupabase({"holidays": {"select": [
        {"holiday_date": "2026-01-03", "name": "Duruthu Full Moon Poya Day"},
    ]}})
    response = _send("HR Officer", supabase, "POST", "/api/hr/holidays/import?year=2026")
    assert response.status_code == 200, response.text
    assert response.json()["added"] == 25

    (inserted,) = [d for t, d in supabase.inserts if t == "holidays"]
    by_name = {r["name"]: r for r in inserted}
    assert "Duruthu Full Moon Poya Day" not in by_name                 # already there
    assert by_name["Il Full Moon Poya Day"]["is_day_off"] is True
    assert by_name["Christmas Day"]["is_day_off"] is True
    assert by_name["Good Friday"]["is_day_off"] is False


def test_import_of_a_year_with_no_file_is_a_404():
    assert _send("HR Officer", _RecordingSupabase(), "POST", "/api/hr/holidays/import?year=2031").status_code == 404


@pytest.mark.parametrize("role", ALL_ROLES)
def test_holiday_calendar_is_readable_by_any_signed_in_role(role):
    assert _send(role, _RecordingSupabase(), "GET", "/api/hr/holidays?year=2026").status_code == 200


@pytest.mark.parametrize("role", ALL_ROLES)
def test_only_hr_manage_can_import(role):
    status = _send(role, _RecordingSupabase(), "POST", "/api/hr/holidays/import?year=2026").status_code
    assert (status != 403) == has_permission(role, "hr:manage")


def test_schedule_rejects_a_weekday_twice():
    body = {"name": "Broken", "days": [
        {"weekday": 1, "start_time": "08:00", "end_time": "16:00"},
        {"weekday": 1, "start_time": "09:00", "end_time": "17:00"},
    ]}
    assert _send("HR Officer", _RecordingSupabase(), "POST", "/api/hr/schedules", json=body).status_code == 422


def test_schedule_rejects_a_zero_length_day():
    body = {"name": "Broken", "days": [{"weekday": 1, "start_time": "08:00", "end_time": "08:00"}]}
    assert _send("HR Officer", _RecordingSupabase(), "POST", "/api/hr/schedules", json=body).status_code == 422


def test_the_default_schedule_cannot_be_deleted():
    supabase = _RecordingSupabase({"work_schedules": {"select": [{**OFFICE, "days": []}]}})
    assert _send("HR Officer", supabase, "DELETE", "/api/hr/schedules/1").status_code == 409


def test_a_schedule_already_assigned_cannot_be_deleted():
    supabase = _RecordingSupabase({
        "work_schedules": {"select": [{**RESCUE, "days": []}]},
        "employee_schedule_assignments": {"select": [{"id": 4, "schedule_id": 2}]},
    })
    assert _send("HR Officer", supabase, "DELETE", "/api/hr/schedules/2").status_code == 409


def test_assignments_show_who_follows_what_today():
    supabase = _RecordingSupabase({
        "employee_profile": {"select": [
            {"id": 7, "first_name": "Amal", "last_name": "Silva", "status": "Active"},
            {"id": 9, "first_name": "Ruwan", "last_name": "Fernando", "status": "Active"},
        ]},
        "employee_schedule_assignments": {"select": [
            {"id": 1, "employee_id": 7, "schedule_id": 2, "effective_from": "2020-01-01"},
        ]},
        "work_schedules": {"select": [
            {"id": 1, "name": "Office hours", "is_default": True},
            {"id": 2, "name": "Rescue rota", "is_default": False},
        ]},
    })
    rows = {r["employee_name"]: r for r in _send("HR Officer", supabase, "GET", "/api/hr/schedule-assignments").json()}
    assert rows["Amal Silva"]["current_schedule_name"] == "Rescue rota"
    assert not rows["Amal Silva"]["follows_default"]
    assert rows["Ruwan Fernando"]["current_schedule_name"] == "Office hours"
    assert rows["Ruwan Fernando"]["follows_default"]
