"""Employee create, edit, login linking and deactivation (app/api/hr.py).

Covers what the database used to be left to catch, with a bare 500 as the
result: NIC format and uniqueness, salary and status. Also that an edit
writes only the fields it was sent, so it can no longer unlink an employee
from their login by leaving user_id out; that a login links to one employee
at most; and that a deactivated employee can no longer clock in or out or
take on new leave.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.supabase import get_supabase
from app.main import app
from tests.test_rbac_matrix import USER_ID, _request, acting_as

LOGIN_ID = "66666666-6666-6666-6666-666666666666"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    """A query over an in-memory table that honours eq(), unlike the shared
    fakes, so the NIC check sees only matching rows."""

    def __init__(self, db, name):
        self._db, self._name = db, name
        self._filters, self._op, self._data = [], "select", None

    def select(self, *a, **k):
        return self

    def insert(self, data, *a, **k):
        self._op, self._data = "insert", data
        return self

    def update(self, data, *a, **k):
        self._op, self._data = "update", data
        self._db.updates.append((self._name, dict(data)))
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def __getattr__(self, name):
        return lambda *a, **k: self

    def execute(self):
        rows = self._db.tables.setdefault(self._name, [])
        if self._op == "insert":
            row = {"id": len(rows) + 100, **self._data}
            rows.append(row)
            return _Result([row])
        matched = [r for r in rows if all(r.get(c) == v for c, v in self._filters)]
        if self._op == "update":
            for r in matched:
                r.update(self._data)
        return _Result([dict(r) for r in matched])


class _Db:
    def __init__(self, employees):
        self.tables = {"employee_profile": [dict(e) for e in employees], "system_audit_logs": []}
        self.updates = []

    def table(self, name):
        return _Query(self, name)

    def employee_writes(self):
        return [d for t, d in self.updates if t == "employee_profile"]


KAMALA = {
    "id": 2, "first_name": "Kamala", "last_name": "Silva", "nic": "925678123V",
    "base_salary": 65000, "status": "Active", "user_id": None,
}
# A seeded demo profile: linked to a login, and with a NIC from before the
# format rule.
STAFF = {
    "id": 14, "first_name": "Staff", "last_name": "User", "nic": "DEMO5V",
    "base_salary": 60000, "status": "Active", "user_id": LOGIN_ID,
}


def _send(db, method, path, json=None, role="HR Officer"):
    with acting_as(role):
        app.dependency_overrides[get_supabase] = lambda: db
        return _request(method, path, json=json)


def _new(**changes):
    body = {"first_name": "Nimal", "last_name": "Fernando", "nic": "199512345678", "base_salary": 50000}
    body.update(changes)
    return body


# --------------------------------------------------------------------------
# Create
# --------------------------------------------------------------------------

def test_create_tidies_and_saves_a_valid_employee():
    db = _Db([KAMALA])
    response = _send(db, "POST", "/api/hr/employees", _new(first_name=" Nimal ", nic=" 951234567v "))

    assert response.status_code == 200, response.text
    saved = db.tables["employee_profile"][-1]
    assert saved["first_name"] == "Nimal"
    assert saved["nic"] == "951234567V"
    assert saved["status"] == "Active"


@pytest.mark.parametrize("nic", ["925678123V", "925678123v", " 925678123V "])
def test_a_nic_already_on_file_is_refused_with_409(nic):
    db = _Db([KAMALA])
    response = _send(db, "POST", "/api/hr/employees", _new(nic=nic))

    assert response.status_code == 409, response.text
    assert "925678123V" in response.json()["detail"]
    assert len(db.tables["employee_profile"]) == 1


@pytest.mark.parametrize("changes", [
    {"nic": "abc"},
    {"nic": "123456788765432"},          # 15 digits
    {"nic": "12345678V"},                # 8 digits + V
    {"base_salary": 0},
    {"base_salary": -5},
    {"first_name": "   "},
    {"last_name": "x" * 101},
    {"status": "Fired"},
])
def test_invalid_employee_details_are_refused_before_any_write(changes):
    db = _Db([KAMALA])
    response = _send(db, "POST", "/api/hr/employees", _new(**changes))

    assert response.status_code == 422, response.text
    assert len(db.tables["employee_profile"]) == 1


# --------------------------------------------------------------------------
# Edit
# --------------------------------------------------------------------------

def test_an_edit_writes_only_the_fields_sent_and_keeps_the_login_link():
    db = _Db([STAFF])
    response = _send(db, "PUT", "/api/hr/employees/14", {"base_salary": 65000})

    assert response.status_code == 200, response.text
    assert db.employee_writes() == [{"base_salary": 65000}]
    assert response.json()["user_id"] == LOGIN_ID


def test_an_employee_can_be_deactivated():
    db = _Db([STAFF])
    response = _send(db, "PUT", "/api/hr/employees/14", {"status": "Inactive"})

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "Inactive"


def test_unlinking_a_login_takes_an_explicit_null():
    db = _Db([STAFF])
    response = _send(db, "PUT", "/api/hr/employees/14", {"user_id": None})

    assert response.status_code == 200, response.text
    assert db.employee_writes() == [{"user_id": None}]


def test_an_edit_cannot_take_another_employees_nic():
    db = _Db([KAMALA, STAFF])
    response = _send(db, "PUT", "/api/hr/employees/14", {"nic": "925678123V"})

    assert response.status_code == 409, response.text
    assert db.employee_writes() == []


def test_an_edit_may_resend_the_employees_own_nic():
    db = _Db([KAMALA])
    response = _send(db, "PUT", "/api/hr/employees/2", {"nic": "925678123V", "base_salary": 70000})

    assert response.status_code == 200, response.text


@pytest.mark.parametrize("body", [
    {"first_name": None},
    {"base_salary": None},
    {"base_salary": -1},
    {"status": "Fired"},
])
def test_an_edit_cannot_blank_or_corrupt_a_required_field(body):
    db = _Db([STAFF])
    response = _send(db, "PUT", "/api/hr/employees/14", body)

    assert response.status_code == 422, response.text
    assert db.employee_writes() == []


def test_an_empty_edit_is_refused():
    db = _Db([STAFF])
    response = _send(db, "PUT", "/api/hr/employees/14", {})

    assert response.status_code == 400, response.text


def test_editing_a_missing_employee_is_404():
    db = _Db([STAFF])
    response = _send(db, "PUT", "/api/hr/employees/999", {"status": "Inactive"})

    assert response.status_code == 404, response.text


# --------------------------------------------------------------------------
# Linking a login
# --------------------------------------------------------------------------

def _accounts(*rows):
    return [{"id": i, "email": e, "roles": {"role_name": r}} for i, e, r in rows]


ACCOUNTS = _accounts(
    (LOGIN_ID, "staff@vff.org", "Operations Lead"),
    ("77777777-7777-7777-7777-777777777777", "new.hire@vff.org", "General Staff"),
    ("88888888-8888-8888-8888-888888888888", "sysadmin@vff.org", "System Administrator"),
)
NEW_HIRE = ACCOUNTS[1]["id"]
SYSADMIN = ACCOUNTS[2]["id"]


def test_the_employee_list_carries_the_linked_logins_email():
    db = _Db([{**STAFF, "users": {"email": "staff@vff.org"}}, {**KAMALA, "users": None}])
    response = _send(db, "GET", "/api/hr/employees")

    assert response.status_code == 200, response.text
    by_id = {e["id"]: e for e in response.json()}
    assert by_id[14]["login_email"] == "staff@vff.org"
    assert by_id[2]["login_email"] is None


def test_linkable_logins_leave_out_linked_accounts_and_system_administrator():
    db = _Db([STAFF])
    db.tables["users"] = ACCOUNTS
    response = _send(db, "GET", "/api/hr/linkable-logins")

    assert response.status_code == 200, response.text
    assert response.json() == [{"id": NEW_HIRE, "email": "new.hire@vff.org", "role": "General Staff"}]


def test_linkable_logins_need_hr_manage():
    db = _Db([STAFF])
    db.tables["users"] = ACCOUNTS
    response = _send(db, "GET", "/api/hr/linkable-logins", role="Director")

    assert response.status_code == 403, response.text


def test_a_free_login_can_be_linked():
    db = _Db([KAMALA])
    db.tables["users"] = ACCOUNTS
    response = _send(db, "PUT", "/api/hr/employees/2", {"user_id": NEW_HIRE})

    assert response.status_code == 200, response.text
    assert response.json()["user_id"] == NEW_HIRE


def test_a_login_already_linked_elsewhere_is_refused_with_409():
    db = _Db([KAMALA, STAFF])
    db.tables["users"] = ACCOUNTS
    response = _send(db, "PUT", "/api/hr/employees/2", {"user_id": LOGIN_ID})

    assert response.status_code == 409, response.text
    assert "Staff User" in response.json()["detail"]
    assert db.employee_writes() == []


def test_relinking_the_same_login_to_its_own_employee_is_fine():
    db = _Db([STAFF])
    db.tables["users"] = ACCOUNTS
    response = _send(db, "PUT", "/api/hr/employees/14", {"user_id": LOGIN_ID, "base_salary": 61000})

    assert response.status_code == 200, response.text


@pytest.mark.parametrize("user_id, status", [(SYSADMIN, 400), ("99999999-9999-9999-9999-999999999999", 404)])
def test_system_administrator_and_missing_logins_cannot_be_linked(user_id, status):
    db = _Db([KAMALA])
    db.tables["users"] = ACCOUNTS
    response = _send(db, "PUT", "/api/hr/employees/2", {"user_id": user_id})

    assert response.status_code == status, response.text
    assert db.employee_writes() == []


def test_create_checks_a_login_sent_with_it():
    db = _Db([STAFF])
    db.tables["users"] = ACCOUNTS
    response = _send(db, "POST", "/api/hr/employees", _new(user_id=LOGIN_ID))

    assert response.status_code == 409, response.text
    assert len(db.tables["employee_profile"]) == 1


# --------------------------------------------------------------------------
# A deactivated employee's self-service
# --------------------------------------------------------------------------

def _me(status):
    # Linked to the login acting_as signs in with.
    return {**STAFF, "user_id": USER_ID, "status": status}


@pytest.mark.parametrize("path", ["/api/hr/attendance/clock-in", "/api/hr/attendance/clock-out"])
def test_an_inactive_employee_cannot_clock_in_or_out(path):
    db = _Db([_me("Inactive")])
    response = _send(db, "POST", path, role="General Staff")

    assert response.status_code == 403, response.text
    assert "inactive" in response.json()["detail"]
    assert db.tables.get("attendance_log", []) == []


def test_an_active_employee_still_clocks_in():
    db = _Db([_me("Active")])
    response = _send(db, "POST", "/api/hr/attendance/clock-in", role="General Staff")

    assert response.status_code == 200, response.text
    assert len(db.tables["attendance_log"]) == 1


LEAVE = {"leave_type_id": 1, "start_date": "2026-12-01", "end_date": "2026-12-01"}


def test_an_inactive_employee_cannot_request_leave():
    db = _Db([_me("Inactive")])
    response = _send(db, "POST", "/api/leave/requests", LEAVE, role="General Staff")

    assert response.status_code == 403, response.text
    assert "inactive" in response.json()["detail"]
    assert db.tables.get("leave_requests", []) == []


def test_hr_cannot_file_leave_for_an_inactive_employee_either():
    db = _Db([_me("Inactive")])
    response = _send(db, "POST", "/api/leave/requests", {**LEAVE, "employee_id": 14}, role="HR Officer")

    assert response.status_code == 403, response.text
    assert "inactive" in response.json()["detail"]
    assert db.tables.get("leave_requests", []) == []
