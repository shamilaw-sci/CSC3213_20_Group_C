"""The "needs your action" inbox behind the bell (app/api/inbox.py).

Confirmed 2026-11-13: worked out live from the data, nothing stored or marked
read; each queue only for people who can act on it, and only when non-empty.
Nobody is asked to decide their own leave or correction.
"""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api import hr, inbox, inventory
from app.core.permissions import has_permission
from app.core.security import get_current_user
from app.core.supabase import get_supabase
from app.main import app
from tests.test_inventory import USER_ID, _FakeDB, client
from tests.test_rbac_matrix import ALL_ROLES

TODAY = date(2026, 11, 13)  # before payroll's approve-from day (25th)
ME_EMPLOYEE, OTHER_EMPLOYEE = 8, 9


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    monkeypatch.setattr(inbox, "_sl_today", lambda: TODAY)
    monkeypatch.setattr(hr, "_sl_today", lambda: TODAY)
    monkeypatch.setattr(inventory, "today_in_sri_lanka", lambda: TODAY)


def _busy_db():
    """Something in every queue, plus the caller's own requests."""
    db = _FakeDB(items=[
        {"id": 1, "item_name": "Gauze", "current_stock": 2, "reorder_level": 10, "expire_date": None},
        {"id": 2, "item_name": "Vaccine", "current_stock": 50, "reorder_level": 10, "expire_date": "2026-11-01"},
        {"id": 3, "item_name": "Tablets", "current_stock": 40, "reorder_level": 10, "expire_date": "2026-12-01"},
        {"id": 4, "item_name": "Empty", "current_stock": 0, "reorder_level": 0, "expire_date": "2026-11-01"},
    ])
    db.tables.update({
        "employee_profile": [{"id": ME_EMPLOYEE, "user_id": USER_ID}, {"id": OTHER_EMPLOYEE, "user_id": "u2"}],
        "leave_requests": [
            {"id": 1, "employee_id": OTHER_EMPLOYEE, "status": "Pending"},
            {"id": 2, "employee_id": OTHER_EMPLOYEE, "status": "Pending"},
            {"id": 3, "employee_id": ME_EMPLOYEE, "status": "Pending"},   # my own
            {"id": 4, "employee_id": OTHER_EMPLOYEE, "status": "Approved"},
        ],
        "attendance_correction_requests": [
            {"id": 1, "employee_id": OTHER_EMPLOYEE, "requested_by": "u2", "status": "Pending"},
            {"id": 2, "employee_id": ME_EMPLOYEE, "requested_by": USER_ID, "status": "Pending"},  # my own
        ],
        "attendance_settings": [{"id": 1, "tracking_start_date": "2026-09-01"}],
        "attendance_month_closes": [],  # October not closed
        "payroll_runs": [
            {"id": 1, "payroll_month": 10, "payroll_year": 2026, "status": "Draft"},
            {"id": 2, "payroll_month": 11, "payroll_year": 2026, "status": "Draft"},  # not until the 25th
            {"id": 3, "payroll_month": 9, "payroll_year": 2026, "status": "Approved"},
        ],
        "volunteers": [{"id": "v1", "status": "pending"}, {"id": "v2", "status": "approved"}],
        "rescue_cases": [
            {"id": "c1", "status": "Reported", "assigned_to": None, "urgency": "Critical"},
            {"id": "c2", "status": "Reported", "assigned_to": None, "urgency": "High"},
            {"id": "c3", "status": "Reported", "assigned_to": None, "urgency": "Low"},
            {"id": "c4", "status": "Reported", "assigned_to": "u2", "urgency": "Critical"},
            {"id": "c5", "status": "In Treatment", "assigned_to": None, "urgency": "Critical"},
        ],
    })
    return db


def _inbox(db, role="Admin"):
    async def _user():
        return {"id": USER_ID, "roles": {"role_name": role}}

    async def _sb():
        return db
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_supabase] = _sb
    try:
        return client.get("/api/inbox")
    finally:
        app.dependency_overrides.clear()


