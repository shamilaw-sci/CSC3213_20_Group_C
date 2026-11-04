from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from datetime import date
from calendar import monthrange
from postgrest.exceptions import APIError
from supabase import Client

# Internal App Imports
from app.core.supabase import get_supabase
from app.core.security import require_permission
from app.core.permissions import has_permission
from app.core.audit import log_audit_action
from app.services.finance_reports import fetch_ledger, finance_snapshot
from app.services.ledger import DEFAULT_SOURCE, SOURCE_LABELS, build_ledger_page
from app.services.program_lifecycle import (
    LOCATION_MIGRATION_MESSAGE, UPCOMING, is_missing_location_column,
)
from app.services.restricted_funds import (
    _to_decimal,
    compute_restricted_balance,
    is_program_restricted,
    restricted_effect,
)
from app.schemas.finance import (
    FinancialTransaction,
    FinancialTransactionCreate,
    Program,
    ProgramCreate,
    RestrictedBalance,
    StockMovementRef,
    VoidTransactionRequest,
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


@router.get("/ledger")
async def get_ledger(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    transaction_type: Optional[str] = Query(None, pattern="^(Income|Expense)$"),
    status: Optional[str] = Query(None, pattern="^(Cash|Receivable|Voided)$"),
    # A program id, or "general" for rows charged to no program.
    program: Optional[str] = Query(None, pattern=r"^(general|\d+)$"),
    restricted: Optional[bool] = None,
    q: Optional[str] = Query(None, max_length=100),
    sort: str = Query("newest", pattern="^(newest|oldest)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    # For CSV export: every matching row, no paging.
    all: bool = False,
    user = Depends(require_permission('finance:read')),
    supabase: Client = Depends(get_supabase)
):
    """
    The ledger page: filtered, paged, totalled, with a running balance.

    Every row is fetched, not just the filtered ones, because each row's
    balance depends on everything dated before it. Filtering happens after.
    """
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be on or before end_date.")

    # Rows after end_date cannot change the balance of rows on or before it.
    rows = fetch_ledger(supabase, end_date or date.max, include_source=True)
    return build_ledger_page(
        rows,
        start=start_date,
        end=end_date,
        tx_type=transaction_type,
        status=status,
        program=program,
        restricted=restricted,
        q=q,
        newest_first=sort == "newest",
        page=page,
        page_size=page_size,
        everything=all,
    )


async def _enforce_restricted_drawdown(
    supabase: Client,
    user: dict,
    old_row: Optional[dict],
    new_row: dict,
    override_restricted: bool,
    transaction_id: Optional[int] = None,
) -> None:
    """
    Refuse a ledger change that would overspend a program's earmarked funds.

    The change is modelled as "take old_row out, put new_row in" — old_row is
    None on a create. Every program either row touches is checked, because an
    edit that moves an expense between programs, or lowers / un-restricts /
    un-settles a restricted donation, draws down earmarked money just as surely
    as a new expense does. Checking only creates let an officer post a small
    expense and then edit it upward past the limit.

    A change that leaves a program's remaining balance where it was or higher
    is never blocked, even if the program is already overdrawn: correcting an
    overspend must not need an override.

    Raises HTTPException (409 / 403 / 503) when the change is refused; returns
    normally when it may proceed, having written the override audit row first
    if one was required.
    """
    program_ids = sorted({
        r["program_id"] for r in (old_row, new_row)
        if r and r.get("program_id") is not None
    })

    for program_id in program_ids:
        delta = restricted_effect(new_row, program_id) - restricted_effect(old_row, program_id)
        if delta >= 0:
            continue

        # Only programs that actually hold earmarked money are gated — see
        # is_program_restricted for why an unrestricted program must not be
        # blocked on a balance of zero.
        if not is_program_restricted(supabase, program_id):
            continue

        balance = compute_restricted_balance(supabase, program_id)
        remaining = balance["remaining"]
        # `remaining` already includes old_row, so applying the delta gives
        # the balance as it would stand after this change.
        after = remaining + delta
        if after >= 0:
            continue

        shortfall = -after
        attempted_amount = _to_decimal(new_row.get("amount"))
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
            change = (
                f"Expense of {attempted_amount}"
                if old_row is None
                else f"This edit to transaction {transaction_id}"
            )
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{change} exceeds the restricted funds "
                    f"remaining for program {program_id} by {shortfall}. "
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

        # The audit row is written BEFORE the ledger change, and a failure to
        # write it aborts the request.
        #
        # log_audit_action is fail-soft everywhere else, which is right when
        # it records something that already happened. Here it IS the
        # control: an override is authorized by being recorded. Writing
        # first and logging after would mean a dropped audit row leaves an
        # unrecorded overspend in the ledger. Ordered this way, the only
        # failure mode is an override logged for a change that then
        # failed to apply — over-recording, which is reviewable, rather
        # than under-recording, which is not.
        new_payload = {
            "program_id": program_id,
            "shortfall_amount": shortfall,
            "attempted_amount": attempted_amount,
            "restricted_raised": balance["raised"],
            "restricted_spent": balance["spent"],
            "restricted_remaining": remaining,
            "authorized_by": str(user["id"]),
        }
        if transaction_id is not None:
            new_payload["transaction_id"] = transaction_id

        logged = await log_audit_action(
            supabase,
            user_id=user["id"],
            action_type="FINANCE_RESTRICTED_OVERRIDE",
            table_name="financial_transactions",
            old_payload=None,
            # Not a row diff: synthetic detail packed into new_payload, which
            # compute_hash covers, so these figures are chain-protected.
            #
            # Money is recorded as a decimal STRING, never a float. A float
            # here silently breaks verification forever: canonicalize()
            # leaves 8000.0 as a float, but JSONB returns whole numbers as
            # 8000, so the digest computed on insert can never be
            # reproduced on read. Decimal serializes via compute_hash's
            # default=str to "8000.00", which survives the round trip
            # unchanged and keeps exact precision as a bonus.
            new_payload=new_payload,
        )

        if not logged:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Override could not be recorded to the audit log and was "
                    "therefore not applied. The ledger was not changed."
                ),
            )


