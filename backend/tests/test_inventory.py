"""Inventory stock rules: validation, stock never below zero, no lost updates,
returns bounded by what was issued, and no half-saved movements.

The RBAC matrix (test_rbac_matrix.py) checks who may call each route. These
tests check what the routes do once the caller is allowed in, against a small
in-memory stand-in for Supabase that actually applies filters and updates.
"""

import copy
import os
import sys

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api import inventory as inventory_api
from app.core.security import get_current_user
from app.core.supabase import get_supabase
from app.main import app

client = TestClient(app, raise_server_exceptions=False)

USER_ID = "11111111-1111-1111-1111-111111111111"
TODAY = "2026-11-01"


# --------------------------------------------------------------------------
# In-memory Supabase
# --------------------------------------------------------------------------

class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, db, table):
        self.db = db
        self.table_name = table
        self.op = "select"
        self.payload = None
        self.filters = []
        self.limit_n = None
        self.range_ = None
        self.select_cols = "*"
        self._negate = False

    # -- operations --------------------------------------------------------
    def select(self, cols="*", *a, **k):
        self.op, self.select_cols = "select", cols
        return self

    def insert(self, data, *a, **k):
        self.op, self.payload = "insert", data
        return self

    def update(self, data, *a, **k):
        self.op, self.payload = "update", data
        return self

    # -- filters -----------------------------------------------------------
    def eq(self, col, value):
        self.filters.append(lambda r: r.get(col) == value)
        return self

    def lt(self, col, value):
        self.filters.append(lambda r: r.get(col) is not None and r.get(col) < value)
        return self

    def lte(self, col, value):
        self.filters.append(lambda r: r.get(col) is not None and str(r.get(col)) <= str(value))
        return self

    def ilike(self, col, pattern):
        plain = pattern.replace("\\%", "%").replace("\\_", "_").replace("\\\\", "\\").lower()
        self.filters.append(lambda r: str(r.get(col, "")).lower() == plain)
        return self

    @property
    def not_(self):
        self._negate = True
        return self

    def is_(self, col, value):
        negate, self._negate = self._negate, False
        check = (lambda r: r.get(col) is None) if value == "null" else (lambda r: r.get(col) == value)
        self.filters.append((lambda r: not check(r)) if negate else check)
        return self

    def order(self, *a, **k):
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def range(self, start, end):
        self.range_ = (start, end)
        return self

    # -- run ---------------------------------------------------------------
    def _matches(self):
        return [r for r in self.db.tables.setdefault(self.table_name, []) if all(f(r) for f in self.filters)]

    def execute(self):
        db = self.db
        if self.table_name in db.fail_on_insert and self.op == "insert":
            raise APIError({"message": "insert rejected", "code": "23503"})
        if self.op == "insert":
            rows = self.payload if isinstance(self.payload, list) else [self.payload]
            out = []
            for row in rows:
                new = {**row, "id": db.next_id(self.table_name)}
                db.tables.setdefault(self.table_name, []).append(new)
                out.append(copy.deepcopy(new))
            return _Result(out)
        if self.op == "update":
            hook = db.before_update.pop(0) if db.before_update else None
            if hook:
                hook(db)
            matched = self._matches()
            for r in matched:
                r.update(self.payload)
            return _Result(copy.deepcopy(matched))
        rows = copy.deepcopy(self._matches())
        if "programs(" in self.select_cols:
            programs = {p["id"]: p for p in db.tables.get("programs", [])}
            for r in rows:
                p = programs.get(r.get("program_id"))
                r["programs"] = {"program_name": p["program_name"]} if p else None
        if self.range_:
            rows = rows[self.range_[0]: self.range_[1] + 1]
        if self.limit_n is not None:
            rows = rows[: self.limit_n]
        return _Result(rows)


class _FakeDB:
    def __init__(self, items=None, programs=None, transactions=None):
        self.tables = {
            "inventory_items": copy.deepcopy(items or []),
            "programs": copy.deepcopy(programs or []),
            "inventory_transactions": copy.deepcopy(transactions or []),
            "system_audit_logs": [],
        }
        self._ids = {}
        self.fail_on_insert = set()
        # Callables run just before the next update executes, to simulate a
        # concurrent request landing between our read and our write.
        self.before_update = []
        self.rpc_calls = []
        self.rpc_result = None
        self.rpc_error = None

    def next_id(self, table):
        self._ids[table] = self._ids.get(table, 1000) + 1
        return self._ids[table]

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params=None):
        """Default: the database function does not exist yet (migration 012
        not applied), so the API takes its fallback path. Tests of the
        function path set `rpc_result` or `rpc_error`."""
        self.rpc_calls.append((name, params))
        db = self

        class _Rpc:
            def execute(self_inner):
                if db.rpc_error is not None:
                    raise db.rpc_error
                if db.rpc_result is not None:
                    return _Result([db.rpc_result])
                raise APIError({"message": f"Could not find the function public.{name}", "code": "PGRST202"})

        return _Rpc()

    def stock(self, item_id):
        return next(i["current_stock"] for i in self.tables["inventory_items"] if i["id"] == item_id)

    def movements(self):
        return self.tables["inventory_transactions"]


