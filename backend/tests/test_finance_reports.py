"""Finance report: the maths behind the reports page, its PDF and its CSVs.

build_finance_report is pure, so most of this runs on plain row dicts. The
endpoint tests reuse the restricted-funds Supabase double.
"""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.supabase import get_supabase
from app.main import app
from app.services.finance_reports import (
    GENERAL_OPERATIONS,
    PAGE_SIZE,
    build_finance_report,
    fetch_ledger,
    previous_period,
)
from app.services.restricted_funds import compute_restricted_balance
from tests.test_rbac_matrix import _FakeResult, _request, acting_as
from tests.test_restricted_funds import _CapturingSupabase

RESCUE, VACCINES = 7, 8
TODAY = date(2026, 6, 30)


def _row(id, day, amount, tx_type, status="Cash", program_id=None, is_restricted=False):
    names = {RESCUE: "Emergency Rescue", VACCINES: "Rabies Vaccination"}
    return {
        "id": id,
        "transaction_date": day,
        "amount": amount,
        "transaction_type": tx_type,
        "status": status,
        "program_id": program_id,
        "is_restricted": is_restricted,
        "programs": {"program_name": names[program_id]} if program_id else None,
    }


# Period under test: June 2026. Previous period: May 2026.
LEDGER = [
    # Before the previous period: restricted opening position for RESCUE.
    _row(1, "2026-03-10", 1000, "Income", program_id=RESCUE, is_restricted=True),
    _row(2, "2026-04-02", 300, "Expense", program_id=RESCUE),
    # May (previous period).
    _row(3, "2026-05-05", 2000, "Income"),
    _row(4, "2026-05-20", 500, "Expense", program_id=VACCINES),
    # June (current period).
    _row(5, "2026-06-01", 4000, "Income", program_id=RESCUE, is_restricted=True),
    _row(6, "2026-06-03", 1500, "Income", status="Receivable"),
    _row(7, "2026-06-10", 1200, "Expense", program_id=RESCUE),
    _row(8, "2026-06-12", 800, "Expense", status="Receivable", program_id=VACCINES),
    _row(9, "2026-06-15", 600, "Expense"),
    _row(10, "2026-06-20", 9999, "Income", status="Voided", program_id=RESCUE, is_restricted=True),
    _row(11, "2026-06-25", 250, "Income", status="Receivable", program_id=RESCUE, is_restricted=True),
    # An old receivable still open: must age into 90+.
    _row(12, "2026-01-15", 700, "Income", status="Receivable"),
]

JUNE = (date(2026, 6, 1), date(2026, 6, 30))


@pytest.fixture
def report():
    return build_finance_report(LEDGER, *JUNE, today=TODAY)


# --------------------------------------------------------------------------
# Comparison period
# --------------------------------------------------------------------------

@pytest.mark.parametrize("start, end, expected", [
    # Whole months compare with whole months, not day counts.
    (date(2026, 3, 1), date(2026, 3, 31), (date(2026, 2, 1), date(2026, 2, 28))),
    (date(2026, 4, 1), date(2026, 6, 30), (date(2026, 1, 1), date(2026, 3, 31))),
    # Financial year April-March against the one before.
    (date(2026, 4, 1), date(2027, 3, 31), (date(2025, 4, 1), date(2026, 3, 31))),
    # Crossing a year boundary backwards.
    (date(2026, 1, 1), date(2026, 2, 28), (date(2025, 11, 1), date(2025, 12, 31))),
    # Anything else: the same number of days, immediately before.
    (date(2026, 6, 11), date(2026, 6, 20), (date(2026, 6, 1), date(2026, 6, 10))),
])
def test_previous_period(start, end, expected):
    assert previous_period(start, end) == expected


# --------------------------------------------------------------------------
# Income & expenditure
# --------------------------------------------------------------------------

def test_summary_splits_settled_from_pending_and_ignores_voided(report):
    current = report["summary"]["current"]
    # 4000 + 1500 pending + 250 pending; the voided 9999 is out.
    assert current["income"] == 5750
    assert current["income_received"] == 4000
    assert current["income_pending"] == 1750
    assert current["expense"] == 2600
    assert current["expense_paid"] == 1800
    assert current["expense_unpaid"] == 800
    assert current["net"] == 3150


def test_summary_compares_with_the_previous_period(report):
    summary = report["summary"]
    assert summary["previous"]["income"] == 2000
    assert summary["previous"]["expense"] == 500
    assert summary["change"]["income_pct"] == 187.5
    assert summary["change"]["expense_pct"] == 420.0
    assert summary["change"]["net_difference"] == 3150 - 1500
    assert report["period"]["previous_start"] == "2026-05-01"


def test_change_is_none_without_a_baseline():
    report = build_finance_report([_row(1, "2026-06-05", 100, "Income")], *JUNE, today=TODAY)
    assert report["summary"]["change"]["income_pct"] is None
    assert report["summary"]["change"]["expense_pct"] is None


# --------------------------------------------------------------------------
# Monthly trend
# --------------------------------------------------------------------------

def test_monthly_has_one_bucket_per_month_including_empty_ones():
    report = build_finance_report(LEDGER, date(2026, 4, 1), date(2026, 6, 30), today=TODAY)
    assert [m["month"] for m in report["monthly"]] == ["2026-04", "2026-05", "2026-06"]
    april, may, june = report["monthly"]
    assert (april["income"], april["expense"]) == (0, 300)
    assert (may["income"], may["expense"]) == (2000, 500)
    assert june["net"] == 3150
    assert sum(m["net"] for m in report["monthly"]) == report["summary"]["current"]["net"]


