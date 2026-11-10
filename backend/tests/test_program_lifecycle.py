"""Program lifecycle: Upcoming -> Active -> Completed, forward only.

Covers the rules in app/services/program_lifecycle.py, the start / complete
endpoints, the create default, the status-filtered list, and the team lock on
completed programs. Supabase is the RBAC matrix's double, which ignores
filters, so every rule asserted here is enforced in Python.
"""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.program_lifecycle import (
    ACTIVE, COMPLETED, UPCOMING, next_status, normalize_status, transition_error,
)
from tests.test_rbac_matrix import _request, acting_as

TODAY = date.today().isoformat()
AUDIT = {"select": [], "insert": [{"id": 1}]}


def _program(status, **extra):
    return {
        "id": 7, "program_name": "Saturday Clinic", "status": status,
        "total_animals_treated": 10, "total_cost": 5000,
        "start_date": None, "end_date": None, **extra,
    }


def _tables(row, updated=None):
    return {
        "programs": {"select": [row], "update": [updated] if updated else []},
        "system_audit_logs": AUDIT,
    }


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------

@pytest.mark.parametrize("current,target", [(UPCOMING, ACTIVE), (ACTIVE, COMPLETED)])
def test_forward_one_step_is_allowed(current, target):
    assert transition_error(current, target) is None


@pytest.mark.parametrize("current,target", [
    (UPCOMING, COMPLETED),   # skipped a step
    (ACTIVE, UPCOMING),      # backwards
    (COMPLETED, ACTIVE),     # backwards
    (COMPLETED, COMPLETED),  # already there
    (ACTIVE, ACTIVE),
])
def test_backward_skipped_or_repeated_moves_are_refused(current, target):
    assert transition_error(current, target)


def test_legacy_in_progress_reads_as_active():
    assert normalize_status("In Progress") == ACTIVE
    assert next_status("In Progress") == COMPLETED
    assert normalize_status(" upcoming ") == UPCOMING
    assert next_status(COMPLETED) is None


# --------------------------------------------------------------------------
# Start / complete
# --------------------------------------------------------------------------

def test_start_moves_upcoming_to_active_and_sets_start_date():
    captured = {}
    updated = _program(ACTIVE, start_date=TODAY)
    with acting_as("Operations Lead", tables=_tables(_program(UPCOMING), updated),
                   capture_update=captured):
        response = _request("POST", "/api/programs/7/start")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == ACTIVE
    assert captured["update_data"] == {"status": ACTIVE, "start_date": TODAY}


def test_start_keeps_a_start_date_already_in_the_past():
    captured = {}
    row = _program(UPCOMING, start_date="2020-01-01")
    with acting_as("Admin", tables=_tables(row, {**row, "status": ACTIVE}),
                   capture_update=captured):
        response = _request("POST", "/api/programs/7/start")
    assert response.status_code == 200, response.text
    assert captured["update_data"] == {"status": ACTIVE}


COUNT = {"total_animals_treated": 42}


def test_complete_records_animals_treated_with_the_status_change():
    captured = {}
    row = _program(ACTIVE, start_date="2026-01-01")
    updated = {**row, "status": COMPLETED, "end_date": TODAY, "total_animals_treated": 42}
    with acting_as("Admin", tables=_tables(row, updated), capture_update=captured):
        response = _request("POST", "/api/programs/7/complete", json=COUNT)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == COMPLETED
    assert response.json()["total_animals_treated"] == 42
    # One update: status, end date and the count land together.
    assert captured["update_data"] == {
        "status": COMPLETED, "end_date": TODAY, "total_animals_treated": 42,
    }


def test_zero_animals_is_a_valid_final_count():
    captured = {}
    row = _program(ACTIVE, start_date="2026-01-01")
    with acting_as("Admin", tables=_tables(row, {**row, "status": COMPLETED}),
                   capture_update=captured):
        response = _request("POST", "/api/programs/7/complete",
                            json={"total_animals_treated": 0})
    assert response.status_code == 200, response.text
    assert captured["update_data"]["total_animals_treated"] == 0


@pytest.mark.parametrize("body", [
    None,                              # missing body
    {},                                # missing count
    {"total_animals_treated": -1},     # negative
    {"total_animals_treated": 12.5},   # not whole
    {"total_animals_treated": "12"},   # not a number
])
def test_complete_needs_a_whole_non_negative_count(body):
    captured = {}
    row = _program(ACTIVE)
    with acting_as("Admin", tables=_tables(row, {**row, "status": COMPLETED}),
                   capture_update=captured):
        response = _request("POST", "/api/programs/7/complete", json=body)
    assert response.status_code == 422, response.text
    assert "update_data" not in captured


