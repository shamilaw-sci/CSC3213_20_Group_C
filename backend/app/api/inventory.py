from fastapi import APIRouter, HTTPException, Depends
from postgrest.exceptions import APIError
from app.core.supabase import get_supabase
from app.core.security import check_user_role, require_any_permission, require_permission
from app.core.permissions import UserRole
from app.core.audit import log_audit_action
from app.schemas.inventory import (
    InventoryItem,
    InventoryItemCreate,
    InventoryTransaction,
    InventoryTransactionCreate,
    LowStockItem,
    ExpiringItem,
    CostPerAnimalResult,
)
from typing import List, Optional
from datetime import date, timedelta
from supabase import Client

# Roles that have any inventory access (read or issue). Operations Lead is
# included alongside General Staff: it holds both inventory:read and
# inventory:issue, so omitting it here would deny a role the permission table
# grants access to.
INVENTORY_ROLES = [
    UserRole.ADMIN.value,
    UserRole.DIRECTOR.value,
    UserRole.FINANCE_OFFICER.value,
    UserRole.OPERATIONS_LEAD.value,
    UserRole.GENERAL_STAFF.value,
]

router = APIRouter()


@router.get("/items", response_model=List[InventoryItem])
async def get_items(
    # Either permission: the Issue and Returns pages (inventory:issue, held by
    # General Staff without inventory:read) pick from this same item list.
    current_user: dict = Depends(require_any_permission('inventory:read', 'inventory:issue')),
    supabase: Client = Depends(get_supabase),
):
    response = supabase.table("inventory_items").select("*").execute()
    return response.data


@router.post("/items", response_model=InventoryItem)
async def create_item(
    item: InventoryItemCreate,
    current_user: dict = Depends(require_permission('inventory:issue')),
    supabase: Client = Depends(get_supabase),
):
    # How much initial stock the caller wants. We store 0 in the DB first,
    # then let the Restock RPC adjust it so total_cost is calculated correctly.
    requested_initial_stock = item.current_stock

    # Always insert with current_stock=0; the Restock RPC below will set
    # the real value if the caller requested initial stock > 0.
    # mode='json' converts Python date/datetime objects to ISO strings so
    # Supabase's HTTP client can serialize them correctly.
    insert_data = item.model_dump(mode="json")
    insert_data["current_stock"] = 0

    response = supabase.table("inventory_items").insert(insert_data).execute()
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create item")

    new_item = response.data[0]

    if requested_initial_stock > 0:
        try:
            supabase.rpc(
                "process_inventory_transaction",
                {
                    "p_item_id": new_item["id"],
                    "p_program_id": None,
                    "p_quantity": requested_initial_stock,
                    "p_transaction_type": "Restock",
                    "p_transaction_date": str(date.today()),
                },
            ).execute()
        except APIError as e:
            # The item row already exists at this point. Rather than
            # leaving the caller with a confusing generic 400, tell them
            # exactly what went wrong with the initial stock-in.
            raise HTTPException(
                status_code=400,
                detail=f"Item created, but failed to record initial stock: {e.message}",
            )

        # Re-fetch so the response reflects the real, current stock level
        # (rather than the 0 we inserted a moment ago).
        refreshed = (
            supabase.table("inventory_items")
            .select("*")
            .eq("id", new_item["id"])
            .single()
            .execute()
        )
        new_item = refreshed.data

    await log_audit_action(
        supabase,
        user_id=current_user["id"],
        action_type="INVENTORY_ITEM_CREATE",
        table_name="inventory_items",
        old_payload=None,
        new_payload=new_item,
    )

    return new_item


# ===================================================================
# HELPER
# ===================================================================

def _map_transaction_row(row: dict) -> dict:
    """
    The live DB uses `transaction_id` as the PK column name on
    inventory_transactions (renamed manually; init.sql was never updated).
    Rename it to `id` here so the Pydantic model and frontend always
    see a consistent field name.
    """
    if "transaction_id" in row and "id" not in row:
        row = {**row, "id": row.pop("transaction_id")}
    # Default total_cost to 0 if the column is missing (older rows)
    row.setdefault("total_cost", 0)
    return row


# ===================================================================
# TRANSACTIONS
# ===================================================================

@router.get("/transactions", response_model=List[InventoryTransaction])
async def get_transactions(
    item_id: Optional[int] = None,
    current_user: dict = Depends(require_permission('inventory:read')),
    supabase: Client = Depends(get_supabase),
):
    query = supabase.table("inventory_transactions").select("*, inventory_items(item_name), programs(program_name)")
    if item_id:
        query = query.eq("item_id", item_id)
    response = query.order("transaction_date", desc=True).execute()

    return [_map_transaction_row(row) for row in response.data]


