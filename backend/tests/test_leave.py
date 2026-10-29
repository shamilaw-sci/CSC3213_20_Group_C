"""Leave management (attendance rework, step 2).

The statutory arithmetic is tested against the Shop and Office Employees Act
as quoted in app/services/leave_rules.py. API tests cover counting days
against the schedule and holiday calendar, balances, the self-approval ban,
and entitlement generation.
"""

import os
import sys
from datetime import date
from decimal import Decimal as D

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.permissions import ROLE_PERMISSIONS, has_permission
from app.core.supabase import get_supabase
from app.main import app
from app.services.leave_rules import (
    Balance,
    LeaveType,
    add_months,
    annual_entitlement,
    carry_forward,
    casual_accrued,
    casual_entitlement,
    check_request,
    complete_months,
    leave_days,
)
from tests.test_ledger_integrity import _RecordingSupabase
from tests.test_rbac_matrix import ALL_ROLES, OTHER_USER_ID, USER_ID, _request, acting_as

# --------------------------------------------------------------------------
# The Act's arithmetic
# --------------------------------------------------------------------------

def test_add_months_clamps_to_month_end():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)


@pytest.mark.parametrize("joined, through, months", [
    (date(2026, 3, 15), date(2026, 5, 14), 2),   # two complete months at the end of 14 May
    (date(2026, 3, 15), date(2026, 5, 13), 1),
    (date(2026, 3, 15), date(2026, 3, 14), 0),   # before joining
    (date(2026, 1, 1), date(2026, 12, 31), 12),
])
def test_complete_months(joined, through, months):
    assert complete_months(joined, through) == months


@pytest.mark.parametrize("joined, expected", [
    (date(2025, 1, 1), 14),     # s.6(1)(a)(i): joined January-March
    (date(2025, 3, 31), 14),
    (date(2025, 4, 1), 10),     # (ii) April-June
    (date(2025, 6, 30), 10),
    (date(2025, 7, 1), 7),      # (iii) July-September
    (date(2025, 9, 30), 7),
    (date(2025, 10, 1), 4),     # (iv) from October
    (date(2025, 12, 31), 4),
    (date(2024, 8, 15), 14),    # s.6(1)(b): second and later years
    (date(2026, 2, 1), 0),      # s.6(2): earned in 2026, taken in 2027
    (date(2027, 1, 1), 0),      # not yet joined
])
def test_annual_leave_follows_the_acts_table_taken_the_following_year(joined, expected):
    assert annual_entitlement(joined, 2026, D(14)) == D(expected)


def test_unknown_join_date_gives_no_figure_rather_than_a_guess():
    assert annual_entitlement(None, 2026, D(14)) is None
    assert casual_entitlement(None, 2026, D(7)) is None


@pytest.mark.parametrize("joined, expected", [
    (date(2026, 1, 1), 6),      # 12 complete months by 31 Dec
    (date(2026, 1, 5), 5),      # 11 complete months
    (date(2026, 3, 15), 4),     # 9 complete months
    (date(2026, 11, 2), 0),     # 1 complete month
    (date(2025, 6, 1), 7),      # second year: the full 7
])
def test_casual_leave_in_the_joining_year_is_one_day_per_two_complete_months(joined, expected):
    assert casual_entitlement(joined, 2026, D(7)) == D(expected)


def test_casual_accrues_during_the_joining_year_only():
    assert casual_accrued(date(2026, 3, 15), date(2026, 7, 20)) == D(2)
    assert casual_accrued(date(2025, 3, 15), date(2026, 7, 20)) is None


@pytest.mark.parametrize("remaining, expected", [(D(10), D(7)), (D(3.5), D("3.5")), (D(-2), D(0))])
def test_carry_forward_is_capped_and_never_negative(remaining, expected):
    assert carry_forward(remaining, 7) == expected


def _weekdays(d: date) -> bool:
    return d.isoweekday() <= 5 and d != date(2026, 11, 24)   # Il Poya, a Tuesday


def test_working_day_leave_skips_weekends_and_holidays():
    days = leave_days(date(2026, 11, 23), date(2026, 11, 29), "none", False, _weekdays)
    assert [d.day for d, _ in days] == [23, 25, 26, 27]


def test_calendar_day_leave_counts_every_date():
    assert len(leave_days(date(2026, 11, 23), date(2026, 11, 29), "none", True, _weekdays)) == 7