# --------------------------------------------------------------------------
# Program breakdown
# --------------------------------------------------------------------------

def test_programs_include_general_operations_and_sum_to_the_summary(report):
    rows = {r["program_name"]: r for r in report["programs"]["rows"]}
    assert set(rows) == {"Emergency Rescue", "Rabies Vaccination", GENERAL_OPERATIONS}
    assert rows["Emergency Rescue"]["income"] == 4250
    assert rows["Emergency Rescue"]["expense"] == 1200
    assert rows[GENERAL_OPERATIONS]["income"] == 1500
    assert rows[GENERAL_OPERATIONS]["expense"] == 600

    totals = report["programs"]["totals"]
    assert totals["income"] == report["summary"]["current"]["income"]
    assert totals["expense"] == report["summary"]["current"]["expense"]


def test_programs_are_ordered_by_spend(report):
    expenses = [r["expense"] for r in report["programs"]["rows"]]
    assert expenses == sorted(expenses, reverse=True)


# --------------------------------------------------------------------------
# Restricted funds statement
# --------------------------------------------------------------------------

def test_restricted_statement_rolls_opening_to_closing(report):
    (rescue,) = report["restricted"]["rows"]
    assert rescue["program_name"] == "Emergency Rescue"
    assert rescue["opening"] == 700          # 1000 raised - 300 spent before June
    assert rescue["received"] == 4000        # the voided 9999 and the 250 pledge are out
    assert rescue["spent"] == 1200
    assert rescue["closing"] == 3500
    assert rescue["pledged"] == 250


def test_restricted_closing_matches_the_balance_the_spend_check_enforces():
    # Over all time, the statement's closing balance must be exactly the
    # `remaining` that create/edit compare an expense against. If the two
    # drift, the report shows money as spendable that the ledger refuses.
    report = build_finance_report(LEDGER, date(2000, 1, 1), TODAY, today=TODAY)
    (rescue,) = report["restricted"]["rows"]

    ledger_for_program = [r for r in LEDGER if r["program_id"] == RESCUE]
    supabase = _CapturingSupabase({"financial_transactions": {"select": ledger_for_program}})
    enforced = compute_restricted_balance(supabase, RESCUE)

    assert rescue["closing"] == float(enforced["remaining"])


def test_program_without_restricted_income_is_not_in_the_statement(report):
    assert VACCINES not in {r["program_id"] for r in report["restricted"]["rows"]}


# --------------------------------------------------------------------------
# Outstanding
# --------------------------------------------------------------------------

def test_outstanding_ages_open_items_as_at_period_end(report):
    outstanding = report["outstanding"]
    assert outstanding["as_of"] == "2026-06-30"

    receivables = outstanding["receivables"]
    assert receivables["count"] == 3
    assert receivables["total"] == 2450
    assert receivables["buckets"] == {"0-30": 1750, "31-60": 0, "61-90": 0, "90+": 700}
    # Oldest first: that is the one to chase.
    assert receivables["items"][0]["days"] == 166

    payables = outstanding["payables"]
    assert payables["total"] == 800
    assert payables["buckets"]["0-30"] == 800


def test_outstanding_is_aged_at_today_when_the_period_is_still_running():
    report = build_finance_report(LEDGER, date(2026, 6, 1), date(2026, 12, 31), today=TODAY)
    assert report["outstanding"]["as_of"] == str(TODAY)


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------

class _PagedSupabase:
    """Honours .range(), which the shared double ignores."""

    def __init__(self, rows):
        self._rows = rows
        self.calls = 0

    def table(self, name):
        outer = self

        class _Query:
            def __getattr__(self, _):
                return lambda *a, **k: self

            def range(self, start, end):
                self._slice = (start, end)
                return self

            def execute(self):
                outer.calls += 1
                start, end = self._slice
                return _FakeResult(outer._rows[start:end + 1])

        return _Query()


def test_fetch_ledger_reads_past_the_postgrest_page_limit():
    rows = [{"id": i} for i in range(PAGE_SIZE * 2 + 5)]
    supabase = _PagedSupabase(rows)
    assert len(fetch_ledger(supabase, TODAY)) == len(rows)
    assert supabase.calls == 3


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

def _get(path, role="Finance Officer"):
    supabase = _CapturingSupabase({"financial_transactions": {"select": LEDGER}})
    with acting_as(role):
        app.dependency_overrides[get_supabase] = lambda: supabase
        return _request("GET", path)


def test_report_endpoint_returns_the_report():
    response = _get("/api/reports/finance?start_date=2026-06-01&end_date=2026-06-30")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"period", "summary", "monthly", "programs", "restricted", "outstanding"}
    assert body["summary"]["current"]["income"] == 5750


@pytest.mark.parametrize("path", ["/api/reports/finance", "/api/reports/finance/summary"])
def test_reversed_period_is_rejected(path):
    response = _get(f"{path}?start_date=2026-06-30&end_date=2026-06-01")
    assert response.status_code == 400, response.text


def test_pdf_renders_every_section():
    response = _get("/api/reports/finance/summary?start_date=2026-06-01&end_date=2026-06-30")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
