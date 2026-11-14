"""When payroll may be generated and approved, and by whom (app/api/hr.py).

Defects found testing the Payroll page on 2026-11-11:

  * a month could be generated and approved before it started (a December
    draft existed in mid-November) or long before it ended (November was
    approved on the 3rd);
  * an out-of-date draft could be approved; the page now lists what changed
    (the SQL check itself is migration 025);
  * "Paid in Ledger" never showed as done;
  * an Admin generated a draft, promoted a General Staff account to Admin,
    and that account approved it a minute later.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api import hr
from app.schemas.hr import SRI_LANKA
from tests.test_employees import _Db, _Result, _send
from tests.test_rbac_matrix import USER_ID

GENERATOR = "99999999-9999-9999-9999-999999999999"


def _at(day, month=11, hh=10):
    return datetime(2026, month, day, hh, 0, tzinfo=SRI_LANKA)


@pytest.fixture
def clock(monkeypatch):
    def set_to(moment):
        monkeypatch.setattr(hr, "_sl_now", lambda: moment)
    set_to(_at(11))
    return set_to


class _PayrollDb(_Db):
    """_Db plus the two payroll RPCs: records calls, returns canned rows."""

    def __init__(self, runs=(), drift=None, drift_error=None, audit=()):
        super().__init__([])
        self.tables["payroll_runs"] = [dict(r) for r in runs]
        self.tables["system_audit_logs"] = [dict(a) for a in audit]
        self.rpc_calls = []
        self.rpc_params = []
        self._drift, self._drift_error = drift or [], drift_error

    def rpc(self, name, params=None):
        self.rpc_calls.append(name)
        self.rpc_params.append((name, params))
        db = self

        class _Call:
            def execute(self):
                if name == "payroll_draft_drift":
                    if db._drift_error:
                        raise db._drift_error
                    return _Result(db._drift)
                run = {**db.tables["payroll_runs"][0], "status": "Approved"} if db.tables["payroll_runs"] else \
                    {"id": 1, "payroll_month": params.get("p_month"), "payroll_year": params.get("p_year"),
                     "status": "Draft", "total": 100}
                return _Result([run])

        return _Call()


def _run(month=10, status="Draft", generated_by=GENERATOR, **extra):
    return {"id": 1, "payroll_month": month, "payroll_year": 2026, "status": status,
            "total": 100000, "generated_by": generated_by, **extra}


def _approve(db, role="Director"):
    return _send(db, "POST", "/api/hr/payroll/runs/1/approve", role=role)


# --------------------------------------------------------------------------
# When a month can be generated and approved
# --------------------------------------------------------------------------

def test_a_month_that_has_not_started_cannot_be_generated(clock):
    db = _PayrollDb()
    response = _send(db, "POST", "/api/hr/payroll/generate?month=12&year=2026")

    assert response.status_code == 400, response.text
    assert "before the month starts" in response.json()["detail"]
    assert db.rpc_calls == []


@pytest.mark.parametrize("month", [10, 11])
def test_the_current_and_past_months_can_be_generated(clock, month):
    db = _PayrollDb()
    assert _send(db, "POST", f"/api/hr/payroll/generate?month={month}&year=2026").status_code == 200


def test_a_future_draft_cannot_be_approved(clock):
    db = _PayrollDb([_run(month=12)])
    response = _approve(db)

    assert response.status_code == 400, response.text
    assert db.rpc_calls == []


def test_the_current_month_is_not_approved_before_the_25th(clock):
    db = _PayrollDb([_run(month=11)])
    response = _approve(db)

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Payroll for November 2026 can be approved from 25 November."
    assert db.rpc_calls == []


def test_the_current_month_can_be_approved_from_the_25th(clock):
    clock(_at(25))
    db = _PayrollDb([_run(month=11)])
    assert _approve(db).status_code == 200


def test_a_past_month_can_be_approved_any_day(clock):
    db = _PayrollDb([_run(month=10)])
    assert _approve(db).status_code == 200


def test_the_run_view_says_when_it_can_be_generated_and_approved(clock):
    body = _send(_PayrollDb(), "GET", "/api/hr/payroll/run?month=11&year=2026").json()
    assert body["generate_block"] is None
    assert body["approve_block"] == "Payroll for November 2026 can be approved from 25 November."

    future = _send(_PayrollDb(), "GET", "/api/hr/payroll/run?month=12&year=2026").json()
    assert "before the month starts" in future["generate_block"]


# --------------------------------------------------------------------------
# An approver whose role the generator just changed
# --------------------------------------------------------------------------

def _role_change(by, target, hours_ago):
    return {
        "action_type": "USER_ROLE_CHANGE", "user_id": by,
        "old_payload": {"id": target, "role_id": 6}, "new_payload": {"id": target, "role_id": 1},
        "timestamp": (_at(11) - timedelta(hours=hours_ago)).astimezone(timezone.utc).isoformat(),
    }


def test_an_approver_promoted_by_the_generator_today_is_refused(clock):
    db = _PayrollDb([_run()], audit=[_role_change(GENERATOR, USER_ID, hours_ago=1)])
    response = _approve(db, role="Admin")

    assert response.status_code == 403, response.text
    assert "role was changed" in response.json()["detail"]
    assert "approve_payroll_run" not in db.rpc_calls


def test_a_role_change_older_than_a_day_does_not_count(clock):
    db = _PayrollDb([_run()], audit=[_role_change(GENERATOR, USER_ID, hours_ago=30)])
    assert _approve(db, role="Admin").status_code == 200


def test_a_role_change_by_someone_else_does_not_count(clock):
    db = _PayrollDb([_run()], audit=[_role_change("88888888-8888-8888-8888-888888888888", USER_ID, hours_ago=1)])
    assert _approve(db, role="Admin").status_code == 200


# --------------------------------------------------------------------------
# What the run view shows
# --------------------------------------------------------------------------

def _staff(id, first, last, base, joined="2020-01-01"):
    return {"id": id, "first_name": first, "last_name": last, "nic": None, "epf_number": None,
            "base_salary": base, "status": "Active", "date_joined": joined, "date_left": None}


def _stored(employee_id, first, last, base):
    """A draft line as generated at `base` for a full month."""
    gross = float(base)
    return {"id": employee_id + 500, "run_id": 1, "employee_id": employee_id,
            "employee_profile": {"first_name": first, "last_name": last},
            "days_in_month": 31, "paid_days": 31, "basic": gross, "nopay_days": 0, "nopay_deduction": 0,
            "gross": gross, "epf_employee": round(gross * 0.08, 2), "epf_employer": round(gross * 0.12, 2),
            "etf": round(gross * 0.03, 2), "net_payable": round(gross * 0.92, 2)}


def _drifted_db():
    # Drafted with Kamala on 65000 and no Thilini; now Kamala earns 70000
    # and Thilini has been added.
    db = _PayrollDb([_run()])
    db.tables["employee_profile"] = [_staff(2, "Kamala", "Silva", 70000), _staff(31, "Thilini", "Perera", 100000)]
    db.tables["payroll_ledger"] = [_stored(2, "Kamala", "Silva", 65000)]
    return db


def test_an_out_of_date_draft_lists_what_changed(clock):
    drift = _send(_drifted_db(), "GET", "/api/hr/payroll/run?month=10&year=2026").json()["drift"]

    assert [(d["employee_name"], d["change"]) for d in drift] == [("Thilini Perera", "added"), ("Kamala Silva", "changed")]
    assert drift[1]["draft_amount"] == 59800.0 and drift[1]["current_amount"] == 64400.0


def test_an_out_of_date_draft_cannot_be_approved(clock):
    db = _drifted_db()
    response = _approve(db)

    assert response.status_code == 409, response.text
    assert "2 employees have changed" in response.json()["detail"]
    assert "approve_payroll_run" not in db.rpc_calls


def test_a_current_draft_is_approved_with_its_generated_at(clock):
    db = _PayrollDb([_run(generated_at="2026-11-01T05:00:00+00:00")])
    db.tables["employee_profile"] = [_staff(2, "Kamala", "Silva", 65000)]
    db.tables["payroll_ledger"] = [_stored(2, "Kamala", "Silva", 65000)]

    assert _approve(db).status_code == 200
    assert db.rpc_calls == ["approve_payroll_run"]


@pytest.mark.parametrize("status", ["Cash", "Receivable"])
def test_the_run_view_says_whether_the_payable_is_paid(clock, status):
    db = _PayrollDb([_run(status="Approved", finance_transaction_id=44)])
    db.tables["financial_transactions"] = [{"id": 44, "status": status}]
    body = _send(db, "GET", "/api/hr/payroll/run?month=10&year=2026").json()

    assert body["payment_status"] == status
    assert body["drift"] is None  # only drafts are compared
