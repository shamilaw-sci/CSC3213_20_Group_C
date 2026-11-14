"""
Attendance tracking start date (confirmed 2026-11-02).

Days before a person's tracked-from date are "Not tracked": not counted in
totals, never in needs-attention, never sent to payroll. Moving a date
earlier is refused when it would bring a day from a month with Approved
payroll into tracking.
"""

from datetime import date

import pytest

from app.core.permissions import has_permission
from app.core.supabase import get_supabase
from app.main import app
from app.services.attendance_month import (
    ABSENT, LEAVE, NOT_EMPLOYED, NOT_TRACKED, build_month, day_cell, days_brought_into_tracking,
    month_has_tracked_days, months_between, payable_absences, tracked_from_for,
)
from app.services.work_calendar import resolve_day
from tests.test_attendance_month import ANNUAL, NOW, OFFICE, TODAY, WED, rec
from tests.test_ledger_integrity import _RecordingSupabase
from tests.test_rbac_matrix import ALL_ROLES, OTHER_USER_ID, _request, acting_as

OCT_15 = date(2026, 10, 15)


# --------------------------------------------------------------------------
# One day
# --------------------------------------------------------------------------

def _cell(d, tracked_from, record=None, approved=None, joined=date(2020, 1, 1)):
    return day_cell(d, resolve_day(d, OFFICE, []), record, approved, None, joined, TODAY, NOW, tracked_from)


def test_a_working_day_before_tracking_is_not_tracked_not_absent():
    assert _cell(WED, tracked_from=date(2026, 10, 29)).status == NOT_TRACKED


def test_a_clock_in_before_tracking_is_shown_but_not_judged():
    c = _cell(WED, tracked_from=date(2026, 10, 29), record=rec(WED, (10, 0)))
    assert c.status == NOT_TRACKED
    assert c.clock_in is not None and c.late_minutes == 0
    assert not c.needs_attention


def test_the_tracking_day_itself_is_tracked():
    assert _cell(WED, tracked_from=WED).status == ABSENT


def test_approved_leave_before_tracking_still_shows_as_leave():
    # No-pay leave goes to payroll whatever the date, so leave stays visible.
    assert _cell(WED, tracked_from=date(2026, 10, 29), approved=ANNUAL).status == LEAVE


def test_before_joining_wins_over_not_tracked():
    assert _cell(WED, tracked_from=date(2026, 10, 29), joined=date(2026, 10, 29)).status == NOT_EMPLOYED


# --------------------------------------------------------------------------
# The month
# --------------------------------------------------------------------------

def _employee(id=7, override=None):
    return {"id": id, "first_name": "Amal", "last_name": f"Silva{id}", "status": "Active",
            "date_joined": "2020-01-01", "attendance_tracked_from": override}


def _month(employees, attendance=(), tracking_start=OCT_15):
    return build_month(2026, 10, employees, [OFFICE], [], [], list(attendance), [],
                       today=TODAY, now=NOW, tracking_start=tracking_start)


def test_days_before_tracking_count_towards_no_total():
    # A late clock-in on the 14th, before tracking: not late, not worked.
    result = _month([_employee()], [rec(date(2026, 10, 14), (10, 0), (17, 0))])
    (row,) = result["employees"]
    t = row["totals"]
    # Weekdays 15-30 October: 15th, 16th, 19th-23rd, 26th-30th = 12, none clocked.
    assert t["absent"] == 12
    assert t["late"] == 0 and t["present"] == 0 and t["worked_minutes"] == 0
    assert t["expected_minutes"] == 12 * 450


def test_days_before_tracking_never_need_attention():
    result = _month([_employee()], [rec(date(2026, 10, 14), (10, 0))])
    assert result["attention"]
    assert all(a["date"] >= "2026-10-15" for a in result["attention"])


def test_the_month_reports_the_dates():
    result = _month([_employee(), _employee(8, override="2026-10-01")])
    assert result["tracking_start_date"] == "2026-10-15"
    rows = {r["employee_id"]: r for r in result["employees"]}
    assert rows[7]["tracked_from"] == "2026-10-15" and not rows[7]["tracking_overridden"]
    assert rows[8]["tracked_from"] == "2026-10-01" and rows[8]["tracking_overridden"]


def test_an_override_can_start_tracking_earlier_than_the_organisation():
    result = _month([_employee(8, override="2026-10-01")])
    first = next(c for c in result["employees"][0]["cells"] if c["date"] == "2026-10-01")
    assert first["status"] == ABSENT


def test_an_override_can_start_tracking_later_than_the_organisation():
    result = _month([_employee(8, override="2026-10-26")])
    statuses = {c["date"]: c["status"] for c in result["employees"][0]["cells"]}
    assert statuses["2026-10-20"] == NOT_TRACKED and statuses["2026-10-26"] == ABSENT