ITEM = {"id": 1, "item_name": "Rabies Vaccine", "current_stock": 10, "unit_cost": 1500.0,
        "expire_date": None, "supplier_name": None}
PROGRAM = {"id": 7, "program_name": "Galle Clinic", "status": "Active"}


@pytest.fixture
def db():
    return _FakeDB(items=[ITEM], programs=[PROGRAM])


@pytest.fixture
def act(db):
    def _as(role="Operations Lead"):
        async def _user():
            return {"id": USER_ID, "roles": {"role_name": role}}

        async def _sb():
            return db

        app.dependency_overrides[get_current_user] = _user
        app.dependency_overrides[get_supabase] = _sb

    yield _as
    app.dependency_overrides.clear()


def _tx(**overrides):
    body = {"item_id": 1, "program_id": 7, "quantity": 3, "transaction_type": "Issue",
            "transaction_date": TODAY}
    body.update(overrides)
    return body


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

@pytest.mark.parametrize("quantity", [0, -5, 2.5, 100_001])
def test_quantity_must_be_a_positive_whole_number(act, db, quantity):
    act()
    for tx_type in ("Issue", "Return", "Restock"):
        r = client.post("/api/inventory/transactions", json=_tx(quantity=quantity, transaction_type=tx_type))
        assert r.status_code == 422, (tx_type, quantity, r.text)
    assert db.stock(1) == 10
    assert db.movements() == []


def test_unknown_transaction_type_is_refused(act, db):
    act()
    r = client.post("/api/inventory/transactions", json=_tx(transaction_type="Adjust"))
    assert r.status_code == 422
    assert db.stock(1) == 10


def test_negative_return_can_no_longer_drive_stock_below_zero(act, db):
    """The old route added -50 for a Return without any check."""
    act("General Staff")
    r = client.post("/api/inventory/transactions", json=_tx(transaction_type="Return", quantity=-50))
    assert r.status_code == 422
    assert db.stock(1) == 10


@pytest.mark.parametrize("body, field", [
    ({"item_name": "   ", "unit_cost": 10}, "item_name"),
    ({"item_name": "Gauze", "unit_cost": 0}, "unit_cost"),
    ({"item_name": "Gauze", "unit_cost": -1}, "unit_cost"),
    ({"item_name": "Gauze", "unit_cost": 10, "current_stock": -3}, "current_stock"),
])
def test_item_fields_are_validated(act, db, body, field):
    act()
    r = client.post("/api/inventory/items", json=body)
    assert r.status_code == 422
    assert field in r.text
    assert len(db.tables["inventory_items"]) == 1


# --------------------------------------------------------------------------
# Issue
# --------------------------------------------------------------------------

def test_issue_reduces_stock_and_records_the_movement(act, db):
    act()
    r = client.post("/api/inventory/transactions", json=_tx(quantity=4))
    assert r.status_code == 200, r.text
    assert db.stock(1) == 6
    assert len(db.movements()) == 1
    audit = db.tables["system_audit_logs"]
    assert audit and audit[-1]["action_type"] == "INVENTORY_ISSUE"
    assert audit[-1]["old_payload"]["current_stock"] == 10
    assert audit[-1]["new_payload"]["current_stock"] == 6


def test_issue_more_than_in_stock_is_refused_with_a_clear_message(act, db):
    act()
    r = client.post("/api/inventory/transactions", json=_tx(quantity=11))
    assert r.status_code == 400
    assert "only 10" in r.json()["detail"]
    assert db.stock(1) == 10
    assert db.movements() == []


def test_concurrent_issue_cannot_overdraw_stock(act, db):
    """Another Issue of 8 lands between our read and our write. The old
    read-modify-write wrote 2 on top of it; now the write is refused, we
    re-read 2, and our Issue of 8 is rejected."""
    def _someone_else_issues_8(fake):
        fake.tables["inventory_items"][0]["current_stock"] = 2

    db.before_update.append(_someone_else_issues_8)
    act()
    r = client.post("/api/inventory/transactions", json=_tx(quantity=8))
    assert r.status_code == 400
    assert db.stock(1) == 2


