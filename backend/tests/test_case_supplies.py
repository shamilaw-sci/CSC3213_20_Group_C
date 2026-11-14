"""Supplies used on a rescue case, and the monthly outcomes report
(app/api/inventory.py, app/api/rescue_cases.py, migration 031).

Confirmed 2026-11-13:

  * anyone who can issue stock (inventory:issue or inventory:manage) can
    issue it to a rescue case;
  * Issue only, no returns from a case; a mistake is undone with Reverse,
    which keeps the case (a trigger in 031), so the case's cost is its
    Stock Outs less their reversals;
  * open cases only, and a program or a case, never both;
  * the report counts the cases resolved in a month (Sri Lanka time), by
    outcome, with all their supplies.
"""

import os
import sys

import pytest
from postgrest.exceptions import APIError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.permissions import has_permission
from app.core.security import get_current_user
from app.core.supabase import get_supabase
from app.main import app
from tests.test_case_timeline import _db as _timeline_db
from tests.test_employees import _send
from tests.test_inventory import ITEM, TODAY, USER_ID, _FakeDB, _Query, client
from tests.test_rbac_matrix import ALL_ROLES, CASE_ID, OTHER_USER_ID

OPEN_CASE = {"id": CASE_ID, "animal_type": "Dog", "status": "In Treatment"}


# --------------------------------------------------------------------------
# Issuing to a case
# --------------------------------------------------------------------------

@pytest.fixture
def db():
    db = _FakeDB(items=[ITEM])
    db.tables["rescue_cases"] = [dict(OPEN_CASE)]
    return db


@pytest.fixture
def act(db):
    def _as(role="General Staff"):
        async def _user():
            return {"id": USER_ID, "roles": {"role_name": role}}

        async def _sb():
            return db
        app.dependency_overrides[get_current_user] = _user
        app.dependency_overrides[get_supabase] = _sb
    yield _as
    app.dependency_overrides.clear()


def _issue(**overrides):
    body = {"item_id": 1, "quantity": 2, "transaction_type": "Issue", "transaction_date": TODAY,
            "rescue_case_id": CASE_ID}
    body.update(overrides)
    return client.post("/api/inventory/transactions", json=body)


def _movement_function_saves(db):
    """The 031 movement function, answering as the database would."""
    db.rpc_result = {"transaction_id": 501, "item_id": 1, "program_id": None, "rescue_case_id": CASE_ID,
                     "quantity": 2, "transaction_type": "Issue", "transaction_date": TODAY,
                     "total_cost": 3000.0, "stock_before": 10, "stock_after": 8}


def test_staff_issue_supplies_to_an_open_case_without_a_program(act, db):
    act("General Staff")  # inventory:issue only: the Issue page's role
    _movement_function_saves(db)
    r = _issue(notes="For the wound")

    assert r.status_code == 200, r.text
    assert r.json()["rescue_case_id"] == CASE_ID
    ((name, params),) = db.rpc_calls
    assert name == "inventory_apply_movement"
    assert params["p_rescue_case_id"] == CASE_ID and params["p_program_id"] is None
    assert db.tables["system_audit_logs"][-1]["action_type"] == "INVENTORY_ISSUE"


def test_a_movement_without_a_case_does_not_send_one():
    """So a database without 031 still takes the locked path for every
    other movement."""
    db = _FakeDB(items=[ITEM], programs=[{"id": 7, "program_name": "Clinic", "status": "Active"}])
    _movement_function_saves(db)

    async def _user():
        return {"id": USER_ID, "roles": {"role_name": "Operations Lead"}}

    async def _sb():
        return db
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_supabase] = _sb
    try:
        client.post("/api/inventory/transactions", json={
            "item_id": 1, "program_id": 7, "quantity": 1, "transaction_type": "Issue", "transaction_date": TODAY})
    finally:
        app.dependency_overrides.clear()
    ((_, params),) = db.rpc_calls
    assert "p_rescue_case_id" not in params


def test_without_migration_031_a_case_issue_is_refused_and_stock_is_untouched(act, db):
    act()
    r = _issue()  # the fake has no movement function, as before 031

    assert r.status_code == 503
    assert "031_case_supplies.sql" in r.json()["detail"]
    assert db.stock(1) == 10 and db.movements() == []


@pytest.mark.parametrize("body, code, needle", [
    ({"transaction_type": "Return"}, 400, "only be issued"),
    ({"transaction_type": "Restock"}, 400, "only be issued"),
    ({"program_id": 7}, 400, "not both"),
], ids=["return", "stock-in", "with-program"])
def test_only_a_plain_issue_goes_to_a_case(act, db, body, code, needle):
    act("Operations Lead")
    r = _issue(**body)

    assert r.status_code == code, r.text
    assert needle in r.json()["detail"]
    assert db.rpc_calls == [] and db.stock(1) == 10


