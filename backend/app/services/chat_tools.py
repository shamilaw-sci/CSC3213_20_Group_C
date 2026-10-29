from calendar import monthrange
from datetime import date
from decimal import Decimal
from supabase import Client

from app.services.finance_reports import fetch_ledger, finance_snapshot
from app.services.restricted_funds import compute_restricted_balance

# ---------- implementations ----------

def get_finance_summary(supabase: Client) -> dict:
    """Current cash position: the same figures as the finance Overview."""
    return finance_snapshot(fetch_ledger(supabase, date.max), date.today())


def get_monthly_summary(supabase: Client, year: int, month: int) -> dict:
    _, last_day = monthrange(year, month)
    rows = supabase.table("financial_transactions") \
        .select("amount, transaction_type, status") \
        .gte("transaction_date", str(date(year, month, 1))) \
        .lte("transaction_date", str(date(year, month, last_day))) \
        .execute().data or []

    live = [t for t in rows if t.get("status") != "Voided"]
    income = sum(float(t["amount"]) for t in live
                 if t["transaction_type"].lower() == "income")
    expense = sum(float(t["amount"]) for t in live
                  if t["transaction_type"].lower() == "expense")
    return {"year": year, "month": month, "income": income,
            "expense": expense, "balance": income - expense}


def get_aging_summary(supabase: Client) -> dict:
    from datetime import datetime
    rows = supabase.table("financial_transactions") \
        .select("transaction_date, amount") \
        .eq("status", "Receivable").execute().data or []
    today = datetime.now().date()
    buckets = {"0-30": 0.0, "31-60": 0.0, "61+": 0.0}
    for t in rows:
        days = (today - datetime.strptime(t["transaction_date"], "%Y-%m-%d").date()).days
        key = "0-30" if days <= 30 else "31-60" if days <= 60 else "61+"
        buckets[key] += float(t["amount"])
    return buckets


def list_programs(supabase: Client) -> list:
    return supabase.table("programs").select("*").execute().data or []


def get_restricted_fund_balance(supabase: Client, program_id: int) -> dict:
    """Earmarked funds position for one program — same helper the finance API uses."""
    balance = compute_restricted_balance(supabase, program_id)
    # Decimal is not JSON-serializable, and this dict is serialized straight
    # into the tool-call result the model reads.
    return {k: float(v) if isinstance(v, Decimal) else v for k, v in balance.items()}


# ---------- schemas ----------

def _fn(name, desc, props=None, required=None):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object",
                       "properties": props or {},
                       "required": required or []}}}

URGENT_CASES_LIMIT = 10
_CASE_COLUMNS = ("id, animal_type, urgency, urgency_reason, urgency_source, "
                 "status, description, reported_at")


def list_urgent_cases(supabase: Client) -> dict:
    """Unresolved cases for 'what needs attention' questions.

    Two lists, because a fail-soft default is an UNKNOWN urgency, not a Medium
    one. Ranked by urgency alongside real classifications, a severe case whose
    classification failed sank below the cut and the model never saw it.

      needs_manual_review  every unresolved default_* case, uncapped, fetched
                           by its own query so neither the top-N cut nor the
                           PostgREST row limit can drop one.
      ranked_cases         the rest — 'ai' and legacy null-source rows — top
                           URGENT_CASES_LIMIT by urgency.

    The totals and `truncated` are there so the model knows what it was NOT
    given. Handed a bare top-10, it answered "no" to "are there cases that
    couldn't be assessed?" with one sitting at position 11.
    """
    review = supabase.table("rescue_cases") \
        .select(_CASE_COLUMNS) \
        .neq("status", "Resolved") \
        .like("urgency_source", "default_%") \
        .order("reported_at", desc=False) \
        .execute().data or []
    for r in review:
        r["needs_manual_review"] = True

    unresolved = supabase.table("rescue_cases") \
        .select(_CASE_COLUMNS, count="exact") \
        .neq("status", "Resolved") \
        .execute()
    # The exact count, not len(data): data is capped by PostgREST's max-rows.
    total_unresolved = unresolved.count if unresolved.count is not None else len(unresolved.data or [])

    review_ids = {r["id"] for r in review}
    ranked = [r for r in (unresolved.data or []) if r["id"] not in review_ids]
    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    ranked.sort(key=lambda r: order.get(r["urgency"], 4))

    ranked_total = total_unresolved - len(review)
    shown = ranked[:URGENT_CASES_LIMIT]

    return {
        "total_unresolved": total_unresolved,
        "needs_manual_review_count": len(review),
        "needs_manual_review": review,
        "ranked_cases_total": ranked_total,
        "ranked_cases_shown": len(shown),
        "truncated": ranked_total > len(shown),
        "ranked_cases": shown,
    }

TOOLS = {
    "get_finance_summary": {
        "permission": "finance:read",
        "impl": get_finance_summary,
        "schema": _fn("get_finance_summary",
                      "Current cash available, receivables, and monthly expenses. "
                      "Use for 'how much money do we have' questions."),
    },
    "get_monthly_summary": {
        "permission": "finance:read",
        "impl": get_monthly_summary,
        "schema": _fn("get_monthly_summary",
                      "Income, expenses, and net balance for one calendar month. "
                      "Excludes voided transactions.",
                      {"year": {"type": "integer"},
                       "month": {"type": "integer", "description": "1-12"}},
                      ["year", "month"]),
    },
    "get_aging_summary": {
        "permission": "finance:read",
        "impl": get_aging_summary,
        "schema": _fn("get_aging_summary",
                      "Outstanding receivables bucketed by age: 0-30, 31-60, 61+ days."),
    },
    "get_restricted_fund_balance": {
        "permission": "finance:read",
        "impl": get_restricted_fund_balance,
        "schema": _fn("get_restricted_fund_balance",
                      "Earmarked (restricted) donation funds for one program: amount "
                      "raised, amount spent against it, and remaining. Use for "
                      "'how much restricted money is left for X' questions.",
                      {"program_id": {"type": "integer",
                                      "description": "Program id, from list_programs"}},
                      ["program_id"]),
    },
    "list_programs": {
        "permission": "programs:read",
        "impl": list_programs,
        "schema": _fn("list_programs", "All programs VFF runs."),
    },
    "list_urgent_cases": {
        "permission": "rescue:read",
        "impl": list_urgent_cases,
        "schema": _fn("list_urgent_cases",
                      "Unresolved rescue cases. Use for 'what's most urgent', 'what "
                      "needs attention', or 'which cases couldn't be assessed' questions. "
                      "needs_manual_review lists EVERY unresolved case whose urgency "
                      "could not be classified (urgency_source 'default_*'); their "
                      "'Medium' is a placeholder, not an assessment, and any of them "
                      "may be severe. Always call these out explicitly as needing "
                      "manual review, before or alongside the ranked list — never "
                      "rank them as Medium or leave them out. "
                      "ranked_cases holds the top classified cases (Critical first); "
                      "urgency_reason explains each. Null urgency_source means the "
                      "case predates reasons being recorded. "
                      "If truncated is true, more ranked cases exist than were "
                      "returned: use total_unresolved for counts, and make no claims "
                      "about cases you were not given."),
    },
}