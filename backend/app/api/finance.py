from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from datetime import date
from calendar import monthrange
from supabase import Client

# Internal App Imports
from app.core.supabase import get_supabase
from app.core.security import require_permission
from app.core.permissions import has_permission
from app.core.audit import log_audit_action
from app.services.restricted_funds import (
    compute_restricted_balance,
    is_program_restricted,
)
from app.schemas.finance import (
    FinancialTransaction,
    FinancialTransactionCreate,
    Program,
    ProgramCreate,
    RestrictedBalance,
)

router = APIRouter()

# ==========================================
# 1. TRANSACTIONS (The Immutable Ledger)
# ==========================================

@router.get("/transactions", response_model=List[FinancialTransaction])
async def get_transactions(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    user = Depends(require_permission('finance:read')), # SECURED
    supabase: Client = Depends(get_supabase)
):
    query = supabase.table("financial_transactions").select("*, programs(program_name)")

    if start_date:
        query = query.gte("transaction_date", str(start_date))
    if end_date:
        query = query.lte("transaction_date", str(end_date))

    response = query.order("transaction_date", desc=True).execute()
    return response.data or []


@router.post("/transactions", response_model=FinancialTransaction)
async def create_transaction(
    transaction: FinancialTransactionCreate,
    override_restricted: bool = False,
    user = Depends(require_permission('finance:write')),
    supabase: Client = Depends(get_supabase)
):
    if transaction.amount <= 0:
        raise HTTPException(status_code=400, detail="Transaction amount must be strictly positive.")

    # Restricted-fund drawdown check.
    #
    # Only Expense rows charged to a program can overspend earmarked money, and
    # only for programs that actually hold some — see is_program_restricted for
    # why an unrestricted program must not be gated on a zero balance. A Voided
    # row is not a real payment, so it is not checked.
    if (
        transaction.transaction_type == "Expense"
        and transaction.program_id is not None
        and transaction.status != "Voided"
        and is_program_restricted(supabase, transaction.program_id)
    ):
        balance = compute_restricted_balance(supabase, transaction.program_id)
        remaining = balance["remaining"]

        if transaction.amount > remaining:
            shortfall = transaction.amount - remaining
            may_override = has_permission(
                (user.get("roles") or {}).get("role_name") or "",
                'finance:restricted:override',
            )

            if not override_restricted:
                # Blocked rather than silently allowed. The message names the
                # exact shortfall so the officer can either reduce the expense
                # or seek authorization, and states whether this user is able
                # to authorize it themselves.
                remedy = (
                    "Resubmit with override_restricted=true to authorize this overspend."
                    if may_override
                    else "Authorization from a user holding finance:restricted:override is required."
                )
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Expense of {transaction.amount} exceeds the restricted funds "
                        f"remaining for program {transaction.program_id} by {shortfall}. "
                        f"Raised: {balance['raised']}, already spent: {balance['spent']}, "
                        f"remaining: {remaining}. {remedy}"
                    ),
                )

            if not may_override:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Insufficient permissions. Overspending restricted program "
                        "funds requires finance:restricted:override."
                    ),
                )

            # The audit row is written BEFORE the expense, and a failure to
            # write it aborts the request.
            #
            # log_audit_action is fail-soft everywhere else, which is right when
            # it records something that already happened. Here it IS the
            # control: an override is authorized by being recorded. Inserting
            # first and logging after would mean a dropped audit row leaves an
            # unrecorded overspend in the ledger. Ordered this way, the only
            # failure mode is an override logged for an expense that then
            # failed to insert — over-recording, which is reviewable, rather
            # than under-recording, which is not.
            logged = await log_audit_action(
                supabase,
                user_id=user["id"],
                action_type="FINANCE_RESTRICTED_OVERRIDE",
                table_name="financial_transactions",
                old_payload=None,
                # Not a row diff. Follows PAYROLL_GENERATE_FINANCE below, which
                # already packs synthetic detail into new_payload. compute_hash
                # covers new_payload, so these figures are chain-protected.
                #
                # Money is recorded as a decimal STRING, never a float. A float
                # here silently breaks verification forever: canonicalize()
                # leaves 8000.0 as a float, but JSONB returns whole numbers as
                # 8000, so the digest computed on insert can never be
                # reproduced on read. Decimal serializes via compute_hash's
                # default=str to "8000.00", which survives the round trip
                # unchanged and keeps exact precision as a bonus.
                new_payload={
                    "program_id": transaction.program_id,
                    "shortfall_amount": shortfall,
                    "attempted_amount": transaction.amount,
                    "restricted_raised": balance["raised"],
                    "restricted_spent": balance["spent"],
                    "restricted_remaining": remaining,
                    "authorized_by": str(user["id"]),
                },
            )

            if not logged:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Override could not be recorded to the audit log and was "
                        "therefore not applied. No transaction was created."
                    ),
                )

    data = transaction.model_dump()
    data["transaction_date"] = str(data["transaction_date"])  # 👈 ADD THIS
    data["amount"] = float(data["amount"])                    # 👈 AND THIS (for Decimal)

    response = supabase.table("financial_transactions").insert(data).execute()

    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create transaction")

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="FINANCE_TRANSACTION_CREATE",
        table_name="financial_transactions",
        old_payload=None,
        new_payload=response.data[0],
    )

    return response.data[0]


