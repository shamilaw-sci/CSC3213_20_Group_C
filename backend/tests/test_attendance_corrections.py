"""Attendance correction requests (app/api/hr.py, migration 028).

Staff ask for a past day's times to be corrected, with a reason; HR approves
or rejects (confirmed 2026-10-29, details 2026-11-12):

  * any day from the tracked-from date to yesterday, not frozen by an
    approved payroll; one pending request per person per day;
  * the same time rules as HR's own edits;
  * nobody decides their own request; rejecting needs a reason;
  * approving writes to attendance_log, creating the record if needed, and a
    locked record stays locked.
"""

import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api import hr
from app.schemas.hr import SRI_LANKA
from tests.test_employees import _Db, _send
from tests.test_rbac_matrix import OTHER_USER_ID, USER_ID

NOW = datetime(2026, 11, 12, 10, 0, tzinfo=SRI_LANKA)


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    monkeypatch.setattr(hr, "_sl_now", lambda: NOW)


def sl(day, hh, mm=0):
    return datetime(2026, 11, day, hh, mm, tzinfo=SRI_LANKA).isoformat()


# acting_as signs in as USER_ID. As staff that is Amal (id 8); as HR, Hiru
# (id 7) is HR's own record, and requests below are Amal's.
AMAL = {"id": 8, "user_id": USER_ID, "first_name": "Amal", "last_name": "Silva", "status": "Active",
        "date_joined": "2020-01-01", "attendance_tracked_from": None}
HIRU = {"id": 7, "user_id": OTHER_USER_ID, "first_name": "Hiru", "last_name": "Officer", "status": "Active",
        "date_joined": "2020-01-01", "attendance_tracked_from": None}


def _db(records=(), requests=(), approved_on=None, tracking_start="2026-09-01", staff=AMAL):
    db = _Db([staff, HIRU])
    db.tables["attendance_log"] = [dict(r) for r in records]
    db.tables["attendance_correction_requests"] = [dict(r) for r in requests]
    db.tables["attendance_settings"] = [{"id": 1, "tracking_start_date": tracking_start}]
    db.tables["payroll_runs"] = [] if not approved_on else [
        {"id": 1, "payroll_month": 11, "payroll_year": 2026, "status": "Approved", "approved_at": approved_on}]
    return db


def _record(day=10, clock_in=(8, 30), clock_out=None, locked=False, employee_id=8):
    return {"id": 70, "employee_id": employee_id, "target_date": f"2026-11-{day:02d}",
            "clock_in": sl(day, *clock_in) if clock_in else None,
            "clock_out": sl(day, *clock_out) if clock_out else None,
            "worked_hours": None, "is_locked": locked}


def _ask(db, **body):
    payload = {"target_date": "2026-11-10", "clock_out": sl(10, 17, 0), "reason": "Forgot to clock out"}
    payload.update(body)
    return _send(db, "POST", "/api/hr/attendance/corrections", payload, role="General Staff")


def _pending(id=5, day=10, employee_id=8, requested_by=USER_ID, clock_in=None, clock_out=(17, 0)):
    return {"id": id, "employee_id": employee_id, "target_date": f"2026-11-{day:02d}",
            "requested_clock_in": sl(day, *clock_in) if clock_in else None,
            "requested_clock_out": sl(day, *clock_out) if clock_out else None,
            "reason": "Forgot to clock out", "status": "Pending", "requested_by": requested_by}


def _log_writes(db):
    return [d for t, d in db.updates if t == "attendance_log"]


# --------------------------------------------------------------------------
# Asking
# --------------------------------------------------------------------------

def test_staff_ask_for_a_missing_clock_out_and_the_original_is_kept():
    db = _db([_record()])
    response = _ask(db)

    assert response.status_code == 200, response.text
    (req,) = db.tables["attendance_correction_requests"]
    assert req["original_clock_in"] == sl(10, 8, 30) and req["original_clock_out"] is None
    assert req["requested_clock_out"] == sl(10, 17, 0) and req["requested_clock_in"] is None
    assert req["reason"] == "Forgot to clock out"


def test_a_day_with_no_record_can_be_asked_for():
    db = _db()
    assert _ask(db, clock_in=sl(10, 8, 30)).status_code == 200


@pytest.mark.parametrize("body, needle", [
    ({"target_date": "2026-11-12", "clock_out": sl(12, 17)}, "past days"),             # today
    ({"target_date": "2026-08-31", "clock_out": "2026-08-31T17:00:00+05:30"}, "tracked from"),
    ({"clock_out": None}, "clock-in, the clock-out or both"),
    ({"clock_out": sl(10, 7, 0)}, "after clock-in"),                                   # before the stored 08:30
    ({"clock_in": sl(10, 8, 30), "clock_out": None}, "already the recorded times"),
])
def test_requests_that_cannot_be_right_are_refused(body, needle):
    db = _db([_record()])
    response = _ask(db, **body)

    assert response.status_code == 400, response.text
    assert needle in response.json()["detail"]
    assert db.tables["attendance_correction_requests"] == []


def test_a_reason_is_required():
    assert _ask(_db([_record()]), reason="   ").status_code == 422


