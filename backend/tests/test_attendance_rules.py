"""Rules for recording and correcting attendance (app/api/hr.py).

Each was a defect found testing the Attendance page on 2026-11-11:

  * a clock-out before the clock-in was wrapped by 24 h, so a typo booked a
    21.8-hour day while the grid showed 0 minutes worked;
  * only unlock respected an approved payroll month, so a record could be
    added, edited and locked there, then never reopened;
  * HR could correct its own attendance (now refused, as with leave);
  * clock-in and clock-out used the server's date, which is UTC on Vercel;
  * an overnight shift could not clock out after midnight;
  * a clock-out could not be cleared, and a double clock-in could insert two
    records (the unique index is migration 024);
  * the day export printed UTC timestamps.
"""

import os
import sys
from datetime import date, datetime

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api import hr
from app.schemas.hr import SRI_LANKA
from tests.test_employees import KAMALA, _Db, _send
from tests.test_rbac_matrix import USER_ID

NOW = datetime(2026, 11, 11, 18, 0, tzinfo=SRI_LANKA)


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch):
    monkeypatch.setattr(hr, "_sl_now", lambda: NOW)


def sl(day, hh, mm=0):
    return datetime(2026, 11, day, hh, mm, tzinfo=SRI_LANKA).isoformat()


# HR's own profile (acting_as signs in as USER_ID) and someone else's.
ME = {**KAMALA, "id": 50, "first_name": "Hiran", "nic": "199012345678", "user_id": USER_ID}
OTHER = KAMALA  # id 2


def _db(attendance=(), approved_months=()):
    db = _Db([ME, OTHER])
    db.tables["attendance_log"] = [dict(a) for a in attendance]
    db.tables["payroll_runs"] = [
        {"id": i, "payroll_month": m, "payroll_year": y, "status": "Approved"}
        for i, (m, y) in enumerate(approved_months, 1)
    ]
    return db


def _record(id=7, employee_id=2, day=2, clock_in=(9, 10), clock_out=(17, 0), locked=False):
    return {
        "id": id, "employee_id": employee_id, "target_date": f"2026-11-{day:02d}",
        "clock_in": sl(day, *clock_in) if clock_in else None,
        "clock_out": sl(day, *clock_out) if clock_out else None,
        "worked_hours": None, "is_locked": locked,
    }


def _log(**body):
    payload = {"employee_id": 2, "target_date": "2026-11-02", "clock_in": sl(2, 8, 30), "clock_out": sl(2, 17, 0)}
    payload.update(body)
    return payload


def _attendance_writes(db):
    return [d for t, d in db.updates if t == "attendance_log"]


# --------------------------------------------------------------------------
# Clock times HR enters
# --------------------------------------------------------------------------

def test_a_clock_out_before_the_clock_in_is_refused():
    db = _db()
    response = _send(db, "POST", "/api/hr/attendance", _log(clock_in=sl(2, 9, 10), clock_out=sl(2, 7, 0)))

    assert response.status_code == 400, response.text
    assert "overnight" in response.json()["detail"]
    assert db.tables["attendance_log"] == []


def test_an_overnight_shift_takes_a_next_day_clock_out():
    db = _db()
    response = _send(db, "POST", "/api/hr/attendance", _log(clock_in=sl(2, 22, 0), clock_out=sl(3, 6, 0)))

    assert response.status_code == 200, response.text
    assert db.tables["attendance_log"][0]["worked_hours"] == 8.0


@pytest.mark.parametrize("body, needle", [
    ({"clock_in": sl(2, 8, 0), "clock_out": sl(3, 9, 0)}, "24 hours"),
    ({"clock_in": sl(1, 23, 0)}, "must be on 2026-11-02"),
    ({"clock_in": None}, "required"),
    ({"target_date": "2026-11-12", "clock_in": sl(12, 8, 30), "clock_out": None}, "future date"),
    ({"target_date": "2026-11-11", "clock_in": sl(11, 19, 0), "clock_out": None}, "future"),
])
def test_impossible_times_are_refused(body, needle):
    db = _db()
    response = _send(db, "POST", "/api/hr/attendance", _log(**body))

    assert response.status_code == 400, response.text
    assert needle in response.json()["detail"]


def test_a_correction_is_checked_against_the_stored_other_end():
    db = _db([_record(clock_in=(9, 10), clock_out=(17, 0))])
    response = _send(db, "PUT", "/api/hr/attendance/7", {"clock_out": sl(2, 7, 0)})

    assert response.status_code == 400, response.text
    assert _attendance_writes(db) == []


def test_a_wrong_clock_out_can_be_cleared():
    db = _db([_record()])
    response = _send(db, "PUT", "/api/hr/attendance/7", {"clock_out": None})

    assert response.status_code == 200, response.text
    assert _attendance_writes(db) == [{"clock_out": None, "worked_hours": None}]


def test_the_clock_in_cannot_be_cleared():
    db = _db([_record()])
    response = _send(db, "PUT", "/api/hr/attendance/7", {"clock_in": None})

    assert response.status_code == 400, response.text
    assert _attendance_writes(db) == []


# --------------------------------------------------------------------------
# An approved payroll month is frozen
# --------------------------------------------------------------------------

