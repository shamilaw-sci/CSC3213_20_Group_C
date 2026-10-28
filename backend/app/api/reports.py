from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from datetime import date
from supabase import Client

# Internal App Imports
from app.core.supabase import get_supabase
from app.core.security import require_permission
from app.services.reports import generate_pdf, PDFGenerationError

router = APIRouter()


# ==========================================
# FINANCE REPORTS
# ==========================================

@router.get("/finance/summary")
async def finance_summary_report(
    start_date: date,
    end_date: date,
    user = Depends(require_permission('finance:read')),
    supabase: Client = Depends(get_supabase)
):
    # Same source as get_transactions/monthly_summary — a date-ranged
    # query against financial_transactions, since get_finance_summary()
    # is an all-time snapshot and doesn't accept a date range.
    response = supabase.table("financial_transactions") \
        .select("*") \
        .gte("transaction_date", str(start_date)) \
        .lte("transaction_date", str(end_date)) \
        .order("transaction_date", desc=True) \
        .execute()

    transactions = response.data or []

    total_income = sum(
        t["amount"] for t in transactions
        if t["transaction_type"].lower() == "income" and t["status"] != "Voided"
    )
    total_expense = sum(
        t["amount"] for t in transactions
        if t["transaction_type"].lower() == "expense" and t["status"] != "Voided"
    )

    try:
        pdf_bytes = generate_pdf(
            "finance_summary.html",
            {
                "report_title": "Finance Summary Report",
                "period": f"{start_date} to {end_date}",
                "transactions": transactions,
                "total_income": total_income,
                "total_expense": total_expense,
                "net_balance": total_income - total_expense,
            },
        )
    except PDFGenerationError as e:
        raise HTTPException(status_code=500, detail=str(e))

    filename = f"finance_summary_{start_date}_{end_date}.pdf"
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