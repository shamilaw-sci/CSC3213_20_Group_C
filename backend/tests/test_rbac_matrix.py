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
VOLUNTEER_ID = "44444444-4444-4444-4444-444444444444"
ASSIGNMENT_ID = "55555555-5555-5555-5555-555555555555"


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
    ("GET", "/api/finance/transactions/1/stock-movement"),
    ("GET", "/api/admin/audit-logs"),
    ("GET", "/api/rescue_cases/cases"),
    ("PATCH", f"/api/rescue_cases/cases/{CASE_ID}/status"),
    ("GET", f"/api/rescue_cases/cases/{CASE_ID}/timeline"),
    ("GET", "/api/rescue_cases/report?year=2026&month=11"),
    ("POST", f"/api/rescue_cases/cases/{CASE_ID}/notes"),
    # Previously reachable anonymously; see the Known gaps section below.
    ("PUT", f"/api/auth/users/{OTHER_USER_ID}/role"),
    ("DELETE", f"/api/auth/users/{OTHER_USER_ID}"),
    ("POST", "/api/inventory/items"),
    ("PATCH", "/api/inventory/items/1"),
    ("POST", "/api/inventory/transactions"),
    ("POST", "/api/inventory/transactions/1/reverse"),
    ("PATCH", "/api/inventory/batches/1"),
    ("GET", "/api/admin/audit-logs/verify"),
    # The volunteer roster holds names, emails and phone numbers of people who
    # are not employees, so anonymous reachability here would be worse than on
    # most of the routes above.
    ("GET", "/api/volunteers"),
    ("GET", "/api/volunteers/shifts"),
    ("GET", "/api/volunteers/assignments"),
    ("PATCH", f"/api/volunteers/{VOLUNTEER_ID}/review"),
    ("POST", f"/api/volunteers/{VOLUNTEER_ID}/link-shared"),
    ("POST", "/api/volunteers/shifts"),
    ("POST", "/api/volunteers/assignments"),
    ("DELETE", f"/api/volunteers/assignments/{ASSIGNMENT_ID}"),
]

PUBLIC_ROUTES = [
    ("GET", "/api/rescue_cases/geo"),
    # Volunteers have no login at all, so these three must work with no token —
    # and must keep working when a stale staff token is present, which is why
    # they depend on get_public_supabase rather than get_supabase.
    ("GET", "/api/volunteers/my-assignments/some-unknown-token"),
]