@router.get("/transactions/type/{transaction_type}")
async def get_transactions_by_type(
    transaction_type: str,
    user = Depends(require_permission('finance:read')), # SECURED
    supabase: Client = Depends(get_supabase)
):
    transaction_type = transaction_type.capitalize()

    response = supabase.table("financial_transactions") \
        .select("*") \
        .eq("transaction_type", transaction_type) \
        .execute()

    return response.data or []

@router.put("/transactions/{transaction_id}", response_model=FinancialTransaction)
async def update_transaction(
    transaction_id: int,
    transaction: FinancialTransactionCreate,
    user = Depends(require_permission('finance:write')),
    supabase: Client = Depends(get_supabase)
):
    if transaction.amount <= 0:
        raise HTTPException(status_code=400, detail="Transaction amount must be strictly positive.")

    data = transaction.model_dump()
    data["transaction_date"] = str(data["transaction_date"])
    data["amount"] = float(data["amount"])

    # Read the row before overwriting it — an amount change is exactly the kind
    # of edit the audit trail exists to make provable.
    existing = supabase.table("financial_transactions") \
        .select("*") \
        .eq("id", transaction_id) \
        .execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Transaction not found")

    response = supabase.table("financial_transactions") \
        .update(data) \
        .eq("id", transaction_id) \
        .execute()

    if not response.data:
        raise HTTPException(status_code=404, detail="Transaction not found")

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="FINANCE_TRANSACTION_UPDATE",
        table_name="financial_transactions",
        old_payload=existing.data[0],
        new_payload=response.data[0],
    )

    return response.data[0]


@router.patch("/transactions/{transaction_id}/void", response_model=FinancialTransaction)
async def void_transaction(
    transaction_id: int,
    user = Depends(require_permission('finance:write')),
    supabase: Client = Depends(get_supabase)
):
    # Check it exists and isn't already voided
    existing = supabase.table("financial_transactions") \
        .select("*") \
        .eq("id", transaction_id) \
        .single() \
        .execute()

    if not existing.data:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if existing.data.get("status") == "Voided":
        raise HTTPException(status_code=400, detail="Transaction is already voided")

    response = supabase.table("financial_transactions") \
        .update({"status": "Voided"}) \
        .eq("id", transaction_id) \
        .execute()

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="FINANCE_TRANSACTION_VOID",
        table_name="financial_transactions",
        old_payload=existing.data,
        new_payload=response.data[0],
    )

    return response.data[0]

@router.patch("/transactions/{transaction_id}/settle", response_model=FinancialTransaction)
async def settle_transaction(
    transaction_id: int,
    user = Depends(require_permission('finance:write')),
    supabase: Client = Depends(get_supabase)
):
    existing = supabase.table("financial_transactions") \
        .select("*") \
        .eq("id", transaction_id) \
        .single() \
        .execute()

    if not existing.data:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if existing.data.get("status") == "Cash":
        raise HTTPException(status_code=400, detail="Transaction is already settled")

    response = supabase.table("financial_transactions") \
        .update({"status": "Cash"}) \
        .eq("id", transaction_id) \
        .execute()

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="FINANCE_TRANSACTION_SETTLE",
        table_name="financial_transactions",
        old_payload=existing.data,
        new_payload=response.data[0],
    )

    return response.data[0]


# ==========================================
# 2. PROGRAMS
# ==========================================

@router.get("/programs", response_model=List[Program])
async def get_programs(
    user = Depends(require_permission('programs:read')), # SECURED
    supabase: Client = Depends(get_supabase)
):
    response = supabase.table("programs").select("*").execute()
    return response.data or []


@router.post("/programs", response_model=Program)
async def create_program(
    program: ProgramCreate,
    user = Depends(require_permission('programs:manage')), # SECURED
    supabase: Client = Depends(get_supabase)
):
    response = supabase.table("programs").insert(program.model_dump()).execute()

    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create program")

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="PROGRAM_CREATE",
        table_name="programs",
        old_payload=None,
        new_payload=response.data[0],
    )

    return response.data[0]


@router.get("/programs/{program_id}/restricted-balance", response_model=RestrictedBalance)
async def get_program_restricted_balance(
    program_id: int,
    user = Depends(require_permission('finance:read')),
    supabase: Client = Depends(get_supabase)
):
    """
    Earmarked funds raised, spent, and remaining for one program.

    Gated on finance:read rather than programs:read: this reports money, and
    Staff hold programs:read but no view of the ledger.
    """
    program = supabase.table("programs") \
        .select("id") \
        .eq("id", program_id) \
        .execute()

    if not program.data:
        raise HTTPException(status_code=404, detail="Program not found")

    return compute_restricted_balance(supabase, program_id)


