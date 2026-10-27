# backend/tests/unit/test_auth_lockdown.py
#
# Signup role, the case board's embedded assignee, and the assign dropdown's
# eligible-user list. No network: Supabase is the RBAC matrix's fake, and the
# user repository is replaced so no real Auth signup can happen.

import pytest

from app.api import auth
from app.core.supabase import get_public_supabase, get_supabase
from app.main import app
from tests.test_rbac_matrix import (
    ALL_ROLES, CASE_ID, OTHER_USER_ID, USER_ID, _case_row, _FakeSupabase, acting_as, client,
)
from app.core.permissions import has_permission

GENERAL_STAFF_ID = 6
THIRD_USER_ID = "66666666-6666-6666-6666-666666666666"


# --------------------------------------------------------------------------
# Signup role
# --------------------------------------------------------------------------

@pytest.fixture
def signup(monkeypatch):
    """Register against a fake roles table; returns the role_ids registered with."""
    registered = []

    class FakeRepo:
        def __init__(self, supabase):
            pass

        def register(self, email, password, role_id):
            registered.append(role_id)
            from app.domain.entities import User
            return User(id=USER_ID, email=email, role_id=role_id)

    monkeypatch.setattr(auth, "SupabaseUserRepository", FakeRepo)

    def install(roles_rows):
        fake = lambda: _FakeSupabase({"roles": roles_rows})
        app.dependency_overrides[get_supabase] = fake
        app.dependency_overrides[get_public_supabase] = fake

    yield install, registered
    app.dependency_overrides.clear()


@pytest.mark.parametrize("body_extra", [
    {},
    {"role_id": 1},                          # the escalation: ask for Admin
    {"role_id": 2},                          # the old default, Director
    {"role_id": "Admin"},
    {"role": "Admin", "name": "X (Admin)"},  # what the admin register page sends
], ids=["none", "role_id-admin", "role_id-director", "role_id-string", "role-string"])
def test_signup_always_gets_general_staff(signup, body_extra):
    install, registered = signup
    install([{"id": GENERAL_STAFF_ID}])

    response = client.post(
        "/api/auth/register",
        json={"email": "new.signup@vff.org", "password": "pw-123456", **body_extra},
    )

    assert response.status_code == 200, response.text
    assert registered == [GENERAL_STAFF_ID]


def test_signup_refused_when_general_staff_role_is_missing(signup):
    install, registered = signup
    install([])

    response = client.post("/api/auth/register", json={"email": "new.signup@vff.org", "password": "pw-123456"})

    assert response.status_code == 500
    assert registered == [], "registered a user with no role decided"


# --------------------------------------------------------------------------
# GET /cases embeds the assignee
# --------------------------------------------------------------------------

def _cases_tables():
    return {
        "rescue_cases": [
            _case_row(status="In Treatment", assigned_to=USER_ID),
            {**_case_row(), "id": "77777777-7777-7777-7777-777777777777", "assigned_to": None},
            # Assigned to a user who no longer exists.
            {**_case_row(status="In Treatment"), "id": "88888888-8888-8888-8888-888888888888",
             "assigned_to": THIRD_USER_ID},
        ],
        "users": [{"id": USER_ID, "email": "field@vff.test"}],
        "employee_profile": [{"user_id": USER_ID, "first_name": "Nimal", "last_name": "Perera"}],
    }


def test_cases_embed_assignee_email_and_name():
    with acting_as("General Staff", tables=_cases_tables()):
        response = client.get("/api/rescue_cases/cases")

    assert response.status_code == 200, response.text
    by_id = {c["id"]: c for c in response.json()}
    assert by_id[CASE_ID]["assignee"] == {"email": "field@vff.test", "display_name": "Nimal Perera"}
    assert by_id["77777777-7777-7777-7777-777777777777"]["assignee"] is None
    assert by_id["88888888-8888-8888-8888-888888888888"]["assignee"] is None


def test_assignee_without_profile_has_no_display_name():
    tables = {**_cases_tables(), "employee_profile": []}
    with acting_as("General Staff", tables=tables):
        case = next(c for c in client.get("/api/rescue_cases/cases").json() if c["id"] == CASE_ID)
    assert case["assignee"] == {"email": "field@vff.test", "display_name": None}


def test_cases_expose_no_other_staff_fields():
    tables = _cases_tables()
    tables["users"] = [{**tables["users"][0], "role_id": 1, "password_hash": "x", "created_at": "t"}]
    tables["employee_profile"] = [{**tables["employee_profile"][0], "nic": "123V", "base_salary": 1}]
    with acting_as("General Staff", tables=tables):
        case = next(c for c in client.get("/api/rescue_cases/cases").json() if c["id"] == CASE_ID)
    assert set(case["assignee"]) == {"email", "display_name"}


# --------------------------------------------------------------------------
# GET /assignees
# --------------------------------------------------------------------------

def _directory():
    return {
        "users": [
            {"id": USER_ID, "email": "zed@vff.test", "roles": {"role_name": "General Staff"}},
            {"id": OTHER_USER_ID, "email": "ops@vff.test", "roles": {"role_name": "Operations Lead"}},
            {"id": THIRD_USER_ID, "email": "admin@vff.test", "roles": {"role_name": "Admin"}},
            {"id": "99999999-9999-9999-9999-999999999991", "email": "dir@vff.test",
             "roles": {"role_name": "Director"}},
            {"id": "99999999-9999-9999-9999-999999999992", "email": "hr@vff.test",
             "roles": {"role_name": "HR Officer"}},
            {"id": "99999999-9999-9999-9999-999999999993", "email": "fin@vff.test",
             "roles": {"role_name": "Finance Officer"}},
            {"id": "99999999-9999-9999-9999-999999999994", "email": "sys@vff.test",
             "roles": {"role_name": "System Administrator"}},
            {"id": "99999999-9999-9999-9999-999999999995", "email": "norole@vff.test", "roles": None},
        ],
        "employee_profile": [{"user_id": USER_ID, "first_name": "Amal", "last_name": "Silva"}],
    }


def test_assignees_are_exactly_the_roles_that_can_work_a_case():
    with acting_as("Admin", tables=_directory()):
        response = client.get("/api/rescue_cases/assignees")

    assert response.status_code == 200, response.text
    got = {a["email"]: a["role_name"] for a in response.json()}
    expected = {
        u["email"]: u["roles"]["role_name"] for u in _directory()["users"]
        if u["roles"] and has_permission(u["roles"]["role_name"], "rescue:manage")
    }
    assert got == expected
    # Pinned as well as derived, so a permission-table change that alters who
    # is offered for assignment shows up here as a decision, not silently.
    assert set(got.values()) == {"General Staff", "Operations Lead", "Admin"}


def test_assignees_carry_display_name_and_sort_by_it():
    with acting_as("Admin", tables=_directory()):
        body = client.get("/api/rescue_cases/assignees").json()
    # By display name where there is one, else email: "admin@…" < "Amal Silva" < "ops@…".
    assert [a["email"] for a in body] == ["admin@vff.test", "zed@vff.test", "ops@vff.test"]
    assert body[1] == {
        "id": USER_ID, "email": "zed@vff.test", "display_name": "Amal Silva", "role_name": "General Staff",
    }


@pytest.mark.parametrize("role", ALL_ROLES)
def test_assignees_gated_on_rescue_assign(role):
    with acting_as(role, tables=_directory()):
        status = client.get("/api/rescue_cases/assignees").status_code
    assert (status == 200) == has_permission(role, "rescue:assign"), f"{role} -> {status}"