def test_tracked_from_falls_back_to_the_organisation_date():
    assert tracked_from_for({"attendance_tracked_from": None}, OCT_15) == OCT_15
    assert tracked_from_for({"attendance_tracked_from": "2026-09-01"}, OCT_15) == date(2026, 9, 1)


# --------------------------------------------------------------------------
# Payroll and month close
# --------------------------------------------------------------------------

def test_not_tracked_days_are_never_payable_absences():
    (row,) = _month([_employee()])["employees"]
    payable = payable_absences(row["cells"])
    assert payable and all(d >= "2026-10-15" for d in payable)


def test_month_close_refuses_a_month_before_tracking_started():
    sept = date(2026, 9, 1)
    assert not month_has_tracked_days(2026, 8, [sept])
    assert month_has_tracked_days(2026, 9, [sept])
    # An override reaching back into August makes August closable.
    assert month_has_tracked_days(2026, 8, [sept, date(2026, 8, 20)])
    # No date at all: everything is tracked.
    assert month_has_tracked_days(2026, 8, [None])


def test_moving_earlier_brings_the_days_between_into_tracking():
    assert days_brought_into_tracking(OCT_15, date(2026, 9, 1)) == (date(2026, 9, 1), date(2026, 10, 14))
    assert days_brought_into_tracking(date(2026, 9, 1), OCT_15) is None
    assert days_brought_into_tracking(OCT_15, OCT_15) is None
    assert days_brought_into_tracking(None, OCT_15) is None


def test_months_between_crosses_the_year():
    assert months_between(date(2026, 11, 20), date(2027, 2, 1)) == [(2026, 11), (2026, 12), (2027, 1), (2027, 2)]


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

