from fastapi import APIRouter, HTTPException, Depends
from app.core.supabase import get_supabase
from app.core.audit import log_audit_action
from app.schemas.inventory import InventoryItem, InventoryItemCreate, InventoryTransaction, InventoryTransactionCreate, CostPerAnimal
from typing import List, Optional
from datetime import date
from supabase import Client
from app.core.security import check_user_role

router = APIRouter()


@router.get("/items", response_model=List[InventoryItem])
async def get_items(supabase: Client = Depends(get_supabase)):
    response = supabase.table("inventory_items").select("*").execute()
    return response.data

@router.post("/items", response_model=InventoryItem)
async def create_item(item: InventoryItemCreate, supabase: Client = Depends(get_supabase)):
    response = supabase.table("inventory_items").insert(item.model_dump()).execute()
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create item")
    return response.data[0]

@router.get("/transactions", response_model=List[InventoryTransaction])
async def get_transactions(item_id: Optional[int] = None, supabase: Client = Depends(get_supabase)):
    query = supabase.table("inventory_transactions").select("*, inventory_items(item_name), programs(program_name)")
    if item_id:
        query = query.eq("item_id", item_id)
    response = query.execute()
    return response.data

@router.post("/transactions", response_model=InventoryTransaction)
async def create_transaction(transaction: InventoryTransactionCreate, supabase: Client = Depends(get_supabase)):
    """
    Records an inventory Issue or Return atomically via the
    `record_inventory_transaction` Postgres function.
    Both the stock update and the transaction log happen inside a single
    database transaction — no partial updates, no manual rollbacks needed.
    """
    try:
        response = supabase.rpc(
            "record_inventory_transaction",
            {
                "p_item_id":          transaction.item_id,
                "p_quantity":         transaction.quantity,
                "p_transaction_type": transaction.transaction_type,
                "p_transaction_date": str(transaction.transaction_date),
                "p_program_id":       transaction.program_id,
            },
        ).execute()
    except Exception as exc:
        # Supabase surfaces Postgres RAISE EXCEPTION messages here
        detail = str(exc)
        if "not found" in detail.lower():
            raise HTTPException(status_code=404, detail=detail)
        if "insufficient stock" in detail.lower():
            raise HTTPException(status_code=400, detail=detail)
        raise HTTPException(status_code=500, detail=f"Database error: {detail}")

    if not response.data:
        raise HTTPException(status_code=400, detail="Transaction failed — no data returned.")

    return response.data


@router.get("/cost-per-animal", response_model=List[CostPerAnimal])
async def get_cost_per_animal(supabase: Client = Depends(get_supabase)):
    # 1. Fetch all Issue transactions joined to inventory_items for unit_cost
    tx_response = supabase.table("inventory_transactions") \
        .select("program_id, quantity, inventory_items(unit_cost)") \
        .eq("transaction_type", "Issue") \
        .not_.is_("program_id", "null") \
        .execute()

    # 2. Group by program_id, accumulate total_cost = sum(quantity * unit_cost)
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

    # 3. Fetch programs to get names and total_animals_treated
    program_ids = list(cost_by_program.keys())
    prog_response = supabase.table("programs") \
        .select("id, program_name, total_animals_treated") \
        .in_("id", program_ids) \
        .execute()

    # 4. Build result rows
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

    # Sort by cost_per_animal descending so highest-cost programs surface first
    results.sort(key=lambda r: r.cost_per_animal, reverse=True)
    return results