def test_half_day_is_half():
    assert leave_days(date(2026, 11, 23), date(2026, 11, 23), "am", False, _weekdays) == [(date(2026, 11, 23), D("0.5"))]


ANNUAL = LeaveType("Annual leave", uses_balance=True, allow_half_day=True, first_year_rule="soe_annual")
CASUAL = LeaveType("Casual leave", uses_balance=True, allow_half_day=True, first_year_rule="soe_casual")
MATERNITY = LeaveType("Maternity leave", uses_balance=False, allow_half_day=False, max_days_per_request=D(84))


def test_balance_blocks_an_oversized_request():
    days = [(date(2026, 11, d), D(1)) for d in (23, 25, 26, 27)]
    check = check_request(ANNUAL, days, "none", {2026: Balance(entitled=D(14), approved=D(9), pending=D(2))}, date(2020, 1, 1))
    assert not check.ok and "Only 3" in check.errors[0]


def test_request_across_new_year_draws_on_each_years_balance():
    days = [(date(2026, 12, 31), D(1)), (date(2027, 1, 4), D(1))]
    check = check_request(ANNUAL, days, "none", {2026: Balance(entitled=D(1)), 2027: None}, date(2020, 1, 1))
    assert len(check.errors) == 1 and "2027" in check.errors[0]


def test_event_leave_is_capped_per_request_not_by_balance():
    days = [(date(2026, 1, 1), D(1))] * 85
    check = check_request(MATERNITY, days, "none", {}, None)
    assert not check.ok and "84" in check.errors[0]


def test_maternity_cannot_be_a_half_day():
    check = check_request(MATERNITY, [(date(2026, 1, 5), D("0.5"))], "am", {}, None)
    assert "half day" in check.errors[0]


def test_first_year_casual_cannot_outrun_what_has_built_up():
    joined = date(2026, 3, 15)
    days = [(date(2026, 7, 20), D(1)), (date(2026, 7, 21), D(1))]   # 2 built up by 21 July
    balances = {2026: Balance(entitled=D(4))}
    assert check_request(CASUAL, days, "none", balances, joined, casual_used_in_joining_year=D(0)).ok
    blocked = check_request(CASUAL, days, "none", balances, joined, casual_used_in_joining_year=D(1))
    assert not blocked.ok and "s.6(4)(a)" in blocked.errors[0]


# --------------------------------------------------------------------------
# Fixtures for the API
# --------------------------------------------------------------------------

THIRD_USER = "33333333-aaaa-bbbb-cccc-333333333333"

EMP_ME = {"id": 7, "user_id": USER_ID, "first_name": "Hiru", "last_name": "Officer", "status": "Active", "date_joined": "2020-01-01"}
EMP_OTHER = {"id": 8, "user_id": OTHER_USER_ID, "first_name": "Amal", "last_name": "Silva", "status": "Active", "date_joined": "2020-01-01"}
EMP_NEW = {"id": 9, "user_id": THIRD_USER, "first_name": "Nimmi", "last_name": "Perera", "status": "Active", "date_joined": None}

TYPES = [
    {"id": 1, "code": "ANNUAL", "name": "Annual leave", "is_paid": True, "uses_balance": True, "default_days": 14,
     "max_days_per_request": None, "counts_calendar_days": False, "allow_half_day": True,
     "carry_forward_max": 7, "first_year_rule": "soe_annual", "is_active": True, "sort_order": 1},
    {"id": 3, "code": "SICK", "name": "Sick leave", "is_paid": True, "uses_balance": True, "default_days": 7,
     "max_days_per_request": None, "counts_calendar_days": False, "allow_half_day": True,
     "carry_forward_max": 0, "first_year_rule": "none", "is_active": True, "sort_order": 3},
    {"id": 5, "code": "MATERNITY", "name": "Maternity leave", "is_paid": True, "uses_balance": False, "default_days": None,
     "max_days_per_request": 84, "counts_calendar_days": False, "allow_half_day": False,
     "carry_forward_max": 0, "first_year_rule": "none", "is_active": True, "sort_order": 5},
]

OFFICE = {"id": 1, "name": "Office hours", "is_default": True, "grace_minutes": 15, "observes_holidays": True,
          "days": [{"weekday": w, "start_time": "08:30:00", "end_time": "17:00:00", "break_minutes": 60} for w in range(1, 6)]}