@pytest.mark.parametrize("method, path", PROTECTED_ROUTES)
def test_protected_routes_reject_anonymous(method, path):
    # 401, not 403: get_current_user answers a missing token itself rather
    # than leaving it to HTTPBearer, whose own error is a 403.
    response = _request(method, path, json={})
    assert response.status_code == 401, f"{method} {path} was reachable anonymously"


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
    ("POST", "/api/hr/schedules", "hr:manage"),
    ("POST", "/api/hr/holidays", "hr:manage"),
    ("PUT", "/api/hr/attendance-tracking", "hr:manage"),
    ("PUT", "/api/hr/employees/1/attendance-tracking", "hr:manage"),
    ("GET", "/api/leave/requests", "leave:approve"),
    ("GET", "/api/leave/me", "hr:attendance:self"),
    ("POST", "/api/hr/employees", "hr:manage"),
    ("POST", "/api/hr/attendance/clock-in", "hr:attendance:self"),
    ("GET", "/api/hr/attendance", "hr:attendance:manage"),
    ("GET", "/api/hr/attendance/me/month?year=2026&month=10", "hr:attendance:self"),
    ("POST", "/api/hr/payroll/generate", "payroll:generate"),
    ("POST", "/api/hr/payroll/runs/1/approve", "payroll:approve"),
    ("GET", "/api/finance/summary", "finance:read"),
    ("GET", "/api/finance/transactions", "finance:read"),
    ("GET", "/api/finance/ledger", "finance:read"),
    ("GET", "/api/finance/transactions/1/stock-movement", "finance:read"),
    ("POST", "/api/finance/transactions", "finance:write"),
    ("GET", "/api/finance/programs", "programs:read"),
    ("POST", "/api/finance/programs", "programs:manage"),
    # Was check_user_role(["admin", "director", "finance"]), which compares
    # role names: "finance officer" != "finance", so the Finance Officer was
    # refused their own report.
    ("GET", "/api/reports/finance/summary?start_date=2026-01-01&end_date=2026-01-31", "finance:read"),
    ("GET", "/api/reports/finance?start_date=2026-01-01&end_date=2026-01-31", "finance:read"),
    ("GET", "/api/reports/monthly?year=2026&month=10", "reports:monthly"),
    ("GET", "/api/admin/audit-logs", "audit:read"),
    ("GET", "/api/admin/audit-logs/verify", "audit:read"),
    ("GET", "/api/admin/stats", "admin:users"),
    ("GET", "/api/rescue_cases/cases", "rescue:read"),
    ("GET", "/api/rescue_cases/assignees", "rescue:assign"),
    ("GET", f"/api/rescue_cases/cases/{CASE_ID}/timeline", "rescue:read"),
    ("GET", "/api/rescue_cases/report?year=2026&month=11", "rescue:read"),
    ("POST", f"/api/rescue_cases/cases/{CASE_ID}/notes", "rescue:manage"),
    ("GET", "/api/auth/users", "admin:users"),
    ("PUT", f"/api/auth/users/{OTHER_USER_ID}/role", "admin:users"),
    ("DELETE", f"/api/auth/users/{OTHER_USER_ID}", "admin:users"),
    ("POST", "/api/inventory/items", "inventory:manage"),
    ("PATCH", "/api/inventory/items/1", "inventory:manage"),
    ("POST", "/api/inventory/transactions/1/reverse", "inventory:manage"),
    ("PATCH", "/api/inventory/batches/1", "inventory:manage"),
    ("GET", "/api/inventory/items/1/batches", "inventory:read"),
    ("GET", "/api/inventory/batches", "inventory:read"),
    ("GET", "/api/inventory/transactions", "inventory:read"),
    # POST /api/inventory/transactions takes inventory:manage OR
    # inventory:issue, which a single-permission row cannot express; it is
    # covered role by role in test_inventory.py.
    # Volunteers. read = see the roster and rota; approve = vetting decisions;
    # assign = scheduling. Deliberately three permissions rather than one, so
    # this table is also what proves the split is actually enforced and not
    # just declared in permissions.py.
    ("GET", "/api/volunteers", "volunteers:read"),
    ("GET", "/api/volunteers/shifts", "volunteers:read"),
    ("GET", "/api/volunteers/assignments", "volunteers:read"),
    ("PATCH", f"/api/volunteers/{VOLUNTEER_ID}/review", "volunteers:approve"),
    ("POST", "/api/volunteers/shifts", "volunteers:assign"),
    ("POST", "/api/volunteers/assignments", "volunteers:assign"),
    ("DELETE", f"/api/volunteers/assignments/{ASSIGNMENT_ID}", "volunteers:assign"),
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
        # Enforced only together with hr:attendance:manage on the monthly grid
        # (require_any_permission), which a single-permission row cannot
        # express. Covered by test_grid_needs_attendance_manage_or_read in
        # test_attendance_month.py, across every role.
        "hr:attendance:read",
        # Enforced only together with inventory:manage (POST /transactions)
        # or inventory:read (the item list, alerts, outstanding) through
        # require_any_permission. Covered across every role in
        # test_inventory.py.
        "inventory:issue",
    }
    assert not uncovered, f"permissions with no route coverage: {sorted(uncovered)}"


# --------------------------------------------------------------------------
# Volunteers — the two gates PERMISSION_ROUTES cannot express
# --------------------------------------------------------------------------

