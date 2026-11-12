"""Month close and absences in arrears (attendance rework, step 5; migration 029).

Confirmed 2026-11-12:
  * HR closes a past month, not one before tracking started, and not while
    a clock-out is missing or a correction is waiting;
  * the close records payable absences (half a day where half-day leave
    covered the other half) and freezes the month;
  * the next payroll generated after closing deducts them at base / 30;
    approving it records which closes it took;
  * HR may reopen until that payroll is approved.
"""

import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api import attendance_month as am
from app.api import hr
from app.schemas.hr import SRI_LANKA
from tests.test_employees import _Db, _Result, _send
from tests.test_leave import OFFICE
from tests.test_rbac_matrix import USER_ID

NOW = datetime(2026, 11, 12, 10, 0, tzinfo=SRI_LANKA)


class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is None else NOW.astimezone(tz)


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    monkeypatch.setattr(am, "datetime", _FixedDatetime)
    monkeypatch.setattr(hr, "_sl_now", lambda: NOW)


AMAL = {"id": 8, "user_id": None, "first_name": "Amal", "last_name": "Silva", "status": "Active",
        "date_joined": "2020-01-01", "attendance_tracked_from": None, "base_salary": 60000, "nic": None,
        "epf_number": None, "date_left": None}


class _CloseDb(_Db):
    """_Db with the close and payroll RPCs."""

    def __init__(self, *, records=(), corrections=(), closes=(), close_lines=(), leave=(), leave_days=(),
                 tracking_start="2026-09-01"):
        super().__init__([AMAL, {"id": 7, "user_id": USER_ID, "first_name": "Hiru", "last_name": "Officer",
                                 "status": "Inactive", "date_joined": "2020-01-01", "date_left": "2020-06-30"}])
        self.tables.update({
            "attendance_log": [dict(r) for r in records],
            "attendance_correction_requests": [dict(c) for c in corrections],
            "attendance_settings": [{"id": 1, "tracking_start_date": tracking_start}],
            "attendance_month_closes": [dict(c) for c in closes],
            "attendance_close_lines": [dict(l) for l in close_lines],
            "work_schedules": [OFFICE], "employee_schedule_assignments": [], "holidays": [],
            "leave_requests": [dict(r) for r in leave], "leave_request_days": [dict(d) for d in leave_days],
            "leave_types": [{"id": 7, "is_paid": False}, {"id": 1, "is_paid": True}],
            "payroll_runs": [], "payroll_ledger": [],
        })
        self.rpcs = []

    def rpc(self, name, params=None):
        self.rpcs.append((name, params))
        db = self

        class _Call:
            def execute(self):
                if name == "close_attendance_month":
                    row = {"id": 90, "close_month": params["p_month"], "close_year": params["p_year"], "status": "Closed"}
                    db.tables["attendance_month_closes"].append(row)
                    return _Result([row])
                return _Result([{"id": 1, "payroll_month": params.get("p_month", 11), "payroll_year": 2026,
                                 "status": "Draft", "total": 1}])

        return _Call()


def _close(month=10, **kw):
    return {"id": 50, "close_month": month, "close_year": 2026, "status": "Closed", "deducted_in_run_id": None, **kw}


def _preview(db, month=10):
    return _send(db, "GET", f"/api/hr/attendance/close?year=2026&month={month}").json()


# --------------------------------------------------------------------------
# What a close records
# --------------------------------------------------------------------------

def test_the_preview_counts_working_days_with_no_clock_in_as_absences():
    body = _preview(_CloseDb())
    (amal,) = body["absences"]
    assert amal["employee_name"] == "Amal Silva"
    assert amal["absent_days"] == 22                      # weekdays in October 2026
    assert body["can_close"] is True and body["status"] == "Open"


def test_half_day_leave_with_no_clock_in_is_half_an_absence():
    leave = [{"id": 3, "employee_id": 8, "status": "Approved", "half_day": "am", "start_date": "2026-10-05", "end_date": "2026-10-05",
              "leave_types": {"name": "Annual leave", "code": "ANNUAL", "is_paid": True}}]
    days = [{"request_id": 3, "leave_date": "2026-10-05", "fraction": 0.5}]
    (amal,) = _preview(_CloseDb(leave=leave, leave_days=days))["absences"]
    assert amal["absent_days"] == 21.5


@pytest.mark.parametrize("db_kw, month, needle", [
    ({}, 11, "once it has ended"),
    ({"records": [{"id": 1, "employee_id": 8, "target_date": "2026-10-05",
                   "clock_in": "2026-10-05T03:00:00+00:00", "clock_out": None, "is_locked": False}]}, 10, "missing a clock-out"),
    ({"corrections": [{"id": 4, "employee_id": 8, "target_date": "2026-10-06", "status": "Pending"}]}, 10, "still waiting"),
    ({"tracking_start": "2026-11-02"}, 9, "wasn't tracked"),
    ({"closes": [_close()]}, 10, "already closed"),
])
def test_a_month_with_loose_ends_cannot_be_closed(db_kw, month, needle):
    db = _CloseDb(**db_kw)
    response = _send(db, "POST", f"/api/hr/attendance/close?year=2026&month={month}")

    assert response.status_code == 409, response.text
    assert needle in response.json()["detail"]
    assert not [n for n, _ in db.rpcs if n == "close_attendance_month"]


def test_closing_records_each_employees_absences():
    db = _CloseDb()
    response = _send(db, "POST", "/api/hr/attendance/close?year=2026&month=10")

    assert response.status_code == 200, response.text
    ((name, params),) = db.rpcs
    assert name == "close_attendance_month"
    (line,) = params["p_lines"]
    assert line["employee_id"] == 8 and line["absent_days"] == 22 and "2026-10-01" in line["absent_dates"]