POYA = {"holiday_date": "2026-11-24", "name": "Il Full Moon Poya Day", "is_day_off": True}

ANNUAL_2026_OTHER = {"id": 40, "employee_id": 8, "leave_type_id": 1, "year": 2026,
                     "entitled_days": 14, "carried_forward": 0, "adjustment": 0}


def _db(requests=(), days=(), entitlements=(ANNUAL_2026_OTHER,), employees=(EMP_ME, EMP_OTHER, EMP_NEW)):
    return _RecordingSupabase({
        "employee_profile": {"select": list(employees)},
        "leave_types": {"select": TYPES},
        "work_schedules": {"select": [OFFICE]},
        "employee_schedule_assignments": {"select": []},
        "holidays": {"select": [POYA]},
        "leave_entitlements": {"select": list(entitlements), "update": [{"id": 40}]},
        "leave_requests": {"select": list(requests), "insert": [{"id": 100, "employee_id": 8}],
                           "update": [{"id": 100, "status": "Approved"}]},
        "leave_request_days": {"select": list(days)},
        "system_audit_logs": {"select": [], "insert": [{"id": 1}]},
    })


def _send(role, supabase, method, path, json=None, user_id=USER_ID):
    with acting_as(role, user_id=user_id):
        app.dependency_overrides[get_supabase] = lambda: supabase
        return _request(method, path, json=json)


def _inserted(supabase, table):
    return [d for t, d in supabase.inserts if t == table]


ANNUAL_WEEK = {"leave_type_id": 1, "start_date": "2026-11-23", "end_date": "2026-11-29", "reason": "Family visit"}


# --------------------------------------------------------------------------
# Requesting
# --------------------------------------------------------------------------

def test_request_counts_working_days_and_saves_each_day():
    supabase = _db()
    response = _send("General Staff", supabase, "POST", "/api/leave/requests", json=ANNUAL_WEEK, user_id=OTHER_USER_ID)
    assert response.status_code == 200, response.text

    (request,) = _inserted(supabase, "leave_requests")
    assert request["employee_id"] == 8 and request["days"] == 4.0   # Mon-Fri less the Poya
    assert request["requested_by"] == OTHER_USER_ID
    (day_rows,) = _inserted(supabase, "leave_request_days")
    assert [r["leave_date"] for r in day_rows] == ["2026-11-23", "2026-11-25", "2026-11-26", "2026-11-27"]


def test_preview_shows_the_balance_after():
    body = _send("General Staff", _db(), "POST", "/api/leave/preview", json=ANNUAL_WEEK, user_id=OTHER_USER_ID).json()
    assert body["total"] == 4.0 and body["errors"] == []
    assert body["balances"]["2026"]["after"] == 10.0


def test_request_beyond_the_balance_is_refused():
    used = [{"id": 90, "employee_id": 8, "leave_type_id": 1, "status": "Approved"}]
    days = [{"request_id": 90, "leave_date": f"2026-03-{d:02d}", "fraction": 1} for d in range(2, 13)]   # 11 days
    response = _send("General Staff", _db(used, days), "POST", "/api/leave/requests", json=ANNUAL_WEEK, user_id=OTHER_USER_ID)
    assert response.status_code == 400 and "Only 3" in response.json()["detail"]


def test_request_with_no_entitlement_says_to_generate_it():
    response = _send("General Staff", _db(entitlements=()), "POST", "/api/leave/requests", json=ANNUAL_WEEK, user_id=OTHER_USER_ID)
    assert response.status_code == 400 and "generate" in response.json()["detail"]


def test_overlapping_request_is_refused_with_the_dates():
    live = [{"id": 91, "employee_id": 8, "leave_type_id": 3, "status": "Pending"}]
    days = [{"request_id": 91, "leave_date": "2026-11-25", "fraction": 1}]
    response = _send("General Staff", _db(live, days), "POST", "/api/leave/requests", json=ANNUAL_WEEK, user_id=OTHER_USER_ID)
    assert response.status_code == 400 and "2026-11-25" in response.json()["detail"]