def test_concurrent_restock_is_not_lost(act, db):
    def _someone_else_restocks_5(fake):
        fake.tables["inventory_items"][0]["current_stock"] = 15

    db.before_update.append(_someone_else_restocks_5)
    act()
    r = client.post("/api/inventory/transactions", json=_tx(quantity=3))
    assert r.status_code == 200, r.text
    assert db.stock(1) == 12  # 15 - 3, not 10 - 3


def test_unknown_item_is_404_not_500(act, db):
    act()
    r = client.post("/api/inventory/transactions", json=_tx(item_id=999))
    assert r.status_code == 404


def test_unknown_program_is_refused_before_stock_moves(act, db):
    act()
    r = client.post("/api/inventory/transactions", json=_tx(program_id=999))
    assert r.status_code == 404
    assert db.stock(1) == 10


def test_failed_insert_puts_the_stock_back(act, db):
    db.fail_on_insert.add("inventory_transactions")
    act()
    r = client.post("/api/inventory/transactions", json=_tx(quantity=4))
    assert r.status_code == 400
    assert "Stock has not changed" in r.json()["detail"]
    assert db.stock(1) == 10


# --------------------------------------------------------------------------
# Restock and Return
# --------------------------------------------------------------------------

def test_restock_never_carries_a_program(act, db):
    act()
    r = client.post("/api/inventory/transactions", json=_tx(transaction_type="Restock", quantity=5))
    assert r.status_code == 200, r.text
    assert db.stock(1) == 15
    assert db.movements()[0]["program_id"] is None


def test_return_cannot_exceed_what_the_program_still_holds(act, db):
    db.tables["inventory_transactions"] = [
        {"id": 1, "item_id": 1, "program_id": 7, "quantity": 5, "transaction_type": "Issue"},
        {"id": 2, "item_id": 1, "program_id": 7, "quantity": 2, "transaction_type": "Return"},
    ]
    act()
    r = client.post("/api/inventory/transactions", json=_tx(transaction_type="Return", quantity=4))
    assert r.status_code == 400
    assert "holds only 3" in r.json()["detail"]
    assert db.stock(1) == 10

    r = client.post("/api/inventory/transactions", json=_tx(transaction_type="Return", quantity=3))
    assert r.status_code == 200, r.text
    assert db.stock(1) == 13


def test_return_to_a_program_that_never_received_the_item_is_refused(act, db):
    act()
    r = client.post("/api/inventory/transactions", json=_tx(transaction_type="Return", quantity=1))
    assert r.status_code == 400
    assert db.stock(1) == 10


def test_outstanding_lists_what_each_program_holds(act, db):
    db.tables["programs"].append({"id": 8, "program_name": "Kandy Drive", "status": "Active"})
    db.tables["inventory_transactions"] = [
        {"id": 1, "item_id": 1, "program_id": 7, "quantity": 5, "transaction_type": "Issue"},
        {"id": 2, "item_id": 1, "program_id": 7, "quantity": 2, "transaction_type": "Return"},
        {"id": 3, "item_id": 1, "program_id": 8, "quantity": 1, "transaction_type": "Issue"},
        {"id": 4, "item_id": 1, "program_id": None, "quantity": 9, "transaction_type": "Restock"},
    ]
    act("General Staff")
    r = client.get("/api/inventory/items/1/outstanding")
    assert r.status_code == 200, r.text
    assert r.json() == [
        {"program_id": 7, "program_name": "Galle Clinic", "issued": 5, "returned": 2, "outstanding": 3},
        {"program_id": 8, "program_name": "Kandy Drive", "issued": 1, "returned": 0, "outstanding": 1},
    ]


# --------------------------------------------------------------------------
# Items
# --------------------------------------------------------------------------

def test_duplicate_item_name_is_refused_case_insensitively(act, db):
    act()
    r = client.post("/api/inventory/items", json={"item_name": "  rabies VACCINE ", "unit_cost": 10})
    assert r.status_code == 409
    assert len(db.tables["inventory_items"]) == 1


def test_add_item_registers_the_item_with_no_stock(act, db):
    act()
    r = client.post("/api/inventory/items", json={"item_name": "Gauze", "unit_cost": 25})
    assert r.status_code == 200, r.text
    assert r.json()["current_stock"] == 0
    assert db.stock(1001) == 0
    # No movement: stock (and its cost) only comes in through Stock In.
    assert db.movements() == []
    assert not db.rpc_calls
    assert db.tables["system_audit_logs"][-1]["action_type"] == "INVENTORY_ITEM_CREATE"