def test_legacy_in_progress_program_can_be_completed():
    row = _program("In Progress", start_date="2026-01-01")
    with acting_as("Admin", tables=_tables(row, {**row, "status": COMPLETED})):
        response = _request("POST", "/api/programs/7/complete", json=COUNT)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("status,action", [
    (UPCOMING, "complete"),   # skipping Active
    (ACTIVE, "start"),        # already started
    (COMPLETED, "start"),     # backwards
    (COMPLETED, "complete"),  # already done
])
def test_invalid_transitions_are_409_and_write_nothing(status, action):
    captured = {}
    with acting_as("Admin", tables=_tables(_program(status)), capture_update=captured):
        response = _request("POST", f"/api/programs/7/{action}",
                            json=COUNT if action == "complete" else None)
    assert response.status_code == 409, response.text
    assert "update_data" not in captured


def test_unknown_program_is_404():
    with acting_as("Admin", tables={"programs": {"select": []}}):
        response = _request("POST", "/api/programs/404/start")
    assert response.status_code == 404


@pytest.mark.parametrize("role", ["Director", "Finance Officer", "General Staff"])
def test_transitions_need_programs_manage(role):
    with acting_as(role, tables=_tables(_program(UPCOMING))):
        response = _request("POST", "/api/programs/7/start")
    assert response.status_code == 403


# --------------------------------------------------------------------------
# Create default
# --------------------------------------------------------------------------

def test_new_program_is_always_upcoming_whatever_the_client_sends():
    from tests.test_restricted_funds import _CapturingSupabase
    from app.core.supabase import get_supabase
    from app.main import app

    supabase = _CapturingSupabase({
        "programs": {"insert": [{"id": 9, "program_name": "New", "status": UPCOMING,
                                 "total_animals_treated": 0}]},
        "system_audit_logs": AUDIT,
    })
    with acting_as("Admin"):
        app.dependency_overrides[get_supabase] = lambda: supabase
        response = _request("POST", "/api/finance/programs", json={
            "program_name": "New", "status": "Completed", "start_date": "2026-12-01",
            "location": "  Kandy  ",
        })
    assert response.status_code == 200, response.text
    inserted = [d for t, d in supabase.inserts if t == "programs"]
    assert inserted and inserted[0]["status"] == UPCOMING
    assert inserted[0]["start_date"] == "2026-12-01"
    assert inserted[0]["location"] == "Kandy"


# --------------------------------------------------------------------------
# Location
# --------------------------------------------------------------------------

@pytest.mark.parametrize("body", [
    {"program_name": "New"},                       # missing
    {"program_name": "New", "location": "   "},    # blank
    {"program_name": "New", "location": "x" * 201},  # too long
])
def test_new_program_needs_a_location(body):
    with acting_as("Admin", tables={"programs": {"insert": [{"id": 9}]}}):
        response = _request("POST", "/api/finance/programs", json=body)
    assert response.status_code == 422, response.text


class _MissingLocationColumn:
    """A Supabase double whose programs table predates migration 011."""

    def __init__(self, select_rows):
        self._rows = select_rows

    def table(self, name):
        rows = self._rows

        class Q:
            _write = False  # a class attribute, so __getattr__ never answers for it

            def __getattr__(self, attr):
                return lambda *a, **k: self

            def insert(self, *a, **k):
                self._write = True
                return self

            def update(self, *a, **k):
                self._write = True
                return self

            def execute(self):
                if self._write:
                    raise Exception(
                        "{'code': 'PGRST204', 'message': \"Could not find the 'location' "
                        "column of 'programs' in the schema cache\"}"
                    )
                return type("R", (), {"data": rows})()

        return Q()


@pytest.mark.parametrize("method,path,body", [
    ("POST", "/api/finance/programs", {"program_name": "New", "location": "Kandy"}),
    ("PATCH", "/api/programs/7", {"location": "Kandy"}),
])
def test_location_writes_explain_the_missing_migration(method, path, body):
    from app.core.supabase import get_supabase
    from app.main import app

    with acting_as("Admin"):
        app.dependency_overrides[get_supabase] = lambda: _MissingLocationColumn([_program(ACTIVE)])
        response = _request(method, path, json=body)
    assert response.status_code == 503, response.text
    assert "011_program_location.sql" in response.json()["detail"]


