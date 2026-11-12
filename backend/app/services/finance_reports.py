"""
Finance report: every figure the reports page, its PDF and its CSV exports
show, computed once.

build_finance_report() is a pure function over ledger rows, so the maths is
testable without a database and the three outputs cannot disagree: the page
renders its JSON, the PDF template renders the same dict, and the CSVs are
written client-side from that JSON.

Money is summed in Decimal and only converted to float on the way out, for
the reason given on RestrictedBalance in app/schemas/finance.py.
"""

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from supabase import Client

from app.services.restricted_funds import _to_decimal, restricted_effect

# Matches the finance overview, which labels expenses with no program the
# same way. Income with no program is unrestricted general funding, so it
# shares the label.
GENERAL_OPERATIONS = "General Operations"

# PostgREST caps a response at 1000 rows by default. A report that silently
# summed the first thousand transactions would be wrong without saying so.
PAGE_SIZE = 1000

# (label, first day, last day); None means open-ended.
AGING_BUCKETS = (
    ("0-30", 0, 30),
    ("31-60", 31, 60),
    ("61-90", 61, 90),
    ("90+", 91, None),
)

ZERO = Decimal("0.00")


_LEDGER_COLUMNS = (
    "id, transaction_date, amount, transaction_type, status, "
    "program_id, is_restricted, programs(program_name)"
)


def _is_missing_source_type_column(error: Exception) -> bool:
    """True when PostgREST refused the select because
    financial_transactions.source_type does not exist yet (migration 013 not
    applied): Postgres 42703 'column ... does not exist'."""
    text = str(error).lower()
    return "source_type" in text and ("42703" in text or "column" in text)


def _is_missing_column(error: Exception, column: str) -> bool:
    text = str(error).lower()
    return column in text and ("42703" in text or "column" in text)


def fetch_ledger(supabase: Client, end: date, *, include_source: bool = False) -> list[dict]:
    """
    Every transaction dated on or before `end`, voided rows included.

    Not just the period: restricted opening balances need everything before
    it, the comparison needs the previous period, and outstanding items can
    date from any time. build_finance_report does the filtering.

    include_source=True also reads source_type (migration 013), for the
    ledger page. Off by default so every other caller sends exactly the
    query it always has. If the column is not there yet, the rows come back
    without it rather than failing.
    """
    if include_source:
        # memo (026) and source_type (013): each falls away if its migration
        # is not applied yet, rather than failing the ledger page.
        try:
            return _fetch_ledger_rows(supabase, end, _LEDGER_COLUMNS + ", source_type, memo")
        except Exception as e:
            if not _is_missing_column(e, "memo"):
                if not _is_missing_source_type_column(e):
                    raise
                return _fetch_ledger_rows(supabase, end, _LEDGER_COLUMNS)
        try:
            return _fetch_ledger_rows(supabase, end, _LEDGER_COLUMNS + ", source_type")
        except Exception as e:
            if not _is_missing_source_type_column(e):
                raise
    return _fetch_ledger_rows(supabase, end, _LEDGER_COLUMNS)


def _fetch_ledger_rows(supabase: Client, end: date, columns: str) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        page = supabase.table("financial_transactions") \
            .select(columns) \
            .lte("transaction_date", str(end)) \
            .order("id") \
            .range(offset, offset + PAGE_SIZE - 1) \
            .execute().data or []
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def previous_period(start: date, end: date) -> tuple[date, date]:
    """
    The period of the same length immediately before [start, end].

    Whole calendar months compare against the same number of whole months,
    so March is compared with February rather than with "the 31 days before
    March 1st", which would start on 29 January. Anything else is compared
    day for day.
    """
    prev_end = start - timedelta(days=1)

    if start.day == 1 and end.day == monthrange(end.year, end.month)[1]:
        months = (end.year - start.year) * 12 + (end.month - start.month) + 1
        index = start.year * 12 + (start.month - 1) - months
        year, month0 = divmod(index, 12)
        return date(year, month0 + 1, 1), prev_end

    days = (end - start).days + 1
    return prev_end - timedelta(days=days - 1), prev_end


def _row_date(row: dict) -> date:
    return date.fromisoformat(str(row["transaction_date"])[:10])


def program_label(row: dict) -> str:
    joined = (row.get("programs") or {}).get("program_name")
    if joined:
        return joined
    if row.get("program_id") is None:
        return GENERAL_OPERATIONS
    return f"Program {row['program_id']}"


