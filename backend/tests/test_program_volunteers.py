"""GET /api/programs/{id}/volunteers: who accepted work on a program.

A shift belongs to a program when its title is the program's name (trimmed,
case-insensitive); volunteer_shifts has no program_id yet. Only ACCEPTED
assignments on non-cancelled shifts of THIS program, or accepted direct
program assignments, may appear.

The endpoint tests use the RBAC matrix's Supabase double, which ignores query
filters and returns every fixture row. That is deliberate here: it proves the
rules are enforced by app/services/program_volunteers.py, not only by
whatever .eq() filters the query happened to send.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.program_volunteers import (
    build_program_volunteers, shift_belongs_to_program,
)
from tests.test_rbac_matrix import _request, acting_as

PROGRAM = {"id": 7, "program_name": "Saturday Sterilization Clinic"}
OTHER_PROGRAM_NAME = "Rabies Vaccination Drive"


def _shift(id, title=PROGRAM["program_name"], cancelled=False, date="2026-11-07"):
    return {
        "id": id, "title": title, "location": "Kandy",
        "shift_date": date, "start_time": "09:00:00", "end_time": "13:00:00",
        "is_cancelled": cancelled,
    }


def _assignment(id, volunteer, response="accepted", shift_id=None, program_id=None):
    return {
        "id": id, "volunteer_id": volunteer, "shift_id": shift_id,
        "rescue_case_id": None, "program_id": program_id,
        "response": response, "responded_at": "2026-11-01T10:00:00+00:00",
        "volunteers": {
            "full_name": f"Volunteer {volunteer}",
            "skills": ["animal_handling"], "skills_other": None,
        },
    }


SHIFTS = [
    _shift("s-open"),
    _shift("s-cancelled", cancelled=True),
    _shift("s-other", title=OTHER_PROGRAM_NAME),
]

ASSIGNMENTS = [
    _assignment("a1", "accepted-vol", shift_id="s-open"),
    _assignment("a2", "pending-vol", response="pending", shift_id="s-open"),
    _assignment("a3", "declined-vol", response="declined", shift_id="s-open"),
    _assignment("a4", "cancelled-vol", shift_id="s-cancelled"),
    _assignment("a5", "other-vol", shift_id="s-other"),
]


def _names(result):
    return {v["full_name"] for v in result}


# --------------------------------------------------------------------------
# The rules (pure helper)
# --------------------------------------------------------------------------

def test_accepted_volunteer_on_program_shift_is_shown():
    result = build_program_volunteers(PROGRAM, SHIFTS, ASSIGNMENTS)
    assert _names(result) == {"Volunteer accepted-vol"}
    assert [s["shift_id"] for s in result[0]["shifts"]] == ["s-open"]


def test_pending_and_declined_are_hidden():
    names = _names(build_program_volunteers(PROGRAM, SHIFTS, ASSIGNMENTS))
    assert "Volunteer pending-vol" not in names
    assert "Volunteer declined-vol" not in names


def test_cancelled_shift_is_hidden():
    names = _names(build_program_volunteers(PROGRAM, SHIFTS, ASSIGNMENTS))
    assert "Volunteer cancelled-vol" not in names


def test_other_programs_shift_is_hidden():
    names = _names(build_program_volunteers(PROGRAM, SHIFTS, ASSIGNMENTS))
    assert "Volunteer other-vol" not in names


def test_direct_program_assignment_counts_only_when_accepted():
    rows = [
        _assignment("d1", "direct-yes", program_id=PROGRAM["id"]),
        _assignment("d2", "direct-pending", response="pending", program_id=PROGRAM["id"]),
        _assignment("d3", "direct-elsewhere", program_id=99),
    ]
    result = build_program_volunteers(PROGRAM, [], rows)
    assert _names(result) == {"Volunteer direct-yes"}
    assert result[0]["program_assignment"] is True
    assert result[0]["shifts"] == []


def test_one_entry_per_volunteer_with_all_their_shifts():
    shifts = [_shift("s1", date="2026-11-14"), _shift("s2", date="2026-11-07")]
    rows = [
        _assignment("a1", "v", shift_id="s1"),
        _assignment("a2", "v", shift_id="s2"),
        _assignment("a2", "v", shift_id="s2"),  # same row returned twice
    ]
    result = build_program_volunteers(PROGRAM, shifts, rows)
    assert len(result) == 1
    assert [s["shift_id"] for s in result[0]["shifts"]] == ["s2", "s1"]


def test_name_match_ignores_case_and_whitespace_but_is_exact():
    assert shift_belongs_to_program({"title": "  saturday   STERILIZATION clinic "}, PROGRAM)
    assert not shift_belongs_to_program({"title": "Saturday Sterilization Clinic 2"}, PROGRAM)
    assert not shift_belongs_to_program({"title": ""}, {"program_name": ""})


# --------------------------------------------------------------------------
# The endpoint
# --------------------------------------------------------------------------

def _tables():
    return {
        "programs": {"select": [PROGRAM]},
        "volunteer_shifts": {"select": SHIFTS},
        "volunteer_assignments": {"select": ASSIGNMENTS},
    }


def test_endpoint_returns_only_the_accepted_volunteer():
    with acting_as("Admin", tables=_tables()):
        response = _request("GET", "/api/programs/7/volunteers")
    assert response.status_code == 200, response.text
    body = response.json()
    assert [v["full_name"] for v in body] == ["Volunteer accepted-vol"]
    assert body[0]["shifts"][0]["shift_date"] == "2026-11-07"


def test_endpoint_never_exposes_contact_details_or_token():
    tables = _tables()
    for a in tables["volunteer_assignments"]["select"]:
        a["volunteers"] = {**a["volunteers"], "email": "x@y.z", "access_token": "secret"}
    # Finance Officer holds programs:read but not volunteers:read.
    with acting_as("Finance Officer", tables=tables):
        response = _request("GET", "/api/programs/7/volunteers")
    assert response.status_code == 200, response.text
    assert "x@y.z" not in response.text and "secret" not in response.text


def test_endpoint_404s_for_unknown_program():
    tables = _tables()
    tables["programs"] = {"select": []}
    with acting_as("Admin", tables=tables):
        response = _request("GET", "/api/programs/404/volunteers")
    assert response.status_code == 404


def test_endpoint_requires_programs_read():
    # HR Officer has no programs:read.
    with acting_as("HR Officer", tables=_tables()):
        response = _request("GET", "/api/programs/7/volunteers")
    assert response.status_code == 403
