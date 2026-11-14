# backend/app/services/monthly_report.py
#
# The monthly management report (confirmed 2026-11-13): one month across the
# organisation, for Admin and Director (reports:monthly). Four sections, each
# built from what the app already computes elsewhere, so the PDF can't
# disagree with the pages:
#
#   rescue   case_report() from app/api/rescue_cases.py (the dashboard card)
#   finance  build_finance_report() (Finance > Reports), plus donations
#   people   headcount, joiners, approved leave days, the month's payroll run
#   stock    value on hand, items issued in the month, low and expiring stock
#
# A month is Sri Lanka time. The current month runs to today and is labelled
# "month to date"; a future month is refused by the route.

from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal

from supabase import Client

from app.api.hr import _period
from app.api.inventory import expiring_items, low_stock_items
from app.api.rescue_cases import case_report
from app.schemas.hr import SRI_LANKA
from app.services.finance_reports import _pct_change, build_finance_report, fetch_ledger

# Lists in the PDF stop here; the full lists are on the app's pages.
TOP = 5


def month_bounds(year: int, month: int, today: date) -> tuple[date, date, bool]:
    """(first day, last day counted, to-date?) for a month."""
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    if (year, month) == (today.year, today.month):
        return first, today, True
    return first, last, False


def comparison_bounds(first: date, last: date) -> tuple[date, date]:
    """The previous calendar month, or for a month to date the same days of
    it (1 to 13 Nov compares with 1 to 13 Oct). Finance > Reports compares
    with the window of equal length just before, which straddles two months
    when the period is one."""
    prev_last_of_month = first - timedelta(days=1)
    prev_first = prev_last_of_month.replace(day=1)
    prev_last = prev_first.replace(day=min(last.day, prev_last_of_month.day))
    if last.day == monthrange(last.year, last.month)[1]:
        prev_last = prev_last_of_month  # a whole month: the whole previous month
    return prev_first, prev_last


def _money(value) -> float:
    return float(round(Decimal(str(value or 0)), 2))


def _rescue(supabase: Client, year: int, month: int) -> dict:
    report = case_report(supabase, year, month)
    report["by_outcome"] = [o for o in report["by_outcome"] if o["cases"]]
    return report


def _finance(supabase: Client, first: date, last: date, today: date) -> dict:
    rows = fetch_ledger(supabase, last)
    report = build_finance_report(rows, first, last, today)
    programs = [p for p in report["programs"]["rows"] if p["income"] or p["expense"]]

    prev_first, prev_last = comparison_bounds(first, last)
    current = report["summary"]["current"]
    previous = build_finance_report(rows, prev_first, prev_last, today)["summary"]["current"]
    d = lambda v: Decimal(str(v))  # noqa: E731
    summary = {
        "current": current,
        "previous": previous,
        "change": {
            "income_pct": _pct_change(d(current["income"]), d(previous["income"])),
            "expense_pct": _pct_change(d(current["expense"]), d(previous["expense"])),
        },
    }

    start = datetime.combine(first, datetime.min.time(), SRI_LANKA)
    end = datetime.combine(last + timedelta(days=1), datetime.min.time(), SRI_LANKA)
    donations = (
        supabase.table("donations").select("amount, purpose")
        .eq("status", "paid").gte("paid_at", start.isoformat()).lt("paid_at", end.isoformat())
        .execute().data or []
    )
    return {
        "summary": summary,
        "previous": {"start": prev_first.isoformat(), "end": prev_last.isoformat()},
        "programs": programs[:TOP],
        "more_programs": max(len(programs) - TOP, 0),
        "donations": {
            "count": len(donations),
            "total": _money(sum(Decimal(str(d["amount"])) for d in donations)),
            "program": _money(sum(Decimal(str(d["amount"])) for d in donations if d.get("purpose") == "program")),
            "general": _money(sum(Decimal(str(d["amount"])) for d in donations if d.get("purpose") != "program")),
        },
    }


def _people(supabase: Client, year: int, month: int, first: date, last: date) -> dict:
    employees = supabase.table("employee_profile").select("id, status, date_joined").execute().data or []
    active = [e for e in employees if (e.get("status") or "Active") == "Active"]
    joined = [e for e in active if e.get("date_joined") and first <= date.fromisoformat(str(e["date_joined"])[:10]) <= last]

    days = (
        supabase.table("leave_request_days").select("request_id, fraction")
        .gte("leave_date", first.isoformat()).lte("leave_date", last.isoformat())
        .execute().data or []
    )
    approved = set()
    if days:
        approved = {
            r["id"] for r in (
                supabase.table("leave_requests").select("id")
                .in_("id", sorted({d["request_id"] for d in days})).eq("status", "Approved")
                .execute().data or []
            )
        }
    leave_days = sum(Decimal(str(d["fraction"])) for d in days if d["request_id"] in approved)

    runs = (
        supabase.table("payroll_runs").select("status, total")
        .eq("payroll_month", month).eq("payroll_year", year).execute().data or []
    )
    return {
        "headcount": len(active),
        "joined": len(joined),
        "leave_days": float(leave_days),
        "payroll": {"status": runs[0]["status"], "total": _money(runs[0]["total"])} if runs else None,
    }


def _stock(supabase: Client, first: date, last: date, today: date) -> dict:
    batches = (
        supabase.table("inventory_batches").select("quantity_remaining, unit_cost")
        .gt("quantity_remaining", 0).execute().data or []
    )
    value = sum(Decimal(str(b["quantity_remaining"])) * Decimal(str(b.get("unit_cost") or 0)) for b in batches)

    movements = (
        supabase.table("inventory_transactions")
        .select("transaction_type, total_cost, program_id, rescue_case_id, reverses_id")
        .gte("transaction_date", first.isoformat()).lte("transaction_date", last.isoformat())
        .execute().data or []
    )
    issued = {"programs": Decimal(0), "cases": Decimal(0), "adjustments": Decimal(0)}
    returned = Decimal(0)
    for m in movements:
        cost = Decimal(str(m.get("total_cost") or 0))
        if m.get("transaction_type") == "Issue" and not m.get("reverses_id"):
            bucket = "programs" if m.get("program_id") else "cases" if m.get("rescue_case_id") else "adjustments"
            issued[bucket] += cost
        elif m.get("transaction_type") == "Return":
            # Program returns and reversals of Stock Outs both give value back.
            returned += cost

    low = low_stock_items(supabase)
    expiring = expiring_items(supabase, 30)
    return {
        "value_on_hand": _money(value),
        "issued": {k: _money(v) for k, v in issued.items()},
        "issued_total": _money(sum(issued.values())),
        "returned": _money(returned),
        "low_stock": low[:TOP],
        "low_stock_count": len(low),
        "expired_count": sum(1 for i in expiring if str(i.get("expire_date")) < str(today)),
        "expiring_count": len(expiring),
    }


def build_monthly_report(supabase: Client, year: int, month: int, today: date) -> dict:
    first, last, to_date = month_bounds(year, month, today)
    return {
        "year": year,
        "month": month,
        "period": _period(month, year),
        "first": first.isoformat(),
        "last": last.isoformat(),
        "to_date": to_date,
        "rescue": _rescue(supabase, year, month),
        "finance": _finance(supabase, first, last, today),
        "people": _people(supabase, year, month, first, last),
        "stock": _stock(supabase, first, last, today),
    }