def test_only_attendance_managers_close():
    assert _send(_CloseDb(), "POST", "/api/hr/attendance/close?year=2026&month=10", role="Director").status_code == 403


# --------------------------------------------------------------------------
# A closed month is frozen
# --------------------------------------------------------------------------

def test_a_closed_month_refuses_attendance_edits():
    db = _CloseDb(closes=[_close()])
    response = _send(db, "POST", "/api/hr/attendance", {
        "employee_id": 8, "target_date": "2026-10-05",
        "clock_in": "2026-10-05T08:30:00+05:30", "clock_out": "2026-10-05T17:00:00+05:30"})

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "October 2026 is closed; reopen the month to change its attendance."


def test_a_reopened_month_is_open_again():
    db = _CloseDb(closes=[_close(status="Reopened")])
    response = _send(db, "POST", "/api/hr/attendance", {
        "employee_id": 8, "target_date": "2026-10-05",
        "clock_in": "2026-10-05T08:30:00+05:30", "clock_out": "2026-10-05T17:00:00+05:30"})
    assert response.status_code == 200, response.text


# --------------------------------------------------------------------------
# Reopening
# --------------------------------------------------------------------------

def test_reopening_a_closed_month():
    db = _CloseDb(closes=[_close()])
    response = _send(db, "POST", "/api/hr/attendance/close/reopen?year=2026&month=10")

    assert response.status_code == 200, response.text
    assert db.tables["attendance_month_closes"][0]["status"] == "Reopened"


def test_a_month_whose_absences_are_in_an_approved_payroll_cannot_be_reopened():
    db = _CloseDb(closes=[_close(deducted_in_run_id=3)])
    response = _send(db, "POST", "/api/hr/attendance/close/reopen?year=2026&month=10")

    assert response.status_code == 409, response.text
    assert db.tables["attendance_month_closes"][0]["status"] == "Closed"


def test_an_open_month_cannot_be_reopened():
    assert _send(_CloseDb(), "POST", "/api/hr/attendance/close/reopen?year=2026&month=10").status_code == 409


# --------------------------------------------------------------------------
# Payroll deducts closed absences in arrears
# --------------------------------------------------------------------------

def _generated(db, month=11):
    _send(db, "POST", f"/api/hr/payroll/generate?month={month}&year=2026")
    (params,) = [p for n, p in db.rpcs if n == "generate_payroll_draft"]
    return params


def test_the_next_payroll_deducts_a_closed_months_absences():
    db = _CloseDb(closes=[_close()], close_lines=[{"close_id": 50, "employee_id": 8, "absent_days": 2}])
    params = _generated(db)

    assert params["p_absence_months"] == "October 2026"
    (line,) = params["p_lines"]
    assert line["absent_days"] == 2.0 and line["absence_deduction"] == 4000.0      # 2 x 60000 / 30
    assert line["gross"] == 56000.0


@pytest.mark.parametrize("close", [
    _close(deducted_in_run_id=3),          # already deducted by an approved payroll
    _close(status="Reopened"),             # reopened since
    _close(month=11),                      # the payroll's own month: not in arrears
])
def test_absences_not_due_are_left_out(close):
    db = _CloseDb(closes=[close], close_lines=[{"close_id": 50, "employee_id": 8, "absent_days": 2}])
    params = _generated(db)

    assert params["p_absence_months"] is None
    assert params["p_lines"][0]["absent_days"] == 0.0


def test_approving_passes_the_closes_it_deducts():
    db = _CloseDb(closes=[_close()], close_lines=[{"close_id": 50, "employee_id": 8, "absent_days": 2}])
    params = _generated(db)
    db.tables["payroll_runs"] = [{"id": 1, "payroll_month": 11, "payroll_year": 2026, "status": "Draft",
                                  "generated_by": "someone-else", "generated_at": "2026-11-26T05:00:00+00:00"}]
    db.tables["payroll_ledger"] = [{**params["p_lines"][0], "id": 600, "run_id": 1,
                                    "employee_profile": {"first_name": "Amal", "last_name": "Silva"}}]
    hr_now = datetime(2026, 11, 26, 10, 0, tzinfo=SRI_LANKA)       # from the 25th: approvable
    hr._sl_now = lambda: hr_now
    try:
        response = _send(db, "POST", "/api/hr/payroll/runs/1/approve", role="Director")
    finally:
        hr._sl_now = lambda: NOW

    assert response.status_code == 200, response.text
    (approve,) = [p for n, p in db.rpcs if n == "approve_payroll_run"]
    assert approve["p_close_ids"] == [50]


def test_reopening_a_month_makes_a_draft_that_deducted_it_out_of_date():
    db = _CloseDb(closes=[_close()], close_lines=[{"close_id": 50, "employee_id": 8, "absent_days": 2}])
    params = _generated(db)
    db.tables["payroll_runs"] = [{"id": 1, "payroll_month": 11, "payroll_year": 2026, "status": "Draft",
                                  "generated_by": "someone-else", "generated_at": "2026-11-26T05:00:00+00:00"}]
    db.tables["payroll_ledger"] = [{**params["p_lines"][0], "id": 600, "run_id": 1,
                                    "employee_profile": {"first_name": "Amal", "last_name": "Silva"}}]
    db.tables["attendance_month_closes"][0]["status"] = "Reopened"

    drift = _send(db, "GET", "/api/hr/payroll/run?month=11&year=2026").json()["drift"]
    assert [(d["employee_name"], d["change"]) for d in drift] == [("Amal Silva", "changed")]