def _volunteer_row(status="approved"):
    return {
        "id": VOLUNTEER_ID,
        "full_name": "Nimal Perera",
        "email": "nimal@example.com",
        "phone": None,
        "skills": [],
        "skills_other": None,
        "availability": [],
        "status": status,
        "access_token": "t" * 43,
        "link_shared_at": None,
        "applied_at": "2026-01-01T00:00:00+00:00",
        "reviewed_at": None,
        "reviewed_by": None,
        "staff_notes": None,
    }


@pytest.mark.parametrize("role", ALL_ROLES)
def test_link_shared_accepts_either_permission(role):
    """
    Copying a volunteer's link is gated on volunteers:approve OR
    volunteers:assign, which no single-permission row in PERMISSION_ROUTES can
    describe. Gating on either alone would strand one of the two roles: an HR
    Officer who just approved someone and cannot send them their link, or an
    Operations Lead who just rostered someone and cannot reach them.
    """
    allowed = has_permission(role, "volunteers:approve") or has_permission(
        role, "volunteers:assign"
    )
    tables = {"volunteers": {"select": [_volunteer_row()],
                             "update": [_volunteer_row()]}}
    with acting_as(role, tables=tables):
        response = _request("POST", f"/api/volunteers/{VOLUNTEER_ID}/link-shared")

    if allowed:
        assert response.status_code != 403, (
            f"{role} holds approve or assign but link-shared returned 403"
        )
    else:
        assert response.status_code == 403, (
            f"{role} holds neither approve nor assign but link-shared returned "
            f"{response.status_code}"
        )


