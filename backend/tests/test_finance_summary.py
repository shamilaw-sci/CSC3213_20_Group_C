"""The finance Overview / dashboard headline figures (GET /finance/summary).

Pins the defect this replaced: the get_finance_summary RPC reported every
expense ever recorded, voided ones included, as "monthly expenses".
"""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.supabase import get_supabase
from app.main import app
from app.services.finance_reports import finance_snapshot
from tests.test_finance_reports import RESCUE, VACCINES, _row
from tests.test_rbac_matrix import _request, acting_as
from tests.test_restricted_funds import _CapturingSupabase

TODAY = date(2026, 10, 28)

# Shaped on the real ledger that exposed the bug: 403,000 of live expenses,
# 480,257 of voided ones, 50,000 of it this month.
LEDGER = [
    _row(1, "2026-04-06", 8000, "Expense", program_id=VACCINES),
    _row(2, "2026-04-07", 25000, "Income", status="Receivable", program_id=RESCUE),
    _row(3, "2026-04-08", 15000, "Expense"),
    _row(4, "2026-06-27", 1.85, "Income", status="Receivable", program_id=VACCINES),
    _row(5, "2026-06-27", 345679, "Expense", status="Voided", program_id=VACCINES),
    _row(6, "2026-06-30", 34578, "Expense", status="Voided", program_id=RESCUE),
    _row(7, "2026-07-06", 230000, "Expense"),
    _row(8, "2026-08-20", 234567, "Income", program_id=RESCUE),
    _row(9, "2026-09-01", 100000, "Income", program_id=VACCINES, is_restricted=True),
    _row(10, "2026-09-01", 50000, "Expense", program_id=VACCINES),
    _row(11, "2026-09-01", 50000, "Expense", program_id=VACCINES),
    _row(12, "2026-09-01", 50000, "Expense", status="Voided", program_id=VACCINES),
    _row(13, "2026-09-01", 50000, "Expense", status="Voided", program_id=VACCINES),
    _row(14, "2026-10-28", 200000, "Income", program_id=VACCINES),
    _row(15, "2026-10-28", 50000, "Expense", program_id=VACCINES),
    # An unpaid bill this month: part of the month's spend, not of cash.
    _row(16, "2026-10-29", 1200, "Expense", status="Receivable"),
]


@pytest.fixture
def snapshot():
    return finance_snapshot(LEDGER, TODAY)


def test_monthly_expenses_are_this_month_only_and_exclude_voided(snapshot):
    # The RPC reported 883,257 here: every expense ever, voided included.
    assert snapshot["monthly_expenses"] == 51200


def test_cash_is_received_income_minus_paid_expenses(snapshot):
    received = 234567 + 100000 + 200000
    paid = 8000 + 15000 + 230000 + 50000 + 50000 + 50000
    assert snapshot["cash_available"] == pytest.approx(received - paid)


def test_receivables_are_open_income_only(snapshot):
    # The unpaid bill (row 16) is a payable, not a receivable.
    assert snapshot["receivables"] == pytest.approx(25001.85)


def test_month_boundary_uses_the_calendar_month():
    rows = [_row(1, "2026-09-30", 500, "Expense"), _row(2, "2026-10-01", 70, "Expense")]
    assert finance_snapshot(rows, TODAY)["monthly_expenses"] == 70
    assert finance_snapshot(rows, date(2026, 9, 30))["monthly_expenses"] == 500


def test_empty_ledger():
    assert finance_snapshot([], TODAY) == {"cash_available": 0, "receivables": 0, "monthly_expenses": 0}


class _RpcTrap(_CapturingSupabase):
    """Fails the test if anything still asks the old RPC."""

    def rpc(self, name, params=None):
        raise AssertionError(f"{name} RPC called; the summary must come from the ledger")


def test_summary_endpoint_uses_the_ledger_not_the_rpc():
    supabase = _RpcTrap({"financial_transactions": {"select": LEDGER}})
    with acting_as("Director"):
        app.dependency_overrides[get_supabase] = lambda: supabase
        response = _request("GET", "/api/finance/summary")

    assert response.status_code == 200, response.text
    assert set(response.json()) == {"cash_available", "receivables", "monthly_expenses"}
    assert response.json()["receivables"] == pytest.approx(25001.85)


def test_chat_tool_reports_the_same_figures_as_the_overview():
    from app.services.chat_tools import TOOLS

    supabase = _RpcTrap({"financial_transactions": {"select": LEDGER}})
    result = TOOLS["get_finance_summary"]["impl"](supabase)
    assert result == finance_snapshot(LEDGER, date.today())
