"""Rows the system posts itself (migrations 013, 014, 016).

  * Stock In, payroll and donation rows cannot be edited; they are corrected
    by voiding and recording a new transaction. Manual rows edit as before.
  * Voiding a Stock In expense needs a reason, written to the audit entry,
    because the stock it paid for stays in Inventory.
  * GET /transactions/{id}/stock-movement returns the movement behind a
    Stock In expense, and null rather than an error before migration 016.

Uses the Supabase double from test_ledger_integrity, which records every
update so a refused request can be shown to have written nothing.
"""

import os
import sys

import pytest
from postgrest.exceptions import APIError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.test_ledger_integrity import _edit, _ledger_writes, _row, _send, _supabase


def _sourced(id, source, tx_type="Expense", program_id=None, **extra):
    return {**_row(id, 2500, tx_type, program_id=program_id), "source_type": source, **extra}


def _audit_rows(supabase, action):
    return [
        d for t, d in supabase.inserts
        if t == "system_audit_logs" and d.get("action_type") == action
    ]


# --------------------------------------------------------------------------
# Edit lock
# --------------------------------------------------------------------------

@pytest.mark.parametrize("source, label", [
    ("stock_in", "Stock in"),
    ("payroll", "Payroll"),
    ("donation", "Donation"),
])
def test_auto_posted_rows_cannot_be_edited(source, label):
    row = _sourced(5, source, tx_type="Income" if source == "donation" else "Expense")
    supabase = _supabase([row], updated_row={**row, "amount": 1})

    response = _send(
        "Finance Officer", supabase, "PUT", "/api/finance/transactions/5",
        json=_edit(row, amount=1),
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"].startswith(f"{label} transactions are posted automatically")
    assert "Void this one" in response.json()["detail"]
    assert _ledger_writes(supabase) == [], "an auto-posted row was rewritten"


@pytest.mark.parametrize("source", ["manual", None])
def test_manual_rows_still_edit(source):
    # None: a row read before migration 013, which counts as manual.
    row = {**_row(5, 300, "Expense", program_id=None), "source_type": source}
    supabase = _supabase([row], updated_row={**row, "amount": 350})

    response = _send(
        "Finance Officer", supabase, "PUT", "/api/finance/transactions/5",
        json=_edit({k: v for k, v in row.items() if k != "source_type"}, amount=350),
    )

    assert response.status_code == 200, response.text
    assert len(_ledger_writes(supabase)) == 1


def test_the_lock_cannot_be_dodged_by_sending_source_type():
    # source_type is not part of the edit payload, so a client claiming the
    # row is manual changes nothing: the stored value decides.
    row = _sourced(5, "stock_in")
    supabase = _supabase([row])

    response = _send(
        "Finance Officer", supabase, "PUT", "/api/finance/transactions/5",
        json={**_edit(row), "source_type": "manual"},
    )

    assert response.status_code == 409, response.text
    assert _ledger_writes(supabase) == []


# --------------------------------------------------------------------------
# Void reason
# --------------------------------------------------------------------------

@pytest.mark.parametrize("body", [None, {}, {"reason": "   "}])
def test_voiding_a_stock_in_expense_needs_a_reason(body):
    row = _sourced(5, "stock_in", inventory_transaction_id=41)
    supabase = _supabase([row], updated_row={**row, "status": "Voided"})

    response = _send("Finance Officer", supabase, "PATCH", "/api/finance/transactions/5/void", json=body)

    assert response.status_code == 400, response.text
    assert "reason" in response.json()["detail"]
    assert _ledger_writes(supabase) == [], "voided without a reason"


def test_voiding_a_stock_in_expense_records_the_reason_in_the_audit():
    row = _sourced(5, "stock_in", inventory_transaction_id=41)
    supabase = _supabase([row], updated_row={**row, "status": "Voided"})

    response = _send(
        "Finance Officer", supabase, "PATCH", "/api/finance/transactions/5/void",
        json={"reason": "  Entered twice  "},
    )

    assert response.status_code == 200, response.text
    assert _ledger_writes(supabase) == [{"status": "Voided"}]
    [audit] = _audit_rows(supabase, "FINANCE_TRANSACTION_VOID")
    assert audit["new_payload"]["void_reason"] == "Entered twice"


@pytest.mark.parametrize("source", ["manual", "payroll"])
def test_other_rows_void_without_a_reason(source):
    row = _sourced(5, source)
    supabase = _supabase([row], updated_row={**row, "status": "Voided"})

    response = _send("Finance Officer", supabase, "PATCH", "/api/finance/transactions/5/void")

    assert response.status_code == 200, response.text
    [audit] = _audit_rows(supabase, "FINANCE_TRANSACTION_VOID")
    assert "void_reason" not in audit["new_payload"]


def test_an_optional_reason_on_any_row_is_still_recorded():
    row = _sourced(5, "manual")
    supabase = _supabase([row], updated_row={**row, "status": "Voided"})

    _send("Finance Officer", supabase, "PATCH", "/api/finance/transactions/5/void", json={"reason": "Typo"})

    [audit] = _audit_rows(supabase, "FINANCE_TRANSACTION_VOID")
    assert audit["new_payload"]["void_reason"] == "Typo"


def test_void_reason_is_capped():
    row = _sourced(5, "stock_in")
    supabase = _supabase([row])

    response = _send(
        "Finance Officer", supabase, "PATCH", "/api/finance/transactions/5/void",
        json={"reason": "x" * 501},
    )

    assert response.status_code == 422
    assert _ledger_writes(supabase) == []


# --------------------------------------------------------------------------
# GET /transactions/{id}/stock-movement
# --------------------------------------------------------------------------

def _linked(id=5, source="stock_in", link=41):
    return {
        "id": id,
        "source_type": source,
        "inventory_transaction_id": link,
        "inventory_transactions": None if link is None else {
            "quantity": 20,
            "transaction_date": "2026-10-30",
            "total_cost": 2500,
            "inventory_items": {"item_name": "Rabies Vaccine"},
        },
    }


def test_stock_movement_of_a_linked_stock_in_expense():
    response = _send(
        "Finance Officer", _supabase([_linked()]), "GET", "/api/finance/transactions/5/stock-movement",
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "inventory_transaction_id": 41,
        "item_name": "Rabies Vaccine",
        "quantity": 20,
        "transaction_date": "2026-10-30",
        "total_cost": 2500.0,
    }


@pytest.mark.parametrize("row", [
    _linked(source="manual", link=None),
    _linked(source="payroll", link=None),
    # A stock_in expense 016 could not pair with its movement.
    _linked(link=None),
])
def test_stock_movement_is_null_when_there_is_none(row):
    response = _send("Finance Officer", _supabase([row]), "GET", "/api/finance/transactions/5/stock-movement")

    assert response.status_code == 200, response.text
    assert response.json() is None


def test_stock_movement_of_an_unknown_transaction_is_404():
    response = _send("Finance Officer", _supabase([]), "GET", "/api/finance/transactions/404/stock-movement")
    assert response.status_code == 404, response.text


class _FailingSelect:
    """Every select raises the given PostgREST error."""

    def __init__(self, error):
        self.error = error

    def table(self, name):
        return self

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def execute(self):
        raise self.error


@pytest.mark.parametrize("error", [
    APIError({"code": "42703", "message": "column financial_transactions.inventory_transaction_id does not exist"}),
    APIError({
        "code": "PGRST200",
        "message": "Could not find a relationship between 'financial_transactions' and 'inventory_transactions'",
    }),
])
def test_stock_movement_is_null_before_migration_016(error):
    response = _send(
        "Finance Officer", _FailingSelect(error), "GET", "/api/finance/transactions/5/stock-movement",
    )

    assert response.status_code == 200, response.text
    assert response.json() is None


def test_stock_movement_does_not_hide_other_errors():
    error = APIError({"code": "57014", "message": "canceling statement due to statement timeout"})
    response = _send(
        "Finance Officer", _FailingSelect(error), "GET", "/api/finance/transactions/5/stock-movement",
    )
    assert response.status_code == 500