def test_patch_sets_the_location_and_is_audited():
    captured = {}
    row = _program(COMPLETED)
    tables = _tables(row, {**row, "location": "Galle"})
    with acting_as("Operations Lead", tables=tables, capture_update=captured):
        response = _request("PATCH", "/api/programs/7", json={"location": " Galle "})
    assert response.status_code == 200, response.text
    assert captured["update_data"] == {"location": "Galle"}
    assert response.json()["location"] == "Galle"


def test_patch_rejects_a_blank_location():
    with acting_as("Admin", tables=_tables(_program(ACTIVE))):
        response = _request("PATCH", "/api/programs/7", json={"location": "  "})
    assert response.status_code == 422


@pytest.mark.parametrize("role", ["Director", "Finance Officer", "General Staff"])
def test_patch_needs_programs_manage(role):
    with acting_as(role, tables=_tables(_program(ACTIVE))):
        response = _request("PATCH", "/api/programs/7", json={"location": "Kandy"})
    assert response.status_code == 403


# --------------------------------------------------------------------------
# List by stage
# --------------------------------------------------------------------------

def test_list_returns_only_the_requested_stage_with_card_figures():
    tables = {
        "programs": {"select": [
            {**_program(UPCOMING), "id": 1},
            {**_program("In Progress"), "id": 2},
            {**_program(COMPLETED), "id": 3},
        ]},
        "program_assignments": {"select": [{"program_id": 2}, {"program_id": 2}]},
        "financial_transactions": {"select": [
            {"program_id": 2, "amount": 8000, "transaction_type": "Income", "status": "Cash"},
            {"program_id": 2, "amount": 999, "transaction_type": "Income", "status": "Voided"},
        ]},
        "volunteer_shifts": {"select": []},
        "volunteer_assignments": {"select": []},
    }
    with acting_as("Finance Officer", tables=tables):
        response = _request("GET", "/api/programs?status=Active")
    assert response.status_code == 200, response.text
    body = response.json()
    assert [p["id"] for p in body] == [2]
    card = body[0]
    assert card["status"] == ACTIVE
    assert card["team_count"] == 2
    assert card["revenue"] == 8000
    assert card["profit"] == 3000
    assert card["cost_per_animal"] == 500


def test_list_rejects_an_unknown_stage():
    with acting_as("Admin", tables={"programs": {"select": []}}):
        response = _request("GET", "/api/programs?status=In%20Progress")
    assert response.status_code == 422


# --------------------------------------------------------------------------
# Completed programs keep their team as a record
# --------------------------------------------------------------------------

def test_team_cannot_change_on_a_completed_program():
    tables = {
        "programs": {"select": [_program(COMPLETED)]},
        "employee_profile": {"select": [{"id": 3}]},
        "program_assignments": {"select": [{"id": 1, "program_id": 7}]},
    }
    with acting_as("Admin", tables=tables):
        add = _request("POST", "/api/programs/7/team", json={"employee_id": 3})
        remove = _request("DELETE", "/api/programs/7/team/1")
    assert add.status_code == 409, add.text
    assert remove.status_code == 409, remove.text


# --------------------------------------------------------------------------
# Correcting a completed program's animal count
# --------------------------------------------------------------------------

def test_patch_corrects_animals_treated_on_a_completed_program():
    captured = {}
    row = _program(COMPLETED, total_animals_treated=0)
    with acting_as("Admin", tables=_tables(row, {**row, "total_animals_treated": 35}),
                   capture_update=captured):
        response = _request("PATCH", "/api/programs/7", json={"total_animals_treated": 35})
    assert response.status_code == 200, response.text
    assert captured["update_data"] == {"total_animals_treated": 35}


@pytest.mark.parametrize("status", [UPCOMING, ACTIVE])
def test_patch_refuses_animals_treated_before_completion(status):
    captured = {}
    with acting_as("Admin", tables=_tables(_program(status)), capture_update=captured):
        response = _request("PATCH", "/api/programs/7", json={"total_animals_treated": 5})
    assert response.status_code == 409, response.text
    assert "update_data" not in captured


@pytest.mark.parametrize("body", [{}, {"total_animals_treated": -1}, {"total_animals_treated": 2.5}])
def test_patch_rejects_an_empty_or_invalid_update(body):
    with acting_as("Admin", tables=_tables(_program(COMPLETED))):
        response = _request("PATCH", "/api/programs/7", json=body)
    assert response.status_code == 422, response.text


# --------------------------------------------------------------------------
# Audit fixes (P1, P3 to P7, X3)
# --------------------------------------------------------------------------

from app.services.program_lifecycle import CANCELLED  # noqa: E402


