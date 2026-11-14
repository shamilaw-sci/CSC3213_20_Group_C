"""Personal updates (migration 032, app/services/notifications.py,
app/api/notifications.py).

Confirmed 2026-11-13: in-app only, for four decisions: leave decided,
attendance correction decided, a rescue case assigned to you by someone
else, and your payslip ready. Fail-soft, never about your own action, and
each person reads and marks only their own.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api import hr, leave, rescue_cases
from app.core.security import get_current_user
from app.core.supabase import get_supabase
from app.main import app
from app.services import notifications as service
from tests.test_inventory import _FakeDB, client

ME, SOMEONE = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"


# --------------------------------------------------------------------------
# notify()
# --------------------------------------------------------------------------

class _Inserts:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def table(self, name):
        outer = self

        class _Q:
            def insert(self, rows, **kw):
                outer.calls.append((name, rows, kw))
                return self

            def execute(self):
                if outer.fail:
                    raise RuntimeError("table missing")

        return _Q()


def test_notify_skips_the_actor_and_duplicates_and_asks_for_nothing_back():
    db = _Inserts()
    service.notify(db, [SOMEONE, ME, SOMEONE, None], actor_id=ME, kind="leave_decided",
                   title="Your leave was approved", body="Annual leave, 3 Dec 2026.", href="/me/leave")

    ((table, rows, kw),) = db.calls
    assert table == "notifications"
    assert rows == [{"user_id": SOMEONE, "kind": "leave_decided", "title": "Your leave was approved",
                     "body": "Annual leave, 3 Dec 2026.", "href": "/me/leave"}]
    # The writer can't read the recipient's row back under RLS.
    assert kw["returning"].value == "minimal"


def test_notify_about_only_your_own_action_writes_nothing():
    db = _Inserts()
    service.notify(db, [ME], actor_id=ME, kind="case_assigned", title="x")
    assert db.calls == []


def test_a_failed_write_is_swallowed():
    service.notify(_Inserts(fail=True), [SOMEONE], actor_id=ME, kind="payslip_ready", title="x")


def test_dates_read_naturally():
    assert service.date_range("2026-12-03", "2026-12-03") == "3 Dec 2026"
    assert service.date_range("2026-11-23", "2026-11-27") == "23 Nov 2026 to 27 Nov 2026"


# --------------------------------------------------------------------------
# The decisions
# --------------------------------------------------------------------------

@pytest.fixture
def sent(monkeypatch):
    """Capture notify() wherever it is called from."""
    calls = []

    def _capture(supabase, recipients, **kw):
        calls.append({"to": [str(r) for r in recipients if r], **kw})
    for module in (hr, leave, rescue_cases):
        monkeypatch.setattr(module, "notify", _capture)
    return calls


def test_an_approved_correction_tells_the_employee(sent):
    from tests.test_attendance_corrections import _hr_db, _hr_pending, _record, _send
    db = _hr_db([_record()], [_hr_pending()])
    assert _send(db, "POST", "/api/hr/attendance/corrections/5/approve", {}).status_code == 200

    (n,) = sent
    assert n["to"] == [SOMEONE]  # Amal's login in this fixture
    assert n["kind"] == "correction_decided" and n["href"] == "/me/attendance"
    assert n["title"] == "Your attendance correction for 10 Nov 2026 was approved"


def test_a_rejected_correction_carries_the_reason(sent):
    from tests.test_attendance_corrections import _hr_db, _hr_pending, _record, _send
    db = _hr_db([_record()], [_hr_pending()])
    _send(db, "POST", "/api/hr/attendance/corrections/5/reject", {"note": "Gate log shows 16:00"})

    (n,) = sent
    assert n["title"].endswith("was rejected") and n["body"] == "Reason: Gate log shows 16:00"


def test_a_refused_decision_sends_nothing(sent):
    from tests.test_attendance_corrections import _hr_db, _hr_pending, _record, _send
    db = _hr_db([_record()], [_hr_pending()])
    assert _send(db, "POST", "/api/hr/attendance/corrections/5/reject", {"note": " "}).status_code == 400
    assert sent == []


@pytest.fixture
def employees_logins(monkeypatch):
    """The recording fakes ignore filters, so map employees to logins here."""
    logins = {7: ME, 8: SOMEONE}
    for module in (hr, leave):
        monkeypatch.setattr(module, "users_of_employees", lambda sb, ids: [logins[i] for i in ids if i in logins])


def test_leave_decisions_tell_the_employee(sent, employees_logins):
    from tests.test_leave import PENDING_DAYS, _db, _pending, _send
    assert _send("HR Officer", _db(_pending(), PENDING_DAYS), "POST",
                 "/api/leave/requests/100/approve", json={}).status_code == 200
    assert _send("HR Officer", _db(_pending(), PENDING_DAYS), "POST",
                 "/api/leave/requests/100/reject", json={"note": "Clinic week"}).status_code == 200

    approved, rejected = sent
    assert approved["to"] == [SOMEONE] and approved["kind"] == "leave_decided"
    assert approved["title"] == "Your leave was approved"
    assert approved["body"] == "Annual leave, 23 Nov 2026 to 27 Nov 2026."
    assert rejected["title"] == "Your leave was rejected"
    assert rejected["body"].endswith("Reason: Clinic week")


def test_an_approved_payroll_tells_everyone_on_it(sent, employees_logins, monkeypatch):
    from tests.test_payroll_approval import APPROVED, WITH_DRAFT, _Rpc, _send
    monkeypatch.setattr(hr, "_stored_lines", lambda sb, run_id: [{"employee_id": 7}, {"employee_id": 8}])
    monkeypatch.setattr(hr, "drift", lambda stored, fresh: [])
    response = _send("Director", _Rpc(tables=WITH_DRAFT, result=[APPROVED]), "POST", "/api/hr/payroll/runs/3/approve")

    assert response.status_code == 200, response.text
    (n,) = sent
    # Both, including the approver's own line: notify() itself drops the actor.
    assert n["to"] == [ME, SOMEONE] and n["kind"] == "payslip_ready"
    assert n["title"] == "Your payslip for October 2026 is ready" and n["href"] == "/me/payslips"


def test_case_assignment_tells_the_assignee(sent):
    from tests.test_rbac_matrix import CASE_ID, _case_row, acting_as
    tables = {"rescue_cases": {
        "select": [{"status": "Reported", "assigned_to": None}],
        "update": [_case_row(status="In Treatment", assigned_to=SOMEONE)],
    }}
    with acting_as("Director", tables=tables):
        response = client.patch(f"/api/rescue_cases/cases/{CASE_ID}/status",
                                json={"new_status": "In Treatment", "assigned_to": SOMEONE})

    assert response.status_code == 200, response.text
    (n,) = sent
    assert n["to"] == [SOMEONE] and n["kind"] == "case_assigned" and n["href"] == "/case-triage"
    assert n["title"] == "You were assigned a Dog case"


def test_a_move_that_keeps_the_assignee_sends_nothing(sent):
    from tests.test_rbac_matrix import CASE_ID, _case_row, acting_as
    tables = {"rescue_cases": {
        "select": [{"status": "In Treatment", "assigned_to": SOMEONE}],
        "update": [_case_row(status="Reported", assigned_to=None)],
    }}
    with acting_as("Admin", tables=tables):
        client.patch(f"/api/rescue_cases/cases/{CASE_ID}/status", json={"new_status": "Reported"})
    assert sent == []


# --------------------------------------------------------------------------
# Reading your own
# --------------------------------------------------------------------------

def _inbox_db():
    db = _FakeDB()
    db.tables["notifications"] = [
        {"id": 1, "user_id": ME, "kind": "leave_decided", "title": "Your leave was approved",
         "created_at": "2026-11-13T05:00:00+00:00", "read_at": None},
        {"id": 2, "user_id": ME, "kind": "payslip_ready", "title": "Payslip",
         "created_at": "2026-11-12T05:00:00+00:00", "read_at": "2026-11-12T06:00:00+00:00"},
        {"id": 3, "user_id": SOMEONE, "kind": "case_assigned", "title": "Not yours",
         "created_at": "2026-11-13T06:00:00+00:00", "read_at": None},
    ]
    return db


def _call(db, method, path):
    async def _user():
        return {"id": ME, "roles": {"role_name": "General Staff"}}

    async def _sb():
        return db
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_supabase] = _sb
    try:
        return client.request(method, path)
    finally:
        app.dependency_overrides.clear()


def test_you_see_only_your_own_with_the_unread_count():
    r = _call(_inbox_db(), "GET", "/api/notifications")
    assert r.status_code == 200, r.text
    assert [n["id"] for n in r.json()["items"]] == [1, 2]
    assert r.json()["unread"] == 1


def test_marking_one_read():
    db = _inbox_db()
    r = _call(db, "POST", "/api/notifications/1/read")
    assert r.status_code == 200 and r.json()["read_at"]
    assert db.tables["notifications"][0]["read_at"]


def test_someone_elses_is_not_found_and_stays_unread():
    db = _inbox_db()
    assert _call(db, "POST", "/api/notifications/3/read").status_code == 404
    assert db.tables["notifications"][2]["read_at"] is None


def test_mark_all_read_touches_only_yours():
    db = _inbox_db()
    r = _call(db, "POST", "/api/notifications/read-all")
    assert r.json() == {"marked": 1}
    assert db.tables["notifications"][0]["read_at"] and db.tables["notifications"][2]["read_at"] is None


def test_notifications_need_a_signed_in_user():
    assert client.get("/api/notifications").status_code in (401, 403)


def test_payroll_still_approves_when_its_lines_cannot_be_listed(sent, monkeypatch):
    from tests.test_payroll_approval import APPROVED, WITH_DRAFT, _Rpc, _send
    calls = {"n": 0}

    def _lines(sb, run_id):
        calls["n"] += 1
        if calls["n"] > 1:  # the drift check reads them first; the notice second
            raise RuntimeError("payroll_ledger unavailable")
        return []
    monkeypatch.setattr(hr, "_stored_lines", _lines)
    monkeypatch.setattr(hr, "drift", lambda stored, fresh: [])
    response = _send("Director", _Rpc(tables=WITH_DRAFT, result=[APPROVED]), "POST", "/api/hr/payroll/runs/3/approve")

    assert response.status_code == 200, response.text
    assert sent[0]["to"] == []
