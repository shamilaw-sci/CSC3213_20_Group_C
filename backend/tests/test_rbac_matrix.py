"""RBAC matrix tests: every protected route x every role.

The permission matrix is imported from app.core.permissions rather than copied into
this file. An earlier hardcoded copy here drifted out of sync with the real matrix
and the tests kept passing against the stale duplicate.
"""

import contextlib
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.permissions import ROLE_PERMISSIONS, has_permission
from app.core.security import get_current_user
from app.core.supabase import get_public_supabase, get_supabase
from app.main import app

# raise_server_exceptions=False so a handler that outruns the DB stub yields a
# 500 instead of propagating. These tests assert on the permission gate; what
# happens after it is another suite's problem.
client = TestClient(app, raise_server_exceptions=False)

ALL_ROLES = sorted(ROLE_PERMISSIONS)

USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"
CASE_ID = "33333333-3333-3333-3333-333333333333"


# --------------------------------------------------------------------------
# Supabase test double
# --------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    """Chainable stand-in for the supabase query builder.

    Rows are keyed by operation so a single table can return one payload for a
    read and a different one for the subsequent write.
    """

    def __init__(self, rows, on_update=None):
        self._rows = rows if isinstance(rows, dict) else {"select": rows}
        self._op = "select"
        self._on_update = on_update

    def select(self, *a, **k):
        self._op = "select"
        return self

    def insert(self, *a, **k):
        self._op = "insert"
        return self

    def update(self, data=None, *a, **k):
        self._op = "update"
        if self._on_update is not None and data is not None:
            self._on_update(data)
        return self

    def delete(self, *a, **k):
        self._op = "delete"
        return self

    def __getattr__(self, name):
        # eq / neq / gte / lte / order / limit / single / ... all just chain.
        def _chain(*a, **k):
            return self
        return _chain

    def execute(self):
        return _FakeResult(self._rows.get(self._op, []))


class _FakeSupabase:
    def __init__(self, tables=None, on_update=None):
        self._tables = tables or {}
        self._on_update = on_update

    def table(self, name):
        return _FakeQuery(self._tables.get(name, []), on_update=self._on_update)

    def rpc(self, name, params=None):
        return _FakeQuery(self._tables.get(f"rpc:{name}", []))


def _case_row(status="Reported", assigned_to=None):
    return {
        "id": CASE_ID,
        "animal_type": "Dog",
        "description": None,
        "status": status,
        # CaseOut requires urgency; the fixture was not updated when the field
        # was added, so every test asserting a 200 from this endpoint failed.
        "urgency": "Medium",
        "lat": 6.9271,
        "lng": 79.8612,
        "photo_url": None,
        "reported_by": None,
        "assigned_to": assigned_to,
        "reported_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


@contextlib.contextmanager
def acting_as(role, tables=None, user_id=USER_ID, capture_update=None):
    """Run requests as `role`, with supabase stubbed out.

    Overrides are cleared in a finally block; a failing assertion must not leak
    an authenticated user into the next test. Pass a dict as `capture_update`
    to record the payload of the first `.update(...)` call under
    `capture_update["update_data"]`, for tests that need to verify what the
    endpoint actually wrote rather than just the response status.
    """

    async def _current_user():
        return {
            "id": user_id,
            "sub": user_id,
            "email": "rbac@vff.test",
            "roles": {"role_name": role},
        }

    on_update = (lambda data: capture_update.setdefault("update_data", data)) if capture_update is not None else None

    async def _supabase():
        return _FakeSupabase(tables, on_update=on_update)

    app.dependency_overrides[get_current_user] = _current_user
    app.dependency_overrides[get_supabase] = _supabase
    app.dependency_overrides[get_public_supabase] = _supabase
    try:
        yield
    finally:
        app.dependency_overrides.clear()


def _request(method, path, json=None):
    return client.request(method, path, json=json)


# --------------------------------------------------------------------------
# Unauthenticated access
# --------------------------------------------------------------------------

PROTECTED_ROUTES = [
    ("GET", "/api/hr/employees"),
    ("GET", "/api/finance/summary"),
    ("GET", "/api/admin/audit-logs"),
    ("GET", "/api/rescue_cases/cases"),
    ("PATCH", f"/api/rescue_cases/cases/{CASE_ID}/status"),
    # Previously reachable anonymously; see the Known gaps section below.
    ("PUT", f"/api/auth/users/{OTHER_USER_ID}/role"),
    ("DELETE", f"/api/auth/users/{OTHER_USER_ID}"),
    ("POST", "/api/inventory/items"),
    ("POST", "/api/inventory/transactions"),
    ("GET", "/api/admin/audit-logs/verify"),
]

PUBLIC_ROUTES = [
    ("GET", "/api/rescue_cases/geo"),
    ("GET", "/api/rescue_cases/hotspots"),
]


@pytest.mark.parametrize("method, path", PROTECTED_ROUTES)
def test_protected_routes_reject_anonymous(method, path):
    # HTTPBearer(auto_error=True) answers a missing Authorization header with
    # 403 "Not authenticated" rather than 401.
    response = _request(method, path, json={})
    assert response.status_code == 403, f"{method} {path} was reachable anonymously"


@pytest.mark.parametrize("method, path", PUBLIC_ROUTES)
def test_public_rescue_routes_allow_anonymous(method, path):
    # The public reporting map must not regress behind auth.
    app.dependency_overrides[get_public_supabase] = lambda: _FakeSupabase()
    try:
        response = _request(method, path)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code not in (401, 403), f"{method} {path} now requires auth"


# --------------------------------------------------------------------------
# Single-permission routes x roles
# --------------------------------------------------------------------------

# (method, path, permission enforced by the route's require_permission dependency)
PERMISSION_ROUTES = [
    ("GET", "/api/hr/employees", "hr:manage"),
    ("POST", "/api/hr/employees", "hr:manage"),
    ("POST", "/api/hr/attendance/clock-in", "hr:attendance:self"),
    ("GET", "/api/hr/attendance", "hr:attendance:manage"),
    ("POST", "/api/hr/payroll/generate", "payroll:generate"),
    ("GET", "/api/finance/summary", "finance:read"),
    ("GET", "/api/finance/transactions", "finance:read"),
    ("POST", "/api/finance/transactions", "finance:write"),
    ("GET", "/api/finance/programs", "programs:read"),
    ("POST", "/api/finance/programs", "programs:manage"),
    ("GET", "/api/admin/audit-logs", "audit:read"),
    ("GET", "/api/admin/audit-logs/verify", "audit:read"),
    ("GET", "/api/admin/stats", "admin:users"),
    ("GET", "/api/rescue_cases/cases", "rescue:read"),
    ("PUT", f"/api/auth/users/{OTHER_USER_ID}/role", "admin:users"),
    ("DELETE", f"/api/auth/users/{OTHER_USER_ID}", "admin:users"),
    ("POST", "/api/inventory/items", "inventory:issue"),
    ("POST", "/api/inventory/transactions", "inventory:issue"),
]


@pytest.mark.parametrize("role", ALL_ROLES)
@pytest.mark.parametrize("method, path, permission", PERMISSION_ROUTES)
def test_route_permissions(role, method, path, permission):
    with acting_as(role):
        response = _request(method, path, json={})

    if has_permission(role, permission):
        # Past the permission gate. The stubbed DB may still yield 422/500 —
        # only the 403 is meaningful here.
        assert response.status_code != 403, (
            f"{role} holds {permission} but {method} {path} returned 403"
        )
    else:
        assert response.status_code == 403, (
            f"{role} lacks {permission} but {method} {path} returned "
            f"{response.status_code}"
        )


def test_permission_routes_cover_every_granted_permission():
    """Guard against a permission existing in the matrix with no route exercising it."""
    covered = {perm for _, _, perm in PERMISSION_ROUTES}
    granted = {p for perms in ROLE_PERMISSIONS.values() for p in perms}
    uncovered = granted - covered - {
        # Enforced inside update_case_status rather than by a route dependency;
        # covered by the rescue scenario tests below.
        "rescue:manage",
        "rescue:assign",
        # Enforced conditionally inside create_transaction — it only applies to
        # an expense that overspends a restricted program — so no route-level
        # Depends can express it. Covered by the restricted-fund tests below.
        "finance:restricted:override",
        # No route enforces these yet.
        "payroll:approve",
        "inventory:read",
        "inventory:issue",
    }
    assert not uncovered, f"permissions with no route coverage: {sorted(uncovered)}"


# --------------------------------------------------------------------------
# Rescue case status/assignment — conditional authorization
# --------------------------------------------------------------------------

# update_case_status gates the route on rescue:read, then distinguishes:
#   * changing status            -> rescue:manage
#   * assigning to someone else  -> rescue:assign
#   * Reported -> In Treatment with an assignee is the claim-and-start handoff
#     itself, so rescue:assign alone authorizes it
# Reported is also the only stage a case can be unclaimed in — leaving it
# requires an assignee (current or supplied), enforced independently of role.
RESCUE_SCENARIOS = [
    # id, current_status, current_assignee, new_status, payload_assigned_to, roles expected to succeed
    ("resolve", "In Treatment", USER_ID, "Resolved", None,
     {"Admin", "General Staff", "Operations Lead"}),
    ("no-op-status", "Reported", None, "Reported", None,
     {"Admin", "Director", "HR Officer", "General Staff", "Operations Lead"}),
    ("self-assign", "Reported", None, "In Treatment", USER_ID,
     {"Admin", "Director", "HR Officer", "General Staff", "Operations Lead"}),
    ("handoff-to-colleague", "Reported", None, "In Treatment", OTHER_USER_ID,
     {"Admin", "Director", "HR Officer"}),
    ("reassign-colleague", "In Treatment", USER_ID, "In Treatment", OTHER_USER_ID,
     {"Admin", "Director", "HR Officer"}),
    # Re-opening a closed case is management, not assignment — the narrow
    # handoff exemption must not let rescue:assign holders through.
    ("reopen-resolved", "Resolved", USER_ID, "In Treatment", OTHER_USER_ID, {"Admin"}),
    # Releasing a case back to Reported needs no assignee — the endpoint
    # clears one unconditionally, so this exercises pure status management.
    ("release-to-reported", "In Treatment", USER_ID, "Reported", None,
     {"Admin", "General Staff", "Operations Lead"}),
]


@pytest.mark.parametrize("role", ALL_ROLES)
@pytest.mark.parametrize(
    "scenario_id, current_status, current_assignee, new_status, payload_assigned_to, allowed_roles",
    RESCUE_SCENARIOS,
    ids=[s[0] for s in RESCUE_SCENARIOS],
)
def test_rescue_case_status_authorization(
    role, scenario_id, current_status, current_assignee, new_status, payload_assigned_to, allowed_roles
):
    tables = {
        "rescue_cases": {
            "select": [{"status": current_status, "assigned_to": current_assignee}],
            "update": [_case_row(status=new_status, assigned_to=payload_assigned_to or current_assignee)],
        }
    }
    payload = {"new_status": new_status}
    if payload_assigned_to is not None:
        payload["assigned_to"] = payload_assigned_to

    with acting_as(role, tables=tables):
        response = client.patch(
            f"/api/rescue_cases/cases/{CASE_ID}/status", json=payload
        )

    if role in allowed_roles:
        assert response.status_code == 200, (
            f"{role} should be able to {scenario_id}, got "
            f"{response.status_code}: {response.text}"
        )
    else:
        assert response.status_code == 403, (
            f"{role} should not be able to {scenario_id}, got "
            f"{response.status_code}"
        )


def test_rescue_case_status_404_when_case_missing():
    with acting_as("Admin", tables={"rescue_cases": {"select": []}}):
        response = client.patch(
            f"/api/rescue_cases/cases/{CASE_ID}/status",
            json={"new_status": "Resolved"},
        )
    assert response.status_code == 404


def test_leaving_reported_without_any_assignee_is_rejected():
    """Neither a current nor a supplied assignee -> 400, for any role, on any
    move out of Reported. Guards against a raw drag or direct API call
    reproducing the "In Treatment with nobody assigned" bug."""
    tables = {
        "rescue_cases": {
            "select": [{"status": "Reported", "assigned_to": None}],
            "update": [_case_row(status="In Treatment")],
        }
    }
    with acting_as("Admin", tables=tables):
        response = client.patch(
            f"/api/rescue_cases/cases/{CASE_ID}/status",
            json={"new_status": "In Treatment"},
        )
    assert response.status_code == 400


def test_moving_to_reported_clears_existing_assignee():
    """Releasing a case back to Reported always drops its assignee, even if
    the caller didn't ask for that — Reported means unclaimed."""
    captured = {}

    tables = {
        "rescue_cases": {
            "select": [{"status": "In Treatment", "assigned_to": USER_ID}],
            "update": [_case_row(status="Reported", assigned_to=None)],
        }
    }
    with acting_as("Admin", tables=tables, capture_update=captured):
        response = client.patch(
            f"/api/rescue_cases/cases/{CASE_ID}/status",
            json={"new_status": "Reported"},
        )
    assert response.status_code == 200
    # Assert the key is actually present and null, not just absent — .get()
    # can't distinguish "explicitly cleared" from "never touched".
    update_data = captured.get("update_data", {})
    assert "assigned_to" in update_data, f"assigned_to was never written: {update_data}"
    assert update_data["assigned_to"] is None