def test_cancelled_reads_as_cancelled_and_only_upcoming_can_be_cancelled():
    assert normalize_status("cancelled") == CANCELLED
    assert transition_error(UPCOMING, CANCELLED) is None
    for status in (ACTIVE, COMPLETED, CANCELLED):
        assert transition_error(status, CANCELLED)
    assert transition_error(CANCELLED, ACTIVE)


def test_cancel_moves_an_upcoming_program_to_cancelled():
    captured = {}
    row = _program(UPCOMING)
    with acting_as("Operations Lead", tables=_tables(row, {**row, "status": CANCELLED}),
                   capture_update=captured):
        response = _request("POST", "/api/programs/7/cancel")
    assert response.status_code == 200, response.text
    assert captured["update_data"] == {"status": CANCELLED}
    assert response.json()["status"] == CANCELLED


@pytest.mark.parametrize("status", [ACTIVE, COMPLETED])
def test_only_an_upcoming_program_can_be_cancelled(status):
    captured = {}
    with acting_as("Admin", tables=_tables(_program(status)), capture_update=captured):
        response = _request("POST", "/api/programs/7/cancel")
    assert response.status_code == 409
    assert "update_data" not in captured


def test_a_cancelled_programs_team_cannot_change():
    tables = {"programs": {"select": [_program(CANCELLED)]}, "employee_profile": {"select": [{"id": 3}]}}
    with acting_as("Admin", tables=tables):
        response = _request("POST", "/api/programs/7/team", json={"employee_id": 3})
    assert response.status_code == 409


def test_complete_records_an_earlier_end_date():
    captured = {}
    row = _program(ACTIVE, start_date="2026-01-01")
    with acting_as("Admin", tables=_tables(row, {**row, "status": COMPLETED}), capture_update=captured):
        response = _request("POST", "/api/programs/7/complete",
                            json={**COUNT, "end_date": "2026-02-01"})
    assert response.status_code == 200, response.text
    assert captured["update_data"]["end_date"] == "2026-02-01"


@pytest.mark.parametrize("end_date, message", [
    ("2999-01-01", "future"),
    ("2025-12-31", "before the start date"),
])
def test_complete_refuses_an_impossible_end_date(end_date, message):
    captured = {}
    row = _program(ACTIVE, start_date="2026-01-01")
    with acting_as("Admin", tables=_tables(row), capture_update=captured):
        response = _request("POST", "/api/programs/7/complete", json={**COUNT, "end_date": end_date})
    assert response.status_code == 400
    assert message in response.json()["detail"]
    assert "update_data" not in captured


def _open_tables(row, updated=None):
    return {
        **_tables(row, updated),
        "inventory_transactions": {"select": [
            {"item_id": 1, "quantity": 10, "transaction_type": "Issue",
             "inventory_items": {"item_name": "Gauze"}},
            {"item_id": 1, "quantity": 4, "transaction_type": "Return",
             "inventory_items": {"item_name": "Gauze"}},
            {"item_id": 2, "quantity": 3, "transaction_type": "Issue",
             "inventory_items": {"item_name": "Syringes"}},
            {"item_id": 2, "quantity": 3, "transaction_type": "Return",
             "inventory_items": {"item_name": "Syringes"}},
        ]},
        "volunteer_shifts": {"select": [
            {"id": "s-1", "title": "Saturday Clinic", "program_id": 7, "shift_date": "2999-01-01",
             "is_cancelled": False},
            {"id": "s-2", "title": "Saturday Clinic", "program_id": 7, "shift_date": "2020-01-01",
             "is_cancelled": False},
            {"id": "s-3", "title": "Saturday Clinic", "program_id": 8, "shift_date": "2999-01-01",
             "is_cancelled": False},
        ]},
    }


def test_open_items_lists_held_stock_and_later_shifts():
    with acting_as("Operations Lead", tables=_open_tables(_program(ACTIVE))):
        response = _request("GET", "/api/programs/7/open-items")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stock_held"] == [{"item_id": 1, "item_name": "Gauze", "outstanding": 6}]
    assert [s["shift_id"] for s in body["shifts_after"]] == ["s-1"]


def test_complete_is_refused_while_stock_or_shifts_are_still_out():
    captured = {}
    row = _program(ACTIVE, start_date="2026-01-01")
    with acting_as("Admin", tables=_open_tables(row), capture_update=captured):
        response = _request("POST", "/api/programs/7/complete", json=COUNT)
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "6 x Gauze" in detail and "1 volunteer shift" in detail
    assert "update_data" not in captured


