"""
Whether a month's attendance is frozen, and through which day.

Two things freeze it: an approved payroll (days up to the approval date) and
a closed month (the whole month, until HR reopens it). Attendance edits,
correction requests, leave and the tracking start all check is_frozen().
"""

import calendar
from datetime import date, datetime, timezone
from typing import Optional

from supabase import Client

from app.services.work_calendar import COLOMBO


def _approved_run(supabase: Client, month: int, year: int) -> Optional[dict]:
    runs = supabase.table("payroll_runs").select("id, status, payroll_month, payroll_year, approved_at") \
        .eq("payroll_month", month).eq("payroll_year", year).execute().data or []
    return next((r for r in runs if r.get("status") == "Approved"
                 and r.get("payroll_month") == month and r.get("payroll_year") == year), None)


def payroll_approved(supabase: Client, month: int, year: int) -> bool:
    return _approved_run(supabase, month, year) is not None


def _month_end(month: int, year: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def payroll_frozen_through(supabase: Client, month: int, year: int) -> Optional[date]:
    """
    The last day of the month that an approved payroll freezes, or None if
    the month's payroll isn't approved.

    Days up to the approval date are frozen; later days in the same month
    stay open (confirmed 2026-11-12). Payroll can be approved from the 25th,
    and freezing the whole month refused a sick day on the 28th. Approved
    after the month ended, the whole month is frozen.
    """
    run = _approved_run(supabase, month, year)
    if run is None:
        return None
    month_end = _month_end(month, year)
    approved_at = run.get("approved_at")
    if not approved_at:
        return month_end
    at = datetime.fromisoformat(str(approved_at).replace("Z", "+00:00"))
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return min(at.astimezone(COLOMBO).date(), month_end)


def month_close(supabase: Client, month: int, year: int) -> Optional[dict]:
    """The month's close (migration 029) if it is currently Closed."""
    try:
        rows = supabase.table("attendance_month_closes").select("*") \
            .eq("close_month", month).eq("close_year", year).execute().data or []
    except Exception as e:
        text = str(e).lower()
        if "attendance_month_closes" in text and any(
                k in text for k in ("42p01", "pgrst205", "does not exist", "could not find the table")):
            return None  # before 029: no month is closed
        raise
    return next((r for r in rows if r.get("status") == "Closed"
                 and r.get("close_month") == month and r.get("close_year") == year), None)


def frozen_through(supabase: Client, month: int, year: int) -> Optional[date]:
    """The last frozen day of the month: all of it if closed, else up to a payroll approval."""
    if month_close(supabase, month, year):
        return _month_end(month, year)
    return payroll_frozen_through(supabase, month, year)


def is_frozen(supabase: Client, d: date, _cache: Optional[dict] = None) -> Optional[date]:
    """The month's frozen-through date if `d` is frozen, else None."""
    key = (d.year, d.month)
    if _cache is not None and key in _cache:
        through = _cache[key]
    else:
        through = frozen_through(supabase, d.month, d.year)
        if _cache is not None:
            _cache[key] = through
    return through if through is not None and d <= through else None
