from fastapi import APIRouter, HTTPException, Depends
from app.core.supabase import get_supabase
from app.core.audit import log_audit_action
from app.core.security import get_current_user
from app.schemas.inventory import (
    InventoryItem, InventoryTransaction, InventoryTransactionCreate, CostPerAnimal,
    StockInCreate, StockOutCreate, StockReturnCreate, AddItemCreate,
)
from typing import List, Optional
from datetime import date
from supabase import Client

router = APIRouter()


# ─── Read Endpoints ───────────────────────────────────────────────────────────

@router.get("/items", response_model=List[InventoryItem])
async def get_items(supabase: Client = Depends(get_supabase)):
    response = supabase.table("inventory_items").select("*").execute()
    return response.data


@router.get("/transactions", response_model=List[InventoryTransaction])
async def get_transactions(item_id: Optional[int] = None, supabase: Client = Depends(get_supabase)):
    query = supabase.table("inventory_transactions").select("*, inventory_items(item_name), programs(program_name)")
    if item_id:
        query = query.eq("item_id", item_id)
    response = query.execute()
    return response.data


@router.get("/cost-per-animal", response_model=List[CostPerAnimal])
async def get_cost_per_animal(supabase: Client = Depends(get_supabase)):
    tx_response = supabase.table("inventory_transactions") \
        .select("program_id, quantity, inventory_items(unit_cost)") \
        .eq("transaction_type", "Issue") \
        .not_.is_("program_id", "null") \
        .execute()

    cost_by_program: dict[int, float] = {}
    for tx in tx_response.data:
        pid = tx.get("program_id")
        if pid is None:
            continue
        unit_cost = (tx.get("inventory_items") or {}).get("unit_cost", 0) or 0
        quantity = tx.get("quantity", 0) or 0
        cost_by_program[pid] = cost_by_program.get(pid, 0.0) + quantity * unit_cost

    if not cost_by_program:
        return []

    program_ids = list(cost_by_program.keys())
    prog_response = supabase.table("programs") \
        .select("id, program_name, total_animals_treated") \
        .in_("id", program_ids) \
        .execute()

    results: List[CostPerAnimal] = []
    for prog in prog_response.data:
        pid = prog["id"]
        total_cost = cost_by_program.get(pid, 0.0)
        animals = prog.get("total_animals_treated") or 0
        cost_per_animal = (total_cost / animals) if animals > 0 else 0.0
        results.append(CostPerAnimal(
            program_id=pid,
            program_name=prog["program_name"],
            total_cost=round(total_cost, 2),
            animals_treated=animals,
            cost_per_animal=round(cost_per_animal, 2),
        ))

    results.sort(key=lambda r: r.cost_per_animal, reverse=True)
    return results


@router.get("/low-stock", response_model=List[InventoryItem])
async def get_low_stock(threshold: int = 10, supabase: Client = Depends(get_supabase)):
    response = supabase.table("inventory_items").select("*").lt("current_stock", threshold).execute()
    return response.data


# ─── Stock In ────────────────────────────────────────────────────────────────

@router.post("/stock-in", status_code=201)
async def stock_in(
    payload: StockInCreate,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(get_current_user),
):
    try:
        response = supabase.rpc(
            "record_inventory_transaction",
            {
                "p_item_id": payload.item_id,
                "p_quantity": payload.quantity,
                "p_transaction_type": "restock",
                "p_transaction_date": str(payload.transaction_date),
                "p_program_id": payload.program_id,
            },
        ).execute()
    except Exception as exc:
        detail = str(exc)
        if "not found" in detail.lower():
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=500, detail=f"Database error: {detail}")

    if not response.data:
        raise HTTPException(status_code=400, detail="Stock-in failed — no data returned.")

    await log_audit_action(
        supabase=supabase,
        user_id=current_user.get("id"),
        action_type="INVENTORY_STOCK_IN",
        table_name="inventory_transactions",
        new_payload=response.data,
    )
    return {"message": "Stock added successfully", "transaction": response.data}


# ─── Stock Out ────────────────────────────────────────────────────────────────