def test_add_item_refuses_opening_stock(act, db):
    act()
    r = client.post("/api/inventory/items", json={"item_name": "Gauze", "unit_cost": 25, "current_stock": 40})
    assert r.status_code == 400
    assert "Stock In" in r.json()["detail"]
    assert len(db.tables["inventory_items"]) == 1
    assert db.movements() == []


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------

def test_transactions_can_be_paged(act, db):
    db.tables["inventory_transactions"] = [
        {"id": i, "item_id": 1, "program_id": None, "quantity": 1, "transaction_type": "Restock",
         "transaction_date": TODAY, "total_cost": 0}
        for i in range(1, 8)
    ]
    act()
    r = client.get("/api/inventory/transactions", params={"limit": 3, "offset": 3})
    assert r.status_code == 200
    assert [t["id"] for t in r.json()] == [4, 5, 6]


@pytest.mark.parametrize("path", [
    "/api/inventory/alerts/low-stock",
    "/api/inventory/alerts/expiring",
    "/api/inventory/items/1/outstanding",
])
@pytest.mark.parametrize("role, allowed", [
    ("Admin", True), ("Director", True), ("Finance Officer", True), ("Operations Lead", True),
    ("General Staff", True), ("HR Officer", False), ("System Administrator", False),
])
def test_inventory_reads_follow_permissions(act, db, path, role, allowed):
    act(role)
    r = client.get(path)
    assert (r.status_code != 403) == allowed, (role, path, r.status_code)


# --------------------------------------------------------------------------
# Business rules (decided 2026-11-01)
# --------------------------------------------------------------------------

def test_future_dates_are_refused(act, db):
    act()
    r = client.post("/api/inventory/transactions", json=_tx(transaction_date="2999-01-01"))
    assert r.status_code == 422
    assert "future" in r.text
    assert db.stock(1) == 10


def test_back_dated_movement_is_allowed(act, db):
    act()
    r = client.post("/api/inventory/transactions", json=_tx(transaction_date="2026-01-15"))
    assert r.status_code == 200, r.text


def test_return_must_name_a_program(act, db):
    act()
    r = client.post("/api/inventory/transactions", json=_tx(transaction_type="Return", program_id=None))
    assert r.status_code == 400
    assert "Stock In" in r.json()["detail"]
    assert db.stock(1) == 10


def test_stock_adjustment_without_a_program_needs_a_reason(act, db):
    act()
    r = client.post("/api/inventory/transactions", json=_tx(program_id=None, quantity=2))
    assert r.status_code == 400
    assert "reason" in r.json()["detail"]
    r = client.post("/api/inventory/transactions", json=_tx(program_id=None, quantity=2, notes="2 vials broken"))
    assert r.status_code == 200, r.text
    assert db.stock(1) == 8
    assert db.movements()[0]["notes"] == "2 vials broken"


def test_movement_cost_is_worked_out_on_the_server(act, db):
    act()
    r = client.post("/api/inventory/transactions", json={**_tx(quantity=2), "total_cost": 1})
    assert r.status_code == 200, r.text
    assert db.movements()[0]["total_cost"] == 3000


# Stock page roles hold inventory:manage; General Staff holds inventory:issue
# only; HR Officer and System Administrator hold neither.
@pytest.mark.parametrize("role, issue, restock, adjust, add_item", [
    ("Admin", 200, 200, 200, 200),
    ("Director", 200, 200, 200, 200),
    ("Finance Officer", 200, 200, 200, 200),
    ("Operations Lead", 200, 200, 200, 200),
    ("General Staff", 200, 403, 400, 403),
    ("HR Officer", 403, 403, 403, 403),
    ("System Administrator", 403, 403, 403, 403),
])
def test_who_may_move_stock(act, db, role, issue, restock, adjust, add_item):
    act(role)
    assert client.post("/api/inventory/transactions", json=_tx(quantity=1)).status_code == issue
    assert client.post("/api/inventory/transactions",
                       json=_tx(transaction_type="Restock", quantity=1)).status_code == restock
    assert client.post("/api/inventory/transactions",
                       json=_tx(program_id=None, quantity=1, notes="damaged")).status_code == adjust
    assert client.post("/api/inventory/items",
                       json={"item_name": f"Item for {role}", "unit_cost": 5}).status_code == add_item


def test_general_staff_can_return_to_a_program(act, db):
    db.tables["inventory_transactions"] = [
        {"id": 1, "item_id": 1, "program_id": 7, "quantity": 5, "transaction_type": "Issue"},
    ]
    act("General Staff")
    r = client.post("/api/inventory/transactions", json=_tx(transaction_type="Return", quantity=2))
    assert r.status_code == 200, r.text
    assert db.stock(1) == 12


