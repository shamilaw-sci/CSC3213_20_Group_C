import logging

from fastapi import APIRouter, HTTPException, Depends, Query
from postgrest.exceptions import APIError
from app.core.supabase import get_supabase
from app.core.security import require_any_permission, require_permission
from app.core.permissions import has_permission
from app.core.audit import log_audit_action
from app.schemas.inventory import (
    InventoryItem,
    InventoryItemCreate,
    InventoryItemUpdate,
    InventoryBatch,
    InventoryBatchUpdate,
    InventoryTransaction,
    InventoryTransactionCreate,
    LowStockItem,
    ExpiringItem,
    MovementReverseRequest,
    OutstandingByProgram,
    CostPerAnimalResult,
    today_in_sri_lanka,
)
from app.services.program_lifecycle import ACTIVE, normalize_status
from typing import List, Optional
from datetime import date, timedelta
from supabase import Client

logger = logging.getLogger(__name__)

# Who may do what (decided 2026-11-01; see app/core/permissions.py):
#   inventory:read   - Stock page reads (Admin, Director, Finance Officer, Operations Lead)
#   inventory:manage - every Stock page action (the same four roles)
#   inventory:issue  - Issue and Returns pages only (Admin, General Staff)
#
# Anyone who works with inventory at all. This used to be a hard-coded list
# of role names, which matched the permission table only by coincidence and
# would have drifted the first time either changed.
_ANY_INVENTORY = require_any_permission('inventory:read', 'inventory:issue')
# Recording a movement: from the Stock page (manage) or the Issue/Returns
# pages (issue). What an issue-only caller may record is narrowed inside
# create_transaction.
_CAN_MOVE_STOCK = require_any_permission('inventory:manage', 'inventory:issue')

# The database function from db/migrations/012_inventory_integrity.sql. It
# does the whole movement in one locked, all-or-nothing step. Until that
# migration is applied the API falls back to the compare-and-set path below.
_MOVEMENT_RPC = "inventory_apply_movement"
# Undo a movement (I4), from migration 019. No fallback: without the function
# the API says which migration to apply.
_REVERSE_RPC = "inventory_reverse_movement"

# Shown when a feature needs db/migrations/020_inventory_batches.sql.
_MIGRATION_020_MESSAGE = (
    "This needs the inventory batches update. Run "
    "backend/db/migrations/020_inventory_batches.sql in Supabase, then try again."
)

# Shown when a feature needs db/migrations/031_case_supplies.sql.
_MIGRATION_031_MESSAGE = (
    "Issuing to a rescue case needs the case supplies update. Run "
    "backend/db/migrations/031_case_supplies.sql in Supabase, then try again."
)

# Shown when a feature needs db/migrations/019_inventory_fixes.sql.
_MIGRATION_019_MESSAGE = (
    "This needs the inventory database update. Run "
    "backend/db/migrations/019_inventory_fixes.sql in Supabase, then try again."
)

# Low stock line for an item with no reorder level of its own.
DEFAULT_REORDER_LEVEL = 10

# How many times a stock update is retried when another request changed the
# same item between our read and our write.
_STOCK_UPDATE_ATTEMPTS = 5

router = APIRouter()