def test_no_new_record_in_a_month_whose_payroll_is_approved():
    db = _db(approved_months=[(11, 2026)])
    response = _send(db, "POST", "/api/hr/attendance", _log())

    assert response.status_code == 409, response.text
    assert db.tables["attendance_log"] == []


def test_no_correction_in_a_month_whose_payroll_is_approved():
    db = _db([_record()], approved_months=[(11, 2026)])
    response = _send(db, "PUT", "/api/hr/attendance/7", {"clock_in": sl(2, 8, 30)})

    assert response.status_code == 409, response.text
    assert _attendance_writes(db) == []


def test_another_months_approval_does_not_freeze_this_one():
    db = _db(approved_months=[(10, 2026)])
    assert _send(db, "POST", "/api/hr/attendance", _log()).status_code == 200


# --------------------------------------------------------------------------
# HR does not correct its own attendance
# --------------------------------------------------------------------------

def test_hr_cannot_record_its_own_attendance():
    db = _db()
    response = _send(db, "POST", "/api/hr/attendance", _log(employee_id=50))

    assert response.status_code == 403, response.text
    assert db.tables["attendance_log"] == []


def test_hr_cannot_correct_its_own_attendance():
    db = _db([_record(employee_id=50)])
    response = _send(db, "PUT", "/api/hr/attendance/7", {"clock_in": sl(2, 8, 30)})

    assert response.status_code == 403, response.text
    assert _attendance_writes(db) == []


def test_hr_cannot_unlock_its_own_record():
    db = _db([_record(employee_id=50, locked=True)])
    response = _send(db, "POST", "/api/hr/attendance/7/unlock")

    assert response.status_code == 403, response.text
    assert _attendance_writes(db) == []


def test_hr_still_corrects_everyone_else():
    db = _db([_record(employee_id=2)])
    assert _send(db, "PUT", "/api/hr/attendance/7", {"clock_in": sl(2, 8, 30)}).status_code == 200


# --------------------------------------------------------------------------
# Self-service clock-in and clock-out
# --------------------------------------------------------------------------

def _staff_db(attendance=()):
    # acting_as signs in as USER_ID, linked here to employee 50.
    return _db(attendance)


def test_clock_in_files_under_sri_lankas_date(monkeypatch):
    # 02:00 on the 12th in Colombo is still the 11th in UTC, the server's zone.
    monkeypatch.setattr(hr, "_sl_now", lambda: datetime(2026, 11, 12, 2, 0, tzinfo=SRI_LANKA))
    db = _staff_db()
    response = _send(db, "POST", "/api/hr/attendance/clock-in", role="General Staff")

    assert response.status_code == 200, response.text
    assert db.tables["attendance_log"][0]["target_date"] == "2026-11-12"


def test_a_double_clock_in_that_races_past_the_check_is_still_refused():
    db = _staff_db()

    class UniqueViolation(Exception):
        code = "23505"

    db.fail_inserts["attendance_log"] = UniqueViolation("duplicate key value violates unique constraint")
    response = _send(db, "POST", "/api/hr/attendance/clock-in", role="General Staff")

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Already clocked in for today."


def test_an_overnight_shift_clocks_out_the_next_morning(monkeypatch):
    monkeypatch.setattr(hr, "_sl_now", lambda: datetime(2026, 11, 12, 6, 0, tzinfo=SRI_LANKA))
    db = _staff_db([_record(employee_id=50, day=11, clock_in=(22, 0), clock_out=None)])
    response = _send(db, "POST", "/api/hr/attendance/clock-out", role="General Staff")

    assert response.status_code == 200, response.text
    (written,) = _attendance_writes(db)
    assert written["worked_hours"] == 8.0


def test_a_clock_out_forgotten_yesterday_is_not_closed_this_morning(monkeypatch):
    # A day shift left open is for HR to fix; closing it would book 23 hours.
    monkeypatch.setattr(hr, "_sl_now", lambda: datetime(2026, 11, 12, 8, 0, tzinfo=SRI_LANKA))
    db = _staff_db([_record(employee_id=50, day=11, clock_in=(9, 0), clock_out=None)])
    response = _send(db, "POST", "/api/hr/attendance/clock-out", role="General Staff")

    assert response.status_code == 400, response.text
    assert _attendance_writes(db) == []


# --------------------------------------------------------------------------
# Day export
# --------------------------------------------------------------------------

def test_the_day_export_shows_sri_lanka_times():
    db = _db([
        {**_record(day=2, clock_in=(8, 30), clock_out=(17, 0)), "employee_profile": {"first_name": "Kamala", "last_name": "Silva"}},
        {**_record(id=8, day=2, clock_in=(22, 0), clock_out=None), "clock_out": sl(3, 6, 0),
         "employee_profile": {"first_name": "Nimal", "last_name": "Fernando"}},
    ])
    response = _send(db, "GET", "/api/hr/attendance/export?target_date=2026-11-02")

    assert response.status_code == 200, response.text
    lines = response.text.strip().splitlines()
    assert lines[1].startswith("Kamala Silva,08:30,17:00")
    assert lines[2].startswith("Nimal Fernando,22:00,06:00 (next day)")
