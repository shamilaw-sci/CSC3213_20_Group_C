"""Payroll approval and attendance locking.

Each test pins a defect that was live before it:

  * "Approve & Finalize" only showed a toast; no route enforced
    payroll:approve, and Generate posted salaries to the ledger at once;
  * one unlocked attendance record blocked the whole month's payroll,
    though pay is a fixed salary that attendance does not change;
  * clocking out locked the record, nothing could unlock it, and HR could
    not correct a wrong time;
  * locking a day froze records with no clock-out, blank hours and all.

The SQL functions themselves (migration 007) cannot run against this
Supabase double; these tests pin what the API sends them and how it maps
what they raise.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api.hr import _sl_today
from app.core.permissions import has_permission
from app.core.supabase import get_supabase
from app.main import app
from tests.test_ledger_integrity import _RecordingSupabase
from tests.test_rbac_matrix import ALL_ROLES, USER_ID, _FakeResult, _request, acting_as

DRAFT = {
    "id": 3, "payroll_month": 10, "payroll_year": 2026, "status": "Draft",
    "total": 155000, "generated_by": "someone-else",
}
APPROVED = {**DRAFT, "status": "Approved", "approved_by": USER_ID}
# The approve endpoint reads the run first, for its month and generator.
WITH_DRAFT = {"payroll_runs": {"select": [DRAFT]}}


class _Rpc(_RecordingSupabase):
    """Records RPC calls; returns `result` or raises `error`."""

    def __init__(self, tables=None, result=None, error=None):
        super().__init__(tables or {})
        self.rpc_calls = []
        self._result = result
        self._error = error

    def rpc(self, name, params=None):
        self.rpc_calls.append((name, params))
        outer = self

        class _Call:
            def execute(self):
                if outer._error:
                    raise Exception(outer._error)
                return _FakeResult(outer._result)

        return _Call()


def _send(role, supabase, method, path):
    with acting_as(role):
        app.dependency_overrides[get_supabase] = lambda: supabase
        return _request(method, path)


def _inserted(supabase, table):
    return [d for t, d in supabase.inserts if t == table]


# --------------------------------------------------------------------------
# Generate
# --------------------------------------------------------------------------

def test_generate_makes_a_draft_and_posts_nothing_to_the_ledger():
    supabase = _Rpc(result=[DRAFT])
    response = _send("HR Officer", supabase, "POST", "/api/hr/payroll/generate?month=10&year=2026")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "Draft"
    assert supabase.rpc_calls == [
        # The engine's lines: none here, as the fake has no employees.
        ("generate_payroll_draft", {"p_month": 10, "p_year": 2026, "p_user": USER_ID, "p_lines": [],
                                    "p_absence_months": None}),
    ]
    assert _inserted(supabase, "financial_transactions") == []


def test_generate_is_not_blocked_by_unlocked_attendance():
    # It used to 422 here. Pay is a fixed monthly salary, so an open
    # attendance record changes nothing about it.
    supabase = _Rpc(
        tables={"attendance_log": {"select": [{"id": 1, "is_locked": False, "clock_out": None}]}},
        result=[DRAFT],
    )
    response = _send("HR Officer", supabase, "POST", "/api/hr/payroll/generate?month=10&year=2026")
    assert response.status_code == 200, response.text


def test_regenerating_an_approved_month_is_refused():
    supabase = _Rpc(error="{'message': 'Payroll for 10/2026 is already approved and cannot be regenerated.'}")
    response = _send("HR Officer", supabase, "POST", "/api/hr/payroll/generate?month=10&year=2026")
    assert response.status_code == 409, response.text


@pytest.mark.parametrize("query", ["month=13&year=2026", "month=0&year=2026", "month=5&year=1999"])
def test_generate_rejects_an_impossible_month(query):
    supabase = _Rpc(result=[DRAFT])
    assert _send("HR Officer", supabase, "POST", f"/api/hr/payroll/generate?{query}").status_code == 400
    assert supabase.rpc_calls == []


# --------------------------------------------------------------------------
# Approve
# --------------------------------------------------------------------------

@pytest.mark.parametrize("role", ALL_ROLES)
def test_only_payroll_approve_holders_can_approve(role):
    supabase = _Rpc(tables=WITH_DRAFT, result=[APPROVED])
    response = _send(role, supabase, "POST", "/api/hr/payroll/runs/3/approve")
    if has_permission(role, "payroll:approve"):
        assert response.status_code == 200, response.text
        assert supabase.rpc_calls == [("approve_payroll_run", {"p_run_id": 3, "p_user": USER_ID, "p_generated_at": None,
                                                                 "p_close_ids": []})]
    else:
        assert response.status_code == 403
        assert supabase.rpc_calls == []


def test_hr_generates_and_director_approves_matches_the_permissions():
    # The confirmed policy, as the permission table encodes it.
    assert has_permission("HR Officer", "payroll:generate")
    assert not has_permission("HR Officer", "payroll:approve")
    assert has_permission("Director", "payroll:approve")
    assert not has_permission("Director", "payroll:generate")
    # HR generates, not Finance (confirmed 2026-11-11).
    assert not has_permission("Finance Officer", "payroll:generate")


@pytest.mark.parametrize("raised, status", [
    ("Payroll must be approved by someone other than the person who generated it.", 403),
    ("Payroll for 10/2026 is already approved.", 409),
    ("Payroll run 99 not found.", 404),
    ("Payroll for 10/2026 has nothing to pay.", 400),
    ("The payroll draft for 10/2026 is out of date: employees or salaries have changed since it was generated. Regenerate it before approving.", 409),
    ("connection reset", 500),
])
def test_approval_errors_map_to_statuses(raised, status):
    response = _send("Director", _Rpc(tables=WITH_DRAFT, error=raised), "POST", "/api/hr/payroll/runs/3/approve")
    assert response.status_code == status, response.text


def test_approval_is_audited_with_a_stable_total():
    supabase = _Rpc(tables=WITH_DRAFT, result=[APPROVED])
    _send("Director", supabase, "POST", "/api/hr/payroll/runs/3/approve")
    rows = [d for d in _inserted(supabase, "system_audit_logs") if d["action_type"] == "PAYROLL_APPROVE"]
    assert len(rows) == 1
    # A string, so the hash survives JSONB turning 155000.0 into 155000.
    assert rows[0]["new_payload"]["total"] == "155000.00"


# --------------------------------------------------------------------------
# Reading a run
# --------------------------------------------------------------------------

def test_run_view_lists_lines_and_counts_incomplete_attendance():
    supabase = _Rpc(tables={
        "payroll_runs": {"select": [DRAFT]},
        "payroll_ledger": {"select": [
            {"id": 1, "employee_id": 7, "net_payable": 90000,
             "employee_profile": {"first_name": "Zara", "last_name": "Perera", "nic": "N1"}},
            {"id": 2, "employee_id": 8, "net_payable": 65000,
             "employee_profile": {"first_name": "Amal", "last_name": "Silva", "nic": "N2"}},
        ]},
        "attendance_log": {"select": [
            {"id": 1, "clock_in": "2026-10-01T03:00:00Z", "clock_out": "2026-10-01T11:00:00Z"},
            {"id": 2, "clock_in": "2026-10-02T03:00:00Z", "clock_out": None},
        ]},
    })
    response = _send("Director", supabase, "GET", "/api/hr/payroll/run?month=10&year=2026")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run"]["status"] == "Draft"
    assert [l["employee_name"] for l in body["lines"]] == ["Amal Silva", "Zara Perera"]
    assert body["incomplete_attendance"] == 1


def test_run_view_with_no_run_yet():
    response = _send("HR Officer", _Rpc(), "GET", "/api/hr/payroll/run?month=10&year=2026")
    assert response.status_code == 200
    assert response.json() == {
        "run": None, "lines": [], "incomplete_attendance": 0,
        "drift": None, "payables": [], "payment_status": None, "generate_block": None, "approve_block": None,
    }


@pytest.mark.parametrize("role", ALL_ROLES)
def test_run_view_needs_generate_or_approve(role):
    response = _send(role, _Rpc(), "GET", "/api/hr/payroll/run?month=10&year=2026")
    allowed = has_permission(role, "payroll:generate") or has_permission(role, "payroll:approve")
    assert (response.status_code != 403) == allowed, (role, response.status_code)


# --------------------------------------------------------------------------
# Attendance locking
# --------------------------------------------------------------------------

def test_clock_out_does_not_lock_the_record():
    supabase = _Rpc(tables={
        "employee_profile": {"select": [{"id": 7, "user_id": USER_ID}]},
        "attendance_log": {
            "select": [{"id": 5, "employee_id": 7, "target_date": _sl_today().isoformat(),
                        "clock_in": "2026-10-29T03:00:00+00:00", "clock_out": None, "is_locked": False}],
            "update": [{"id": 5}],
        },
    })
    response = _send("HR Officer", supabase, "POST", "/api/hr/attendance/clock-out")

    assert response.status_code == 200, response.text
    (written,) = [d for t, d in supabase.updates if t == "attendance_log"]
    assert "is_locked" not in written
    assert written["clock_out"] and written["worked_hours"] is not None


def test_lock_day_skips_records_without_a_clock_out():
    supabase = _Rpc(tables={"attendance_log": {
        "select": [
            {"id": 1, "clock_in": "x", "clock_out": "y", "is_locked": False},
            {"id": 2, "clock_in": "x", "clock_out": None, "is_locked": False},
            {"id": 3, "clock_in": "x", "clock_out": "y", "is_locked": True},
        ],
        "update": [{"id": 1}],
    }})
    response = _send("HR Officer", supabase, "POST", "/api/hr/attendance/lock-day?target_date=2026-10-29")

    assert response.status_code == 200, response.text
    assert response.json()["updated_count"] == 1
    assert response.json()["skipped_incomplete"] == 1
    assert [d for t, d in supabase.updates if t == "attendance_log"] == [{"is_locked": True}]


def test_lock_day_with_nothing_complete_writes_nothing():
    supabase = _Rpc(tables={"attendance_log": {"select": [
        {"id": 2, "clock_in": "x", "clock_out": None, "is_locked": False},
    ]}})
    response = _send("HR Officer", supabase, "POST", "/api/hr/attendance/lock-day?target_date=2026-10-29")
    assert response.json()["updated_count"] == 0
    assert supabase.updates == []


def _locked(record_date="2026-10-05"):
    return {"id": 9, "employee_id": 7, "target_date": record_date, "clock_in": None,
            "clock_out": None, "worked_hours": 8, "is_locked": True}


def test_unlock_reopens_a_locked_record():
    supabase = _Rpc(tables={
        "attendance_log": {"select": [_locked()], "update": [{**_locked(), "is_locked": False}]},
        "payroll_runs": {"select": [DRAFT]},
    })
    response = _send("HR Officer", supabase, "POST", "/api/hr/attendance/9/unlock")
    assert response.status_code == 200, response.text
    assert [d for t, d in supabase.updates if t == "attendance_log"] == [{"is_locked": False}]


def test_unlock_is_refused_once_the_month_is_approved():
    supabase = _Rpc(tables={
        "attendance_log": {"select": [_locked()]},
        "payroll_runs": {"select": [APPROVED]},
    })
    response = _send("HR Officer", supabase, "POST", "/api/hr/attendance/9/unlock")
    assert response.status_code == 409, response.text
    assert supabase.updates == []


def test_unlock_of_an_unlocked_record_is_a_400():
    supabase = _Rpc(tables={"attendance_log": {"select": [{**_locked(), "is_locked": False}]}})
    assert _send("HR Officer", supabase, "POST", "/api/hr/attendance/9/unlock").status_code == 400


def test_unlock_needs_attendance_management():
    assert _send("Director", _Rpc(), "POST", "/api/hr/attendance/9/unlock").status_code == 403
