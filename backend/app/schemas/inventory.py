from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional


# The three stock movements the system records. Anything else is refused at
# the edge, before it can reach the stock maths in app/api/inventory.py.
TransactionType = Literal["Issue", "Return", "Restock"]

# Upper bound on a single movement. Far above any real clinic order, low
# enough that a typo (or a deliberate 10**12) cannot overflow current_stock.
MAX_QUANTITY = 100_000

# Sri Lanka has no daylight saving, so a fixed +05:30 offset is exact and
# avoids depending on the tz database being installed.
_SRI_LANKA = timezone(timedelta(hours=5, minutes=30))


def today_in_sri_lanka() -> date:
    """Today's date where the clinics are. The server may run on UTC, which
    is still 'yesterday' until 05:30 local time."""
    return datetime.now(_SRI_LANKA).date()


class InventoryItemBase(BaseModel):
    item_name: str
    current_stock: int = 0
    unit_cost: float
    # These two already exist in your live DB (we confirmed via screenshot),
    # but were missing from this schema, so the API was silently ignoring them.
    expire_date: Optional[date] = None
    supplier_name: Optional[str] = None


# What the client sends to create an item. The rules live here and not on the
# base class, so that reading an older row that breaks them (a 0 unit cost,
# say) never turns a GET into a 500.
class InventoryItemCreate(InventoryItemBase):
    item_name: str = Field(min_length=1, max_length=255)
    current_stock: int = Field(default=0, ge=0, le=MAX_QUANTITY)
    unit_cost: float = Field(gt=0, le=100_000_000)
    supplier_name: Optional[str] = Field(default=None, max_length=255)

    @field_validator("item_name", mode="before")
    @classmethod
    def _strip_name(cls, value):
        # "  " must count as empty (min_length then refuses it), and stray
        # spaces must not create a second item that only differs by whitespace.
        return value.strip() if isinstance(value, str) else value

    @field_validator("supplier_name", mode="before")
    @classmethod
    def _blank_supplier_is_none(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value


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
#
# quantity must be a positive whole number: the stock maths adds it for a
# Return/Restock and subtracts it for an Issue, so a negative value would turn
# an Issue into a hidden restock (and skip the stock check) and a Return into
# a hidden issue that can drive stock below zero.
class InventoryTransactionCreate(InventoryTransactionBase):
    quantity: int = Field(gt=0, le=MAX_QUANTITY)
    transaction_type: TransactionType
    notes: Optional[str] = Field(default=None, max_length=500)

    @field_validator("notes", mode="before")
    @classmethod
    def _blank_notes_are_none(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    # Back-dating is allowed (a movement recorded the next day); a date that
    # has not happened yet is not (decided 2026-11-01).
    @field_validator("transaction_date")
    @classmethod
    def _not_in_the_future(cls, value: date):
        if value > today_in_sri_lanka():
            raise ValueError("Date cannot be in the future")
        return value


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


# How much of one item a program still holds: everything issued to it, less
# everything already returned from it. The Returns form uses this to offer
# only programs that actually have something to give back.
class OutstandingByProgram(BaseModel):
    program_id: int
    program_name: Optional[str] = None
    issued: int
    returned: int
    outstanding: int


class CostPerAnimalResult(BaseModel):
    program_id: int
    program_name: str
    inventory_cost: float
    other_cost: float
    total_cost: float
    animals_treated: int
    cost_per_animal: float