def _type(row: dict) -> str:
    return (row.get("transaction_type") or "").lower()


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def _pct_change(current: Decimal, previous: Decimal) -> Optional[float]:
    # No baseline, no percentage: "+inf%" or "+100%" would both mislead.
    if previous == 0:
        return None
    return float(((current - previous) / previous * 100).quantize(Decimal("0.1")))


def _period_totals(rows: list[dict]) -> dict:
    """Income and expenditure for rows already limited to one period."""
    t = {k: ZERO for k in ("income_received", "income_pending", "expense_paid", "expense_unpaid")}

    for row in rows:
        if row.get("status") == "Voided":
            continue
        amount = _to_decimal(row.get("amount"))
        settled = row.get("status") == "Cash"
        if _type(row) == "income":
            t["income_received" if settled else "income_pending"] += amount
        elif _type(row) == "expense":
            t["expense_paid" if settled else "expense_unpaid"] += amount

    income = t["income_received"] + t["income_pending"]
    expense = t["expense_paid"] + t["expense_unpaid"]
    return {
        "income": income,
        "expense": expense,
        "net": income - expense,
        **t,
    }


def _monthly(rows: list[dict], start: date, end: date) -> list[dict]:
    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append({"month": f"{year:04d}-{month:02d}", "income": ZERO, "expense": ZERO})
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)

    by_key = {m["month"]: m for m in months}
    for row in rows:
        if row.get("status") == "Voided":
            continue
        bucket = by_key.get(str(row["transaction_date"])[:7])
        if bucket is None:
            continue
        if _type(row) == "income":
            bucket["income"] += _to_decimal(row.get("amount"))
        elif _type(row) == "expense":
            bucket["expense"] += _to_decimal(row.get("amount"))

    return [
        {
            "month": m["month"],
            "income": _money(m["income"]),
            "expense": _money(m["expense"]),
            "net": _money(m["income"] - m["expense"]),
        }
        for m in months
    ]


def _programs(rows: list[dict]) -> dict:
    by_program: dict = {}
    for row in rows:
        if row.get("status") == "Voided":
            continue
        key = row.get("program_id")
        entry = by_program.setdefault(
            key, {"program_id": key, "program_name": program_label(row), "income": ZERO, "expense": ZERO}
        )
        if _type(row) == "income":
            entry["income"] += _to_decimal(row.get("amount"))
        elif _type(row) == "expense":
            entry["expense"] += _to_decimal(row.get("amount"))

    ordered = sorted(
        by_program.values(),
        key=lambda e: (-e["expense"], -e["income"], e["program_name"]),
    )
    total_income = sum((e["income"] for e in ordered), ZERO)
    total_expense = sum((e["expense"] for e in ordered), ZERO)

    return {
        "rows": [
            {
                "program_id": e["program_id"],
                "program_name": e["program_name"],
                "income": _money(e["income"]),
                "expense": _money(e["expense"]),
                "net": _money(e["income"] - e["expense"]),
            }
            for e in ordered
        ],
        "totals": {
            "income": _money(total_income),
            "expense": _money(total_expense),
            "net": _money(total_income - total_expense),
        },
    }


def _restricted(rows: list[dict], start: date, end: date) -> dict:
    """
    Earmarked funds statement, one row per restricted program.

    Built on restricted_effect, the rule the spend check enforces, so the
    closing balance here is the balance an expense is checked against.
    A program counts as restricted once it has any non-voided restricted
    income, as in is_program_restricted.
    """
    names: dict = {}
    for row in rows:
        if (
            _type(row) == "income"
            and row.get("is_restricted")
            and row.get("status") != "Voided"
            and row.get("program_id") is not None
        ):
            names[row["program_id"]] = program_label(row)

    statement = []
    for program_id, name in sorted(names.items(), key=lambda item: item[1]):
        opening = received = spent = pledged = ZERO
        for row in rows:
            row_date = _row_date(row)
            effect = restricted_effect(row, program_id)
            if row_date < start:
                opening += effect
            elif row_date <= end:
                if effect > 0:
                    received += effect
                else:
                    spent -= effect
                # A pledge is earmarked but not yet spendable; restricted_effect
                # rightly gives it nothing, so it is reported beside the balance.
                if (
                    row.get("program_id") == program_id
                    and _type(row) == "income"
                    and row.get("is_restricted")
                    and row.get("status") == "Receivable"
                ):
                    pledged += _to_decimal(row.get("amount"))

        statement.append({
            "program_id": program_id,
            "program_name": name,
            "opening": opening,
            "received": received,
            "spent": spent,
            "closing": opening + received - spent,
            "pledged": pledged,
        })

    columns = ("opening", "received", "spent", "closing", "pledged")
    return {
        "rows": [
            {
                "program_id": s["program_id"],
                "program_name": s["program_name"],
                **{c: _money(s[c]) for c in columns},
            }
            for s in statement
        ],
        "totals": {c: _money(sum((s[c] for s in statement), ZERO)) for c in columns},
    }