def test_cancelled_leave_does_not_use_up_the_balance():
    gone = [{"id": 92, "employee_id": 8, "leave_type_id": 1, "status": "Cancelled"}]
    days = [{"request_id": 92, "leave_date": f"2026-03-{d:02d}", "fraction": 1} for d in range(2, 16)]
    response = _send("General Staff", _db(gone, days), "POST", "/api/leave/preview", json=ANNUAL_WEEK, user_id=OTHER_USER_ID)
    assert response.json()["errors"] == []


def test_staff_cannot_file_leave_for_someone_else():
    body = {**ANNUAL_WEEK, "employee_id": 7}
    assert _send("General Staff", _db(), "POST", "/api/leave/requests", json=body, user_id=OTHER_USER_ID).status_code == 403


def test_hr_can_file_on_someones_behalf():
    body = {**ANNUAL_WEEK, "employee_id": 8}
    supabase = _db()
    assert _send("HR Officer", supabase, "POST", "/api/leave/requests", json=body).status_code == 200
    assert _inserted(supabase, "leave_requests")[0]["employee_id"] == 8


# --------------------------------------------------------------------------
# Approval, and the self-approval ban
# --------------------------------------------------------------------------

def _pending(employee_id=8, requested_by=OTHER_USER_ID):
    return [{"id": 100, "employee_id": employee_id, "leave_type_id": 1, "status": "Pending",
             "requested_by": requested_by, "start_date": "2026-11-23", "end_date": "2026-11-27"}]


PENDING_DAYS = [{"request_id": 100, "leave_date": d, "fraction": 1} for d in ("2026-11-23", "2026-11-25", "2026-11-26", "2026-11-27")]


def test_hr_approves_someone_elses_leave():
    supabase = _db(_pending(), PENDING_DAYS)
    response = _send("HR Officer", supabase, "POST", "/api/leave/requests/100/approve", json={})
    assert response.status_code == 200, response.text
    (written,) = [d for t, d in supabase.updates if t == "leave_requests"]
    assert written["status"] == "Approved" and written["decided_by"] == USER_ID


@pytest.mark.parametrize("role", ["HR Officer", "Admin"])
def test_nobody_approves_their_own_leave(role):
    # The approver is employee 7; the request is employee 7's.
    supabase = _db(_pending(employee_id=7, requested_by=USER_ID), PENDING_DAYS,
                   entitlements=({**ANNUAL_2026_OTHER, "employee_id": 7},))
    response = _send(role, supabase, "POST", "/api/leave/requests/100/approve", json={})
    assert response.status_code == 403, response.text
    assert [d for t, d in supabase.updates if t == "leave_requests"] == []


def test_nobody_approves_their_own_leave_even_when_someone_else_filed_it():
    supabase = _db(_pending(employee_id=7, requested_by=OTHER_USER_ID), PENDING_DAYS)
    assert _send("HR Officer", supabase, "POST", "/api/leave/requests/100/approve", json={}).status_code == 403


def test_nobody_approves_a_request_they_filed_for_someone_else():
    supabase = _db(_pending(employee_id=8, requested_by=USER_ID), PENDING_DAYS)
    assert _send("HR Officer", supabase, "POST", "/api/leave/requests/100/approve", json={}).status_code == 403


def test_nobody_rejects_their_own_leave_either():
    supabase = _db(_pending(employee_id=7, requested_by=USER_ID), PENDING_DAYS)
    response = _send("HR Officer", supabase, "POST", "/api/leave/requests/100/reject", json={"note": "no"})
    assert response.status_code == 403


@pytest.mark.parametrize("role", ALL_ROLES)
def test_only_leave_approve_holders_can_approve(role):
    response = _send(role, _db(_pending(), PENDING_DAYS), "POST", "/api/leave/requests/100/approve", json={},
                     user_id=THIRD_USER)
    assert (response.status_code != 403) == has_permission(role, "leave:approve"), (role, response.status_code)


def test_leave_approve_is_exactly_hr_officer_and_admin():
    holders = sorted(r for r, perms in ROLE_PERMISSIONS.items() if "leave:approve" in perms)
    assert holders == ["Admin", "HR Officer"]


def test_rejection_needs_a_reason():
    response = _send("HR Officer", _db(_pending(), PENDING_DAYS), "POST", "/api/leave/requests/100/reject", json={})
    assert response.status_code == 400