def _get_transaction_or_404(supabase: Client, transaction_id: int) -> dict:
    # Not .single(): supabase-py raises on zero rows rather than returning
    # empty data, which turned an unknown id into a 500 instead of a 404.
    existing = supabase.table("financial_transactions") \
        .select("*") \
        .eq("id", transaction_id) \
        .execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return existing.data[0]


def _source_of(row: dict) -> str:
    """Where a row came from (migration 013). A row read before 013 has no
    source_type; the column's default is 'manual', so it is manual."""
    return row.get("source_type") or DEFAULT_SOURCE


def _is_missing_stock_link(error: APIError) -> bool:
    """True when PostgREST refused the select because migration 016 is not
    applied: no inventory_transaction_id column (42703) or no relationship
    to inventory_transactions to embed (PGRST200)."""
    text = f"{getattr(error, 'code', '')} {getattr(error, 'message', '')}".lower()
    return "inventory_transaction" in text and any(
        marker in text for marker in ("42703", "pgrst200", "column", "relationship")
    )


@router.post("/transactions", response_model=FinancialTransaction)
async def create_transaction(
    transaction: FinancialTransactionCreate,
    override_restricted: bool = False,
    user = Depends(require_permission('finance:write')),
    supabase: Client = Depends(get_supabase)
):
    if transaction.amount <= 0:
        raise HTTPException(status_code=400, detail="Transaction amount must be strictly positive.")

    await _enforce_restricted_drawdown(
        supabase,
        user,
        old_row=None,
        new_row=transaction.model_dump(mode="json"),
        override_restricted=override_restricted,
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
    override_restricted: bool = False,
    user = Depends(require_permission('finance:write')),
    supabase: Client = Depends(get_supabase)
):
    if transaction.amount <= 0:
        raise HTTPException(status_code=400, detail="Transaction amount must be strictly positive.")

    # Voiding goes through PATCH /void, which records FINANCE_TRANSACTION_VOID.
    # Allowing it here would produce a void the audit log calls an update.
    if transaction.status == "Voided":
        raise HTTPException(
            status_code=400,
            detail="Use the void action to void a transaction, not an edit.",
        )

    # Read the row before overwriting it — an amount change is exactly the kind
    # of edit the audit trail exists to make provable.
    existing = _get_transaction_or_404(supabase, transaction_id)

    # A voided row is a reversal on the record. Editing it would either change
    # history silently or, by sending any other status, bring it back as live
    # money without anyone having un-voided it.
    if existing.get("status") == "Voided":
        raise HTTPException(
            status_code=409,
            detail="Voided transactions cannot be edited. Record a new transaction instead.",
        )

    # Stock In, payroll and donations post their own rows. An edit here would
    # let one drift from the movement, payroll run or donation behind it, so
    # they are corrected by voiding and recording a new transaction.
    source = _source_of(existing)
    if source != DEFAULT_SOURCE:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{SOURCE_LABELS.get(source, source)} transactions are posted automatically and "
                "cannot be edited. Void this one and record a new transaction instead."
            ),
        )

    await _enforce_restricted_drawdown(
        supabase,
        user,
        old_row=existing,
        new_row=transaction.model_dump(mode="json"),
        override_restricted=override_restricted,
        transaction_id=transaction_id,
    )

    data = transaction.model_dump()
    data["transaction_date"] = str(data["transaction_date"])
    data["amount"] = float(data["amount"])

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
        old_payload=existing,
        new_payload=response.data[0],
    )

    return response.data[0]


