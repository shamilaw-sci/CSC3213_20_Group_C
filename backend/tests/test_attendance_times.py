"""HR-entered clock times are Sri Lanka times.

The HR forms sent times like "2026-10-29T08:30:00" with no offset; Postgres
stored them as 08:30 UTC, so they read back as 14:00 in Sri Lanka and worked
hours went wrong when only one end of a record was edited.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api.hr import _compute_worked_hours
from app.core.supabase import get_supabase
from app.main import app
from app.schemas.hr import SRI_LANKA, AttendanceLogCreate, AttendanceLogUpdate
from tests.test_ledger_integrity import _RecordingSupabase
from tests.test_rbac_matrix import _request, acting_as


def test_a_time_without_an_offset_is_sri_lanka_time():
    log = AttendanceLogCreate(employee_id=1, target_date="2026-10-29", clock_in="2026-10-29T08:30:00")
    assert log.model_dump(mode="json")["clock_in"] == "2026-10-29T08:30:00+05:30"


def test_an_explicit_offset_is_kept():
    assert AttendanceLogUpdate(clock_in="2026-10-29T03:00:00Z").clock_in.utcoffset().total_seconds() == 0


def test_worked_hours_subtract_real_instants():
    stored_out = datetime.fromisoformat("2026-10-29T11:30:00+00:00")   # 17:00 in Sri Lanka, as the DB returns it
    new_in = datetime(2026, 10, 29, 8, 30, tzinfo=SRI_LANKA)
    # Stripping timezones gave 11:30 - 08:30 = 3 h. The real answer is 8.5 h.
    assert _compute_worked_hours(new_in, stored_out) == 8.5


def test_overnight_shift_still_wraps():
    assert _compute_worked_hours(datetime(2026, 10, 29, 20, 0), datetime(2026, 10, 29, 4, 0)) == 8.0


def test_hr_logged_times_are_stored_with_the_sri_lanka_offset():
    supabase = _RecordingSupabase({"attendance_log": {"select": [], "insert": [{
        "id": 1, "employee_id": 7, "target_date": "2026-10-29", "clock_in": "2026-10-29T03:00:00+00:00",
        "clock_out": "2026-10-29T11:30:00+00:00", "worked_hours": 8.5, "is_locked": False}]}})
    with acting_as("HR Officer"):
        app.dependency_overrides[get_supabase] = lambda: supabase
        response = _request("POST", "/api/hr/attendance", json={
            "employee_id": 7, "target_date": "2026-10-29",
            "clock_in": "2026-10-29T08:30:00", "clock_out": "2026-10-29T17:00:00"})
    assert response.status_code == 200, response.text
    (written,) = [d for t, d in supabase.inserts if t == "attendance_log"]
    assert written["clock_in"] == "2026-10-29T08:30:00+05:30"
    assert written["worked_hours"] == 8.5
