"""scripts/seed_demo_users.py against an in-memory Supabase stand-in."""

import importlib.util
import itertools
from pathlib import Path
from types import SimpleNamespace

import pytest

_spec = importlib.util.spec_from_file_location(
    "seed_demo_users", Path(__file__).resolve().parents[1] / "scripts" / "seed_demo_users.py")
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)


class _Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self.op = db, table, [], ("select", None)

    def select(self, *_):
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def insert(self, row):
        self.op = ("insert", row)
        return self

    def upsert(self, row):
        self.op = ("upsert", row)
        return self

    def update(self, changes):
        self.op = ("update", changes)
        return self

    def execute(self):
        rows = self.db.tables.setdefault(self.table, [])
        kind, data = self.op
        self.db.writes.append((kind, self.table)) if kind != "select" else None
        if kind == "insert":
            row = {"id": next(self.db.ids), **data}
            rows.append(row)
            return SimpleNamespace(data=[row])
        if kind == "upsert":
            existing = next((r for r in rows if r["id"] == data["id"]), None)
            existing.update(data) if existing else rows.append(dict(data))
            return SimpleNamespace(data=[data])
        matched = [r for r in rows if all(r.get(c) == v for c, v in self.filters)]
        if kind == "update":
            for r in matched:
                r.update(data)
        return SimpleNamespace(data=matched)


class _Db:
    def __init__(self, roles, users=(), auth=()):
        self.ids = itertools.count(100)
        self.tables = {"roles": [{"id": i, "role_name": n} for i, n in roles], "users": list(users),
                       "employee_profile": []}
        self.auth_users = list(auth)
        self.writes = []
        self.auth = SimpleNamespace(admin=SimpleNamespace(create_user=self._create, list_users=self._list))

    def table(self, name):
        return _Query(self, name)

    def _create(self, attrs):
        assert attrs["email_confirm"] is True
        user = SimpleNamespace(id=f"uid-{attrs['email']}", email=attrs["email"])
        self.auth_users.append(user)
        return SimpleNamespace(user=user)

    def _list(self, page, per_page):
        return self.auth_users[(page - 1) * per_page:page * per_page]


@pytest.fixture
def run(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "service-key")

    def _run(db, check=False):
        monkeypatch.setattr(seed, "create_client", lambda *_: db)
        seed.main(check=check)
        return db
    return _run


def _role_of(db, email):
    names = {r["id"]: r["role_name"] for r in db.tables["roles"]}
    return names[next(u["role_id"] for u in db.tables["users"] if u["email"] == email)]


def test_a_new_project_gets_all_seven_roles_and_logins(run):
    db = run(_Db(roles=[(1, "Admin"), (2, "Director")]))

    assert [r["role_name"] for r in db.tables["roles"]] == seed.ROLES
    for email, role, _ in seed.USERS:
        assert _role_of(db, email) == role
    linked = {p["user_id"] for p in db.tables["employee_profile"]}
    assert linked == {f"uid-{e}" for e, _, profile in seed.USERS if profile}


def test_hr_and_finance_are_no_longer_swapped(run):
    db = run(_Db(roles=list(enumerate(seed.ROLES, 1))))

    assert _role_of(db, "hr@vff.org") == "HR Officer"
    assert _role_of(db, "finance@vff.org") == "Finance Officer"


def test_a_second_run_changes_nothing(run, capsys):
    db = run(_Db(roles=[(1, "Admin"), (2, "Director")]))
    db.writes.clear()
    run(db)

    assert db.writes == []
    assert "Nothing to change" in capsys.readouterr().out


def test_a_wrong_role_is_corrected_and_the_linked_employee_kept(run):
    db = _Db(roles=list(enumerate(seed.ROLES, 1)),
             users=[{"id": "uid-hr", "email": "hr@vff.org", "role_id": 3}])
    db.tables["employee_profile"].append({"id": 1, "user_id": "uid-hr", "first_name": "Dilani", "nic": "x"})
    run(db)

    assert _role_of(db, "hr@vff.org") == "HR Officer"
    assert [p["first_name"] for p in db.tables["employee_profile"] if p["user_id"] == "uid-hr"] == ["Dilani"]


def test_an_auth_account_without_a_users_row_is_reused(run):
    db = run(_Db(roles=list(enumerate(seed.ROLES, 1)),
                 auth=[SimpleNamespace(id="uid-old", email="admin@vff.org")]))

    assert [u.email for u in db.auth_users].count("admin@vff.org") == 1
    assert next(u for u in db.tables["users"] if u["email"] == "admin@vff.org")["id"] == "uid-old"


def test_check_mode_writes_nothing(run, capsys):
    db = run(_Db(roles=[(1, "Admin"), (2, "Director")]), check=True)

    assert db.writes == [] and db.auth_users == []
    assert "Run without --check" in capsys.readouterr().out
