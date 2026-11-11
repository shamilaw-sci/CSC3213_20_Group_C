"""Leave defects found testing the Leave pages on 2026-11-11 (app/api/leave.py).

  * HR could adjust their own leave allowance;
  * leave could be dated before the employee joined;
  * messages showed "1E+1" for 10 days and "1E+2" for 100;
  * correcting a join date left already-generated allowances as they were;
  * filing for someone, the overlap message said "You already have";
  * leave could be requested, approved and cancelled in a month whose payroll
    is approved, although that month's attendance is frozen (confirmed);
  * HR could cancel their own approved leave after it started (confirmed:
    another HR officer must, as for staff).
"""

import os
import sys
from datetime import date
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api import leave
from app.services.leave_rules import days_text
from tests.test_employees import _Db
from tests.test_leave import OFFICE, TYPES
from tests.test_rbac_matrix import OTHER_USER_ID, USER_ID


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch):
    monkeypatch.setattr(leave, "_today", lambda: date(2026, 11, 11))


# HR (acting_as signs in as USER_ID) and two staff.
HR = {"id": 7, "user_id": USER_ID, "first_name": "Hiru", "last_name": "Officer", "status": "Active", "date_joined": "2020-01-01"}
AMAL = {"id": 8, "user_id": OTHER_USER_ID, "first_name": "Amal", "last_name": "Silva", "status": "Active", "date_joined": "2020-01-01"}
NIMMI = {"id": 9, "user_id": None, "first_name": "Nimmi", "last_name": "Perera", "status": "Active", "date_joined": "2026-03-01"}

NOPAY = {"id": 7, "code": "NOPAY", "name": "No-pay leave", "is_paid": False, "uses_balance": False, "default_days": None,
         "max_days_per_request": None, "counts_calendar_days": False, "allow_half_day": True,
         "carry_forward_max": 0, "first_year_rule": "none", "is_active": True, "sort_order": 7}


def _ent(id, employee_id, type_id, year, days, adjustment=0, carried=0):
    return {"id": id, "employee_id": employee_id, "leave_type_id": type_id, "year": year,
            "entitled_days": days, "carried_forward": carried, "adjustment": adjustment}


def _db(requests=(), days=(), entitlements=(), approved_months=()):
    db = _Db([HR, AMAL, NIMMI])
    db.tables.update({
        "leave_types": [dict(t) for t in [*TYPES, NOPAY]],
        "work_schedules": [OFFICE],
        "employee_schedule_assignments": [],
        "holidays": [],
        "leave_requests": [dict(r) for r in requests],
        "leave_request_days": [dict(d) for d in days],
        "leave_entitlements": [dict(e) for e in entitlements] or [
            _ent(40, 8, 1, 2026, 14), _ent(41, 8, 3, 2026, 7), _ent(42, 7, 1, 2026, 14), _ent(43, 9, 3, 2026, 7),
        ],
        "payroll_runs": [{"id": i, "payroll_month": m, "payroll_year": y, "status": "Approved"}
                         for i, (m, y) in enumerate(approved_months, 1)],
    })
    return db


def _preview(db, body, role="General Staff", user=OTHER_USER_ID):
    return _send_as(db, "POST", "/api/leave/preview", body, role, user).json()


def _send_as(db, method, path, body=None, role="HR Officer", user=USER_ID):
    from app.core.supabase import get_supabase
    from app.main import app
    from tests.test_rbac_matrix import _request, acting_as
    with acting_as(role, user_id=user):
        app.dependency_overrides[get_supabase] = lambda: db
        return _request(method, path, json=body)


def _request_row(id=100, employee_id=8, status="Pending", start="2026-12-01", end="2026-12-01", requested_by=OTHER_USER_ID, type_id=3):
    return {"id": id, "employee_id": employee_id, "leave_type_id": type_id, "status": status,
            "start_date": start, "end_date": end, "half_day": "none", "days": 1, "requested_by": requested_by}


def _day(request_id, d):
    return {"request_id": request_id, "leave_date": d, "fraction": 1}


# --------------------------------------------------------------------------
# Messages
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value, text", [(Decimal("10.0"), "10"), (Decimal("100"), "100"), (Decimal("0.5"), "0.5"),
                                         (Decimal("7"), "7"), (Decimal("2.50"), "2.5")])
def test_day_counts_are_written_out_plainly(value, text):
    assert days_text(value) == text


def test_a_balance_of_ten_reads_ten():
    db = _db(entitlements=[_ent(40, 8, 1, 2026, 10)])
    body = _preview(db, {"leave_type_id": 1, "start_date": "2026-12-01", "end_date": "2026-12-15"})
    assert body["errors"] == ["Only 10 days of annual leave are available in 2026; this request needs 11."]


def test_filing_for_someone_names_them_in_the_overlap_message():
    db = _db([_request_row(id=90, status="Approved", start="2026-12-02", end="2026-12-02")], [_day(90, "2026-12-02")])
    body = _send_as(db, "POST", "/api/leave/preview",
                    {"leave_type_id": 3, "start_date": "2026-12-02", "end_date": "2026-12-02", "employee_id": 8}).json()
    assert body["errors"] == ["Amal Silva already has leave requested or approved on 2026-12-02."]


# --------------------------------------------------------------------------
# Before joining
# --------------------------------------------------------------------------