@router.post("/stock-out", status_code=201)
async def stock_out(
    payload: StockOutCreate,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(get_current_user),
):
    item_resp = supabase.table("inventory_items") \
        .select("current_stock, item_name") \
        .eq("id", payload.item_id) \
        .single() \
        .execute()

    if not item_resp.data:
        raise HTTPException(status_code=404, detail="Item not found")

    available = item_resp.data["current_stock"]
    if available < payload.quantity:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient stock. Available: {available}, Requested: {payload.quantity}",
        )

    try:
        response = supabase.rpc(
            "record_inventory_transaction",
            {
                "p_item_id": payload.item_id,
                "p_quantity": payload.quantity,
                "p_transaction_type": "Issue",
                "p_transaction_date": str(payload.transaction_date),
                "p_program_id": payload.program_id,
            },
        ).execute()
    except Exception as exc:
        detail = str(exc)
        if "insufficient stock" in detail.lower():
            raise HTTPException(status_code=422, detail=detail)
        raise HTTPException(status_code=500, detail=f"Database error: {detail}")

    if not response.data:
        raise HTTPException(status_code=400, detail="Stock-out failed — no data returned.")

    await log_audit_action(
        supabase=supabase,
        user_id=current_user.get("id"),
        action_type="INVENTORY_ISSUE",
        table_name="inventory_transactions",
        new_payload=response.data,
    )
    return {"message": "Stock issued successfully", "transaction": response.data}


# ─── Stock Return ─────────────────────────────────────────────────────────────

@router.post("/stock-return", status_code=201)
async def stock_return(
    payload: StockReturnCreate,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(get_current_user),
):
    try:
        response = supabase.rpc(
            "record_inventory_transaction",
            {
                "p_item_id": payload.item_id,
                "p_quantity": payload.quantity,
                "p_transaction_type": "Return",
                "p_transaction_date": str(date.today()),
                "p_program_id": payload.program_id,
            },
        ).execute()
    except Exception as exc:
        detail = str(exc)
        if "not found" in detail.lower():
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=500, detail=f"Database error: {detail}")

    if not response.data:
        raise HTTPException(status_code=400, detail="Stock-return failed — no data returned.")

    await log_audit_action(
        supabase=supabase,
        user_id=current_user.get("id"),
        action_type="INVENTORY_RETURN",
        table_name="inventory_transactions",
        new_payload=response.data,
    )
    return {"message": "Stock returned successfully", "transaction": response.data}


# ─── Add Item ─────────────────────────────────────────────────────────────────

@router.post("/items", response_model=InventoryItem, status_code=201)
async def create_item(
    item: AddItemCreate,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(get_current_user),
):
    response = supabase.table("inventory_items").insert({
        "item_name": item.item_name,
        "current_stock": item.initial_quantity,
        "unit_cost": item.unit_cost,
    }).execute()

    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create item")

    new_item = response.data[0]

    if item.initial_quantity > 0:
        try:
            supabase.rpc(
                "record_inventory_transaction",
                {
                    "p_item_id": new_item["id"],
                    "p_quantity": item.initial_quantity,
                    "p_transaction_type": "restock",
                    "p_transaction_date": str(date.today()),
                    "p_program_id": None,
                },
            ).execute()
        except Exception as exc:
            print(f"[WARN] Initial stock transaction failed for item {new_item['id']}: {exc}")

    await log_audit_action(
        supabase=supabase,
        user_id=current_user.get("id"),
        action_type="CREATE",
        table_name="inventory_items",
        new_payload=new_item,
    )
    return new_item


# ─── Legacy (kept for backward compat) ───────────────────────────────────────

@router.post("/transactions", response_model=InventoryTransaction)
async def create_transaction(
    transaction: InventoryTransactionCreate,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(get_current_user),
):
    try:
        response = supabase.rpc(
            "record_inventory_transaction",
            {
                "p_item_id": transaction.item_id,
                "p_quantity": transaction.quantity,
                "p_transaction_type": transaction.transaction_type,
                "p_transaction_date": str(transaction.transaction_date),
                "p_program_id": transaction.program_id,
            },
        ).execute()
    except Exception as exc:
        detail = str(exc)
        if "not found" in detail.lower():
            raise HTTPException(status_code=404, detail=detail)
        if "insufficient stock" in detail.lower():
            raise HTTPException(status_code=400, detail=detail)
        raise HTTPException(status_code=500, detail=f"Database error: {detail}")

    if not response.data:
        raise HTTPException(status_code=400, detail="Transaction failed — no data returned.")

    await log_audit_action(
        supabase=supabase,
        user_id=current_user.get("id"),
        action_type=f"INVENTORY_{transaction.transaction_type.upper()}",
        table_name="inventory_transactions",
        new_payload=response.data,
    )
    return response.data
