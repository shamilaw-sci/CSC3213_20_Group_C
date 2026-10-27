"""Ledger integrity: what edit, settle and void may and may not do to a row.

Each test here pins a defect that was live before it was written:

  * settling a Voided row set it to Cash, reinstating reversed money;
  * PUT skipped the restricted-funds check that POST enforces, so an expense
    could be posted small and edited past the limit;
  * PUT could rewrite a Voided row, or void a row without a VOID audit entry;
  * unknown ids on settle / void came back 500 instead of 404 (via .single());
  * a second payroll endpoint in finance.py bypassed the atomic RPC.

The Supabase double is the one test_restricted_funds uses, with updates
recorded so a refused request can be shown to have written nothing.
"""

import os
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.supabase import get_supabase
from app.main import app
from app.services.restricted_funds import restricted_effect
from tests.test_rbac_matrix import _request, acting_as
from tests.test_restricted_funds import _CapturingSupabase

PROGRAM_ID = 7
OTHER_PROGRAM_ID = 8


class _RecordingSupabase(_CapturingSupabase):
    """Adds a log of (table, payload) for every .update() call."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.updates = []

    def table(self, name):
        query = super().table(name)
        original = query.update

        def update(data=None, *a, **k):
            self.updates.append((name, data))
            return original(data, *a, **k)

        query.update = update
        return query


def _row(id, amount, tx_type, status="Cash", program_id=PROGRAM_ID, is_restricted=False):
    return {
        "id": id,
        "transaction_date": "2026-01-15",
        "amount": amount,
        "transaction_type": tx_type,
        "status": status,
        "program_id": program_id,
        "is_restricted": is_restricted,
    }


# Program 7: 1000 restricted cash raised (row 1), 400 spent (row 2) -> 600 left.
RESTRICTED_INCOME = _row(1, 1000, "Income", is_restricted=True)
EXPENSE = _row(2, 400, "Expense")


def _supabase(ledger, updated_row=None):
    return _RecordingSupabase({
        "financial_transactions": {
            "select": ledger,
            "update": [updated_row] if updated_row else [],
        },
        "system_audit_logs": {"select": [], "insert": [{"id": 1}]},
    })


def _send(role, supabase, method, path, json=None):
    with acting_as(role):
        app.dependency_overrides[get_supabase] = lambda: supabase
        return _request(method, path, json=json)


def _edit(row, **changes):
    payload = {k: v for k, v in row.items() if k != "id"}
    payload.update(changes)
    return payload


def _ledger_writes(supabase):
    return [d for t, d in supabase.updates if t == "financial_transactions"]


# --------------------------------------------------------------------------
# Settle
# --------------------------------------------------------------------------

def test_settling_a_voided_row_is_refused_and_writes_nothing():
    voided = _row(5, 300, "Income", status="Voided")
    supabase = _supabase([voided])

    response = _send("Finance Officer", supabase, "PATCH", "/api/finance/transactions/5/settle")

    assert response.status_code == 409, response.text
    assert _ledger_writes(supabase) == [], "a voided row was rewritten as Cash"


def test_settling_an_open_receivable_marks_it_cash():
    open_row = _row(5, 300, "Income", status="Receivable")
    supabase = _supabase([open_row], updated_row={**open_row, "status": "Cash"})

    response = _send("Finance Officer", supabase, "PATCH", "/api/finance/transactions/5/settle")

    assert response.status_code == 200, response.text
    assert _ledger_writes(supabase) == [{"status": "Cash"}]


@pytest.mark.parametrize("action", ["settle", "void"])
def test_unknown_transaction_is_404_not_500(action):
    # The 500 came from supabase-py's .single() raising on zero rows, which
    # this double does not reproduce; what this pins is the 404 contract the
    # replacement lookup has to keep.
    response = _send("Finance Officer", _supabase([]), "PATCH", f"/api/finance/transactions/404/{action}")
    assert response.status_code == 404, response.text


# --------------------------------------------------------------------------
# Edit: status rules
# --------------------------------------------------------------------------

def test_editing_a_voided_row_is_refused():
    voided = _row(5, 300, "Expense", status="Voided")
    supabase = _supabase([voided])

    response = _send(
        "Finance Officer", supabase, "PUT", "/api/finance/transactions/5",
        json=_edit(voided, status="Cash"),
    )

    assert response.status_code == 409, response.text
    assert _ledger_writes(supabase) == []


def test_edit_cannot_void_a_row():
    supabase = _supabase([EXPENSE, RESTRICTED_INCOME])

    response = _send(
        "Finance Officer", supabase, "PUT", "/api/finance/transactions/2",
        json=_edit(EXPENSE, status="Voided"),
    )

    assert response.status_code == 400, response.text
    assert _ledger_writes(supabase) == []


# --------------------------------------------------------------------------
# Edit: restricted funds
# --------------------------------------------------------------------------

def test_editing_an_expense_past_the_restricted_balance_is_blocked():
    supabase = _supabase([RESTRICTED_INCOME, EXPENSE])

    # 400 -> 1100 draws a further 700 against 600 remaining.
    response = _send(
        "Finance Officer", supabase, "PUT", "/api/finance/transactions/2",
        json=_edit(EXPENSE, amount=1100),
    )

    assert response.status_code == 409, response.text
    assert "by 100" in response.json()["detail"]
    assert _ledger_writes(supabase) == []


def test_editing_an_expense_within_the_balance_does_not_count_itself_twice():
    edited = {**EXPENSE, "amount": 900}
    supabase = _supabase([RESTRICTED_INCOME, EXPENSE], updated_row=edited)

    # 900 > the 600 "remaining", but 400 of that remaining figure is this
    # very row. Checked as a new expense, this edit would be wrongly refused.
    response = _send(
        "Finance Officer", supabase, "PUT", "/api/finance/transactions/2",
        json=_edit(EXPENSE, amount=900),
    )

    assert response.status_code == 200, response.text


def test_unrestricting_earmarked_income_that_is_already_spent_is_blocked():
    supabase = _supabase([RESTRICTED_INCOME, EXPENSE])

    # The edit modal used to drop is_restricted, so any edit of restricted
    # income did exactly this.
    response = _send(
        "Finance Officer", supabase, "PUT", "/api/finance/transactions/1",
        json=_edit(RESTRICTED_INCOME, is_restricted=False),
    )

    assert response.status_code == 409, response.text
    assert _ledger_writes(supabase) == []


def test_moving_an_expense_onto_a_restricted_program_is_checked_there():
    elsewhere = _row(3, 700, "Expense", program_id=OTHER_PROGRAM_ID)
    supabase = _supabase([RESTRICTED_INCOME, EXPENSE, elsewhere])

    response = _send(
        "Finance Officer", supabase, "PUT", "/api/finance/transactions/3",
        json=_edit(elsewhere, program_id=PROGRAM_ID),
    )

    assert response.status_code == 409, response.text
    assert f"program {PROGRAM_ID}" in response.json()["detail"]


def test_reducing_an_expense_on_an_overdrawn_program_needs_no_override():
    big_expense = _row(2, 1500, "Expense")
    edited = {**big_expense, "amount": 1200}
    supabase = _supabase([RESTRICTED_INCOME, big_expense], updated_row=edited)

    # Still overdrawn afterwards (1000 - 1200), but less so. Correcting an
    # overspend must never itself be blocked as one.
    response = _send(
        "Finance Officer", supabase, "PUT", "/api/finance/transactions/2",
        json=_edit(big_expense, amount=1200),
    )

    assert response.status_code == 200, response.text


def test_edit_override_is_admin_only_and_audited_with_the_transaction_id():
    edited = {**EXPENSE, "amount": 1100}

    officer = _supabase([RESTRICTED_INCOME, EXPENSE], updated_row=edited)
    refused = _send(
        "Finance Officer", officer, "PUT",
        "/api/finance/transactions/2?override_restricted=true",
        json=_edit(EXPENSE, amount=1100),
    )
    assert refused.status_code == 403, refused.text
    assert _ledger_writes(officer) == []

    admin = _supabase([RESTRICTED_INCOME, EXPENSE], updated_row=edited)
    allowed = _send(
        "Admin", admin, "PUT",
        "/api/finance/transactions/2?override_restricted=true",
        json=_edit(EXPENSE, amount=1100),
    )
    assert allowed.status_code == 200, allowed.text

    overrides = [
        d for t, d in admin.inserts
        if t == "system_audit_logs" and d["action_type"] == "FINANCE_RESTRICTED_OVERRIDE"
    ]
    assert len(overrides) == 1
    assert overrides[0]["new_payload"]["transaction_id"] == 2
    assert overrides[0]["new_payload"]["shortfall_amount"] == "100.00"


# --------------------------------------------------------------------------
# restricted_effect mirrors compute_restricted_balance
# --------------------------------------------------------------------------

@pytest.mark.parametrize("row, expected", [
    (RESTRICTED_INCOME, Decimal("1000")),
    (EXPENSE, Decimal("-400")),
    # Pledged, not received: not spendable.
    (_row(9, 500, "Income", status="Receivable", is_restricted=True), Decimal("0")),
    # Unrestricted income is not earmarked money.
    (_row(9, 500, "Income"), Decimal("0")),
    (_row(9, 500, "Expense", status="Voided"), Decimal("0")),
    (_row(9, 500, "Expense", program_id=OTHER_PROGRAM_ID), Decimal("0")),
    (None, Decimal("0")),
])
def test_restricted_effect(row, expected):
    assert restricted_effect(row, PROGRAM_ID) == expected


# --------------------------------------------------------------------------
# Payroll has one path
# --------------------------------------------------------------------------

def test_finance_payroll_endpoint_is_gone():
    # It duplicated /hr/payroll/generate without the RPC's duplicate-month
    # guard, so calling both booked the payroll expense twice.
    response = _send("Admin", _supabase([]), "POST", "/api/finance/calculate-payroll/2026/1")
    # The old handler also answered 404 ("No locked attendance records") on an
    # empty ledger, so the status alone cannot tell "route gone" from "route
    # ran". Starlette's own body for an unmatched path can.
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Not Found"}
