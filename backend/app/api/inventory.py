from fastapi import APIRouter, HTTPException, Depends
from app.core.supabase import get_supabase
from app.core.security import check_user_role
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
from postgrest.exceptions import APIError

router = APIRouter()

# Who is allowed to touch inventory data. Matches the roles used in
# finance.py, per what you told me — keeps the permission model
# consistent across modules instead of every module inventing its own.
INVENTORY_ROLES = ["admin", "director", "ops"]


# -----------------------------------------------------------------
# Small helper: your live DB's inventory_transactions primary key is
# actually called `transaction_id`, not `id` (confirmed via
# information_schema — you renamed it manually at some point, and
# init.sql was never updated to match). Every place that reads a
# transaction row from Supabase needs this rename applied BEFORE
# handing the dict to the InventoryTransaction pydantic model,
# otherwise pydantic will complain "field required: id".
# -----------------------------------------------------------------
def _map_transaction_row(row: dict) -> dict:
    if row is None:
        return row
    if "transaction_id" in row:
        row = dict(row)  # don't mutate the original
        row["id"] = row.pop("transaction_id")
    return row


# ===================================================================
# ITEMS
# ===================================================================

@router.get("/items", response_model=List[InventoryItem])
async def get_items(
    user=Depends(check_user_role(INVENTORY_ROLES)),
    supabase: Client = Depends(get_supabase),
):
    response = supabase.table("inventory_items").select("*").execute()
    return response.data


@router.post("/items", response_model=InventoryItem)
async def create_item(
    item: InventoryItemCreate,
    user=Depends(check_user_role(INVENTORY_ROLES)),
    supabase: Client = Depends(get_supabase),
):
    # WHY we insert with current_stock = 0 first, then use the stored
    # procedure to bring stock up to the requested amount:
    #
    # Your write-up (Section 4.1) says "If an initial stock quantity is
    # provided, the system automatically creates an initial Restock
    # transaction, ensuring inventory history begins from the first
    # stock entry." If we just inserted the item with current_stock
    # already set to, say, 100, there would be NO transaction record
    # explaining where that 100 came from — breaking the audit trail
    # your doc promises. So instead: create the item at 0, then let
    # process_inventory_transaction() (the same function used for every
    # other stock movement) do a 'Restock' of the requested amount.
    # Now every single stock change in the system, including the very
    # first one, goes through one consistent, audited code path.

    requested_initial_stock = item.current_stock

    insert_payload = item.model_dump(mode="json")  # converts date → ISO string for httpx
    insert_payload["current_stock"] = 0

    response = supabase.table("inventory_items").insert(insert_payload).execute()
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

    return new_item


# ===================================================================
# TRANSACTIONS
# ===================================================================

@router.get("/transactions", response_model=List[InventoryTransaction])
async def get_transactions(
    item_id: Optional[int] = None,
    user=Depends(check_user_role(INVENTORY_ROLES)),
    supabase: Client = Depends(get_supabase),
):
    query = supabase.table("inventory_transactions").select(
        "*, inventory_items(item_name), programs(program_name)"
    )
    if item_id:
        query = query.eq("item_id", item_id)
    response = query.order("transaction_date", desc=True).execute()

    return [_map_transaction_row(row) for row in response.data]


@router.post("/transactions", response_model=InventoryTransaction)
async def create_transaction(
    transaction: InventoryTransactionCreate,
    user=Depends(check_user_role(INVENTORY_ROLES)),
    supabase: Client = Depends(get_supabase),
):
    # WHY this calls an RPC instead of doing read-check-update-insert
    # in Python (like the old version did):
    #
    # The old code did four separate network round-trips to Supabase:
    # read stock, check it in Python, update stock, insert transaction.
    # If two people issued stock for the same item at the same moment,
    # both requests could read the SAME "current_stock = 20" before
    # either one wrote back — both would pass the "enough stock?" check,
    # both would issue 15 units, and you'd end up with -10 stock even
    # though the code explicitly checked for that. This is called a
    # race condition.
    #
    # process_inventory_transaction() (see migration_001) does all four
    # steps INSIDE a single Postgres function call, using "FOR UPDATE"
    # to lock the item's row for the duration. The second request simply
    # waits its turn instead of reading stale data. One network call,
    # one atomic operation, no race condition.
    try:
        response = supabase.rpc(
            "process_inventory_transaction",
            {
                "p_item_id": transaction.item_id,
                "p_program_id": transaction.program_id,
                "p_quantity": transaction.quantity,
                "p_transaction_type": transaction.transaction_type,
                "p_transaction_date": str(transaction.transaction_date),
            },
        ).execute()
    except APIError as e:
        # e.message carries the RAISE EXCEPTION text from inside the
        # Postgres function (e.g. "Insufficient stock: have 5, requested 10")
        # straight through to the frontend, so the error the user sees
        # is specific instead of a generic "something went wrong".
        raise HTTPException(status_code=400, detail=e.message)

    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to log inventory transaction")

    return _map_transaction_row(response.data)


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