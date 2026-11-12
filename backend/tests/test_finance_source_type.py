"""Ledger source_type (migration 013): the Description column and the
fallback for a database that does not have the column yet."""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.finance_reports import fetch_ledger
from app.services.ledger import build_ledger_page, describe
from tests.test_finance_reports import RESCUE, _row


def _with_source(row, source):
    return {**row, "source_type": source}


LEDGER = [
    _with_source(_row(1, "2026-04-01", 1000, "Income", program_id=RESCUE, is_restricted=True), "donation"),
    _with_source(_row(2, "2026-04-05", 2500, "Expense"), "stock_in"),
    _with_source(_row(3, "2026-04-30", 80000, "Expense", status="Receivable"), "payroll"),
    _with_source(_row(4, "2026-05-02", 300, "Expense", program_id=RESCUE), "manual"),
    # Read before migration 013: no source_type at all.
    _row(5, "2026-05-03", 50, "Income"),
]


def _rows():
    return {r["id"]: r for r in build_ledger_page(LEDGER)["rows"]}


def test_description_is_source_then_program_or_general():
    rows = _rows()
    assert rows[1]["description"] == "Donation-Emergency Rescue"
    assert rows[2]["description"] == "Stock in-General"
    assert rows[3]["description"] == "Payroll-General"
    assert rows[4]["description"] == "Manual-Emergency Rescue"


def test_row_without_source_type_reads_as_manual():
    row = _rows()[5]
    assert row["source_type"] == "manual"
    assert row["description"] == "Manual-General"


def test_existing_fields_are_unchanged():
    # program_name keeps its old "General Operations" label for other pages.
    row = _rows()[2]
    assert row["program_name"] == "General Operations"
    assert row["source_type"] == "stock_in"


def test_search_matches_the_description():
    page = build_ledger_page(LEDGER, q="stock in")
    assert [r["id"] for r in page["rows"]] == [2]


def test_unknown_source_is_still_readable():
    assert describe({"program_id": None, "source_type": "grant_fund"}) == "Grant fund-General"


class _Query:
    def __init__(self, client):
        self.client = client

    def select(self, columns):
        self.client.selects.append(columns)
        self.columns = columns
        return self

    def lte(self, *a):
        return self

    def order(self, *a):
        return self

    def range(self, *a):
        return self

    def execute(self):
        if "source_type" in self.columns and self.client.missing_column:
            raise Exception("{'code': '42703', 'message': 'column financial_transactions.source_type does not exist'}")
        return type("R", (), {"data": [{"id": 1}]})()


class _Client:
    def __init__(self, missing_column):
        self.missing_column = missing_column
        self.selects = []

    def table(self, name):
        assert name == "financial_transactions"
        return _Query(self)


def test_fetch_ledger_default_query_is_unchanged():
    client = _Client(missing_column=False)
    fetch_ledger(client, date.max)
    assert client.selects == [
        "id, transaction_date, amount, transaction_type, status, "
        "program_id, is_restricted, programs(program_name)"
    ]


def test_fetch_ledger_reads_source_type_when_asked():
    client = _Client(missing_column=False)
    assert fetch_ledger(client, date.max, include_source=True) == [{"id": 1}]
    # memo (migration 026) labels the payroll payables.
    assert client.selects[0].endswith(", source_type, memo")
    assert len(client.selects) == 1


def test_fetch_ledger_falls_back_before_migration_026():
    class NoMemo(_Client):
        def table(self, name):
            query = super().table(name)
            original = query.execute

            def execute():
                if "memo" in query.columns:
                    raise Exception("{'code': '42703', 'message': 'column financial_transactions.memo does not exist'}")
                return original()

            query.execute = execute
            return query

    client = NoMemo(missing_column=False)
    assert fetch_ledger(client, date.max, include_source=True) == [{"id": 1}]
    assert client.selects[-1].endswith(", source_type")


def test_a_memo_names_the_entry():
    row = {"program_id": None, "source_type": "payroll", "memo": "November 2026 ETF (3%)"}
    assert describe(row) == "Payroll-November 2026 ETF (3%)"


def test_fetch_ledger_falls_back_before_migration_013():
    client = _Client(missing_column=True)
    assert fetch_ledger(client, date.max, include_source=True) == [{"id": 1}]
    assert "source_type" not in client.selects[-1]


def test_fetch_ledger_does_not_hide_other_errors():
    class Broken(_Client):
        def table(self, name):
            raise RuntimeError("network down")

    with pytest.raises(RuntimeError):
        fetch_ledger(Broken(missing_column=False), date.max, include_source=True)