def _outstanding_side(rows: list[dict], as_of: date) -> dict:
    buckets = {label: ZERO for label, _, _ in AGING_BUCKETS}
    items = []
    for row in rows:
        days = max((as_of - _row_date(row)).days, 0)
        amount = _to_decimal(row.get("amount"))
        for label, low, high in AGING_BUCKETS:
            if days >= low and (high is None or days <= high):
                buckets[label] += amount
                break
        items.append({
            "id": row.get("id"),
            "transaction_date": str(row["transaction_date"])[:10],
            "program_name": program_label(row),
            "amount": _money(amount),
            "days": days,
        })

    items.sort(key=lambda i: (-i["days"], -i["amount"]))
    return {
        "total": _money(sum(buckets.values(), ZERO)),
        "count": len(items),
        "buckets": {label: _money(value) for label, value in buckets.items()},
        "items": items,
    }


def _outstanding(rows: list[dict], end: date, today: date) -> dict:
    """
    Receivables and payables that are open NOW and dated on or before `end`.

    The ledger records a settlement by flipping status to Cash, not when it
    happened, so "open as at a past period end" cannot be reconstructed. The
    page says so beside these figures.
    """
    as_of = min(end, today)
    open_rows = [r for r in rows if r.get("status") == "Receivable"]
    return {
        "as_of": str(as_of),
        "receivables": _outstanding_side([r for r in open_rows if _type(r) == "income"], as_of),
        "payables": _outstanding_side([r for r in open_rows if _type(r) == "expense"], as_of),
    }


def rows_in_period(rows: list[dict], start: date, end: date) -> list[dict]:
    return [r for r in rows if start <= _row_date(r) <= end]


def build_finance_report(rows: list[dict], start: date, end: date, today: date) -> dict:
    """
    The whole report for [start, end].

    `rows` must include everything dated on or before `end` (fetch_ledger),
    not just the period. `today` is passed in rather than read so the aging
    figures are testable.
    """
    prev_start, prev_end = previous_period(start, end)
    current_rows = rows_in_period(rows, start, end)

    current = _period_totals(current_rows)
    previous = _period_totals(rows_in_period(rows, prev_start, prev_end))

    return {
        "period": {
            "start": str(start),
            "end": str(end),
            "previous_start": str(prev_start),
            "previous_end": str(prev_end),
        },
        "summary": {
            "current": {k: _money(v) for k, v in current.items()},
            "previous": {k: _money(v) for k, v in previous.items()},
            "change": {
                "income_pct": _pct_change(current["income"], previous["income"]),
                "expense_pct": _pct_change(current["expense"], previous["expense"]),
                # Net can change sign, where a percentage means nothing.
                "net_difference": _money(current["net"] - previous["net"]),
            },
        },
        "monthly": _monthly(current_rows, start, end),
        "programs": _programs(current_rows),
        "restricted": _restricted(rows, start, end),
        "outstanding": _outstanding(rows, end, today),
    }


def finance_snapshot(rows: list[dict], today: date) -> dict:
    """
    The three headline figures on the finance Overview and dashboards.

    Replaces the get_finance_summary RPC, whose SQL is not in this repo and
    which counted voided expenses, and every month's, as "monthly
    expenses": on real data it reported 883,257 when this month's spend
    was 50,000.

    cash_available    received income minus paid expenses, all time
    receivables       income still to be received, all time
    monthly_expenses  expenses dated this calendar month, paid or not,
                      the same figure as this month in the Reports trend
    Voided rows count toward none of them.
    """
    cash = receivables = month_expenses = ZERO
    this_month = f"{today.year:04d}-{today.month:02d}"

    for row in rows:
        if row.get("status") == "Voided":
            continue
        amount = _to_decimal(row.get("amount"))
        kind = _type(row)
        settled = row.get("status") == "Cash"

        if settled and kind == "income":
            cash += amount
        elif settled and kind == "expense":
            cash -= amount
        elif kind == "income":
            receivables += amount

        if kind == "expense" and str(row["transaction_date"])[:7] == this_month:
            month_expenses += amount

    return {
        "cash_available": _money(cash),
        "receivables": _money(receivables),
        "monthly_expenses": _money(month_expenses),
    }
