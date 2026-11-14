"""Rescue case timeline and outcome (app/api/rescue_cases.py, migration 030).

Confirmed 2026-11-13:

  * resolving needs one of five fixed outcomes; any other move refuses one,
    and reopening clears it (the timeline keeps the old one);
  * every status change, assignment and outcome adds a line to the timeline;
  * notes need rescue:manage, the timeline rescue:read;
  * notes are append-only: there is no edit or delete route.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.permissions import has_permission
from app.main import app
from tests.test_employees import _Db, _Query, _send
from tests.test_rbac_matrix import ALL_ROLES, CASE_ID, OTHER_USER_ID, USER_ID, _case_row

STATUS = f"/api/rescue_cases/cases/{CASE_ID}/status"
TIMELINE = f"/api/rescue_cases/cases/{CASE_ID}/timeline"
NOTES = f"/api/rescue_cases/cases/{CASE_ID}/notes"


NOW = "2026-11-13T09:00:00+00:00"


class _EventsQuery(_Query):
    """Fills created_at on new timeline lines, as the column default does, and
    refuses a bulk insert whose rows have different keys, as PostgREST does
    (PGRST102). That second rule is what broke the first live run."""

    def insert(self, data, *a, **k):
        rows = data if isinstance(data, list) else [data]
        if len({frozenset(r) for r in rows}) > 1:
            self._db.fail_inserts.setdefault(self._name, RuntimeError("PGRST102: All object keys must match"))
        return super().insert([{**r, "created_at": NOW} for r in rows])


class _TimelineDb(_Db):
    def table(self, name):
        return _EventsQuery(self, name) if name == "rescue_case_events" else super().table(name)


def _db(status="In Treatment", assigned_to=USER_ID, events=(), **case):
    db = _TimelineDb([
        {"user_id": USER_ID, "first_name": "Amal", "last_name": "Silva"},
        {"user_id": OTHER_USER_ID, "first_name": "Nimal", "last_name": "Perera"},
    ])
    db.tables["rescue_cases"] = [{**_case_row(status=status, assigned_to=assigned_to), **case}]
    db.tables["rescue_case_events"] = [dict(e) for e in events]
    db.tables["users"] = [
        {"id": USER_ID, "email": "amal@vff.test"},
        {"id": OTHER_USER_ID, "email": "nimal@vff.test"},
    ]
    return db


def _case(db):
    (case,) = db.tables["rescue_cases"]
    return case


def _events(db):
    return [{k: v for k, v in e.items() if k not in ("id", "case_id", "created_at") and v is not None}
            for e in db.tables["rescue_case_events"]]


def _move(db, role="Admin", **body):
    return _send(db, "PATCH", STATUS, body, role=role)


# --------------------------------------------------------------------------
# Outcome
# --------------------------------------------------------------------------

def test_resolving_without_an_outcome_is_refused_and_changes_nothing():
    db = _db()
    response = _move(db, new_status="Resolved")

    assert response.status_code == 400, response.text
    assert "outcome" in response.json()["detail"]
    assert _case(db)["status"] == "In Treatment"
    assert db.tables["rescue_case_events"] == []


def test_resolving_records_the_outcome_and_adds_it_to_the_timeline():
    db = _db()
    response = _move(db, new_status="Resolved", outcome="Rehomed", outcome_note="  Adopted by the Pereras  ")

    assert response.status_code == 200, response.text
    case = _case(db)
    assert case["status"] == "Resolved" and case["outcome"] == "Rehomed"
    assert case["resolved_at"] is not None
    assert response.json()["outcome"] == "Rehomed"
    assert _events(db) == [
        {"event_type": "status", "author_id": USER_ID, "from_status": "In Treatment", "to_status": "Resolved"},
        {"event_type": "outcome", "author_id": USER_ID, "outcome": "Rehomed", "body": "Adopted by the Pereras"},
    ]


def test_an_outcome_outside_the_five_is_refused():
    assert _move(_db(), new_status="Resolved", outcome="Escaped").status_code == 422


@pytest.mark.parametrize("current, body", [
    ("In Treatment", {"new_status": "In Treatment", "outcome": "Released"}),
    ("In Treatment", {"new_status": "Reported", "outcome_note": "why"}),
    # Already resolved: changing the outcome means reopening first.
    ("Resolved", {"new_status": "Resolved", "outcome": "Died"}),
], ids=["not-resolving", "note-alone", "already-resolved"])
def test_an_outcome_is_only_taken_when_resolving(current, body):
    db = _db(status=current, outcome="Released" if current == "Resolved" else None)
    response = _move(db, **body)

    assert response.status_code == 400, response.text
    assert db.updates == []


def test_reopening_clears_the_outcome_and_the_timeline_keeps_the_old_one():
    old = {"event_type": "outcome", "outcome": "Released", "author_id": USER_ID}
    db = _db(status="Resolved", outcome="Released", resolved_at="2026-11-01T10:00:00+00:00", events=[old])
    response = _move(db, new_status="In Treatment")

    assert response.status_code == 200, response.text
    case = _case(db)
    assert case["outcome"] is None and case["resolved_at"] is None
    assert _events(db) == [
        old,
        {"event_type": "status", "author_id": USER_ID, "from_status": "Resolved", "to_status": "In Treatment"},
    ]


# --------------------------------------------------------------------------
# Status and assignment lines
# --------------------------------------------------------------------------

def test_a_claim_reads_assigned_then_moved():
    db = _db(status="Reported", assigned_to=None)
    assert _move(db, new_status="In Treatment", assigned_to=OTHER_USER_ID).status_code == 200

    assert [e["event_type"] for e in _events(db)] == ["assign", "status"]
    assert _events(db)[0]["assignee_id"] == OTHER_USER_ID


def test_releasing_to_reported_records_the_unassignment():
    db = _db()
    assert _move(db, new_status="Reported").status_code == 200

    assign, status = _events(db)
    assert assign == {"event_type": "assign", "author_id": USER_ID}  # assignee_id NULL: unassigned
    assert status["to_status"] == "Reported"


def test_a_no_op_move_adds_nothing():
    db = _db()
    assert _move(db, new_status="In Treatment").status_code == 200
    assert db.tables["rescue_case_events"] == []


def test_a_failed_timeline_write_does_not_fail_the_move():
    db = _db()
    db.fail_inserts["rescue_case_events"] = RuntimeError("timeline down")
    response = _move(db, new_status="Resolved", outcome="Released")

    assert response.status_code == 200, response.text
    assert _case(db)["status"] == "Resolved"


# --------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------

@pytest.mark.parametrize("role", ALL_ROLES)
def test_notes_need_rescue_manage(role):
    db = _db()
    response = _send(db, "POST", NOTES, {"body": "Wound cleaned"}, role=role)

    if has_permission(role, "rescue:manage"):
        assert response.status_code == 200, response.text
        assert _events(db) == [{"event_type": "note", "body": "Wound cleaned", "author_id": USER_ID}]
    else:
        assert response.status_code == 403
        assert db.tables["rescue_case_events"] == []


def test_a_note_comes_back_with_its_author_and_is_audited():
    db = _db()
    response = _send(db, "POST", NOTES, {"body": "  Vet visit, antibiotics started  "}, role="General Staff")

    assert response.status_code == 200, response.text
    note = response.json()
    assert note["body"] == "Vet visit, antibiotics started"
    assert note["author"] == {"email": "amal@vff.test", "display_name": "Amal Silva"}
    assert [a["action_type"] for a in db.tables["system_audit_logs"]] == ["RESCUE_CASE_NOTE"]


def test_a_resolved_case_still_takes_follow_up_notes():
    db = _db(status="Resolved", outcome="Rehomed")
    assert _send(db, "POST", NOTES, {"body": "Checked in, doing well"}, role="Admin").status_code == 200


@pytest.mark.parametrize("body, code", [("   ", 400), ("x" * 2001, 422)], ids=["blank", "too-long"])
def test_blank_and_overlong_notes_are_refused(body, code):
    db = _db()
    assert _send(db, "POST", NOTES, {"body": body}, role="Admin").status_code == code
    assert db.tables["rescue_case_events"] == []


def test_a_note_on_a_missing_case_is_404():
    db = _db()
    db.tables["rescue_cases"] = []
    assert _send(db, "POST", NOTES, {"body": "hello"}, role="Admin").status_code == 404


def test_notes_cannot_be_edited_or_deleted():
    """Append-only: no route edits or removes a timeline line."""
    for route in app.routes:
        if "{case_id}" in getattr(route, "path", "") and "notes" in route.path:
            assert route.methods <= {"POST"}, route.methods


# --------------------------------------------------------------------------
# Timeline
# --------------------------------------------------------------------------

def test_the_timeline_starts_with_the_report_and_names_people():
    db = _db(description="Limping near the bus stand", events=[
        {"id": 1, "case_id": CASE_ID, "event_type": "assign", "assignee_id": OTHER_USER_ID,
         "author_id": USER_ID, "created_at": "2026-01-01T01:00:00+00:00"},
        {"id": 2, "case_id": CASE_ID, "event_type": "note", "body": "Found him",
         "author_id": OTHER_USER_ID, "created_at": "2026-01-01T02:00:00+00:00"},
    ])
    response = _send(db, "GET", TIMELINE, role="Director")

    assert response.status_code == 200, response.text
    reported, assign, note = response.json()
    assert reported["event_type"] == "reported" and reported["id"] == 0
    assert reported["body"] == "Limping near the bus stand" and reported["author"] is None
    assert assign["author"]["display_name"] == "Amal Silva"
    assert assign["assignee"]["display_name"] == "Nimal Perera"
    assert note["body"] == "Found him" and note["author"]["email"] == "nimal@vff.test"


GONE = "99999999-9999-9999-9999-999999999999"


def test_a_deleted_author_shows_as_a_deleted_user_rather_than_failing():
    db = _db(events=[{"id": 1, "case_id": CASE_ID, "event_type": "note", "body": "x",
                      "author_id": GONE, "created_at": "2026-01-01T02:00:00+00:00"}])
    response = _send(db, "GET", TIMELINE, role="Admin")

    assert response.status_code == 200, response.text
    assert response.json()[1]["author"]["display_name"] == "Deleted user"


def test_an_assignment_to_a_deleted_user_does_not_read_as_unassigned():
    # No assignee means "released, now unassigned" to the timeline, so a
    # deleted assignee must not come back as None (migration 034).
    db = _db(events=[{"id": 1, "case_id": CASE_ID, "event_type": "assign",
                      "assignee_id": GONE, "author_id": USER_ID,
                      "created_at": "2026-01-01T01:00:00+00:00"}])
    response = _send(db, "GET", TIMELINE, role="Admin")

    assert response.json()[1]["assignee"]["display_name"] == "Deleted user"


def test_the_timeline_of_a_missing_case_is_404():
    db = _db()
    db.tables["rescue_cases"] = []
    assert _send(db, "GET", TIMELINE, role="Admin").status_code == 404


@pytest.mark.parametrize("role", ALL_ROLES)
def test_the_timeline_needs_rescue_read(role):
    response = _send(_db(), "GET", TIMELINE, role=role)
    assert (response.status_code == 200) == has_permission(role, "rescue:read"), response.text