def _escape_like(value: str) -> str:
    """Make user text safe to use as an exact ilike pattern."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/items", response_model=List[InventoryItem])
async def get_items(
    # Either permission: the Issue and Returns pages (inventory:issue, held by
    # General Staff without inventory:read) pick from this same item list.
    current_user: dict = Depends(_ANY_INVENTORY),
    supabase: Client = Depends(get_supabase),
):
    response = supabase.table("inventory_items").select("*").execute()
    return response.data


@router.post("/items", response_model=InventoryItem)
async def create_item(
    item: InventoryItemCreate,
    # Adding to the catalogue is a Stock page action, not something the
    # Issue/Returns pages (General Staff) do.
    current_user: dict = Depends(require_permission('inventory:manage')),
    supabase: Client = Depends(get_supabase),
):
    # Names are compared without case, so "Rabies vaccine" and "rabies
    # Vaccine" cannot become two items whose stock is tracked separately.
    existing = (
        supabase.table("inventory_items")
        .select("id, item_name")
        .ilike("item_name", _escape_like(item.item_name))
        .limit(1)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=409,
            detail=f"An item named '{existing.data[0]['item_name']}' already exists. Use Stock In to add to it.",
        )

    # Add Item only registers the item. Stock is added afterwards with Stock
    # In, the one place a purchase is recorded (and posted to finance), so an
    # opening quantity here is refused rather than quietly dropped.
    if item.current_stock:
        raise HTTPException(
            status_code=400,
            detail="A new item starts with 0 stock. Add the item first, then use Stock In to add its stock.",
        )
    insert_data = item.model_dump(mode="json")
    insert_data["current_stock"] = 0
    # Only sent when set, so adding an item works before migration 019.
    if insert_data.get("reorder_level") is None:
        insert_data.pop("reorder_level", None)

    try:
        response = supabase.table("inventory_items").insert(insert_data).execute()
    except APIError as e:
        if _is_missing_019_column(e):
            raise HTTPException(status_code=503, detail=_MIGRATION_019_MESSAGE)
        # Someone added the same name at the same moment (unique index, 012).
        if _is_duplicate_name(e):
            raise HTTPException(
                status_code=409,
                detail=f"An item named '{item.item_name}' already exists. Use Stock In to add to it.",
            )
        raise
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create item")

    new_item = response.data[0]

    await log_audit_action(
        supabase,
        user_id=current_user["id"],
        action_type="INVENTORY_ITEM_CREATE",
        table_name="inventory_items",
        old_payload=None,
        new_payload=new_item,
    )

    return new_item


@router.patch("/items/{item_id}", response_model=InventoryItem)
async def update_item(
    item_id: int,
    changes: InventoryItemUpdate,
    # The same people who add items (Stock page roles).
    current_user: dict = Depends(require_permission('inventory:manage')),
    supabase: Client = Depends(get_supabase),
):
    """Correct an item's name, supplier or reorder level (I6). Stock, unit
    cost and expiry are not editable here; see InventoryItemUpdate."""
    data = changes.model_dump(mode="json", exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to change.")

    existing = (
        supabase.table("inventory_items").select("*").eq("id", item_id).limit(1).execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Item not found")
    before = existing.data[0]

    if "item_name" in data:
        clash = (
            supabase.table("inventory_items")
            .select("id, item_name")
            .ilike("item_name", _escape_like(data["item_name"]))
            .execute()
        )
        if any(row["id"] != item_id for row in (clash.data or [])):
            raise HTTPException(status_code=409, detail=f"An item named '{data['item_name']}' already exists.")

    try:
        response = supabase.table("inventory_items").update(data).eq("id", item_id).execute()
    except APIError as e:
        if _is_missing_019_column(e):
            raise HTTPException(status_code=503, detail=_MIGRATION_019_MESSAGE)
        # O5: two renames to the same name at the same moment. The check
        # above passed for both; the unique index (012) stops the second.
        if _is_duplicate_name(e):
            raise HTTPException(status_code=409, detail=f"An item named '{data['item_name']}' already exists.")
        raise
    if not response.data:
        raise HTTPException(status_code=404, detail="Item not found")
    after = response.data[0]

    await log_audit_action(
        supabase,
        user_id=current_user["id"],
        action_type="INVENTORY_ITEM_UPDATE",
        table_name="inventory_items",
        old_payload={k: before.get(k) for k in data},
        new_payload={"id": item_id, **{k: after.get(k) for k in data}},
    )
    return after


# ===================================================================
# HELPERS
# ===================================================================

def _is_duplicate_name(error: Exception) -> bool:
    """True when the write broke the unique item-name index (Postgres 23505)."""
    text = f"{getattr(error, 'code', '')} {getattr(error, 'message', '')} {error}"
    return "23505" in text or "inventory_items_name_unique" in text


def _is_missing_table(error: Exception, table: str) -> bool:
    """True when PostgREST does not know the table yet (migration not applied)."""
    text = f"{getattr(error, 'code', '')} {getattr(error, 'message', '')} {error}"
    return table in text and ("PGRST205" in text or "42P01" in text or "Could not find the table" in text)


def _is_missing_019_column(error: Exception) -> bool:
    """True when PostgREST refused a write because a column added by
    migration 019 does not exist yet (PGRST204 'Could not find the ... column')."""
    text = str(error).lower()
    return ("pgrst204" in text or "column" in text) and any(
        name in text for name in ("reorder_level", "expire_date", "reverses_id")
    )


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


def _get_item(supabase: Client, item_id: int) -> dict:
    """The item row, or a 404. (.single() raised on a missing row, so the
    404 it was meant to give was unreachable and the user saw a 500.)"""
    response = (
        supabase.table("inventory_items")
        .select("id, item_name, current_stock, unit_cost")
        .eq("id", item_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Item not found")
    return response.data[0]


def _change_stock(supabase: Client, item_id: int, delta: int) -> tuple[int, int]:
    """
    Add `delta` (negative for an Issue) to an item's stock without losing a
    concurrent update, and never below zero. Returns (before, after).

    The write only lands if current_stock still holds the value we read
    (compare-and-set). If another request changed it in between, nothing is
    written and we read again. Without this, two Issues of 8 against a stock
    of 10 both passed the check and both wrote 2, so 16 units left the store
    while the record showed 8.
    """
    for _ in range(_STOCK_UPDATE_ATTEMPTS):
        item = _get_item(supabase, item_id)
        before = int(item["current_stock"] or 0)
        after = before + delta
        if after < 0:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock: only {before} of '{item['item_name']}' available.",
            )
        updated = (
            supabase.table("inventory_items")
            .update({"current_stock": after})
            .eq("id", item_id)
            .eq("current_stock", before)
            .execute()
        )
        if updated.data:
            return before, after
    raise HTTPException(
        status_code=409,
        detail="This item's stock changed while saving. Please try again.",
    )


def _get_program(supabase: Client, program_id: int) -> dict:
    response = (
        supabase.table("programs")
        .select("id, program_name, status")
        .eq("id", program_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Program not found")
    return response.data[0]


def _outstanding_by_program(supabase: Client, item_id: int, program_id: Optional[int] = None) -> dict:
    """{program_id: {"issued", "returned", "held_cost", "program_name"}} for
    one item, counting only movements tied to a program. held_cost is what
    the program paid for what it still holds (issue costs less return costs)."""
    query = (
        supabase.table("inventory_transactions")
        .select("program_id, quantity, transaction_type, total_cost, programs(program_name)")
        .eq("item_id", item_id)
    )
    query = query.eq("program_id", program_id) if program_id is not None else query.not_.is_("program_id", "null")
    rows = query.execute().data or []

    totals: dict = {}
    for row in rows:
        pid = row.get("program_id")
        if pid is None:
            continue
        entry = totals.setdefault(
            pid,
            {"issued": 0, "returned": 0, "held_cost": 0.0,
             "program_name": (row.get("programs") or {}).get("program_name")},
        )
        cost = float(row.get("total_cost") or 0)
        if row.get("transaction_type") == "Issue":
            entry["issued"] += int(row.get("quantity") or 0)
            entry["held_cost"] += cost
        elif row.get("transaction_type") == "Return":
            entry["returned"] += int(row.get("quantity") or 0)
            entry["held_cost"] -= cost
    return totals


def _return_cost(held: Optional[dict], quantity: int) -> float:
    """What a Return of `quantity` gives back to the program (I3): its share
    of what the program paid for the stock it still holds, not today's price.
    Returning everything gives back exactly what is left, so no rounding is
    left on the program. Same rule as inventory_apply_movement() in 019."""
    if not held:
        return 0.0
    count = held["issued"] - held["returned"]
    if count <= 0:
        return 0.0
    value = max(held["held_cost"], 0.0)
    if quantity >= count:
        return round(value, 2)
    return round(quantity * value / count, 2)


# ===================================================================
# TRANSACTIONS
# ===================================================================

@router.get("/transactions", response_model=List[InventoryTransaction])
async def get_transactions(
    item_id: Optional[int] = None,
    # Optional paging. Without it the whole history is returned, as before,
    # so existing callers are unaffected.
    limit: Optional[int] = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    # Optional date range (inclusive). The Stock page asks for one month.
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: dict = Depends(require_permission('inventory:read')),
    supabase: Client = Depends(get_supabase),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be on or before end_date")
    query = supabase.table("inventory_transactions").select("*, inventory_items(item_name), programs(program_name)")
    if item_id:
        query = query.eq("item_id", item_id)
    if start_date:
        query = query.gte("transaction_date", start_date.isoformat())
    if end_date:
        query = query.lte("transaction_date", end_date.isoformat())
    query = query.order("transaction_date", desc=True)
    if limit is not None:
        query = query.range(offset, offset + limit - 1)
    response = query.execute()
    rows = [_map_transaction_row(row) for row in (response.data or [])]

    # Mark the movements on this page that have been reversed, so the page
    # does not offer Reverse twice. Skipped quietly before migration 019.
    ids = [row["id"] for row in rows if row.get("id") is not None]
    if ids:
        try:
            reversals = (
                supabase.table("inventory_transactions")
                .select("*")
                .in_("reverses_id", ids)
                .execute()
            )
            by_original = {
                r["reverses_id"]: _map_transaction_row(r)["id"] for r in (reversals.data or [])
            }
            for row in rows:
                if row["id"] in by_original:
                    row["reversed_by"] = by_original[row["id"]]
        except APIError as e:
            if not _is_missing_019_column(e):
                raise

    # Name the rescue case a movement was used on (031). Fetched separately
    # rather than embedded, so the list still loads before the migration.
    case_ids = sorted({str(row["rescue_case_id"]) for row in rows if row.get("rescue_case_id")})
    if case_ids:
        cases = (
            supabase.table("rescue_cases").select("id, animal_type, status").in_("id", case_ids).execute().data
            or []
        )
        by_id = {c["id"]: {"animal_type": c["animal_type"], "status": c["status"]} for c in cases}
        for row in rows:
            if row.get("rescue_case_id"):
                row["rescue_case"] = by_id.get(str(row["rescue_case_id"]))

    # Show each Stock In's batch number. Skipped quietly before migration 020.
    restock_ids = [row["id"] for row in rows if row.get("transaction_type") == "Restock" and row.get("id") is not None]
    if restock_ids:
        try:
            batches = (
                supabase.table("inventory_batches")
                .select("stock_in_id, batch_number")
                .in_("stock_in_id", restock_ids)
                .execute()
            )
            number_by_stock_in = {b["stock_in_id"]: b["batch_number"] for b in (batches.data or [])}
            for row in rows:
                if row["id"] in number_by_stock_in:
                    row["batch_number"] = number_by_stock_in[row["id"]]
        except APIError as e:
            if not _is_missing_table(e, "inventory_batches"):
                raise
    return rows


@router.get("/items/{item_id}/outstanding", response_model=List[OutstandingByProgram])
async def get_outstanding_by_program(
    item_id: int,
    # The Returns form needs this, and General Staff (inventory:issue only)
    # use that form. It shows quantities per program, not the movement log.
    current_user: dict = Depends(_ANY_INVENTORY),
    supabase: Client = Depends(get_supabase),
):
    _get_item(supabase, item_id)
    totals = _outstanding_by_program(supabase, item_id)
    result = [
        {
            "program_id": pid,
            "program_name": t["program_name"],
            "issued": t["issued"],
            "returned": t["returned"],
            "outstanding": max(t["issued"] - t["returned"], 0),
        }
        for pid, t in totals.items()
    ]
    return sorted(result, key=lambda r: (-r["outstanding"], r["program_name"] or ""))


# The audit trail distinguishes the three stock movements, matching the
# action_type values already present in system_audit_logs.
_TRANSACTION_ACTION = {
    "Issue": "INVENTORY_ISSUE",
    "Return": "INVENTORY_RETURN",
    "Restock": "INVENTORY_STOCK_IN",
}


def _rpc_missing(error: APIError) -> bool:
    """True when the migration has not been applied yet, so the function
    does not exist (PostgREST answers PGRST202)."""
    text = f"{getattr(error, 'code', '')} {getattr(error, 'message', '')}"
    return "PGRST202" in text or "Could not find the function" in text


def _record_movement(
    supabase: Client,
    *,
    item_id: int,
    tx_type: str,
    program_id: Optional[int],
    quantity: int,
    transaction_date: str,
    notes: Optional[str],
    unit_cost: Optional[float] = None,
    expire_date: Optional[str] = None,
    return_cost: Optional[float] = None,
    batch_number: Optional[str] = None,
    rescue_case_id: Optional[str] = None,
) -> tuple[dict, int, int]:
    """
    Move the stock and write the movement row as one step. Returns
    (movement row, stock before, stock after).

    unit_cost is a Stock In's new price paid: it costs the movement and
    becomes the item's stored unit_cost. None means the stored cost.
    expire_date is a Stock In batch's expiry (needs migration 019).
    return_cost is a Return's cost worked out by the API, used only on the
    fallback path (the database function works it out itself).

    Preferred path: the inventory_apply_movement() database function, which
    locks the item row, checks every rule and writes both rows in a single
    transaction, so they succeed or fail together.

    Fallback (only while migration 012, or 017 for a new price, is not
    applied): compare-and-set the stock, insert the row, and put the stock
    back if the insert fails.
    """
    params = {
        "p_item_id": item_id,
        "p_program_id": program_id,
        "p_quantity": quantity,
        "p_transaction_type": tx_type,
        "p_transaction_date": transaction_date,
        "p_notes": notes,
    }
    # Sent only when there is a new price, so a database with 012 but not
    # 017 still takes the locked path for every other movement.
    if unit_cost is not None:
        params["p_unit_cost"] = unit_cost
    # Likewise only sent when given, so 017's function still takes the rest.
    if expire_date is not None:
        params["p_expire_date"] = expire_date
    if batch_number is not None:
        params["p_batch_number"] = batch_number
    if rescue_case_id is not None:
        params["p_rescue_case_id"] = rescue_case_id
    try:
        result = supabase.rpc(_MOVEMENT_RPC, params).execute()
        row = result.data[0] if isinstance(result.data, list) else result.data
        if not row:
            raise HTTPException(status_code=400, detail="The movement was not saved.")
        before = int(row.pop("stock_before", 0) or 0)
        after = int(row.pop("stock_after", 0) or 0)
        return row, before, after
    except APIError as e:
        if not _rpc_missing(e):
            # A rule inside the function refused it (insufficient stock, an
            # over-return, ...). Its message is written for the user.
            # P0002 = no_data_found, raised for an unknown item or program.
            status = 404 if getattr(e, "code", None) == "P0002" else 400
            raise HTTPException(status_code=status, detail=e.message or "The movement was not saved.")
        logger.warning(
            "%s() not found with these parameters; apply db/migrations/012_inventory_integrity.sql, "
            "017_stock_in_price.sql and 019_inventory_fixes.sql",
            _MOVEMENT_RPC,
        )
        # A case needs 031's function, a batch number 020's, a batch expiry
        # 019's column.
        if rescue_case_id is not None:
            raise HTTPException(status_code=503, detail=_MIGRATION_031_MESSAGE)
        if batch_number is not None:
            raise HTTPException(status_code=503, detail=_MIGRATION_020_MESSAGE)
        if expire_date is not None:
            raise HTTPException(status_code=503, detail=_MIGRATION_019_MESSAGE)

    item = _get_item(supabase, item_id)
    delta = -quantity if tx_type == "Issue" else quantity
    before, after = _change_stock(supabase, item_id, delta)

    cost_each = unit_cost if unit_cost is not None else float(item.get("unit_cost") or 0)
    payload = {
        "item_id": item_id,
        "program_id": program_id,
        "quantity": quantity,
        "transaction_type": tx_type,
        "transaction_date": transaction_date,
        "notes": notes,
        # Cost at the price paid on a Stock In, a Return at what the program
        # paid (I3), else today's unit cost. Worked out here, never sent as a
        # total by the client. Some movements were saved with 0 before.
        "total_cost": return_cost if (tx_type == "Return" and return_cost is not None)
        else round(quantity * cost_each, 2),
    }

    failure: Optional[str] = None
    try:
        response = supabase.table("inventory_transactions").insert(payload).execute()
        if not response.data:
            failure = "the database returned no row"
    except APIError as e:
        failure = e.message or "database error"

    if failure is not None:
        try:
            _change_stock(supabase, item_id, -delta)
        except HTTPException:
            logger.error(
                "Inventory movement not recorded and stock not restored: item %s delta %s", item_id, delta,
            )
            raise HTTPException(
                status_code=500,
                detail=(
                    f"The {tx_type.lower()} was not saved and the stock could not be put back "
                    f"(it now shows {after}, was {before}). Please tell an administrator."
                ),
            )
        raise HTTPException(
            status_code=400,
            detail=f"The {tx_type.lower()} was not saved ({failure}). Stock has not changed.",
        )

    # Last price paid becomes the stored cost. Not atomic with the movement on
    # this path; the movement is already saved at the right price, so a
    # failure here only leaves the stored cost stale.
    if unit_cost is not None:
        try:
            supabase.table("inventory_items").update({"unit_cost": unit_cost}).eq("id", item_id).execute()
        except APIError:
            logger.error("Stock In saved but unit_cost of item %s not updated to %s", item_id, unit_cost)

    return response.data[0], before, after


@router.post("/transactions", response_model=InventoryTransaction)
async def create_transaction(
    transaction: InventoryTransactionCreate,
    current_user: dict = Depends(_CAN_MOVE_STOCK),
    supabase: Client = Depends(get_supabase),
):
    tx_type = transaction.transaction_type
    role = (current_user.get("roles") or {}).get("role_name") or ""
    can_manage = has_permission(role, "inventory:manage")

    # Stock In is new stock entering the organisation, never a program's
    # usage. A program_id on it would wrongly count as that program's cost.
    program_id = None if tx_type == "Restock" else transaction.program_id
    case_id = str(transaction.rescue_case_id) if transaction.rescue_case_id else None

    # Supplies used on a rescue case (confirmed 2026-11-13): Issue only, since
    # what is used on an animal is consumed, and to a case or a program, not
    # both. A mistake is undone with Reverse, which keeps the case.
    if case_id is not None:
        if tx_type != "Issue":
            raise HTTPException(
                status_code=400,
                detail="Supplies can only be issued to a rescue case. Undo a mistake with Reverse on the Stock page.",
            )
        if program_id is not None:
            raise HTTPException(status_code=400, detail="Issue to a program or to a rescue case, not both.")

    # A price paid only exists for stock bought. Issue and Return are always
    # costed at the stored unit cost (programs.total_cost relies on that).
    if transaction.unit_cost is not None and tx_type != "Restock":
        raise HTTPException(status_code=400, detail="A unit price is only entered for Stock In.")
    # Expiry belongs to the batch that arrives.
    if transaction.expire_date is not None:
        if tx_type != "Restock":
            raise HTTPException(status_code=400, detail="An expiry date is only entered for Stock In.")
        if transaction.expire_date < transaction.transaction_date:
            raise HTTPException(status_code=400, detail="This batch has already expired. Check the expiry date.")
    if transaction.batch_number is not None and tx_type != "Restock":
        raise HTTPException(status_code=400, detail="A batch number is only entered for Stock In.")

    # --- Rules (decided 2026-11-01) ------------------------------------
    # Issue/Returns pages (inventory:issue without manage) record only
    # issues to a program and returns from one.
    if not can_manage:
        if tx_type == "Restock":
            raise HTTPException(status_code=403, detail="Stock In is done from the Stock page.")
        if tx_type == "Issue" and program_id is None and case_id is None:
            raise HTTPException(status_code=400, detail="Choose the program the stock is issued to.")
    # A return always names the program it comes back from. Unused stock
    # with no program is recorded as Stock In instead.
    if tx_type == "Return" and program_id is None:
        raise HTTPException(
            status_code=400,
            detail="Choose the program this stock is returned from. Stock that was never issued is added with Stock In.",
        )
    # Stock Out with no program is a stock adjustment (a write-off, a
    # breakage): allowed, but it must say why.
    if tx_type == "Issue" and program_id is None and case_id is None and not transaction.notes:
        raise HTTPException(status_code=400, detail="A stock adjustment needs a reason in the notes.")

    # --- Checks that need the database -----------------------------------
    # The database function repeats these under a row lock; doing them here
    # too gives the same clear messages on the fallback path.
    item = _get_item(supabase, transaction.item_id)
    if program_id is not None:
        program = _get_program(supabase, program_id)
        # I1: stock goes out only to a program that is running. Returns are
        # allowed from any program, so leftovers come back after it ends.
        if tx_type == "Issue" and normalize_status(program.get("status")) != ACTIVE:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Stock can only be issued to an Active program. "
                    f"'{program.get('program_name')}' is {normalize_status(program.get('status'))}."
                ),
            )

    if case_id is not None:
        cases = supabase.table("rescue_cases").select("id, status").eq("id", case_id).limit(1).execute().data
        if not cases:
            raise HTTPException(status_code=404, detail="Rescue case not found")
        # Open cases only, as stock goes only to Active programs.
        if cases[0].get("status") == "Resolved":
            raise HTTPException(status_code=400, detail="This case is resolved. Reopen it to record more supplies.")

    return_cost = None
    if tx_type == "Return":
        held = _outstanding_by_program(supabase, transaction.item_id, program_id).get(program_id)
        outstanding = (held["issued"] - held["returned"]) if held else 0
        if transaction.quantity > outstanding:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot return {transaction.quantity}: that program holds only "
                    f"{max(outstanding, 0)} of '{item['item_name']}' (issued minus already returned)."
                ),
            )
        return_cost = _return_cost(held, transaction.quantity)

    # Stock In at a new price: the movement is costed at what was paid and the
    # item keeps it as its stored cost (last price paid). The stored price
    # sent back unchanged is not a new price, so nothing extra is sent.
    stored_cost = round(float(item.get("unit_cost") or 0), 2)
    new_cost = None
    if transaction.unit_cost is not None and round(transaction.unit_cost, 2) != stored_cost:
        new_cost = round(transaction.unit_cost, 2)

    created_row, before, after = _record_movement(
        supabase,
        item_id=transaction.item_id,
        tx_type=tx_type,
        program_id=program_id,
        quantity=transaction.quantity,
        transaction_date=transaction.transaction_date.isoformat(),
        notes=transaction.notes,
        unit_cost=new_cost,
        expire_date=transaction.expire_date.isoformat() if transaction.expire_date else None,
        return_cost=return_cost,
        batch_number=transaction.batch_number,
        rescue_case_id=case_id,
    )
    created = _map_transaction_row(created_row)

    # The stock level either side of the movement is the part worth being
    # able to prove later; the transaction row alone doesn't show it. A price
    # change is recorded the same way.
    old_payload = {"item_id": transaction.item_id, "current_stock": before}
    new_payload = {**created, "current_stock": after}
    if new_cost is not None:
        old_payload["unit_cost"] = stored_cost
        new_payload["unit_cost"] = new_cost

    await log_audit_action(
        supabase,
        user_id=current_user["id"],
        action_type=_TRANSACTION_ACTION.get(tx_type, "INVENTORY_TRANSACTION"),
        table_name="inventory_transactions",
        old_payload=old_payload,
        new_payload=new_payload,
    )

    return created


@router.post("/transactions/{transaction_id}/reverse", response_model=InventoryTransaction)
async def reverse_transaction(
    transaction_id: int,
    body: MovementReverseRequest,
    # Undoing a movement is a Stock page action. Issue-only users (General
    # Staff) ask someone on the Stock page, as they do for adjustments.
    current_user: dict = Depends(require_permission('inventory:manage')),
    supabase: Client = Depends(get_supabase),
):
    """
    Undo a mistaken movement (I4) by recording the opposite one, dated today
    and at the same cost. The original stays in the history. Reversing a
    Stock In also voids the expense it posted to the ledger, so stock and
    money are corrected together. All of it happens in one database step
    (inventory_reverse_movement() in migration 019).
    """
    try:
        result = supabase.rpc(
            _REVERSE_RPC, {"p_transaction_id": transaction_id, "p_reason": body.reason}
        ).execute()
    except APIError as e:
        if _rpc_missing(e):
            raise HTTPException(status_code=503, detail=_MIGRATION_019_MESSAGE)
        status = 404 if getattr(e, "code", None) == "P0002" else 400
        raise HTTPException(status_code=status, detail=e.message or "The reversal was not saved.")

    row = result.data[0] if isinstance(result.data, list) else result.data
    if not row:
        raise HTTPException(status_code=400, detail="The reversal was not saved.")
    before = int(row.pop("stock_before", 0) or 0)
    after = int(row.pop("stock_after", 0) or 0)
    ledger_voided = int(row.pop("ledger_voided", 0) or 0)
    # O3 (020): the price put back when the latest Stock In was undone.
    price_restored = row.pop("unit_cost_restored", None)
    created = _map_transaction_row(row)

    await log_audit_action(
        supabase,
        user_id=current_user["id"],
        action_type="INVENTORY_REVERSAL",
        table_name="inventory_transactions",
        old_payload={"reversed_transaction_id": transaction_id, "item_id": created.get("item_id"),
                     "current_stock": before},
        new_payload={**created, "current_stock": after, "reason": body.reason,
                     "ledger_rows_voided": ledger_voided, "unit_cost_restored": price_restored},
    )
    return created


# ===================================================================
# BATCHES  (migration 020)
# ===================================================================

def _batch_order(batch: dict):
    """The order Stock Out takes batches in: soonest expiry first, no expiry
    last, then the oldest."""
    return (batch.get("expire_date") is None, str(batch.get("expire_date") or ""),
            str(batch.get("received_date") or ""), batch["id"])


@router.get("/batches", response_model=List[InventoryBatch])
async def get_batches(
    # The Stock page lists every item's batches with their prices.
    current_user: dict = Depends(require_permission('inventory:read')),
    supabase: Client = Depends(get_supabase),
):
    """Every batch with stock left, grouped by item in Stock Out order.
    Empty before migration 020."""
    try:
        response = supabase.table("inventory_batches").select("*").gt("quantity_remaining", 0).execute()
    except APIError as e:
        if _is_missing_table(e, "inventory_batches"):
            return []
        raise
    return sorted(response.data or [], key=lambda b: (b["item_id"], *_batch_order(b)))


@router.get("/items/{item_id}/batches", response_model=List[InventoryBatch])
async def get_item_batches(
    item_id: int,
    # Shown in the Stock page's Edit Item dialog.
    current_user: dict = Depends(require_permission('inventory:read')),
    supabase: Client = Depends(get_supabase),
):
    """An item's batches with stock left, soonest expiry first (the order
    Stock Out takes them in). Empty before migration 020."""
    _get_item(supabase, item_id)
    try:
        response = (
            supabase.table("inventory_batches")
            .select("*")
            .eq("item_id", item_id)
            .gt("quantity_remaining", 0)
            .execute()
        )
    except APIError as e:
        if _is_missing_table(e, "inventory_batches"):
            return []
        raise
    return sorted(response.data or [], key=_batch_order)


@router.patch("/batches/{batch_id}", response_model=InventoryBatch)
async def update_batch(
    batch_id: int,
    changes: InventoryBatchUpdate,
    current_user: dict = Depends(require_permission('inventory:manage')),
    supabase: Client = Depends(get_supabase),
):
    """Correct a batch's number, expiry date or unit price. The item's expiry
    is then worked out again from its batches. A new price on the item's
    newest batch also becomes the item's stored price (what Stock In
    suggests next time)."""
    data = changes.model_dump(mode="json", exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to change.")
    try:
        existing = supabase.table("inventory_batches").select("*").eq("id", batch_id).limit(1).execute()
    except APIError as e:
        if _is_missing_table(e, "inventory_batches"):
            raise HTTPException(status_code=503, detail=_MIGRATION_020_MESSAGE)
        raise
    if not existing.data:
        raise HTTPException(status_code=404, detail="Batch not found")
    before = existing.data[0]

    response = supabase.table("inventory_batches").update(data).eq("id", batch_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Batch not found")
    after = response.data[0]
    supabase.rpc("inventory_refresh_expiry", {"p_item_id": before["item_id"]}).execute()

    if "unit_cost" in data:
        newest = (
            supabase.table("inventory_batches")
            .select("id, received_date")
            .eq("item_id", before["item_id"])
            .execute()
        )
        newest_id = max(
            (newest.data or [after]), key=lambda b: (str(b.get("received_date") or ""), b["id"])
        )["id"]
        if newest_id == batch_id:
            supabase.table("inventory_items").update({"unit_cost": data["unit_cost"]}).eq(
                "id", before["item_id"]
            ).execute()

    await log_audit_action(
        supabase,
        user_id=current_user["id"],
        action_type="INVENTORY_BATCH_UPDATE",
        table_name="inventory_batches",
        old_payload={"id": batch_id, "item_id": before["item_id"], **{k: before.get(k) for k in data}},
        new_payload={"id": batch_id, "item_id": before["item_id"], **{k: after.get(k) for k in data}},
    )
    return after


# ===================================================================
# ALERTS  (write-up Section 7 & 8)
# ===================================================================

@router.get("/alerts/low-stock", response_model=List[LowStockItem])
async def get_low_stock_items(
    # The line for items with no reorder level of their own (I8).
    threshold: int = Query(default=DEFAULT_REORDER_LEVEL, ge=0, le=100_000),
    user=Depends(_ANY_INVENTORY),
    supabase: Client = Depends(get_supabase),
):
    return low_stock_items(supabase, threshold)


def low_stock_items(supabase: Client, threshold: int = DEFAULT_REORDER_LEVEL) -> list[dict]:
    """Items below their reorder level, lowest first. Also counted by the
    inbox (app/api/inbox.py)."""
    # Each item is compared with its own reorder level. PostgREST cannot
    # compare two columns, so the (small) item list is filtered here. "*"
    # keeps this working before migration 019 adds reorder_level.
    response = supabase.table("inventory_items").select("*").execute()
    low = []
    for item in response.data or []:
        level = item.get("reorder_level")
        level = threshold if level is None else int(level)
        stock = int(item.get("current_stock") or 0)
        if stock < level:
            low.append({
                "id": item["id"],
                "item_name": item["item_name"],
                "current_stock": stock,
                "supplier_name": item.get("supplier_name"),
                "reorder_level": level,
            })
    return sorted(low, key=lambda i: (i["current_stock"], i["item_name"].lower()))


@router.get("/alerts/expiring", response_model=List[ExpiringItem])
async def get_expiring_items(
    days: int = Query(default=30, ge=0, le=3650),
    user=Depends(_ANY_INVENTORY),
    supabase: Client = Depends(get_supabase),
):
    return expiring_items(supabase, days)


def expiring_items(supabase: Client, days: int = 30) -> list[dict]:
    """Items on the shelf that have expired or expire within `days`. Also
    counted by the inbox (app/api/inbox.py)."""
    # "Expiring" = already expired OR expiring within the next `days` days.
    # We don't filter out already-expired items here on purpose: those are
    # arguably the MOST urgent ones to show, not something to hide.
    cutoff = today_in_sri_lanka() + timedelta(days=days)
    response = (
        supabase.table("inventory_items")
        .select("id, item_name, expire_date, current_stock")
        .not_.is_("expire_date", "null")
        # Only stock still on the shelf. An empty item's old date is not a
        # warning anyone can act on.
        .gt("current_stock", 0)
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
    user=Depends(_ANY_INVENTORY),
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