@router.patch("/transactions/{transaction_id}/void", response_model=FinancialTransaction)
async def void_transaction(
    transaction_id: int,
    body: Optional[VoidTransactionRequest] = None,
    user = Depends(require_permission('finance:write')),
    supabase: Client = Depends(get_supabase)
):
    existing = _get_transaction_or_404(supabase, transaction_id)

    if existing.get("status") == "Voided":
        raise HTTPException(status_code=400, detail="Transaction is already voided")

    # Voiding a Stock In expense takes the money off the books but leaves the
    # stock in Inventory, which has no reversal yet. The reason is what tells
    # whoever reconciles the two later what happened.
    reason = body.reason if body else None
    if _source_of(existing) == "stock_in" and not reason:
        raise HTTPException(
            status_code=400,
            detail="Give a reason for voiding a Stock In expense.",
        )

    response = supabase.table("financial_transactions") \
        .update({"status": "Voided"}) \
        .eq("id", transaction_id) \
        .execute()

    new_payload = response.data[0]
    if reason:
        new_payload = {**new_payload, "void_reason": reason}

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="FINANCE_TRANSACTION_VOID",
        table_name="financial_transactions",
        old_payload=existing,
        new_payload=new_payload,
    )

    return response.data[0]


@router.get(
    "/transactions/{transaction_id}/stock-movement",
    response_model=Optional[StockMovementRef],
)
async def get_transaction_stock_movement(
    transaction_id: int,
    user = Depends(require_permission('finance:read')),
    supabase: Client = Depends(get_supabase)
):
    """
    The Stock In movement a stock_in expense was posted for, so the void
    dialog can say exactly what to correct in Inventory. null when the row is
    not a Stock In expense or has no link: migration 016 not applied yet, or
    an old expense 016 could not pair with its movement.
    """
    try:
        response = supabase.table("financial_transactions") \
            .select(
                "id, source_type, inventory_transaction_id, "
                "inventory_transactions(quantity, transaction_date, total_cost, inventory_items(item_name))"
            ) \
            .eq("id", transaction_id) \
            .execute()
    except APIError as e:
        if _is_missing_stock_link(e):
            return None
        raise

    if not response.data:
        raise HTTPException(status_code=404, detail="Transaction not found")

    row = response.data[0]
    movement = row.get("inventory_transactions")
    if _source_of(row) != "stock_in" or not movement or row.get("inventory_transaction_id") is None:
        return None

    return {
        "inventory_transaction_id": row["inventory_transaction_id"],
        "item_name": (movement.get("inventory_items") or {}).get("item_name"),
        "quantity": movement.get("quantity") or 0,
        "transaction_date": movement.get("transaction_date"),
        "total_cost": movement.get("total_cost") or 0,
    }

@router.patch("/transactions/{transaction_id}/settle", response_model=FinancialTransaction)
async def settle_transaction(
    transaction_id: int,
    user = Depends(require_permission('finance:write')),
    supabase: Client = Depends(get_supabase)
):
    existing = _get_transaction_or_404(supabase, transaction_id)

    # Only an open receivable/payable can be settled. Checking just for "Cash"
    # let a Voided row through, and settling it set it to Cash — reinstating a
    # reversed transaction as real money.
    if existing.get("status") == "Voided":
        raise HTTPException(status_code=409, detail="A voided transaction cannot be settled")

    if existing.get("status") == "Cash":
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
        old_payload=existing,
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
    # Every program starts as Upcoming, whatever the client sent; it only
    # moves on through POST /api/programs/{id}/start and /complete.
    data = program.model_dump(mode="json", exclude_none=True)
    data["status"] = UPCOMING
    data.pop("end_date", None)
    try:
        response = supabase.table("programs").insert(data).execute()
    except Exception as e:
        if is_missing_location_column(e):
            raise HTTPException(status_code=503, detail=LOCATION_MIGRATION_MESSAGE)
        raise

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
    # Was the get_finance_summary RPC; see finance_snapshot for why. Same
    # response shape, so the Overview and dashboards are unchanged.
    return finance_snapshot(fetch_ledger(supabase, date.max), date.today())

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
