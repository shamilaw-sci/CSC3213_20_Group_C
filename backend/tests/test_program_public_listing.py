"""Public program listings: the /clinics page and the publish control.

GET /api/programs/public is open to anyone, so the tests that matter most are
the ones proving it never shows an unpublished, finished or cancelled program
and never leaks costs or counts. The Supabase double ignores filters, so every
rule asserted here is the Python one, not the query's.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.supabase import get_public_supabase
from app.main import app
from app.services.program_lifecycle import is_missing_public_listing_column
from tests.test_rbac_matrix import _FakeSupabase, _request, acting_as, client

AUDIT = {"select": [], "insert": [{"id": 1}]}

LISTING = {
    "is_public": True,
    "program_type": "Sterilization",
    "public_venue": "Peradeniya Community Hall",
    "public_schedule": "Sat 22 - Mon 24 Nov, 8am - 1pm",
    "public_notes": "Free. No food after 10pm the night before.",
}


def _program(status="Upcoming", **extra):
    return {
        "id": 7, "program_name": "Kandy Sterilization Drive", "status": status,
        "total_animals_treated": 0, "total_cost": 5000,
        "start_date": "2026-11-22", "end_date": None, "location": "Kandy",
        "is_public": False, "program_type": None, "public_venue": None,
        "public_schedule": None, "public_notes": None, **extra,
    }


def _public_get(rows):
    app.dependency_overrides[get_public_supabase] = lambda: _FakeSupabase({"programs": rows})
    try:
        return client.get("/api/programs/public")
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# GET /public
# --------------------------------------------------------------------------

def test_public_list_needs_no_sign_in_and_shows_published_programs():
    response = _public_get([_program(**LISTING)])
    assert response.status_code == 200, response.text
    [card] = response.json()
    assert card["program_name"] == "Kandy Sterilization Drive"
    assert card["program_type"] == "Sterilization"
    assert card["public_venue"] == "Peradeniya Community Hall"


def test_public_list_never_carries_costs_counts_or_the_flag():
    [card] = _public_get([_program(**LISTING)]).json()
    for private in ("total_cost", "total_animals_treated", "end_date", "is_public"):
        assert private not in card


@pytest.mark.parametrize("row", [
    _program(**{**LISTING, "is_public": False}),
    _program("Completed", **LISTING),
    _program("Cancelled", **LISTING),
])
def test_public_list_leaves_out_unpublished_and_finished_programs(row):
    assert _public_get([row]).json() == []


def test_public_list_puts_running_programs_first_then_soonest():
    rows = [
        _program(id=1, start_date="2026-12-10", **{k: v for k, v in LISTING.items()}),
        _program("Active", id=2, start_date="2026-11-01", **LISTING),
        _program(id=3, start_date="2026-11-20", **LISTING),
        # Legacy stored value that means Active.
        _program("In Progress", id=4, start_date="2026-11-05", **LISTING),
    ]
    listed = _public_get(rows).json()
    assert [p["id"] for p in listed] == [2, 4, 3, 1]
    assert listed[1]["status"] == "Active"


def test_public_list_is_empty_before_the_migration():
    class _NoColumns(_FakeSupabase):
        def table(self, name):
            raise Exception("{'code': '42703', 'message': 'column programs.is_public does not exist'}")

    app.dependency_overrides[get_public_supabase] = lambda: _NoColumns()
    try:
        response = client.get("/api/programs/public")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == []


def test_missing_column_detection_does_not_swallow_other_errors():
    assert is_missing_public_listing_column(Exception("PGRST204 Could not find the 'public_venue' column"))
    assert not is_missing_public_listing_column(Exception("connection reset"))


# --------------------------------------------------------------------------
# PUT /{id}/public-listing
# --------------------------------------------------------------------------

def _tables(row, updated=None):
    return {
        "programs": {"select": [row], "update": [updated or row]},
        "system_audit_logs": AUDIT,
    }


def test_operations_lead_can_publish_and_the_listing_is_written_whole():
    captured = {}
    updated = _program(**LISTING)
    with acting_as("Operations Lead", tables=_tables(_program(), updated), capture_update=captured):
        response = _request("PUT", "/api/programs/7/public-listing", json=LISTING)
    assert response.status_code == 200, response.text
    assert response.json()["is_public"] is True
    assert captured["update_data"] == LISTING


def test_publishing_trims_text_and_clears_blank_fields():
    captured = {}
    payload = {**LISTING, "public_venue": "  Peradeniya   Hall ", "public_schedule": "   ",
               "public_notes": "  Free.  \n  Bring   a leash. "}
    with acting_as("Operations Lead", tables=_tables(_program()), capture_update=captured):
        response = _request("PUT", "/api/programs/7/public-listing", json=payload)
    assert response.status_code == 200, response.text
    assert captured["update_data"]["public_venue"] == "Peradeniya Hall"
    assert captured["update_data"]["public_schedule"] is None
    assert captured["update_data"]["public_notes"] == "Free.\nBring a leash."


@pytest.mark.parametrize("row,payload,expected", [
    (_program(), {**LISTING, "program_type": None}, "a type"),
    (_program(location=None), LISTING, "a location"),
    (_program(start_date=None), LISTING, "a start date"),
])
def test_publishing_needs_type_location_and_start_date(row, payload, expected):
    captured = {}
    with acting_as("Operations Lead", tables=_tables(row), capture_update=captured):
        response = _request("PUT", "/api/programs/7/public-listing", json=payload)
    assert response.status_code == 422
    assert expected in response.json()["detail"]
    assert "update_data" not in captured


def test_an_active_program_can_be_published_without_a_start_date():
    with acting_as("Operations Lead", tables=_tables(_program("Active", start_date=None))):
        response = _request("PUT", "/api/programs/7/public-listing", json=LISTING)
    assert response.status_code == 200, response.text


def test_the_live_missing_column_error_is_recognised():
    # The exact message the live database returns for a select before 035.
    assert is_missing_public_listing_column(Exception(
        "{'code': '42703', 'details': None, 'hint': None, "
        "'message': 'column programs.is_public does not exist'}"
    ))


def test_unknown_program_type_is_refused():
    with acting_as("Operations Lead", tables=_tables(_program())):
        response = _request("PUT", "/api/programs/7/public-listing",
                            json={**LISTING, "program_type": "Grooming"})
    assert response.status_code == 422


@pytest.mark.parametrize("status", ["Completed", "Cancelled"])
def test_finished_programs_cannot_be_published_but_can_be_taken_down(status):
    with acting_as("Operations Lead", tables=_tables(_program(status))):
        refused = _request("PUT", "/api/programs/7/public-listing", json=LISTING)
    assert refused.status_code == 409

    captured = {}
    with acting_as("Operations Lead", tables=_tables(_program(status, **LISTING)), capture_update=captured):
        down = _request("PUT", "/api/programs/7/public-listing", json={**LISTING, "is_public": False})
    assert down.status_code == 200, down.text
    assert captured["update_data"]["is_public"] is False


def test_unpublishing_needs_nothing_else_set():
    with acting_as("Operations Lead", tables=_tables(_program(location=None, start_date=None))):
        response = _request("PUT", "/api/programs/7/public-listing", json={"is_public": False})
    assert response.status_code == 200, response.text


def test_unknown_program_is_404():
    with acting_as("Operations Lead", tables={"programs": {"select": []}}):
        response = _request("PUT", "/api/programs/99/public-listing", json=LISTING)
    assert response.status_code == 404


@pytest.mark.parametrize("role", ["Finance Officer", "General Staff", "Director"])
def test_roles_without_programs_manage_cannot_publish(role):
    with acting_as(role, tables=_tables(_program())):
        response = _request("PUT", "/api/programs/7/public-listing", json=LISTING)
    assert response.status_code == 403


def test_publishing_before_the_migration_explains_what_to_run():
    class _NoColumns(_FakeSupabase):
        def table(self, name):
            query = super().table(name)
            if name == "programs":
                def _update(*a, **k):
                    raise Exception("PGRST204 Could not find the 'is_public' column of 'programs'")
                query.update = _update
            return query

    from app.core.security import get_current_user
    from app.core.supabase import get_supabase

    async def _user():
        return {"id": "u", "sub": "u", "email": "x@vff.test", "roles": {"role_name": "Operations Lead"}}

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_supabase] = lambda: _NoColumns({"programs": {"select": [_program()]}})
    try:
        response = client.put("/api/programs/7/public-listing", json=LISTING)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert "035_program_public_listing.sql" in response.json()["detail"]