def test_complete_goes_ahead_when_confirmed():
    row = _program(ACTIVE, start_date="2026-01-01")
    with acting_as("Admin", tables=_open_tables(row, {**row, "status": COMPLETED})):
        response = _request("POST", "/api/programs/7/complete",
                            json={**COUNT, "confirm_open_items": True})
    assert response.status_code == 200, response.text


def test_name_and_start_date_can_be_corrected_while_upcoming():
    captured = {}
    row = _program(UPCOMING)
    with acting_as("Operations Lead", tables=_tables(row, {**row, "program_name": "Kandy Clinic"}),
                   capture_update=captured):
        response = _request("PATCH", "/api/programs/7",
                            json={"program_name": "  Kandy   Clinic ", "start_date": "2026-12-01"})
    assert response.status_code == 200, response.text
    assert captured["update_data"] == {"program_name": "Kandy Clinic", "start_date": "2026-12-01"}


@pytest.mark.parametrize("status", [ACTIVE, COMPLETED])
@pytest.mark.parametrize("body", [{"program_name": "New"}, {"start_date": "2026-12-01"}])
def test_name_and_start_date_are_fixed_once_started(status, body):
    captured = {}
    with acting_as("Admin", tables=_tables(_program(status)), capture_update=captured):
        response = _request("PATCH", "/api/programs/7", json=body)
    assert response.status_code == 409
    assert "update_data" not in captured


@pytest.mark.parametrize("name", ["", "   "])
def test_a_program_needs_a_name(name):
    with acting_as("Admin", tables={"programs": {"insert": [{"id": 9}]}}):
        response = _request("POST", "/api/finance/programs",
                            json={"program_name": name, "location": "Kandy"})
    assert response.status_code == 422


def _list_tables():
    return {
        "programs": {"select": [{**_program(ACTIVE), "id": 2}]},
        "program_assignments": {"select": []},
        "financial_transactions": {"select": [
            {"program_id": 2, "amount": 8000, "transaction_type": "Income", "status": "Cash"},
        ]},
        "volunteer_shifts": {"select": []},
        "volunteer_assignments": {"select": []},
    }


@pytest.mark.parametrize("role, money, costs", [
    ("Finance Officer", True, True),
    ("Operations Lead", False, True),
    ("General Staff", False, False),
])
def test_program_money_is_shown_only_to_roles_that_may_see_it(role, money, costs):
    with acting_as(role, tables=_list_tables()):
        response = _request("GET", "/api/programs?status=Active")
    assert response.status_code == 200, response.text
    card = response.json()[0]
    assert (card["revenue"] is not None) == money
    assert (card["profit"] is not None) == money
    assert (card["total_cost"] is not None) == costs
    assert (card["cost_per_animal"] is not None) == costs


@pytest.mark.parametrize("role, allowed", [
    ("Finance Officer", True), ("Operations Lead", False), ("General Staff", False),
])
def test_program_financials_need_finance_read(role, allowed):
    tables = {"programs": {"select": [{"id": 7, "total_cost": 100}]},
              "financial_transactions": {"select": []}}
    with acting_as(role, tables=tables):
        response = _request("GET", "/api/programs/7/financials")
    assert (response.status_code == 200) == allowed, response.text


def test_program_detail_hides_cost_from_general_staff():
    with acting_as("General Staff", tables={"programs": {"select": [_program(ACTIVE)]}}):
        response = _request("GET", "/api/programs/7")
    assert response.status_code == 200, response.text
    assert response.json()["total_cost"] is None


@pytest.mark.parametrize("role, allowed", [
    ("Operations Lead", True), ("Admin", True), ("Director", False), ("General Staff", False),
])
def test_team_picker_lists_active_employees_to_program_managers(role, allowed):
    tables = {"employee_profile": {"select": [
        {"id": 2, "first_name": "Zara", "last_name": "Silva", "status": "Active", "basic_salary": 90000},
        {"id": 1, "first_name": "Amal", "last_name": "Perera", "status": "Active"},
        {"id": 3, "first_name": "Old", "last_name": "Hand", "status": "Resigned"},
    ]}}
    with acting_as(role, tables=tables):
        response = _request("GET", "/api/programs/assignable-employees")
    if not allowed:
        assert response.status_code == 403
        return
    assert response.status_code == 200, response.text
    assert response.json() == [
        {"id": 1, "first_name": "Amal", "last_name": "Perera"},
        {"id": 2, "first_name": "Zara", "last_name": "Silva"},
    ]