def test_leave_cannot_start_before_the_join_date():
    db = _db()
    body = _send_as(db, "POST", "/api/leave/preview",
                    {"leave_type_id": 7, "start_date": "2026-02-10", "end_date": "2026-02-12", "employee_id": 9}).json()
    assert body["errors"] == ["Nimmi Perera joined on 1 March 2026; leave can't start before that."]


def test_leave_from_the_join_date_is_fine():
    db = _db()
    body = _send_as(db, "POST", "/api/leave/preview",
                    {"leave_type_id": 7, "start_date": "2026-03-02", "end_date": "2026-03-02", "employee_id": 9}).json()
    assert body["errors"] == []


# --------------------------------------------------------------------------
# Months whose payroll is approved
# --------------------------------------------------------------------------

def test_no_new_leave_in_an_approved_payroll_month():
    db = _db(approved_months=[(7, 2026)])
    response = _send_as(db, "POST", "/api/leave/requests",
                        {"leave_type_id": 3, "start_date": "2026-07-14", "end_date": "2026-07-14"}, "General Staff", OTHER_USER_ID)

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Payroll for July 2026 is approved, so leave on its days can no longer be requested."
    assert db.tables["leave_requests"] == []


def test_leave_in_an_open_month_is_unaffected():
    db = _db(approved_months=[(7, 2026)])
    body = _preview(db, {"leave_type_id": 3, "start_date": "2026-12-01", "end_date": "2026-12-01"})
    assert body["errors"] == []


def test_a_pending_request_in_an_approved_month_cannot_be_approved_but_can_be_rejected():
    rows = [_request_row(start="2026-07-14", end="2026-07-14")]
    db = _db(rows, [_day(100, "2026-07-14")], approved_months=[(7, 2026)])

    approve = _send_as(db, "POST", "/api/leave/requests/100/approve", {})
    assert approve.status_code == 409, approve.text
    assert "can no longer be approved" in approve.json()["detail"]

    reject = _send_as(db, "POST", "/api/leave/requests/100/reject", {"note": "Payroll is closed for July"})
    assert reject.status_code == 200, reject.text


def test_approved_leave_in_an_approved_month_cannot_be_cancelled():
    db = _db([_request_row(status="Approved", start="2026-07-14", end="2026-07-14")], [_day(100, "2026-07-14")],
             approved_months=[(7, 2026)])
    response = _send_as(db, "POST", "/api/leave/requests/100/cancel")

    assert response.status_code == 409, response.text
    assert "can no longer be cancelled" in response.json()["detail"]


def test_a_pending_request_in_an_approved_month_can_still_be_withdrawn():
    db = _db([_request_row(start="2026-07-14", end="2026-07-14")], [_day(100, "2026-07-14")], approved_months=[(7, 2026)])
    assert _send_as(db, "POST", "/api/leave/requests/100/cancel", None, "General Staff", OTHER_USER_ID).status_code == 200


# --------------------------------------------------------------------------
# HR's own leave and allowance
# --------------------------------------------------------------------------

def test_hr_cannot_cancel_their_own_leave_once_it_has_started():
    db = _db([_request_row(employee_id=7, status="Approved", start="2026-11-09", end="2026-11-12", requested_by=USER_ID)],
             [_day(100, "2026-11-10")])
    response = _send_as(db, "POST", "/api/leave/requests/100/cancel")

    assert response.status_code == 409, response.text
    assert "another HR officer" in response.json()["detail"]


def test_hr_still_cancels_someone_elses_started_leave():
    db = _db([_request_row(status="Approved", start="2026-11-09", end="2026-11-12")], [_day(100, "2026-11-10")])
    assert _send_as(db, "POST", "/api/leave/requests/100/cancel").status_code == 200


def test_hr_cannot_adjust_their_own_allowance():
    db = _db()
    response = _send_as(db, "PUT", "/api/leave/entitlements/42", {"adjustment": 5, "note": "self"})

    assert response.status_code == 403, response.text
    assert [d for t, d in db.updates if t == "leave_entitlements"] == []


def test_hr_adjusts_someone_elses_allowance():
    db = _db()
    response = _send_as(db, "PUT", "/api/leave/entitlements/40", {"adjustment": 2, "note": "Approved by Director"})
    assert response.status_code == 200, response.text


# --------------------------------------------------------------------------
# Correcting a join date
# --------------------------------------------------------------------------

def test_a_corrected_join_date_recomputes_this_years_allowance_keeping_adjustments():
    # Joined 1 Nov 2025 gives 4 days of 2026 annual leave; 1 Feb 2025 gives 14.
    db = _db(entitlements=[
        _ent(40, 8, 1, 2026, 4, adjustment=1),
        _ent(39, 8, 1, 2025, 0),            # a past year: left alone
        _ent(41, 8, 3, 2026, 7),            # sick: unchanged by the date
    ])
    response = _send_as(db, "PATCH", "/api/leave/employees/8/date-joined", {"date_joined": "2025-02-01"})

    assert response.status_code == 200, response.text
    assert response.json()["entitlements_updated"] == [{"year": 2026, "leave_type": "Annual leave", "from": 4.0, "to": 14.0}]
    rows = {r["id"]: r for r in db.tables["leave_entitlements"]}
    assert rows[40]["entitled_days"] == 14.0 and rows[40]["adjustment"] == 1
    assert rows[39]["entitled_days"] == 0
