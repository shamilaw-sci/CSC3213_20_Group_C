"""The monthly management report (app/services/monthly_report.py,
GET /api/reports/monthly).

Confirmed 2026-11-13: Admin and Director only (reports:monthly); any month
up to the current one, which is labelled "month to date"; four sections
built from what the app already computes.
"""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api import reports
from app.core.permissions import has_permission
from app.core.security import get_current_user
from app.core.supabase import get_supabase
from app.main import app
from app.services import monthly_report
from app.services.monthly_report import build_monthly_report, comparison_bounds, month_bounds
from tests.test_finance_reports import _row
from tests.test_inventory import USER_ID, _FakeDB, _Query, client
from tests.test_rbac_matrix import ALL_ROLES

TODAY = date(2026, 11, 13)


@pytest.mark.parametrize("first, last, expected", [
    (date(2026, 11, 1), date(2026, 11, 13), (date(2026, 10, 1), date(2026, 10, 13))),   # to date
    (date(2026, 10, 1), date(2026, 10, 31), (date(2026, 9, 1), date(2026, 9, 30))),     # whole month
    (date(2026, 3, 1), date(2026, 3, 30), (date(2026, 2, 1), date(2026, 2, 28))),       # clamped
    (date(2026, 1, 1), date(2026, 1, 31), (date(2025, 12, 1), date(2025, 12, 31))),     # year end
])
def test_it_compares_with_the_previous_calendar_month(first, last, expected):
    assert comparison_bounds(first, last) == expected


def test_the_current_month_runs_to_today():
    assert month_bounds(2026, 11, TODAY) == (date(2026, 11, 1), TODAY, True)
    assert month_bounds(2026, 10, TODAY) == (date(2026, 10, 1), date(2026, 10, 31), False)


class _ReportQuery(_Query):
    def neq(self, col, value):
        self.filters.append(lambda r: r.get(col) != value)
        return self


class _ReportDB(_FakeDB):
    def table(self, name):
        return _ReportQuery(self, name)


def _db():
    db = _ReportDB(items=[{"id": 1, "item_name": "Gauze", "current_stock": 2, "reorder_level": 10,
                           "expire_date": "2026-10-01"}])
    db.tables.update({
        "rescue_cases": [
            {"id": "a", "status": "Resolved", "outcome": "Rehomed",
             "resolved_at": "2026-10-05T10:00:00+05:30", "reported_at": "2026-10-01T09:00:00+05:30"},
            {"id": "b", "status": "In Treatment", "outcome": None, "resolved_at": None,
             "reported_at": "2026-10-20T09:00:00+05:30"},
            {"id": "c", "status": "Reported", "outcome": None, "resolved_at": None,
             "reported_at": "2026-09-30T09:00:00+05:30"},  # September's
        ],
        "inventory_transactions": [
            {"rescue_case_id": "a", "program_id": None, "transaction_type": "Issue", "total_cost": 300,
             "transaction_date": "2026-10-03", "reverses_id": None},
            {"rescue_case_id": None, "program_id": 7, "transaction_type": "Issue", "total_cost": 1000,
             "transaction_date": "2026-10-10", "reverses_id": None},
            {"rescue_case_id": None, "program_id": 7, "transaction_type": "Return", "total_cost": 200,
             "transaction_date": "2026-10-12", "reverses_id": None},
            {"rescue_case_id": None, "program_id": None, "transaction_type": "Issue", "total_cost": 50,
             "transaction_date": "2026-10-15", "reverses_id": None, "notes": "Broken"},
            {"rescue_case_id": None, "program_id": 7, "transaction_type": "Issue", "total_cost": 999,
             "transaction_date": "2026-09-28", "reverses_id": None},  # September's
        ],
        "inventory_batches": [{"quantity_remaining": 4, "unit_cost": 25}, {"quantity_remaining": 0, "unit_cost": 99}],
        "donations": [
            {"amount": 1000, "purpose": "general", "status": "paid", "paid_at": "2026-10-02T10:00:00+05:30"},
            {"amount": 500, "purpose": "program", "status": "paid", "paid_at": "2026-10-03T10:00:00+05:30"},
            {"amount": 700, "purpose": "general", "status": "pending", "paid_at": None},
        ],
        "employee_profile": [
            {"id": 1, "status": "Active", "date_joined": "2020-01-01"},
            {"id": 2, "status": "Active", "date_joined": "2026-10-15"},
            {"id": 3, "status": "Inactive", "date_joined": "2026-10-16"},
        ],
        "leave_request_days": [
            {"request_id": 10, "leave_date": "2026-10-06", "fraction": 1},
            {"request_id": 10, "leave_date": "2026-10-07", "fraction": 0.5},
            {"request_id": 11, "leave_date": "2026-10-08", "fraction": 1},   # rejected
        ],
        "leave_requests": [{"id": 10, "status": "Approved"}, {"id": 11, "status": "Rejected"}],
        "payroll_runs": [{"payroll_month": 10, "payroll_year": 2026, "status": "Draft", "total": 150000}],
    })
    return db


