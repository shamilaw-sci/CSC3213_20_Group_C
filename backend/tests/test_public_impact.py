"""Public impact numbers (GET /api/rescue_cases/impact).

Confirmed 2026-11-13: this year's totals for the homepage and donate page,
for anyone; good outcomes only (Died and Not found stay in staff reports);
supplies spent on rescues but no donation totals. Public and read with
service_role, so the response is pinned field by field.
"""

import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api import rescue_cases
from app.core.supabase import get_public_supabase
from app.main import app
from app.schemas.hr import SRI_LANKA
from tests.test_inventory import _FakeDB, _Query, client

NOW = datetime(2026, 11, 13, 10, 0, tzinfo=SRI_LANKA)


class _CountingDB(_FakeDB):
    def __init__(self):
        super().__init__()
        self.queries = 0

    def table(self, name):
        self.queries += 1
        return _Query(self, name)


def _db():
    db = _CountingDB()
    db.tables["rescue_cases"] = [
        # Reported this year
        {"status": "Reported", "outcome": None, "reported_at": "2026-02-01T09:00:00+05:30", "resolved_at": None},
        {"status": "In Treatment", "outcome": None, "reported_at": "2026-03-01T09:00:00+05:30", "resolved_at": None},
        {"status": "Resolved", "outcome": "Rehomed", "reported_at": "2026-04-01T09:00:00+05:30",
         "resolved_at": "2026-04-20T09:00:00+05:30"},
        {"status": "Resolved", "outcome": "Released", "reported_at": "2026-05-01T09:00:00+05:30",
         "resolved_at": "2026-05-10T09:00:00+05:30"},
        {"status": "Resolved", "outcome": "Died", "reported_at": "2026-06-01T09:00:00+05:30",
         "resolved_at": "2026-06-02T09:00:00+05:30"},
        {"status": "Resolved", "outcome": "Not found", "reported_at": "2026-07-01T09:00:00+05:30",
         "resolved_at": "2026-07-01T12:00:00+05:30"},
        # Reported last year, transferred this year: counts as an outcome, not as reported
        {"status": "Resolved", "outcome": "Transferred", "reported_at": "2025-12-20T09:00:00+05:30",
         "resolved_at": "2026-01-03T09:00:00+05:30"},
        # Last year entirely
        {"status": "Resolved", "outcome": "Rehomed", "reported_at": "2025-03-01T09:00:00+05:30",
         "resolved_at": "2025-03-05T09:00:00+05:30"},
    ]
    db.tables["inventory_transactions"] = [
        {"rescue_case_id": "a", "transaction_type": "Issue", "total_cost": 400, "transaction_date": "2026-04-02"},
        {"rescue_case_id": "a", "transaction_type": "Return", "total_cost": 100, "transaction_date": "2026-04-03"},
        {"rescue_case_id": None, "transaction_type": "Issue", "total_cost": 9999, "transaction_date": "2026-04-02"},
        {"rescue_case_id": "b", "transaction_type": "Issue", "total_cost": 5000, "transaction_date": "2025-12-31"},
    ]
    return db


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    rescue_cases._impact_cache.clear()

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz is None else NOW.astimezone(tz)
    monkeypatch.setattr(rescue_cases, "datetime", _Clock)
    yield
    app.dependency_overrides.clear()


def _get(db):
    app.dependency_overrides[get_public_supabase] = lambda: db
    return client.get("/api/rescue_cases/impact")  # no sign-in


def test_anyone_gets_this_years_totals():
    r = _get(_db())
    assert r.status_code == 200, r.text
    body = r.json()
    assert {k: body[k] for k in body if k != "as_of"} == {
        "year": 2026,
        "reported": 6,          # last year's cases left out
        "cared_for": 4,         # not the unclaimed one, not Not found; Died was cared for
        "rehomed": 1,
        "released": 1,
        "transferred": 1,       # resolved this year, though reported last year
        "supplies_cost": 300.0, # case supplies this year, less the reversal; not program stock
    }


def test_the_response_is_totals_and_nothing_else():
    """Public and service_role: any new field must be a deliberate change."""
    assert set(_get(_db()).json()) == {
        "year", "reported", "cared_for", "rehomed", "released", "transferred", "supplies_cost", "as_of"}


def test_it_is_cached_rather_than_queried_on_every_visit(monkeypatch):
    db = _db()
    clock = {"t": 1000.0}
    monkeypatch.setattr(rescue_cases, "monotonic", lambda: clock["t"])

    first = _get(db).json()
    queried = db.queries
    db.tables["rescue_cases"].append(
        {"status": "Reported", "outcome": None, "reported_at": "2026-11-12T09:00:00+05:30", "resolved_at": None})

    clock["t"] += rescue_cases.IMPACT_CACHE_SECONDS - 1
    assert _get(db).json()["reported"] == first["reported"] and db.queries == queried

    clock["t"] += 2
    assert _get(db).json()["reported"] == first["reported"] + 1


def test_it_still_works_before_case_supplies_existed():
    db = _db()
    original = db.table

    class _NoColumn:
        def __getattr__(self, name):
            return lambda *a, **k: self

        @property
        def not_(self):
            return self

        def execute(self):
            from postgrest.exceptions import APIError
            raise APIError({"message": "column inventory_transactions.rescue_case_id does not exist", "code": "42703"})

    db.table = lambda name: _NoColumn() if name == "inventory_transactions" else original(name)
    r = _get(db)
    assert r.status_code == 200 and r.json()["supplies_cost"] == 0
