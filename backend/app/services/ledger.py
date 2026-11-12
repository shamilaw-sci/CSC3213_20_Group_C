"""
The general ledger: every transaction, filtered, totalled, sorted, paged,
with a running balance.

build_ledger_page() is pure over ledger rows, like build_finance_report, and
reuses its row helpers so a program is named the same way on both pages.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from app.services.finance_reports import ZERO, _money, _row_date, _type, program_label
from app.services.restricted_funds import _to_decimal

# Sentinel for the program filter: rows charged to no program.
GENERAL = "general"

# How each financial_transactions.source_type (migration 013) is named on the
# ledger. A row read before that migration has no source_type; the column's
# default is 'manual', so it is shown as Manual.
SOURCE_LABELS = {
    "donation": "Donation",
    "stock_in": "Stock in",
    "payroll": "Payroll",
    "manual": "Manual",
}
DEFAULT_SOURCE = "manual"


def source_type(row: dict) -> str:
    return row.get("source_type") or DEFAULT_SOURCE


def describe(row: dict) -> str:
    """
    The ledger's Description column: "<Source>-<Program>", for example
    "Donation-Distemper outbreak", or "<Source>-General" when the row is
    charged to no program, for example "Stock in-General".
    """
    source = source_type(row)
    label = SOURCE_LABELS.get(source, source.replace("_", " ").capitalize())
    # A memo (migration 026) says which entry this is when one source posts
    # several at once: payroll's net salaries, EPF and ETF payables.
    if row.get("memo"):
        return f"{label}-{row['memo']}"
    program = "General" if row.get("program_id") is None else program_label(row)
    return f"{label}-{program}"


def _signed(row: dict) -> Decimal:
    """What a row does to the balance: income adds, expense subtracts."""
    if row.get("status") == "Voided":
        return ZERO
    amount = _to_decimal(row.get("amount"))
    return amount if _type(row) == "income" else -amount if _type(row) == "expense" else ZERO


def _matches_search(row: dict, q: str) -> bool:
    """
    Free-text match. Search covers what a row carries: program, its
    Description (source and program, e.g. "Stock in-General"), type, status,
    id ("#12") and amount, with or without thousands separators.
    """
    needle = q.strip().lower()
    if not needle:
        return True
    if needle.startswith("#"):
        return str(row.get("id")) == needle[1:]

    amount = f"{_to_decimal(row.get('amount')):.2f}"
    haystack = " ".join([
        program_label(row).lower(),
        describe(row).lower(),
        _type(row),
        (row.get("status") or "").lower(),
        "restricted" if row.get("is_restricted") else "",
        amount,
        f"{_to_decimal(row.get('amount')):,.2f}",
    ])
    return needle.replace(",", "") in amount or needle in haystack


def build_ledger_page(
    rows: list[dict],
    *,
    start: Optional[date] = None,
    end: Optional[date] = None,
    tx_type: Optional[str] = None,
    status: Optional[str] = None,
    program: Optional[str] = None,
    restricted: Optional[bool] = None,
    q: Optional[str] = None,
    newest_first: bool = True,
    page: int = 1,
    page_size: int = 50,
    everything: bool = False,
) -> dict:
    """
    One page of the ledger.

    `balance` on each row is the ledger-wide running net (income minus
    expense, pending included, voided excluded) after that entry, in date
    order. It is computed over ALL rows before filtering, so a filtered view
    still shows each entry's true position rather than a subtotal of
    whatever the filter happened to keep. Voided rows have no balance.

    `totals` cover every row the filters match, not just this page.
    """
    chronological = sorted(rows, key=lambda r: (_row_date(r), r.get("id") or 0))

    balance = ZERO
    enriched = []
    for row in chronological:
        voided = row.get("status") == "Voided"
        balance += _signed(row)
        enriched.append({
            "id": row.get("id"),
            "transaction_date": str(row["transaction_date"])[:10],
            "amount": _money(_to_decimal(row.get("amount"))),
            "transaction_type": row.get("transaction_type"),
            "status": row.get("status"),
            "program_id": row.get("program_id"),
            "program_name": program_label(row),
            "source_type": source_type(row),
            "description": describe(row),
            "is_restricted": bool(row.get("is_restricted")),
            "balance": None if voided else _money(balance),
            "_row": row,
        })

    def keep(e: dict) -> bool:
        row = e["_row"]
        d = _row_date(row)
        if start and d < start:
            return False
        if end and d > end:
            return False
        if tx_type and _type(row) != tx_type.lower():
            return False
        if status and row.get("status") != status:
            return False
        if program == GENERAL and row.get("program_id") is not None:
            return False
        if program not in (None, GENERAL) and str(row.get("program_id")) != program:
            return False
        if restricted is not None and bool(row.get("is_restricted")) != restricted:
            return False
        if q and not _matches_search(row, q):
            return False
        return True

    matched = [e for e in enriched if keep(e)]

    # _signed is already zero for voided rows, so they drop out of the totals.
    income = sum((_signed(e["_row"]) for e in matched if _type(e["_row"]) == "income"), ZERO)
    expense = sum((-_signed(e["_row"]) for e in matched if _type(e["_row"]) == "expense"), ZERO)

    if newest_first:
        matched.reverse()

    total = len(matched)
    if everything:
        page, pages, window = 1, 1, matched
    else:
        pages = max(1, -(-total // page_size))
        page = min(max(page, 1), pages)
        window = matched[(page - 1) * page_size: page * page_size]

    return {
        "rows": [{k: v for k, v in e.items() if k != "_row"} for e in window],
        "total": total,
        "page": page,
        "pages": pages,
        "page_size": len(window) if everything else page_size,
        "totals": {
            "income": _money(income),
            "expense": _money(expense),
            "net": _money(income - expense),
        },
    }