def test_a_resolved_case_takes_no_supplies(act, db):
    db.tables["rescue_cases"][0]["status"] = "Resolved"
    act()
    r = _issue()

    assert r.status_code == 400
    assert "Reopen" in r.json()["detail"]
    assert db.rpc_calls == []


def test_an_unknown_case_is_404(act, db):
    db.tables["rescue_cases"] = []
    act()
    assert _issue().status_code == 404


@pytest.mark.parametrize("role", ALL_ROLES)
def test_anyone_who_can_issue_stock_can_issue_to_a_case(act, db, role):
    act(role)
    _movement_function_saves(db)
    r = _issue()

    can = has_permission(role, "inventory:issue") or has_permission(role, "inventory:manage")
    assert (r.status_code == 200) == can, (role, r.status_code, r.text)
    if not can:
        assert r.status_code == 403


def test_the_stock_page_names_the_case_a_movement_was_used_on(act, db):
    db.tables["inventory_transactions"] = [
        {"transaction_id": 9, "item_id": 1, "program_id": None, "rescue_case_id": CASE_ID, "quantity": 2,
         "transaction_type": "Issue", "transaction_date": TODAY, "total_cost": 3000.0},
    ]
    act("Operations Lead")
    r = client.get("/api/inventory/transactions")

    assert r.status_code == 200, r.text
    assert r.json()[0]["rescue_case"] == {"animal_type": "Dog", "status": "In Treatment"}


# --------------------------------------------------------------------------
# Supplies on the timeline
# --------------------------------------------------------------------------

def _supply(id, kind="Issue", qty=2, cost=3000.0, created_at="2026-01-01T03:00:00+00:00", **extra):
    return {"transaction_id": id, "rescue_case_id": CASE_ID, "item_id": 1, "quantity": qty,
            "transaction_type": kind, "transaction_date": "2026-01-01", "total_cost": cost,
            "created_at": created_at, "recorded_by": OTHER_USER_ID, "notes": None,
            "inventory_items": {"item_name": "Amoxicillin"}, **extra}


def test_supplies_and_their_reversal_sit_among_the_notes_in_time_order():
    db = _timeline_db(events=[
        {"id": 1, "case_id": CASE_ID, "event_type": "note", "body": "Vet visit",
         "author_id": USER_ID, "created_at": "2026-01-01T02:00:00+00:00"},
        {"id": 2, "case_id": CASE_ID, "event_type": "note", "body": "Wrong dose recorded",
         "author_id": USER_ID, "created_at": "2026-01-01T04:00:00+00:00"},
    ])
    db.tables["inventory_transactions"] = [
        _supply(9, notes="Two tablets"),
        _supply(10, kind="Return", created_at="2026-01-01T05:00:00+00:00", reverses_id=9),
    ]
    r = _send(db, "GET", f"/api/rescue_cases/cases/{CASE_ID}/timeline", role="Director")

    assert r.status_code == 200, r.text
    lines = r.json()
    assert [line["event_type"] for line in lines] == [
        "reported", "note", "supplies", "note", "supplies_reversed"]
    used = lines[2]
    assert (used["id"], used["item_name"], used["quantity"], used["cost"], used["body"]) == (
        9, "Amoxicillin", 2, 3000.0, "Two tablets")
    assert used["author"]["display_name"] == "Nimal Perera"


def test_supplies_recorded_by_a_deleted_user_name_a_deleted_user():
    # recorded_by is a plain uuid column, so the id outlives the account; the
    # line must say so like the timeline's other lines do, not name nobody.
    db = _timeline_db()
    db.tables["inventory_transactions"] = [
        _supply(9, recorded_by="99999999-9999-9999-9999-999999999999")]
    lines = _send(db, "GET", f"/api/rescue_cases/cases/{CASE_ID}/timeline", role="Admin").json()

    assert lines[1]["author"]["display_name"] == "Deleted user"


def test_an_older_movement_without_created_at_sorts_at_the_start_of_its_day():
    db = _timeline_db(events=[{"id": 1, "case_id": CASE_ID, "event_type": "note", "body": "x",
                               "author_id": USER_ID, "created_at": "2026-01-01T09:00:00+00:00"}])
    db.tables["inventory_transactions"] = [_supply(9, created_at=None)]
    lines = _send(db, "GET", f"/api/rescue_cases/cases/{CASE_ID}/timeline", role="Admin").json()

    assert [line["event_type"] for line in lines] == ["reported", "supplies", "note"]
    assert lines[1]["created_at"].startswith("2026-01-01T00:00:00")


