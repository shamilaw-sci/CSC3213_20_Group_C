"""Recording an outcome on a case resolved before outcomes existed
(POST /api/rescue_cases/cases/{id}/outcome).

Confirmed 2026-11-13: rescue:manage; only a Resolved case with no outcome;
the case's last update stands in for its resolve date, and the timeline
says that date is an estimate.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.permissions import has_permission
from tests.test_case_timeline import _db, _events
from tests.test_employees import _send
from tests.test_rbac_matrix import ALL_ROLES, CASE_ID, USER_ID

URL = f"/api/rescue_cases/cases/{CASE_ID}/outcome"
OLD_UPDATE = "2026-07-29T19:00:00+00:00"  # 00:30 on 30 Jul in Sri Lanka: the date shown is local


def _legacy(**case):
    return _db(status="Resolved", outcome=None, resolved_at=None, updated_at=OLD_UPDATE, **case)


def _case(db):
    (c,) = db.tables["rescue_cases"]
    return c


def test_an_older_case_gets_its_outcome_dated_from_its_last_update(board_pings):
    db = _legacy()
    r = _send(db, "POST", URL, {"outcome": "Rehomed", "outcome_note": "Adopted by a neighbour"}, role="General Staff")

    assert r.status_code == 200, r.text
    case = _case(db)
    assert case["status"] == "Resolved"  # not reopened
    assert case["outcome"] == "Rehomed" and case["resolved_at"] == OLD_UPDATE
    (line,) = _events(db)
    assert line["event_type"] == "outcome" and line["outcome"] == "Rehomed" and line["author_id"] == USER_ID
    assert line["body"] == ("Adopted by a neighbour (Recorded later. Resolve date estimated from the "
                            "case's last update: 30 Jul 2026.)")
    assert [a["action_type"] for a in db.tables["system_audit_logs"]] == ["RESCUE_CASE_OUTCOME_RECORDED"]
    assert len(board_pings) == 1


def test_without_a_note_the_line_still_says_the_date_is_an_estimate():
    db = _legacy()
    _send(db, "POST", URL, {"outcome": "Released"}, role="Admin")
    (line,) = _events(db)
    assert line["body"].startswith("Recorded later. Resolve date estimated")


@pytest.mark.parametrize("case, code, needle", [
    ({"status": "In Treatment", "outcome": None}, 400, "Resolve it instead"),
    ({"status": "Resolved", "outcome": "Died"}, 409, "Reopen it"),
], ids=["not-resolved", "already-has-one"])
def test_only_a_resolved_case_without_an_outcome(case, code, needle):
    db = _db(**case)
    r = _send(db, "POST", URL, {"outcome": "Rehomed"}, role="Admin")

    assert r.status_code == code, r.text
    assert needle in r.json()["detail"]
    assert db.updates == [] and _events(db) == []


def test_an_unknown_outcome_or_case_is_refused():
    assert _send(_legacy(), "POST", URL, {"outcome": "Escaped"}, role="Admin").status_code == 422
    db = _legacy()
    db.tables["rescue_cases"] = []
    assert _send(db, "POST", URL, {"outcome": "Rehomed"}, role="Admin").status_code == 404


@pytest.mark.parametrize("role", ALL_ROLES)
def test_it_needs_rescue_manage(role):
    db = _legacy()
    r = _send(db, "POST", URL, {"outcome": "Rehomed"}, role=role)
    assert (r.status_code == 200) == has_permission(role, "rescue:manage"), (role, r.status_code)
    if r.status_code != 200:
        assert _case(db)["outcome"] is None
