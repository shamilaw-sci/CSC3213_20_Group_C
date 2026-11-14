"""GET /api/admin/audit-logs without a users foreign key (migration 033).

system_audit_logs.user_id is no longer a foreign key, so the list cannot embed
users(...) through PostgREST. It looks the users up in a second query instead,
and a row written by a since-deleted account keeps its uuid and shows no user.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.supabase import get_supabase
from app.main import app
from tests.test_rbac_matrix import _FakeResult, _request, acting_as

LIVE_USER = "11111111-1111-1111-1111-111111111111"
DELETED_USER = "22222222-2222-2222-2222-222222222222"

AUDIT_ROWS = [
    {"id": 2, "user_id": LIVE_USER, "action_type": "USER_ROLE_CHANGE",
     "timestamp": "2026-11-14T05:24:14+00:00"},
    {"id": 1, "user_id": DELETED_USER, "action_type": "USER_REGISTER",
     "timestamp": "2026-11-14T05:23:50+00:00"},
    {"id": 0, "user_id": None, "action_type": "SYSTEM",
     "timestamp": "2026-11-14T05:00:00+00:00"},
]
USERS = [{"id": LIVE_USER, "email": "hr@vff.test", "roles": {"role_name": "HR Officer"}}]


class _Query:
    def __init__(self, sb, table):
        self._sb, self._table, self._ids = sb, table, None

    def select(self, columns="*", *a, **k):
        self._sb.selects.append((self._table, columns))
        return self

    def in_(self, column, values):
        self._ids = set(values)
        return self

    def __getattr__(self, name):
        return lambda *a, **k: self

    def execute(self):
        if self._table == "system_audit_logs":
            return _FakeResult([dict(r) for r in AUDIT_ROWS])
        if self._table == "users":
            return _FakeResult([u for u in USERS if self._ids is None or u["id"] in self._ids])
        return _FakeResult([])


class _Supabase:
    def __init__(self):
        self.selects = []

    def table(self, name):
        return _Query(self, name)


def _list():
    sb = _Supabase()
    with acting_as("Admin"):
        app.dependency_overrides[get_supabase] = lambda: sb
        response = _request("GET", "/api/admin/audit-logs")
    return response, sb


def test_audit_log_list_does_not_embed_users_through_a_foreign_key():
    response, sb = _list()

    assert response.status_code == 200, response.text
    audit_selects = [cols for table, cols in sb.selects if table == "system_audit_logs"]
    assert audit_selects and all("users(" not in cols for cols in audit_selects), audit_selects


def test_audit_log_list_attaches_users_and_survives_a_deleted_account():
    response, _ = _list()
    rows = {r["id"]: r for r in response.json()}

    assert rows[2]["users"] == {"email": "hr@vff.test", "roles": {"role_name": "HR Officer"}}
    # The deleted account's row is still there, still names the uuid, and has
    # no user to show rather than failing the whole list.
    assert rows[1]["user_id"] == DELETED_USER
    assert rows[1]["users"] is None
    assert rows[0]["users"] is None
