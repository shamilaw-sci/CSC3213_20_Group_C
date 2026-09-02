"""
Restricted (earmarked) fund accounting.

Implemented in Python against a plain table select, following get_aging_summary
rather than get_finance_summary. Those two "existing patterns" diverge, and the
divergence is not cosmetic: get_finance_summary calls an RPC whose SQL body
exists nowhere in this repository — db/init.sql defines only
generate_monthly_payroll — so it cannot be reviewed in a diff, and the test
suite's stubbed Supabase client cannot exercise it. A rule that decides whether
spending is allowed should be readable by the people it governs, so it lives
here.

This module is imported by BOTH the finance API and the chatbot tool. That is
deliberate: get_aging_summary is currently implemented twice, once in
app/api/finance.py and once in app/services/chat_tools.py, and the two copies
can silently disagree. One definition, two callers.
"""

from decimal import Decimal
from supabase import Client


def _to_decimal(value) -> Decimal:
    """
    Supabase hands DECIMAL columns back as floats or strings depending on the
    driver path. str() first, so a float that arrived as 0.1 does not become
    0.1000000000000000055511151231257827 the moment it is compared against a
    spending limit.
    """
    return Decimal(str(value if value is not None else 0))


def compute_restricted_balance(supabase: Client, program_id: int) -> dict:
    """
    Earmarked funds position for one program.

    raised    Income rows for this program flagged is_restricted, status Cash.
              Receivable is excluded on purpose: a pledge that has not arrived
              is not money that can be spent, and counting it would let a
              promise authorize a real payment. Voided is excluded because a
              reversed donation was never raised.
    spent     ALL Expense rows against this program, excluding Voided —
              is_restricted is not consulted. An expense charged to a
              restricted program draws down that program's earmarked money
              first, whether or not whoever booked it said so.
    remaining raised - spent. May go negative: a program can already be
              overdrawn from expenses booked before this feature existed, and
              reporting that as 0 would hide it.
    """
    rows = supabase.table("financial_transactions") \
        .select("amount, transaction_type, status, is_restricted") \
        .eq("program_id", program_id) \
        .neq("status", "Voided") \
        .execute().data or []

    raised = Decimal("0.00")
    spent = Decimal("0.00")

    for row in rows:
        amount = _to_decimal(row.get("amount"))
        # .lower() matches the defensive casing already used by
        # monthly_summary; the DB CHECK constrains these values, but the
        # comparison costs nothing.
        tx_type = (row.get("transaction_type") or "").lower()

        if tx_type == "income":
            if row.get("is_restricted") and row.get("status") == "Cash":
                raised += amount
        elif tx_type == "expense":
            spent += amount

    return {
        "program_id": program_id,
        "raised": raised,
        "spent": spent,
        "remaining": raised - spent,
    }


def is_program_restricted(supabase: Client, program_id: int) -> bool:
    """
    True if this program has ever received restricted income.

    Enforcement is scoped to programs that actually hold earmarked money.
    Without this, the first expense against an ordinary unrestricted program
    would be blocked for exceeding a restricted balance of zero, which would
    make every unrestricted program unspendable.
    """
    rows = supabase.table("financial_transactions") \
        .select("id") \
        .eq("program_id", program_id) \
        .eq("transaction_type", "Income") \
        .eq("is_restricted", True) \
        .neq("status", "Voided") \
        .limit(1) \
        .execute().data or []

    return bool(rows)