def test_approval_rechecks_the_balance():
    approved = [{"id": 93, "employee_id": 8, "leave_type_id": 1, "status": "Approved"}]
    approved_days = [{"request_id": 93, "leave_date": f"2026-03-{d:02d}", "fraction": 1} for d in range(2, 14)]   # 12
    supabase = _db(_pending() + approved, PENDING_DAYS + approved_days)
    response = _send("HR Officer", supabase, "POST", "/api/leave/requests/100/approve", json={})
    assert response.status_code == 409 and "2 days left" in response.json()["detail"]


def test_a_decided_request_cannot_be_decided_again():
    done = [{**_pending()[0], "status": "Approved"}]
    assert _send("HR Officer", _db(done, PENDING_DAYS), "POST", "/api/leave/requests/100/approve", json={}).status_code == 409


# --------------------------------------------------------------------------
# Cancelling
# --------------------------------------------------------------------------

def test_staff_cancel_their_own_pending_leave():
    supabase = _db(_pending(), PENDING_DAYS)
    assert _send("General Staff", supabase, "POST", "/api/leave/requests/100/cancel", user_id=OTHER_USER_ID).status_code == 200


def test_staff_cannot_cancel_someone_elses_leave():
    assert _send("General Staff", _db(_pending(employee_id=7), PENDING_DAYS), "POST",
                 "/api/leave/requests/100/cancel", user_id=OTHER_USER_ID).status_code == 403


def test_staff_cannot_cancel_approved_leave_that_has_started():
    started = [{**_pending()[0], "status": "Approved", "start_date": "2020-01-06"}]
    assert _send("General Staff", _db(started, PENDING_DAYS), "POST", "/api/leave/requests/100/cancel",
                 user_id=OTHER_USER_ID).status_code == 409


# --------------------------------------------------------------------------
# Entitlements
# --------------------------------------------------------------------------

def test_generation_flags_missing_join_dates_instead_of_skipping_silently():
    supabase = _db(entitlements=())
    body = _send("HR Officer", supabase, "POST", "/api/leave/entitlements/generate?year=2026").json()

    (flag,) = body["needs_date_joined"]
    assert flag["employee_name"] == "Nimmi Perera" and flag["leave_types"] == ["Annual leave"]

    (rows,) = _inserted(supabase, "leave_entitlements")
    nimmi = [r for r in rows if r["employee_id"] == 9]
    # Sick leave has no first-year rule, so it is still created for her.
    assert [r["leave_type_id"] for r in nimmi] == [3]
    assert {(r["employee_id"], r["leave_type_id"]) for r in rows} >= {(7, 1), (7, 3), (8, 1), (8, 3)}


def test_generation_never_overwrites_an_existing_row():
    supabase = _db()   # employee 8 already has annual 2026
    _send("HR Officer", supabase, "POST", "/api/leave/entitlements/generate?year=2026")
    (rows,) = _inserted(supabase, "leave_entitlements")
    assert (8, 1) not in {(r["employee_id"], r["leave_type_id"]) for r in rows}


def test_annual_carry_forward_is_capped_at_seven():
    prior = {**ANNUAL_2026_OTHER, "id": 41, "year": 2025}   # 14 unused in 2025
    supabase = _db(entitlements=(prior,))
    _send("HR Officer", supabase, "POST", "/api/leave/entitlements/generate?year=2026")
    (rows,) = _inserted(supabase, "leave_entitlements")
    amal_annual = next(r for r in rows if r["employee_id"] == 8 and r["leave_type_id"] == 1)
    assert amal_annual["carried_forward"] == 7.0


def test_entitlements_list_names_who_needs_a_join_date():
    body = _send("HR Officer", _db(), "GET", "/api/leave/entitlements?year=2026").json()
    assert body["needs_date_joined"] == [{"employee_id": 9, "employee_name": "Nimmi Perera"}]


def test_join_date_needs_hr_manage():
    assert _send("General Staff", _db(), "PATCH", "/api/leave/employees/9/date-joined",
                 json={"date_joined": "2026-03-15"}).status_code == 403
    supabase = _db()
    assert _send("HR Officer", supabase, "PATCH", "/api/leave/employees/9/date-joined",
                 json={"date_joined": "2026-03-15"}).status_code == 200
    assert {"date_joined": "2026-03-15"} in [d for t, d in supabase.updates if t == "employee_profile"]