class _Db(_RecordingSupabase):
    """Also records upserts, which is how the organisation date is saved."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.upserts = []

    def table(self, name):
        query = super().table(name)

        def upsert(data=None, *a, **k):
            self.upserts.append((name, data))
            return query

        query.upsert = upsert
        return query


def _db(org="2026-10-15", approved=(), override=None):
    return _Db({
        "attendance_settings": {"select": [{"id": 1, "tracking_start_date": org}]},
        "employee_profile": {"select": [
            {"id": 7, "first_name": "Amal", "last_name": "Silva", "status": "Active", "date_joined": "2020-01-01",
             "user_id": OTHER_USER_ID, "attendance_tracked_from": override},
        ]},
        "attendance_log": {"select": []},
        "work_schedules": {"select": [OFFICE]},
        "employee_schedule_assignments": {"select": []},
        "holidays": {"select": []},
        "leave_requests": {"select": []},
        "leave_request_days": {"select": []},
        "payroll_runs": {"select": [{"payroll_month": m, "payroll_year": y, "status": "Approved"} for y, m in approved]},
        "system_audit_logs": {"select": [], "insert": [{"id": 1}]},
    })


def _send(db, method, path, json=None, role="HR Officer"):
    with acting_as(role):
        app.dependency_overrides[get_supabase] = lambda: db
        return _request(method, path, json=json)


def test_impact_counts_the_absences_moving_earlier_would_create():
    body = _send(_db(), "GET", "/api/hr/attendance-tracking/impact?start=2026-10-01").json()
    assert body["direction"] == "earlier"
    assert (body["first"], body["last"]) == ("2026-10-01", "2026-10-14")
    # Weekdays 1-14 October: 1st, 2nd, 5th-9th, 12th-14th = 10, none clocked.
    assert body["working_days"] == 10 and body["absences"] == 10 and body["employees"] == 1
    assert body["blocked_months"] == []


def test_impact_of_moving_later_counts_what_stops_being_tracked():
    body = _send(_db(org="2026-10-01"), "GET", "/api/hr/attendance-tracking/impact?start=2026-10-15").json()
    assert body["direction"] == "later" and body["absences"] == 10


def test_moving_earlier_into_an_approved_payroll_month_is_refused():
    db = _db(approved=[(2026, 9)])
    response = _send(db, "PUT", "/api/hr/attendance-tracking", json={"tracking_start_date": "2026-09-20"})
    assert response.status_code == 409
    assert "September 2026" in response.json()["detail"]
    assert db.upserts == []


def test_the_impact_names_the_paid_months_before_saving():
    body = _send(_db(approved=[(2026, 9)]), "GET", "/api/hr/attendance-tracking/impact?start=2026-08-01").json()
    # No approval date on the fixture: the whole month is frozen.
    assert body["blocked_months"] == [{"year": 2026, "month": 9, "frozen_through": "2026-09-30", "closed": False}]


def test_moving_earlier_past_unpaid_months_is_saved():
    db = _db(approved=[(2026, 8)])
    response = _send(db, "PUT", "/api/hr/attendance-tracking", json={"tracking_start_date": "2026-09-01"})
    assert response.status_code == 200, response.text
    assert db.upserts and db.upserts[0][1]["tracking_start_date"] == "2026-09-01"


def test_moving_later_is_allowed_even_over_a_paid_month():
    db = _db(org="2026-08-01", approved=[(2026, 8)])
    response = _send(db, "PUT", "/api/hr/attendance-tracking", json={"tracking_start_date": "2026-09-01"})
    assert response.status_code == 200, response.text


def test_an_override_into_a_paid_month_is_refused():
    db = _db(approved=[(2026, 9)])
    response = _send(db, "PUT", "/api/hr/employees/7/attendance-tracking", json={"tracked_from": "2026-09-15"})
    assert response.status_code == 409
    assert not [u for u in db.updates if u[0] == "employee_profile"]


def test_an_override_later_is_saved_and_clearing_it_follows_the_organisation():
    db = _db()
    assert _send(db, "PUT", "/api/hr/employees/7/attendance-tracking",
                 json={"tracked_from": "2026-10-26"}).status_code == 200
    assert ("employee_profile", {"attendance_tracked_from": "2026-10-26"}) in db.updates

    db = _db(override="2026-10-26")
    body = _send(db, "PUT", "/api/hr/employees/7/attendance-tracking", json={"tracked_from": None}).json()
    assert body["attendance_tracked_from"] is None
    # Back to the organisation's 15th: earlier than the override.
    assert body["impact"]["direction"] == "earlier" and body["impact"]["new_date"] == "2026-10-15"


def test_clearing_an_override_into_a_paid_month_is_refused():
    # Override 1 Oct, organisation 1 Sep, September paid: clearing would
    # track September again.
    db = _db(org="2026-09-01", override="2026-10-01", approved=[(2026, 9)])
    response = _send(db, "PUT", "/api/hr/employees/7/attendance-tracking", json={"tracked_from": None})
    assert response.status_code == 409


def test_an_impossible_date_is_rejected():
    response = _send(_db(), "PUT", "/api/hr/attendance-tracking", json={"tracking_start_date": "1999-12-31"})
    assert response.status_code == 422


@pytest.mark.parametrize("role", ALL_ROLES)
def test_only_hr_manage_changes_the_date(role):
    response = _send(_db(), "PUT", "/api/hr/attendance-tracking",
                     json={"tracking_start_date": "2026-10-20"}, role=role)
    assert (response.status_code != 403) == has_permission(role, "hr:manage"), (role, response.status_code)


def test_the_director_sees_the_date_on_the_grid():
    body = _send(_db(), "GET", "/api/hr/attendance/month?year=2026&month=10", role="Director").json()
    assert body["tracking_start_date"] == "2026-10-15"
    assert body["employees"][0]["tracked_from"] == "2026-10-15"


def _approved_on(db, month, year, approved_at):
    db._tables["payroll_runs"] = {"select": [
        {"payroll_month": month, "payroll_year": year, "status": "Approved", "approved_at": approved_at}]}
    return db


def test_days_after_a_mid_month_approval_can_still_be_brought_into_tracking():
    # Approved on 25 October (Colombo): the 26th onwards stays open.
    db = _approved_on(_db(org="2026-10-31"), 10, 2026, "2026-10-25T04:30:00+00:00")
    response = _send(db, "PUT", "/api/hr/attendance-tracking", json={"tracking_start_date": "2026-10-26"})
    assert response.status_code == 200, response.text


def test_days_up_to_the_approval_date_are_refused_and_the_message_says_from_when():
    db = _approved_on(_db(org="2026-10-31"), 10, 2026, "2026-10-25T04:30:00+00:00")
    response = _send(db, "PUT", "/api/hr/attendance-tracking", json={"tracking_start_date": "2026-10-20"})
    assert response.status_code == 409
    assert "Choose 26 October 2026 or later" in response.json()["detail"]


def test_a_frozen_rest_day_does_not_block_an_earlier_start():
    # November approved on Tue 3 Nov; the span brought in ends on Sun 1 Nov,
    # a rest day, so nothing paid would become an absence.
    db = _approved_on(_db(org="2026-11-02"), 11, 2026, "2026-11-03T06:00:00+00:00")
    body = _send(db, "GET", "/api/hr/attendance-tracking/impact?start=2026-10-26").json()
    assert body["blocked_months"] == []


def test_a_frozen_working_day_still_blocks():
    # Start 3 Nov; moving to 2 Nov brings in Mon 2 Nov, a working day with no
    # clock-in, frozen by the approval on the 3rd.
    db = _approved_on(_db(org="2026-11-03"), 11, 2026, "2026-11-03T06:00:00+00:00")
    response = _send(db, "PUT", "/api/hr/attendance-tracking", json={"tracking_start_date": "2026-11-02"})
    assert response.status_code == 409
    assert "Choose 4 November 2026 or later" in response.json()["detail"]