def test_days_frozen_by_an_approved_payroll_are_refused():
    db = _db([_record()], approved_on="2026-11-11T05:00:00+00:00")
    assert _ask(db).status_code == 409
    assert db.tables["attendance_correction_requests"] == []


def test_one_waiting_request_per_day():
    db = _db([_record()], [_pending()])
    response = _ask(db)

    assert response.status_code == 409, response.text
    assert len(db.tables["attendance_correction_requests"]) == 1


def test_an_inactive_employee_cannot_ask():
    db = _db([_record()], staff={**AMAL, "status": "Inactive"})
    assert _ask(db).status_code == 403


def test_staff_withdraw_their_own_waiting_request_only():
    db = _db(requests=[_pending(id=5), _pending(id=6, day=9, employee_id=7, requested_by=OTHER_USER_ID)])
    assert _send(db, "POST", "/api/hr/attendance/corrections/5/cancel", role="General Staff").status_code == 200
    assert _send(db, "POST", "/api/hr/attendance/corrections/6/cancel", role="General Staff").status_code == 403
    # Already cancelled now.
    assert _send(db, "POST", "/api/hr/attendance/corrections/5/cancel", role="General Staff").status_code == 409


def test_staff_list_their_own_requests():
    db = _db(requests=[_pending(id=5), _pending(id=6, day=9, employee_id=7, requested_by=OTHER_USER_ID)])
    body = _send(db, "GET", "/api/hr/attendance/corrections/me", role="General Staff").json()
    assert [r["id"] for r in body] == [5]


# --------------------------------------------------------------------------
# Deciding (as HR: acting_as signs in as USER_ID, here HR's own login)
# --------------------------------------------------------------------------

def _hr_db(records=(), requests=(), **kw):
    # As HR, USER_ID belongs to Hiru (7); requests are Amal's (8).
    db = _db(records, requests, staff={**AMAL, "user_id": OTHER_USER_ID}, **kw)
    db.tables["employee_profile"][1] = {**HIRU, "user_id": USER_ID}
    return db


def _hr_pending(**kw):
    return _pending(requested_by=OTHER_USER_ID, **kw)


def test_hr_sees_waiting_requests_with_the_current_times():
    # The fake does no joins: the row carries what PostgREST would embed.
    db = _hr_db([_record()], [{**_hr_pending(), "employee_profile": {"first_name": "Amal", "last_name": "Silva"}}])
    (row,) = _send(db, "GET", "/api/hr/attendance/corrections?status=Pending").json()
    assert row["employee_name"] == "Amal Silva"
    assert row["current_clock_in"] == sl(10, 8, 30) and row["current_clock_out"] is None


def test_approving_writes_the_times_and_keeps_a_lock():
    db = _hr_db([_record(locked=True)], [_hr_pending()])
    response = _send(db, "POST", "/api/hr/attendance/corrections/5/approve", {})

    assert response.status_code == 200, response.text
    (written,) = _log_writes(db)
    assert written["clock_out"] == sl(10, 17, 0) and written["worked_hours"] == 8.5
    assert "is_locked" not in written
    req = db.tables["attendance_correction_requests"][0]
    assert req["status"] == "Approved" and req["attendance_log_id"] == 70


def test_approving_creates_the_record_when_the_day_had_none():
    db = _hr_db([], [_hr_pending(clock_in=(8, 30), clock_out=(17, 0))])
    assert _send(db, "POST", "/api/hr/attendance/corrections/5/approve", {}).status_code == 200
    (created,) = db.tables["attendance_log"]
    assert created["employee_id"] == 8 and created["worked_hours"] == 8.5


def test_rejecting_needs_a_reason():
    db = _hr_db([_record()], [_hr_pending()])
    assert _send(db, "POST", "/api/hr/attendance/corrections/5/reject", {"note": " "}).status_code == 400
    assert _send(db, "POST", "/api/hr/attendance/corrections/5/reject", {"note": "Gate log shows 16:00"}).status_code == 200
    assert _log_writes(db) == []


def test_hr_cannot_decide_their_own_request():
    db = _hr_db([_record(employee_id=7)], [_pending(employee_id=7, requested_by=USER_ID)])
    response = _send(db, "POST", "/api/hr/attendance/corrections/5/approve", {})
    assert response.status_code == 403
    assert _log_writes(db) == []


def test_a_day_frozen_since_the_request_cannot_be_approved():
    db = _hr_db([_record()], [_hr_pending()], approved_on="2026-11-11T05:00:00+00:00")
    assert _send(db, "POST", "/api/hr/attendance/corrections/5/approve", {}).status_code == 409
    assert _log_writes(db) == []


def test_a_decided_request_cannot_be_decided_again():
    db = _hr_db([_record()], [{**_hr_pending(), "status": "Rejected"}])
    assert _send(db, "POST", "/api/hr/attendance/corrections/5/approve", {}).status_code == 409


@pytest.mark.parametrize("role", ["General Staff", "Director", "Finance Officer"])
def test_only_attendance_managers_decide(role):
    db = _hr_db([_record()], [_hr_pending()])
    assert _send(db, "POST", "/api/hr/attendance/corrections/5/approve", {}, role=role).status_code == 403
    assert _send(db, "GET", "/api/hr/attendance/corrections", role=role).status_code == 403