# The audit trail distinguishes the three stock movements, matching the
# action_type values already present in system_audit_logs.
_TRANSACTION_ACTION = {
    "Issue": "INVENTORY_ISSUE",
    "Return": "INVENTORY_RETURN",
    "Restock": "INVENTORY_STOCK_IN",
}


@router.post("/transactions", response_model=InventoryTransaction)
async def create_transaction(
    transaction: InventoryTransactionCreate,
    current_user: dict = Depends(require_permission('inventory:issue')),
    supabase: Client = Depends(get_supabase),
):
    # 1. Start transaction (Supabase doesn't support multi-table atomic transactions easily via client, so we do it step-wise)
    # In a real production app, we should use a Postgres function (RPC) for atomicity.
    
    # Check stock
    item_response = supabase.table("inventory_items").select("current_stock").eq("id", transaction.item_id).single().execute()
    if not item_response.data:
        raise HTTPException(status_code=404, detail="Item not found")
    
    current_stock = item_response.data["current_stock"]
    new_stock = current_stock
    
    if transaction.transaction_type == "Issue":
        if current_stock < transaction.quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock")
        new_stock -= transaction.quantity
    elif transaction.transaction_type == "Return":
        new_stock += transaction.quantity
    elif transaction.transaction_type == "Restock":
        new_stock += transaction.quantity
    
    # Update stock
    update_response = supabase.table("inventory_items").update({"current_stock": new_stock}).eq("id", transaction.item_id).execute()
    
    # Log transaction
    # mode='json' converts the date field to an ISO string so Supabase
    # can serialize it correctly.
    response = supabase.table("inventory_transactions").insert(transaction.model_dump(mode="json")).execute()
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to log inventory transaction")

    created = _map_transaction_row(response.data[0])

    await log_audit_action(
        supabase,
        user_id=current_user["id"],
        action_type=_TRANSACTION_ACTION.get(transaction.transaction_type, "INVENTORY_TRANSACTION"),
        table_name="inventory_transactions",
        # The stock level either side of the movement is the part worth being
        # able to prove later; the transaction row alone doesn't show it.
        old_payload={"item_id": transaction.item_id, "current_stock": current_stock},
        new_payload={**created, "current_stock": new_stock},
    )

    return created


# ===================================================================
# ALERTS  (write-up Section 7 & 8)
# ===================================================================

@router.get("/alerts/low-stock", response_model=List[LowStockItem])
async def get_low_stock_items(
    threshold: int = 10,
    user=Depends(check_user_role(INVENTORY_ROLES)),
    supabase: Client = Depends(get_supabase),
):
    response = (
        supabase.table("inventory_items")
        .select("id, item_name, current_stock, supplier_name")
        .lt("current_stock", threshold)
        .order("current_stock", desc=False)
        .execute()
    )
    return response.data or []


@router.get("/alerts/expiring", response_model=List[ExpiringItem])
async def get_expiring_items(
    days: int = 30,
    user=Depends(check_user_role(INVENTORY_ROLES)),
    supabase: Client = Depends(get_supabase),
):
    # "Expiring" = already expired OR expiring within the next `days` days.
    # We don't filter out already-expired items here on purpose: those are
    # arguably the MOST urgent ones to show, not something to hide.
    cutoff = date.today() + timedelta(days=days)
    response = (
        supabase.table("inventory_items")
        .select("id, item_name, expire_date, current_stock")
        .not_.is_("expire_date", "null")
        .lte("expire_date", str(cutoff))
        .order("expire_date", desc=False)
        .execute()
    )
    return response.data or []


# ===================================================================
# ANALYTICS  (write-up Section 11: Cost-per-Animal)
# ===================================================================

@router.get("/analytics/cost-per-animal/{program_id}", response_model=CostPerAnimalResult)
async def get_cost_per_animal(
    program_id: int,
    user=Depends(check_user_role(INVENTORY_ROLES)),
    supabase: Client = Depends(get_supabase),
):
    try:
        response = supabase.rpc(
            "get_cost_per_animal", {"p_program_id": program_id}
        ).execute()
    except APIError as e:
        raise HTTPException(status_code=400, detail=e.message)

    if not response.data:
        raise HTTPException(status_code=404, detail="Program not found")

    # get_cost_per_animal() is a RETURNS TABLE function, so Supabase
    # gives it back as a list of rows even though there's only ever one.
    return response.data[0]