"""The payroll engine through the API: inputs, payslips, leavers (app/api/hr.py)."""

import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api import hr
from app.schemas.hr import SRI_LANKA
from tests.test_employees import _Db, _send
from tests.test_payroll_rules import _PayrollDb, _run, _staff, _stored
from tests.test_rbac_matrix import OTHER_USER_ID, USER_ID


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    monkeypatch.setattr(hr, "_sl_now", lambda: datetime(2026, 11, 11, 10, 0, tzinfo=SRI_LANKA))


def _lines_sent(db):
    (params,) = [p for name, p in db.rpc_params if name == "generate_payroll_draft"]
    return {l["employee_id"]: l for l in params["p_lines"]}


# --------------------------------------------------------------------------
# What a draft is generated from
# --------------------------------------------------------------------------

def test_approved_no_pay_leave_is_deducted_in_the_draft():
    db = _PayrollDb()
    db.tables["employee_profile"] = [_staff(2, "Kamala", "Silva", 60000)]
    db.tables["leave_types"] = [{"id": 3, "is_paid": True}, {"id": 7, "is_paid": False}]
    db.tables["leave_requests"] = [
        {"id": 50, "employee_id": 2, "status": "Approved", "leave_type_id": 7, "start_date": "2026-10-05", "end_date": "2026-10-06"},
        {"id": 51, "employee_id": 2, "status": "Approved", "leave_type_id": 3, "start_date": "2026-10-07", "end_date": "2026-10-07"},  # paid sick
        {"id": 52, "employee_id": 2, "status": "Pending", "leave_type_id": 7, "start_date": "2026-10-08", "end_date": "2026-10-08"},
    ]
    db.tables["leave_request_days"] = [
        {"request_id": 50, "leave_date": "2026-10-05", "fraction": 1},
        {"request_id": 50, "leave_date": "2026-10-06", "fraction": 0.5},
        {"request_id": 51, "leave_date": "2026-10-07", "fraction": 1},
        {"request_id": 52, "leave_date": "2026-10-08", "fraction": 1},
    ]
    response = _send(db, "POST", "/api/hr/payroll/generate?month=10&year=2026")

    assert response.status_code == 200, response.text
    line = _lines_sent(db)[2]
    assert line["nopay_days"] == 1.5                      # approved and unpaid only
    assert line["nopay_deduction"] == 3000.0              # 1.5 x 60000 / 30
    assert line["gross"] == 57000.0 and line["net_payable"] == 52440.0


def test_a_leaver_is_paid_to_their_last_day_and_not_after():
    db = _PayrollDb()
    db.tables["employee_profile"] = [
        {**_staff(2, "Kamala", "Silva", 60000), "status": "Inactive", "date_left": "2026-10-10"},
        {**_staff(3, "Amal", "Perera", 60000), "status": "Inactive", "date_left": "2026-09-30"},
    ]
    _send(db, "POST", "/api/hr/payroll/generate?month=10&year=2026")

    lines = _lines_sent(db)
    assert set(lines) == {2}
    assert lines[2]["paid_days"] == 10 and lines[2]["basic"] == 20000.0


# --------------------------------------------------------------------------
# Payslips
# --------------------------------------------------------------------------

def _payslip_db(status="Approved"):
    db = _PayrollDb([_run(status=status)])
    db.tables["payroll_ledger"] = [_stored(7, "Hiru", "Officer", 60000)]
    db.tables["payroll_ledger"][0]["payroll_runs"] = {"id": 1, "payroll_month": 10, "payroll_year": 2026,
                                                      "status": status, "approved_at": "2026-11-02T05:00:00+00:00"}
    # acting_as signs in as USER_ID, linked to employee 7.
    db.tables["employee_profile"] = [{**_staff(7, "Hiru", "Officer", 60000), "user_id": USER_ID}]
    return db


def test_hr_downloads_anyones_payslip_as_a_pdf():
    response = _send(_payslip_db(), "GET", "/api/hr/payroll/runs/1/payslips/7")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert "payslip_2026-10_Hiru_Officer.pdf" in response.headers["content-disposition"]


def test_staff_cannot_use_the_hr_payslip_route():
    assert _send(_payslip_db(), "GET", "/api/hr/payroll/runs/1/payslips/7", role="General Staff").status_code == 403


def test_staff_list_and_download_their_own_approved_payslips():
    db = _payslip_db()
    listed = _send(db, "GET", "/api/hr/payroll/me/payslips", role="General Staff").json()
    assert [(p["run_id"], p["net_payable"]) for p in listed] == [(1, 55200.0)]

    response = _send(db, "GET", "/api/hr/payroll/me/payslips/1", role="General Staff")
    assert response.status_code == 200 and response.content.startswith(b"%PDF")


def test_staff_do_not_see_a_draft_payslip():
    db = _payslip_db(status="Draft")
    assert _send(db, "GET", "/api/hr/payroll/me/payslips", role="General Staff").json() == []
    assert _send(db, "GET", "/api/hr/payroll/me/payslips/1", role="General Staff").status_code == 404


def test_someone_not_on_the_payroll_has_no_payslip_there():
    db = _payslip_db()
    db.tables["employee_profile"] = [{**_staff(9, "Someone", "Else", 1), "user_id": USER_ID}]
    assert _send(db, "GET", "/api/hr/payroll/me/payslips/1", role="General Staff").status_code == 404


# --------------------------------------------------------------------------
# A leaver's last day on the employee record
# --------------------------------------------------------------------------

LEAVER = {"id": 2, "first_name": "Kamala", "last_name": "Silva", "nic": "925678123V", "base_salary": 65000,
          "status": "Inactive", "user_id": None, "date_joined": "2020-01-15", "date_left": "2026-10-10"}


def test_reactivating_clears_the_last_day():
    db = _Db([LEAVER])
    response = _send(db, "PUT", "/api/hr/employees/2", {"status": "Active"})

    assert response.status_code == 200, response.text
    assert response.json()["date_left"] is None


def test_the_last_day_cannot_be_before_joining():
    db = _Db([LEAVER])
    response = _send(db, "PUT", "/api/hr/employees/2", {"status": "Inactive", "date_left": "2019-12-31"})
    assert response.status_code == 400, response.text


def test_deactivating_records_the_last_day_and_epf_number():
    db = _Db([{**LEAVER, "status": "Active", "date_left": None}])
    response = _send(db, "PUT", "/api/hr/employees/2",
                     {"status": "Inactive", "date_left": "2026-11-20", "epf_number": " EPF-0042 "})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["date_left"] == "2026-11-20" and body["epf_number"] == "EPF-0042"