def test_rescue_read_gate_blocks_finance_officer():
    """Finance Officer holds no rescue permission and is stopped at the route."""
    with acting_as("Finance Officer", tables={"rescue_cases": [_case_row()]}):
        assert client.get("/api/rescue_cases/cases").status_code == 403
        assert client.patch(
            f"/api/rescue_cases/cases/{CASE_ID}/status",
            json={"new_status": "Reported"},
        ).status_code == 403


# --------------------------------------------------------------------------
# Known gaps
# --------------------------------------------------------------------------

# These routes carry no auth dependency at all. Each is reachable by an
# unauthenticated caller; the role/user ones allow privilege escalation.
# xfail(strict=True) keeps the suite honest: once a route is protected the
# test XPASSes and fails, prompting removal from this list.
UNPROTECTED_ROUTES = [
    ("GET", "/api/auth/users"),
    ("GET", "/api/inventory/items"),
    ("GET", "/api/inventory/transactions"),
]


@pytest.mark.xfail(strict=True, reason="route has no auth dependency; see UNPROTECTED_ROUTES")
@pytest.mark.parametrize("method, path", UNPROTECTED_ROUTES)
def test_unprotected_routes_should_require_auth(method, path):
    app.dependency_overrides[get_supabase] = lambda: _FakeSupabase()
    try:
        response = _request(method, path, json={"role_id": 1})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code in (401, 403), (
        f"{method} {path} is reachable without authentication"
    )