@pytest.mark.parametrize("token", [
    "obviously-not-a-real-token",
    "' OR 1=1 --",
    "x" * 500,
    # Traversal-shaped input is normalised by the URL layer before routing, so
    # it never reaches the handler and gets the framework's own 404. Included
    # anyway: "the route does not exist" is a perfectly good outcome, and the
    # point of the case is that it does not 500 or echo anything back.
    "../../etc/passwd",
])
def test_unknown_volunteer_token_degrades_gracefully(token):
    """
    An invalid token must 404 cleanly — no crash, no stack trace, and nothing
    echoed back to the caller.
    """
    app.dependency_overrides[get_public_supabase] = lambda: _FakeSupabase()
    try:
        response = client.get(f"/api/volunteers/my-assignments/{token}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404, response.text
    body = response.text.lower()
    assert "traceback" not in body
    assert "supabase" not in body
    # Never reflect the supplied token back — that is how a 404 page becomes a
    # reflected-XSS or a log-poisoning vector.
    assert token.lower() not in body


@pytest.mark.parametrize("token", ["obviously-not-a-real-token", "' OR 1=1 --"])
def test_invalid_token_message_is_uniform(token):
    """
    Every rejection the handler itself makes must be indistinguishable —
    unknown token, pending applicant, rejected applicant, deactivated
    volunteer. A different status or message per case would turn this route
    into an oracle for the status of any token someone holds.
    """
    app.dependency_overrides[get_public_supabase] = lambda: _FakeSupabase()
    try:
        response = client.get(f"/api/volunteers/my-assignments/{token}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "This link is not valid"


def test_access_log_redacts_volunteer_token():
    """
    A volunteer link token is their only credential and it travels in the URL
    path, which uvicorn's access logger writes verbatim. Without the filter in
    app/main.py every token would be logged in plaintext on first use, then
    shipped wherever those logs are aggregated.
    """
    import logging as _logging
    from app.main import RedactVolunteerToken

    token = "S3cr3tT0k3n_" + "x" * 31
    record = _logging.LogRecord(
        name="uvicorn.access", level=_logging.INFO, pathname="", lineno=0,
        msg='%s - "%s %s HTTP/%s" %d', args=(
            "127.0.0.1:1234", "GET", f"/api/volunteers/my-assignments/{token}",
            "1.1", 200,
        ),
        exc_info=None,
    )

    assert RedactVolunteerToken().filter(record) is True
    rendered = record.getMessage()
    assert token not in rendered, "token survived into the access log"
    assert "<redacted>" in rendered
    # The rest of the line must still be useful for debugging.
    assert "GET" in rendered and "200" in rendered


def test_access_log_filter_leaves_other_paths_alone():
    """The filter must not mangle every other route's logging."""
    import logging as _logging
    from app.main import RedactVolunteerToken

    record = _logging.LogRecord(
        name="uvicorn.access", level=_logging.INFO, pathname="", lineno=0,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:1234", "GET", "/api/rescue_cases/geo", "1.1", 200),
        exc_info=None,
    )
    RedactVolunteerToken().filter(record)
    assert "/api/rescue_cases/geo" in record.getMessage()


def test_access_log_filter_survives_unexpected_args():
    """A uvicorn change to the access-log shape must degrade to 'not redacted',
    never to an exception inside a logging filter — that would break logging
    for every request in the application."""
    import logging as _logging
    from app.main import RedactVolunteerToken

    for args in [(), ("only-one",), None, ("a", "b")]:
        record = _logging.LogRecord(
            name="uvicorn.access", level=_logging.INFO, pathname="", lineno=0,
            msg="something", args=args, exc_info=None,
        )
        assert RedactVolunteerToken().filter(record) is True


@pytest.mark.parametrize("status", ["pending", "rejected", "inactive"])
def test_unapproved_volunteer_token_is_inert(status):
    """A token exists from the moment of application, but must not work until
    the volunteer is approved — and must fail identically to an unknown one."""
    # The endpoint filters on status in the query, so an unapproved volunteer
    # is simply not returned; the stub mirrors that by returning no rows.
    app.dependency_overrides[get_public_supabase] = lambda: _FakeSupabase(
        {"volunteers": {"select": []}}
    )
    try:
        response = client.get("/api/volunteers/my-assignments/" + "t" * 43)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "This link is not valid"


# --------------------------------------------------------------------------
# Rescue case status/assignment — conditional authorization
# --------------------------------------------------------------------------

# update_case_status gates the route on rescue:read, then distinguishes:
#   * changing status            -> rescue:manage
#   * assigning to someone else  -> rescue:assign
#   * Reported -> In Treatment with an assignee is the claim-and-start handoff
#     itself, so rescue:assign alone authorizes it — for someone else
#   * naming yourself as assignee (claiming) -> rescue:manage, by any route:
#     a claimant must be able to move the case on to Resolved
# Reported is also the only stage a case can be unclaimed in — leaving it
# requires an assignee (current or supplied), enforced independently of role.
RESCUE_SCENARIOS = [
    # id, current_status, current_assignee, new_status, payload_assigned_to, roles expected to succeed
    ("resolve", "In Treatment", USER_ID, "Resolved", None,
     {"Admin", "General Staff", "Operations Lead"}),
    ("no-op-status", "Reported", None, "Reported", None,
     {"Admin", "Director", "HR Officer", "General Staff", "Operations Lead"}),
    # HR Officer and Director hold rescue:assign but not rescue:manage. They
    # could claim through the handoff until it was closed: a claimant who
    # cannot resolve owns a case nobody can finish.
    ("self-assign", "Reported", None, "In Treatment", USER_ID,
     {"Admin", "General Staff", "Operations Lead"}),
    # The same claim by the other route: taking over a case already in
    # treatment. Status is unchanged, so only the claim rule stops it.
    ("self-reassign", "In Treatment", OTHER_USER_ID, "In Treatment", USER_ID,
     {"Admin", "General Staff", "Operations Lead"}),
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
    if new_status == "Resolved" and current_status != "Resolved":
        payload["outcome"] = "Released"  # required to resolve (030_case_timeline_outcome.sql)

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
