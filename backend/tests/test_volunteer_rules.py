"""Volunteer rules from the audit (V2-V7, V9).

Most tests use the RBAC matrix's Supabase double, which ignores filters and
returns the fixture rows for each table and operation. Emails are replaced by
recorders, so nothing is sent.
"""

import os
import sys
from datetime import timedelta

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api import volunteers as volunteers_api
from app.schemas.inventory import today_in_sri_lanka
from app.schemas.volunteer import AssignmentCreate
from tests.test_rbac_matrix import _FakeQuery, _FakeSupabase, _request, acting_as

VOL_ID = "11111111-1111-1111-1111-111111111111"
SHIFT_ID = "22222222-2222-2222-2222-222222222222"
ASSIGN_ID = "33333333-3333-3333-3333-333333333333"
TODAY = today_in_sri_lanka()
FUTURE = (TODAY + timedelta(days=10)).isoformat()
PAST = (TODAY - timedelta(days=3)).isoformat()


def _volunteer(status="approved", token="old-token"):
    return {
        "id": VOL_ID, "full_name": "Nimal Perera", "email": "nimal@example.com",
        "phone": None, "skills": [], "skills_other": None, "availability": [],
        "status": status, "access_token": token, "link_shared_at": None,
        "applied_at": "2026-11-01T00:00:00+00:00", "reviewed_at": None,
        "reviewed_by": None, "staff_notes": None,
    }


def _shift(date=FUTURE, cancelled=False, needed=2, **extra):
    return {
        "id": SHIFT_ID, "title": "Kandy Clinic", "description": None, "location": "Kandy",
        "shift_date": date, "start_time": "09:00:00", "end_time": "13:00:00",
        "volunteers_needed": needed, "is_cancelled": cancelled, "program_id": None,
        "created_by": None, "created_at": "2026-11-01T00:00:00+00:00", **extra,
    }


def _assignment(response="pending", shift_id=SHIFT_ID, program_id=None, id=ASSIGN_ID):
    return {
        "id": id, "volunteer_id": VOL_ID, "shift_id": shift_id, "rescue_case_id": None,
        "program_id": program_id, "response": response, "decline_reason": None,
        "responded_at": None, "assigned_by": None,
        "assigned_at": "2026-11-01T00:00:00+00:00",
    }


@pytest.fixture
def sent(monkeypatch):
    """Record every email instead of sending it."""
    calls = []

    async def record(*args, **kwargs):
        calls.append(args)
        return True

    for name in ("send_shift_notice", "send_volunteer_new_link",
                 "send_volunteer_approved", "send_assignment_notice"):
        monkeypatch.setattr(volunteers_api.email_service, name,
                            lambda *a, _n=name, **k: record(_n, *a, **k))
    return calls


# --------------------------------------------------------------------------
# V2 / V7: review status changes
# --------------------------------------------------------------------------

@pytest.mark.parametrize("current,target,code", [
    ("pending", "approved", 200),
    ("pending", "rejected", 200),
    ("approved", "inactive", 200),
    ("inactive", "approved", 200),
    ("approved", "approved", 409),   # would re-send the welcome email
    ("rejected", "approved", 409),
    ("pending", "inactive", 409),
    ("approved", "rejected", 409),
    ("rejected", "inactive", 409),
])
def test_review_only_allows_the_listed_changes(current, target, code, sent):
    tables = {"volunteers": {"select": [_volunteer(current)], "update": [_volunteer(target)]}}
    with acting_as("Director", tables=tables):
        response = _request("PATCH", f"/api/volunteers/{VOL_ID}/review", json={"status": target})
    assert response.status_code == code, response.text


def test_reactivating_gives_a_new_link(sent):
    captured = {}
    tables = {"volunteers": {"select": [_volunteer("inactive")],
                             "update": [_volunteer("approved", token="new-token")]}}
    with acting_as("Director", tables=tables, capture_update=captured):
        response = _request("PATCH", f"/api/volunteers/{VOL_ID}/review", json={"status": "approved"})
    assert response.status_code == 200
    assert captured["update_data"]["access_token"] not in ("old-token", "", None)
    assert captured["update_data"]["link_shared_at"] is None


def test_reset_link_issues_a_new_token_and_emails_it(sent):
    captured = {}
    tables = {"volunteers": {"select": [_volunteer("approved")],
                             "update": [_volunteer("approved", token="new-token")]}}
    with acting_as("Director", tables=tables, capture_update=captured):
        response = _request("POST", f"/api/volunteers/{VOL_ID}/reset-link")
    assert response.status_code == 200
    assert captured["update_data"]["access_token"] != "old-token"
    assert [c[0] for c in sent] == ["send_volunteer_new_link"]