# ==========================================
# 3. FINANCIAL SUMMARIES (Optimized)
# ==========================================

@router.get("/summary")
async def get_financial_summary(
    user = Depends(require_permission('finance:read')),
    supabase: Client = Depends(get_supabase)
):
    response = supabase.rpc("get_finance_summary", {}).execute()

    # RPC already returns {"cash_available": ..., "receivables": ..., "monthly_expenses": ...}
    return response.data

@router.get("/aging")
async def get_aging_summary(
    user = Depends(require_permission('finance:read')),
    supabase: Client = Depends(get_supabase)
):
    response = supabase.table("financial_transactions") \
        .select("*") \
        .eq("status", "Receivable") \
        .execute()
    
    transactions = response.data or []
    from datetime import datetime
    today = datetime.now().date()
    
    aging = {
        "0-30": 0,
        "31-60": 0,
        "61+": 0
    }
    
    for t in transactions:
        t_date = datetime.strptime(t["transaction_date"], "%Y-%m-%d").date()
        days = (today - t_date).days
        amt = float(t["amount"])
        
        if days <= 30:
            aging["0-30"] += amt
        elif days <= 60:
            aging["31-60"] += amt
        else:
            aging["61+"] += amt
            
    return aging


@router.get("/summary/monthly")
async def monthly_summary(
    month: int,
    year: int,
    user = Depends(require_permission('finance:read')), # SECURED
    supabase: Client = Depends(get_supabase)
):
    # Big-O Optimization: Database-level filtering
    _, last_day = monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)

    response = supabase.table("financial_transactions") \
        .select("amount, transaction_type") \
        .gte("transaction_date", str(start_date)) \
        .lte("transaction_date", str(end_date)) \
        .neq("status", "Voided") \
        .execute()

    transactions = response.data or []

    total_income = sum(
        float(t["amount"]) for t in transactions
        if t["transaction_type"].lower() == "income"
    )
    total_expense = sum(
        float(t["amount"]) for t in transactions
        if t["transaction_type"].lower() == "expense"
    )

    return {
        "month": month,
        "year": year,
        "income": total_income,
        "expense": total_expense,
        "balance": total_income - total_expense
    }


# ==========================================
# 4. CROSS-MODULE PAYROLL ENGINE
# ==========================================

@router.post("/calculate-payroll/{year}/{month}")
async def calculate_monthly_payroll(
    year: int,
    month: int,
    user = Depends(require_permission('payroll:generate')), # SECURED
    supabase: Client = Depends(get_supabase)
):
    # 1. Date boundaries
    _, last_day = monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)

    # 2. Fetch LOCKED HR attendance logs + base salary (Cross-Module DB Join)
    attendance_response = supabase.table("attendance_logs") \
        .select("employee_id, worked_hours, employee_profiles(base_salary)") \
        .gte("target_date", str(start_date)) \
        .lte("target_date", str(end_date)) \
        .eq("is_locked", True) \
        .execute()

    if not attendance_response.data:
        raise HTTPException(status_code=404, detail="No locked attendance records found for this month.")

    # 3. Aggregate hours and calculate pay
    payroll_data = {}
    for log in attendance_response.data:
        emp_id = log["employee_id"]
        hours = float(log.get("worked_hours", 0))
        base_rate = float(log["employee_profiles"]["base_salary"]) 

        if emp_id not in payroll_data:
            payroll_data[emp_id] = {"total_hours": 0, "rate": base_rate}
        
        payroll_data[emp_id]["total_hours"] += hours

    processed_count = 0
    total_payroll_expense = 0

    # 4. Post to Payroll Ledger
    for emp_id, data in payroll_data.items():
        net_payable = data["total_hours"] * data["rate"]
        if net_payable <= 0:
            continue

        supabase.table("payroll_ledgers").insert({
            "employee_id": emp_id,
            "payroll_month": month,
            "payroll_year": year,
            "net_payable": net_payable
        }).execute()

        total_payroll_expense += net_payable
        processed_count += 1

    # 5. Automatically deduct from main charity financial ledger
    if total_payroll_expense > 0:
        supabase.table("financial_transactions").insert({
            "transaction_date": str(date.today()),
            "amount": total_payroll_expense,
            "transaction_type": "Expense",
            "status": "Cash"
        }).execute()

    result = {
        "message": f"Successfully processed payroll for {processed_count} employees.",
        "month": month,
        "year": year,
        "total_payout": total_payroll_expense
    }

    # Distinct from PAYROLL_GENERATE_HR: this is the inline-loop implementation,
    # and the two paths could diverge. Collapsing them into one action_type
    # would hide which one actually ran.
    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="PAYROLL_GENERATE_FINANCE",
        table_name="payroll_ledgers",
        old_payload=None,
        new_payload={
            "month": month,
            "year": year,
            "employees_processed": processed_count,
            "total_payout": total_payroll_expense,
        },
    )

    return result