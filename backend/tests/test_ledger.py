"""The general ledger: running balance, filters, search, totals and paging."""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.supabase import get_supabase
from app.main import app
from app.services.ledger import GENERAL, build_ledger_page
from tests.test_finance_reports import RESCUE, VACCINES, _row
from tests.test_rbac_matrix import _request, acting_as
from tests.test_restricted_funds import _CapturingSupabase

LEDGER = [
    _row(1, "2026-04-01", 1000, "Income", program_id=RESCUE, is_restricted=True),
    _row(2, "2026-04-05", 300, "Expense", program_id=RESCUE),
    _row(3, "2026-04-05", 9999, "Income", status="Voided"),
    _row(4, "2026-05-10", 2500, "Income", status="Receivable"),
    _row(5, "2026-05-20", 1200, "Expense", program_id=VACCINES),
    _row(6, "2026-06-02", 45000, "Expense"),
]


def _page(**kwargs):
    return build_ledger_page(LEDGER, **kwargs)


def _ids(page):
    return [r["id"] for r in page["rows"]]


# --------------------------------------------------------------------------
# Running balance
# --------------------------------------------------------------------------

def test_balance_runs_in_date_order_and_skips_voided():
    rows = {r["id"]: r for r in _page()["rows"]}
    assert rows[1]["balance"] == 1000
    assert rows[2]["balance"] == 700
    # Same date as row 2, later id: after it. Voided: no balance, no effect.
    assert rows[3]["balance"] is None
    assert rows[4]["balance"] == 3200          # pending income counts
    assert rows[5]["balance"] == 2000
    assert rows[6]["balance"] == -43000


def test_balance_is_the_true_position_even_when_filtered():
    # Filtering to expenses must not turn the balance into an expense
    # subtotal: row 5 still sits at 2000 in the whole ledger.
    rows = {r["id"]: r for r in _page(tx_type="Expense")["rows"]}
    assert set(rows) == {2, 5, 6}
    assert rows[5]["balance"] == 2000


def test_balance_is_independent_of_input_order():
    shuffled = list(reversed(LEDGER))
    assert build_ledger_page(shuffled)["rows"] == _page()["rows"]


# --------------------------------------------------------------------------
# Sorting and filters
# --------------------------------------------------------------------------

def test_newest_first_by_default_and_oldest_on_request():
    assert _ids(_page()) == [6, 5, 4, 3, 2, 1]
    assert _ids(_page(newest_first=False)) == [1, 2, 3, 4, 5, 6]


@pytest.mark.parametrize("filters, expected", [
    ({"start": date(2026, 5, 1)}, [6, 5, 4]),
    ({"end": date(2026, 4, 30)}, [3, 2, 1]),
    ({"start": date(2026, 5, 1), "end": date(2026, 5, 31)}, [5, 4]),
    ({"tx_type": "Income"}, [4, 3, 1]),
    ({"status": "Voided"}, [3]),
    ({"status": "Receivable"}, [4]),
    ({"program": str(RESCUE)}, [2, 1]),
    ({"program": GENERAL}, [6, 4, 3]),
    ({"restricted": True}, [1]),
    ({"tx_type": "Expense", "program": GENERAL}, [6]),
])
def test_filters(filters, expected):
    assert _ids(_page(**filters)) == expected


@pytest.mark.parametrize("q, expected", [
    ("rabies", [5]),                 # program name, case-insensitive
    ("general", [6, 4, 3]),
    ("receivable", [4]),
    ("restricted", [1]),
    ("#4", [4]),
    ("45000", [6]),                  # amount without separators
    ("45,000", [6]),                 # ...and with them
    ("1200", [5]),
    ("   ", [6, 5, 4, 3, 2, 1]),     # blank search filters nothing
])
def test_search(q, expected):
    assert _ids(_page(q=q)) == expected


# --------------------------------------------------------------------------
# Totals and paging
# --------------------------------------------------------------------------

def test_totals_cover_every_match_not_just_the_page_and_skip_voided():
    page = _page(page_size=2)
    assert len(page["rows"]) == 2
    assert page["total"] == 6
    assert page["totals"] == {"income": 3500, "expense": 46500, "net": -43000}


def test_totals_follow_the_filters():
    assert _page(program=str(RESCUE))["totals"] == {"income": 1000, "expense": 300, "net": 700}


def test_paging():
    first = _page(page_size=4)
    assert (first["page"], first["pages"], _ids(first)) == (1, 2, [6, 5, 4, 3])
    second = _page(page_size=4, page=2)
    assert _ids(second) == [2, 1]


def test_page_past_the_end_clamps_to_the_last_page():
    assert _page(page_size=4, page=99)["page"] == 2


def test_everything_returns_all_matches_unpaged():
    page = _page(page_size=2, everything=True)
    assert len(page["rows"]) == 6 and page["pages"] == 1


def test_empty_ledger():
    page = build_ledger_page([])
    assert page["rows"] == [] and page["total"] == 0 and page["pages"] == 1
    assert page["totals"] == {"income": 0, "expense": 0, "net": 0}


# --------------------------------------------------------------------------
# Endpoint
# --------------------------------------------------------------------------

def _get(path, role="Finance Officer"):
    supabase = _CapturingSupabase({"financial_transactions": {"select": LEDGER}})
    with acting_as(role):
        app.dependency_overrides[get_supabase] = lambda: supabase
        return _request("GET", path)


def test_endpoint_returns_a_page():
    response = _get(f"/api/finance/ledger?program={RESCUE}&page_size=1")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2 and len(body["rows"]) == 1
    assert body["rows"][0]["program_name"] == "Emergency Rescue"


@pytest.mark.parametrize("query", [
    "start_date=2026-06-01&end_date=2026-05-01",   # reversed
    "transaction_type=Refund",
    "status=Paid",
    "program=rescue",
    "page_size=500",
    "sort=random",
])
def test_endpoint_rejects_bad_parameters(query):
    assert _get(f"/api/finance/ledger?{query}").status_code in (400, 422)


def test_director_can_read_the_ledger_data():
    # finance:read, like GET /transactions. Whether the Ledger *page* is in
    # Director's navigation is a separate, front-end decision.
    assert _get("/api/finance/ledger", role="Director").status_code == 200