def _by_key(response):
    assert response.status_code == 200, response.text
    return {i["key"]: i for i in response.json()["items"]}


def test_admin_sees_every_queue_in_order_with_counts():
    r = _inbox(_busy_db())
    items = _by_key(r)

    assert list(items) == ["urgent_cases", "payroll", "leave", "corrections", "month_close",
                           "volunteers", "expiring", "low_stock"]
    assert items["urgent_cases"]["count"] == 2  # Reported, unclaimed, Critical/High only
    assert items["payroll"] == {"key": "payroll", "title": "Payroll for October 2026 to approve",
                                "count": 1, "href": "/hr/payroll", "tone": "action"}
    assert items["leave"]["count"] == 2        # not my own
    assert items["corrections"]["count"] == 1  # not my own
    assert items["month_close"]["title"] == "October 2026 attendance is not closed yet"
    assert items["volunteers"]["count"] == 1
    assert items["expiring"]["count"] == 2 and "(1 already expired)" in items["expiring"]["title"]
    assert items["low_stock"]["count"] == 1
    assert items["low_stock"]["tone"] == "alert"
    assert r.json()["total"] == sum(i["count"] for i in items.values())


PERMISSION_FOR = {
    "urgent_cases": ("rescue:assign", "rescue:manage"),
    "payroll": ("payroll:approve",),
    "leave": ("leave:approve",),
    "corrections": ("hr:attendance:manage",),
    "month_close": ("hr:attendance:manage",),
    "volunteers": ("volunteers:approve",),
    "expiring": ("inventory:manage",),
    "low_stock": ("inventory:manage",),
}


@pytest.mark.parametrize("role", ALL_ROLES)
def test_each_role_sees_exactly_the_queues_it_can_act_on(role):
    expected = [k for k, perms in PERMISSION_FOR.items() if any(has_permission(role, p) for p in perms)]
    assert list(_by_key(_inbox(_busy_db(), role))) == expected


def test_an_empty_queue_is_left_out():
    db = _FakeDB(items=[])
    db.tables.update({
        "employee_profile": [], "leave_requests": [], "attendance_correction_requests": [],
        "attendance_settings": [{"id": 1, "tracking_start_date": "2026-09-01"}],
        "attendance_month_closes": [{"close_month": 10, "close_year": 2026, "status": "Closed"}],
        "payroll_runs": [], "volunteers": [], "rescue_cases": [],
    })
    r = _inbox(db)
    assert r.json() == {"items": [], "total": 0}


def test_a_reopened_month_still_needs_closing():
    db = _busy_db()
    db.tables["attendance_month_closes"] = [{"close_month": 10, "close_year": 2026, "status": "Reopened"}]
    assert "month_close" in _by_key(_inbox(db))


def test_no_close_is_asked_for_a_month_before_tracking_started():
    db = _busy_db()
    db.tables["attendance_settings"] = [{"id": 1, "tracking_start_date": "2026-11-01"}]
    assert "month_close" not in _by_key(_inbox(db))


def test_several_ready_drafts_are_counted_together(monkeypatch):
    monkeypatch.setattr(hr, "_sl_today", lambda: date(2026, 11, 26))  # November is approvable now
    items = _by_key(_inbox(_busy_db()))
    assert items["payroll"]["count"] == 2 and items["payroll"]["title"] == "2 payroll drafts to approve"


def test_a_failing_queue_is_left_out_and_the_rest_still_show(monkeypatch):
    def _broken(supabase, user):
        raise RuntimeError("volunteers table missing")
    monkeypatch.setattr(inbox, "QUEUES", [
        (lambda role: True, _broken), *inbox.QUEUES,
    ])
    items = _by_key(_inbox(_busy_db()))
    assert "leave" in items and len(items) == 8


def test_the_inbox_needs_a_signed_in_user():
    assert client.get("/api/inbox").status_code in (401, 403)