def test_the_timeline_still_loads_before_migration_031():
    db = _timeline_db()
    db.fail_inserts.clear()
    original = db.table

    class _NoColumn:
        def __getattr__(self, name):
            return lambda *a, **k: self

        def execute(self):
            raise APIError({"message": "column inventory_transactions.rescue_case_id does not exist",
                            "code": "42703"})

    db.table = lambda name: _NoColumn() if name == "inventory_transactions" else original(name)
    r = _send(db, "GET", f"/api/rescue_cases/cases/{CASE_ID}/timeline", role="Admin")

    assert r.status_code == 200, r.text
    assert [line["event_type"] for line in r.json()] == ["reported"]


# --------------------------------------------------------------------------
# Monthly report
# --------------------------------------------------------------------------

class _ReportQuery(_Query):
    def neq(self, col, value):
        self.filters.append(lambda r: r.get(col) != value)
        return self


class _ReportDB(_FakeDB):
    def table(self, name):
        return _ReportQuery(self, name)


A, B, C, D = (f"aaaaaaaa-0000-0000-0000-00000000000{i}" for i in range(1, 5))


def _report_db():
    db = _ReportDB()
    db.tables["rescue_cases"] = [
        # November 2026, Sri Lanka time. B is 00:10 on the 1st locally.
        {"id": A, "status": "Resolved", "outcome": "Released", "resolved_at": "2026-11-05T10:00:00+05:30"},
        {"id": B, "status": "Resolved", "outcome": "Released", "resolved_at": "2026-11-01T00:10:00+05:30"},
        {"id": C, "status": "Resolved", "outcome": "Died", "resolved_at": "2026-11-30T23:00:00+05:30"},
        # October, and an older case with no outcome, and two open ones.
        {"id": D, "status": "Resolved", "outcome": "Rehomed", "resolved_at": "2026-10-31T23:59:00+05:30"},
        {"id": "old", "status": "Resolved", "outcome": None, "resolved_at": None},
        {"id": "open1", "status": "In Treatment", "outcome": None, "resolved_at": None},
        {"id": "open2", "status": "Reported", "outcome": None, "resolved_at": None},
    ]
    db.tables["inventory_transactions"] = [
        {"rescue_case_id": A, "transaction_type": "Issue", "total_cost": 1000.0},
        {"rescue_case_id": A, "transaction_type": "Issue", "total_cost": 500.0},
        {"rescue_case_id": A, "transaction_type": "Return", "total_cost": 500.0},  # a reversal
        {"rescue_case_id": C, "transaction_type": "Issue", "total_cost": 250.0},
        {"rescue_case_id": D, "transaction_type": "Issue", "total_cost": 9999.0},
    ]
    return db


def _report(db, role="Director", year=2026, month=11):
    async def _user():
        return {"id": USER_ID, "roles": {"role_name": role}}

    async def _sb():
        return db
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_supabase] = _sb
    try:
        return client.get(f"/api/rescue_cases/report?year={year}&month={month}")
    finally:
        app.dependency_overrides.clear()


def test_the_report_counts_a_months_resolved_cases_by_outcome_with_their_supplies():
    r = _report(_report_db())

    assert r.status_code == 200, r.text
    report = r.json()
    assert report["resolved"] == 3
    by = {line["outcome"]: line for line in report["by_outcome"]}
    assert list(by) == ["Released", "Rehomed", "Transferred", "Died", "Not found"]
    assert (by["Released"]["cases"], by["Released"]["supplies_cost"]) == (2, 1000.0)  # A net of its reversal
    assert (by["Died"]["cases"], by["Died"]["supplies_cost"]) == (1, 250.0)
    assert by["Rehomed"]["cases"] == 0  # D is October's
    assert report["supplies_cost"] == 1250.0
    assert report["average_cost"] == round(1250 / 3, 2)
    assert report["open_cases"] == 2
    assert report["unrecorded_outcomes"] == 1


def test_a_month_with_nothing_resolved_has_no_average():
    report = _report(_report_db(), month=9).json()
    assert report["resolved"] == 0 and report["average_cost"] is None and report["supplies_cost"] == 0


def test_the_report_rolls_over_the_year_end():
    db = _report_db()
    db.tables["rescue_cases"].append(
        {"id": "dec", "status": "Resolved", "outcome": "Rehomed", "resolved_at": "2026-12-31T23:30:00+05:30"})
    assert _report(db, month=12).json()["resolved"] == 1


@pytest.mark.parametrize("role", ALL_ROLES)
def test_the_report_needs_rescue_read(role):
    r = _report(_report_db(), role=role)
    assert (r.status_code == 200) == has_permission(role, "rescue:read"), (role, r.text)