def test_reset_link_needs_an_approved_volunteer(sent):
    with acting_as("Director", tables={"volunteers": {"select": [_volunteer("pending")]}}):
        response = _request("POST", f"/api/volunteers/{VOL_ID}/reset-link")
    assert response.status_code == 409


def test_reset_link_needs_volunteers_approve():
    with acting_as("Operations Lead", tables={"volunteers": {"select": [_volunteer()]}}):
        response = _request("POST", f"/api/volunteers/{VOL_ID}/reset-link")
    assert response.status_code == 403


# --------------------------------------------------------------------------
# V6: deactivating clears open assignments
# --------------------------------------------------------------------------

class _RecordingQuery(_FakeQuery):
    def __init__(self, name, rows, log):
        super().__init__(rows)
        self._name, self._log = name, log

    def delete(self, *a, **k):
        self._log.append(self._name)
        return super().delete()


class _RecordingSupabase(_FakeSupabase):
    def __init__(self, tables):
        super().__init__(tables)
        self.deletes = []

    def table(self, name):
        return _RecordingQuery(name, self._tables.get(name, []), self.deletes)


@pytest.mark.anyio
@pytest.mark.parametrize("rows,removed", [
    ([{**_assignment(), "volunteer_shifts": {"shift_date": FUTURE}}], 1),
    ([{**_assignment("accepted"), "volunteer_shifts": {"shift_date": TODAY.isoformat()}}], 1),
    ([{**_assignment("accepted"), "volunteer_shifts": {"shift_date": PAST}}], 0),   # history
    ([{**_assignment("pending", shift_id=None, program_id=7), "volunteer_shifts": None}], 1),
    ([{**_assignment("accepted", shift_id=None, program_id=7), "volunteer_shifts": None}], 0),
])
async def test_deactivating_clears_future_and_unanswered_assignments(rows, removed):
    supabase = _RecordingSupabase({"volunteer_assignments": {"select": rows}})
    count = await volunteers_api._clear_open_assignments(supabase, VOL_ID, "user")
    assert count == removed
    assert supabase.deletes == (["volunteer_assignments"] if removed else [])


# --------------------------------------------------------------------------
# V3: exactly one assignment target
# --------------------------------------------------------------------------

@pytest.mark.parametrize("body", [
    {"volunteer_id": VOL_ID},
    {"volunteer_id": VOL_ID, "shift_id": SHIFT_ID, "rescue_case_id": SHIFT_ID},
])
def test_assignment_needs_exactly_one_target(body):
    with pytest.raises(ValidationError):
        AssignmentCreate(**body)


def test_assignment_with_two_targets_is_422_not_500():
    body = {"volunteer_id": VOL_ID, "shift_id": SHIFT_ID, "rescue_case_id": SHIFT_ID}
    with acting_as("Operations Lead"):
        response = _request("POST", "/api/volunteers/assignments", json=body)
    assert response.status_code == 422


# --------------------------------------------------------------------------
# V4: assignments respect the shift's state
# --------------------------------------------------------------------------

def _assign(shift, existing=(), sent_fixture=None):
    tables = {
        "volunteers": {"select": [_volunteer()]},
        "volunteer_shifts": {"select": [shift]},
        "volunteer_assignments": {"select": list(existing), "insert": [_assignment()]},
    }
    with acting_as("Operations Lead", tables=tables):
        return _request("POST", "/api/volunteers/assignments",
                        json={"volunteer_id": VOL_ID, "shift_id": SHIFT_ID})


def test_cannot_assign_to_a_cancelled_shift(sent):
    assert _assign(_shift(cancelled=True)).status_code == 409


def test_cannot_assign_to_a_past_shift(sent):
    assert _assign(_shift(date=PAST)).status_code == 409


def test_assigning_to_a_full_shift_warns_but_works(sent):
    response = _assign(_shift(needed=1), existing=[{"id": "x", "response": "accepted"}])
    assert response.status_code == 200
    assert "needs 1 volunteer" in response.json()["warning"]


def test_assigning_with_room_left_has_no_warning(sent):
    response = _assign(_shift(needed=3), existing=[{"id": "x", "response": "declined"}])
    assert response.status_code == 200
    assert response.json()["warning"] is None


