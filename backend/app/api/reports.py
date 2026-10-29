from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from datetime import date
from supabase import Client

# Internal App Imports
from app.core.supabase import get_supabase
from app.core.security import require_permission
from app.services.reports import generate_pdf, PDFGenerationError
from app.services.finance_reports import (
    build_finance_report,
    fetch_ledger,
    program_label,
    rows_in_period,
)

router = APIRouter()

# A decade of monthly buckets is already 120 rows; past that the request is a
# typo, not a report.
MAX_REPORT_DAYS = 3660


def _validate_period(start_date: date, end_date: date) -> None:
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be on or before end_date.")
    if (end_date - start_date).days > MAX_REPORT_DAYS:
        raise HTTPException(status_code=400, detail="A report can cover at most 10 years.")


# ==========================================
# FINANCE REPORTS
# ==========================================

@router.get("/finance")
async def finance_report(
    start_date: date,
    end_date: date,
    user = Depends(require_permission('finance:read')),
    supabase: Client = Depends(get_supabase)
):
    """
    Income & expenditure, monthly trend, program breakdown, restricted funds
    and outstanding items for one period. The PDF below renders this same
    dict, and the page's CSV exports are written from it.
    """
    _validate_period(start_date, end_date)
    rows = fetch_ledger(supabase, end_date)
    return build_finance_report(rows, start_date, end_date, date.today())


@router.get("/finance/summary")
async def finance_summary_report(
    start_date: date,
    end_date: date,
    user = Depends(require_permission('finance:read')),
    supabase: Client = Depends(get_supabase)
):
    _validate_period(start_date, end_date)
    rows = fetch_ledger(supabase, end_date)
    report = build_finance_report(rows, start_date, end_date, date.today())

    # The PDF also lists the period's transactions, which the page leaves to
    # the ledger. Newest first, voided rows kept and marked as such: an
    # auditor needs to see the reversal, not a gap.
    transactions = sorted(
        rows_in_period(rows, start_date, end_date),
        key=lambda r: (str(r["transaction_date"]), r.get("id") or 0),
        reverse=True,
    )
    for t in transactions:
        t["program_name"] = program_label(t)

    try:
        pdf_bytes = generate_pdf(
            "finance_summary.html",
            {
                "report_title": "Finance Report",
                "period": f"{start_date} to {end_date}",
                "report": report,
                "transactions": transactions,
            },
        )
    except PDFGenerationError as e:
        raise HTTPException(status_code=500, detail=str(e))

    filename = f"finance_report_{start_date}_{end_date}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Add HR / Admin report endpoints below, following the same shape:
#   1. Depends(require_permission(...)), not check_user_role: role-name
#      lists drift from the real role table (see test_rbac_matrix)
#   2. fetch data via supabase (reuse existing RPCs/tables where possible)
#   3. generate_pdf("your_template.html", {...})
#   4. return as Response with Content-Disposition