@pytest.fixture(autouse=True)
def _ledger(monkeypatch):
    monkeypatch.setattr(monthly_report, "fetch_ledger", lambda sb, end: [
        _row(1, "2026-09-10", 400, "Income"),
        _row(2, "2026-10-10", 1500, "Income"),
        _row(3, "2026-10-12", 600, "Expense"),
    ])


def test_the_report_gathers_each_section_for_the_month():
    r = build_monthly_report(_db(), 2026, 10, TODAY)

    assert (r["period"], r["first"], r["last"], r["to_date"]) == ("October 2026", "2026-10-01", "2026-10-31", False)

    assert r["rescue"]["reported"] == 2 and r["rescue"]["resolved"] == 1
    assert r["rescue"]["by_outcome"] == [{"outcome": "Rehomed", "cases": 1, "supplies_cost": 300.0}]  # empty ones left out
    assert r["rescue"]["open_cases"] == 2

    fin = r["finance"]
    assert fin["summary"]["current"]["income"] == 1500 and fin["summary"]["previous"]["income"] == 400
    assert fin["summary"]["change"]["income_pct"] == 275.0
    assert fin["previous"] == {"start": "2026-09-01", "end": "2026-09-30"}
    assert fin["donations"] == {"count": 2, "total": 1500.0, "program": 500.0, "general": 1000.0}

    assert r["people"] == {"headcount": 2, "joined": 1, "leave_days": 1.5,
                           "payroll": {"status": "Draft", "total": 150000.0}}

    st = r["stock"]
    assert st["value_on_hand"] == 100.0
    assert st["issued"] == {"programs": 1000.0, "cases": 300.0, "adjustments": 50.0}
    assert st["issued_total"] == 1350.0 and st["returned"] == 200.0
    assert st["low_stock_count"] == 1 and st["expired_count"] == 1


def test_a_month_without_payroll_says_so():
    db = _db()
    db.tables["payroll_runs"] = []
    assert build_monthly_report(db, 2026, 10, TODAY)["people"]["payroll"] is None


def _get(role, query, db=None):
    async def _user():
        return {"id": USER_ID, "roles": {"role_name": role}}

    async def _sb():
        return db or _db()
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_supabase] = _sb
    try:
        return client.get(f"/api/reports/monthly?{query}")
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def _today(monkeypatch):
    monkeypatch.setattr(reports, "_sl_today", lambda: TODAY)


def test_admin_downloads_a_pdf(_today):
    r = _get("Admin", "year=2026&month=10")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert 'filename="monthly_report_2026-10.pdf"' in r.headers["content-disposition"]
    assert r.content.startswith(b"%PDF")


def test_the_current_month_is_allowed_and_a_future_one_refused(_today):
    assert _get("Director", "year=2026&month=11").status_code == 200
    r = _get("Director", "year=2026&month=12")
    assert r.status_code == 400 and "hasn't started" in r.json()["detail"]


@pytest.mark.parametrize("role", ALL_ROLES)
def test_only_admin_and_director_can_download(role, _today):
    r = _get(role, "year=2026&month=10")
    allowed = has_permission(role, "reports:monthly")
    assert (r.status_code == 200) == allowed, (role, r.status_code)
    assert allowed == (role in ("Admin", "Director"))
