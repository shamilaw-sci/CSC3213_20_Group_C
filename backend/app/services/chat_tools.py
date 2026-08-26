from calendar import monthrange
from datetime import date
from supabase import Client

# ---------- implementations ----------

def get_finance_summary(supabase: Client) -> dict:
    """Current cash position — same RPC the finance dashboard uses."""
    return supabase.rpc("get_finance_summary", {}).execute().data


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


# ---------- schemas ----------

def _fn(name, desc, props=None, required=None):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object",
                       "properties": props or {},
                       "required": required or []}}}


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
    "list_programs": {
        "permission": "programs:read",
        "impl": list_programs,
        "schema": _fn("list_programs", "All programs VFF runs."),
    },
}