@pytest.mark.parametrize("status", ["Completed", "Cancelled"])
def test_cannot_assign_to_an_ended_program(status, sent):
    tables = {"volunteers": {"select": [_volunteer()]},
              "programs": {"select": [{"id": 7, "status": status}]}}
    with acting_as("Operations Lead", tables=tables):
        response = _request("POST", "/api/volunteers/assignments",
                            json={"volunteer_id": VOL_ID, "program_id": 7})
    assert response.status_code == 409


@pytest.mark.parametrize("shift", [_shift(cancelled=True), _shift(date=PAST)])
def test_volunteer_cannot_answer_a_cancelled_or_past_shift(shift):
    tables = {"volunteers": {"select": [_volunteer()]},
              "volunteer_assignments": {"select": [_assignment()]},
              "volunteer_shifts": {"select": [shift]}}
    with acting_as("General Staff", tables=tables):
        response = _request("POST", f"/api/volunteers/my-assignments/tok/{ASSIGN_ID}/respond",
                            json={"response": "accepted"})
    assert response.status_code == 409


# --------------------------------------------------------------------------
# V5: volunteers are told about changes
# --------------------------------------------------------------------------

def _patch_shift(body, before, after, sent):
    tables = {
        "volunteer_shifts": {"select": [before], "update": [after]},
        "volunteer_assignments": {"select": [
            {"volunteer_id": VOL_ID, "response": "accepted"},
            {"volunteer_id": "declined-one", "response": "declined"},
        ]},
        "volunteers": {"select": [_volunteer()]},
    }
    with acting_as("Operations Lead", tables=tables):
        return _request("PATCH", f"/api/volunteers/shifts/{SHIFT_ID}", json=body)


def test_cancelling_a_shift_emails_its_volunteers(sent):
    response = _patch_shift({"is_cancelled": True}, _shift(), _shift(cancelled=True), sent)
    assert response.status_code == 200
    assert [c[1] for c in sent] == ["cancelled"]


def test_moving_a_shift_emails_its_volunteers(sent):
    later = (TODAY + timedelta(days=12)).isoformat()
    response = _patch_shift({"shift_date": later}, _shift(), _shift(date=later), sent)
    assert response.status_code == 200
    assert [c[1] for c in sent] == ["changed"]


def test_editing_only_the_description_sends_nothing(sent):
    response = _patch_shift({"description": "Bring gloves"}, _shift(),
                            _shift(description="Bring gloves"), sent)
    assert response.status_code == 200
    assert sent == []


def test_removing_a_volunteer_emails_them(sent):
    tables = {"volunteer_assignments": {"select": [_assignment("accepted")]},
              "volunteer_shifts": {"select": [_shift()]},
              "volunteers": {"select": [_volunteer()]}}
    with acting_as("Operations Lead", tables=tables):
        response = _request("DELETE", f"/api/volunteers/assignments/{ASSIGN_ID}")
    assert response.status_code == 200
    assert [c[1] for c in sent] == ["removed"]


# --------------------------------------------------------------------------
# V9: shift dates
# --------------------------------------------------------------------------

def _new_shift(date, program=None):
    body = {"title": "Kandy Clinic", "shift_date": date,
            "start_time": "09:00", "end_time": "13:00"}
    tables = {"volunteer_shifts": {"insert": [_shift(date=date)]}}
    if program:
        body["program_id"] = 7
        tables["programs"] = {"select": [program]}
    with acting_as("Operations Lead", tables=tables):
        return _request("POST", "/api/volunteers/shifts", json=body)


def test_a_new_shift_cannot_be_in_the_past():
    assert _new_shift(PAST).status_code == 400


def test_a_shift_before_the_program_starts_is_a_warning():
    start = (TODAY + timedelta(days=20)).isoformat()
    response = _new_shift(FUTURE, {"id": 7, "status": "Upcoming", "start_date": start, "end_date": None})
    assert response.status_code == 200
    assert "before the program starts" in response.json()["warning"]


def test_a_shift_inside_the_program_has_no_warning():
    response = _new_shift(FUTURE, {"id": 7, "status": "Active", "start_date": PAST, "end_date": None})
    assert response.status_code == 200
    assert response.json()["warning"] is None


def test_a_shift_cannot_be_moved_into_the_past(sent):
    response = _patch_shift({"shift_date": PAST}, _shift(), _shift(date=PAST), sent)
    assert response.status_code == 400
