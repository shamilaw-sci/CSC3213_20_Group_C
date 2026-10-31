from pydantic import BaseModel, ConfigDict
from datetime import date
from typing import Optional


class InventoryItemBase(BaseModel):
    item_name: str
    current_stock: int = 0
    unit_cost: float
    # These two already exist in your live DB (we confirmed via screenshot),
    # but were missing from this schema, so the API was silently ignoring them.
    expire_date: Optional[date] = None
    supplier_name: Optional[str] = None


class InventoryItemCreate(InventoryItemBase):
    pass


class InventoryItem(InventoryItemBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class InventoryTransactionBase(BaseModel):
    item_id: int
    program_id: Optional[int] = None
    quantity: int
    # Now includes 'Restock', matching the updated CHECK constraint in the DB.
    transaction_type: str  # Enum: Issue, Return, Restock
    transaction_date: date
    # The Stock In form sends a free-text note and inventory_transactions has a
    # `notes` column, but this field was missing, so the note was silently dropped.
    notes: Optional[str] = None


# What the CLIENT sends us to create a transaction. Deliberately has NO
# total_cost field — the client never gets to decide what something cost.
# The database calculates that itself (quantity * unit_cost) inside
# process_inventory_transaction(), so a buggy or malicious request can't
# fake a cost.
class InventoryTransactionCreate(InventoryTransactionBase):
    pass


# ---------------------------------------------------------------
# Small nested references returned with each transaction.
#
# GET /inventory/transactions already asks Supabase for
#   "*, inventory_items(item_name), programs(program_name)"
# but FastAPI only returns the fields declared on the response model,
# so those two joined names were being thrown away before they reached
# the browser. Declaring them here lets them through.
# Both are Optional because a transaction may have no program, and the
# POST /transactions response does not include the joins at all.
# ---------------------------------------------------------------
class TransactionItemRef(BaseModel):
    item_name: str


class TransactionProgramRef(BaseModel):
    program_name: str


# What we return to the client.
#
# IMPORTANT: your live database's primary key column on this table is
# actually called `transaction_id`, not `id` (you renamed it manually,
# and init.sql was never updated to match). Rather than making the
# frontend deal with that inconsistent name, the API layer (inventory.py)
# explicitly renames transaction_id -> id on every row BEFORE handing it
# to this model, using a small helper function. That keeps the rename
# visible and easy to find, instead of hiding it inside a serialization
# alias that behaves differently for input vs output.
class InventoryTransaction(InventoryTransactionBase):
    id: int
    total_cost: float = 0
    inventory_items: Optional[TransactionItemRef] = None
    programs: Optional[TransactionProgramRef] = None
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------
# Response models for the new alert / analytics endpoints
# ---------------------------------------------------------------

class LowStockItem(BaseModel):
    id: int
    item_name: str
    current_stock: int
    supplier_name: Optional[str] = None


class ExpiringItem(BaseModel):
    id: int
    item_name: str
    expire_date: date
    current_stock: int


class CostPerAnimalResult(BaseModel):
    program_id: int
    program_name: str
    inventory_cost: float
    other_cost: float
    total_cost: float
    animals_treated: int
    cost_per_animal: float