def test_general_staff_cannot_read_the_movement_log(act, db):
    act("General Staff")
    assert client.get("/api/inventory/transactions").status_code == 403


# --------------------------------------------------------------------------
# Database function path (after migration 012)
# --------------------------------------------------------------------------

def test_database_function_result_is_returned_and_audited(act, db):
    db.rpc_result = {
        "transaction_id": 55, "item_id": 1, "program_id": 7, "quantity": 3, "transaction_type": "Issue",
        "transaction_date": TODAY, "notes": None, "total_cost": 4500, "stock_before": 10, "stock_after": 7,
    }
    act()
    r = client.post("/api/inventory/transactions", json=_tx())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == 55 and body["total_cost"] == 4500
    assert "stock_before" not in body
    assert db.rpc_calls[-1][0] == "inventory_apply_movement"
    audit = db.tables["system_audit_logs"][-1]
    assert audit["old_payload"]["current_stock"] == 10
    assert audit["new_payload"]["current_stock"] == 7
    # The function did the write, so the API did not touch the tables itself.
    assert db.stock(1) == 10 and db.movements() == []


@pytest.mark.parametrize("code, status", [("P0001", 400), ("P0002", 404)])
def test_database_function_refusal_is_passed_on(act, db, code, status):
    db.rpc_error = APIError({"message": "Insufficient stock: only 2 available", "code": code})
    act()
    r = client.post("/api/inventory/transactions", json=_tx())
    assert r.status_code == status
    assert r.json()["detail"] == "Insufficient stock: only 2 available"


# --------------------------------------------------------------------------
# Price paid at Stock In (migration 017)
# --------------------------------------------------------------------------

def _stock_in(**overrides):
    return _tx(transaction_type="Restock", program_id=None, quantity=4, **overrides)


def test_stock_in_at_a_new_price_costs_the_movement_and_updates_the_item(act, db):
    act()
    r = client.post("/api/inventory/transactions", json=_stock_in(unit_cost=1750))
    assert r.status_code == 200, r.text
    # 4 x 1750, not 4 x the stored 1500: this total is what finance posts.
    assert db.movements()[0]["total_cost"] == 7000
    assert db.tables["inventory_items"][0]["unit_cost"] == 1750
    audit = db.tables["system_audit_logs"][-1]
    assert audit["old_payload"]["unit_cost"] == 1500
    assert audit["new_payload"]["unit_cost"] == 1750


def test_stock_in_at_a_new_price_is_sent_to_the_database_function(act, db):
    db.rpc_result = {
        "transaction_id": 56, "item_id": 1, "program_id": None, "quantity": 4, "transaction_type": "Restock",
        "transaction_date": TODAY, "notes": None, "total_cost": 7000, "stock_before": 10, "stock_after": 14,
    }
    act()
    r = client.post("/api/inventory/transactions", json=_stock_in(unit_cost=1750))
    assert r.status_code == 200, r.text
    assert db.rpc_calls[-1][1]["p_unit_cost"] == 1750


@pytest.mark.parametrize("price", [None, 1500, 1500.001])
def test_stock_in_at_the_stored_price_sends_no_price(act, db, price):
    # Unchanged price: the call is exactly 012's, so a database without 017
    # still takes the locked path.
    act()
    body = _stock_in() if price is None else _stock_in(unit_cost=price)
    r = client.post("/api/inventory/transactions", json=body)
    assert r.status_code == 200, r.text
    assert "p_unit_cost" not in db.rpc_calls[-1][1]
    assert db.movements()[0]["total_cost"] == 6000
    assert db.tables["inventory_items"][0]["unit_cost"] == 1500
    assert "unit_cost" not in db.tables["system_audit_logs"][-1]["old_payload"]


@pytest.mark.parametrize("tx_type, program_id", [("Issue", 7), ("Return", 7)])
def test_only_stock_in_takes_a_price(act, db, tx_type, program_id):
    act()
    r = client.post("/api/inventory/transactions",
                    json=_tx(transaction_type=tx_type, program_id=program_id, unit_cost=10))
    assert r.status_code == 400
    assert "only entered for Stock In" in r.json()["detail"]
    assert db.stock(1) == 10 and db.movements() == []


@pytest.mark.parametrize("price", [0, -1, 100_000_001])
def test_stock_in_price_is_validated(act, db, price):
    act()
    r = client.post("/api/inventory/transactions", json=_stock_in(unit_cost=price))
    assert r.status_code == 422
    assert db.stock(1) == 10
