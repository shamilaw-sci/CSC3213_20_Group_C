from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import date
from typing import Optional, Literal


# ─── Inventory Items ──────────────────────────────────────────────────────────

class InventoryItemBase(BaseModel):
    item_name: str = Field(..., min_length=1, max_length=200)
    current_stock: int = Field(default=0, ge=0)
    unit_cost: float = Field(default=0.0, ge=0)
    supplier: Optional[str] = None


class InventoryItemCreate(InventoryItemBase):
    pass


class InventoryItem(InventoryItemBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# ─── Stock Action Schemas ─────────────────────────────────────────────────────

class StockInCreate(BaseModel):
    item_id: int = Field(..., description="ID of inventory item")
    quantity: int = Field(..., gt=0, description="Quantity to add")
    unit_price: Optional[float] = Field(None, ge=0)
    supplier: Optional[str] = None
    transaction_date: date = Field(default_factory=date.today)
    reason_notes: Optional[str] = None
    program_id: Optional[int] = None

    @field_validator('transaction_date')
    @classmethod
    def no_future_date(cls, v: date) -> date:
        if v > date.today():
            raise ValueError('Transaction date cannot be in the future')
        return v


class StockOutCreate(BaseModel):
    item_id: int = Field(..., description="ID of inventory item")
    quantity: int = Field(..., gt=0)
    transaction_date: date = Field(default_factory=date.today)
    reason_notes: Optional[str] = None
    program_id: Optional[int] = None

    @field_validator('transaction_date')
    @classmethod
    def no_future_date(cls, v: date) -> date:
        if v > date.today():
            raise ValueError('Transaction date cannot be in the future')
        return v


class StockReturnCreate(BaseModel):
    item_id: int = Field(..., description="ID of inventory item")
    quantity: int = Field(..., gt=0)
    supplier: Optional[str] = None
    reason_notes: Optional[str] = None
    program_id: Optional[int] = None


class AddItemCreate(BaseModel):
    item_name: str = Field(..., min_length=1, max_length=200)
    initial_quantity: int = Field(default=0, ge=0)
    unit_cost: float = Field(default=0.0, ge=0)


# ─── Inventory Transactions ───────────────────────────────────────────────────

class InventoryTransactionBase(BaseModel):
    item_id: int
    program_id: Optional[int] = None
    quantity: int = Field(gt=0)
    transaction_type: Literal["Issue", "Return", "restock"]
    transaction_date: date

    @field_validator('transaction_date')
    @classmethod
    def prevent_future_dates(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("Transaction date cannot be in the future")
        return v


class InventoryTransactionCreate(InventoryTransactionBase):
    pass


class InventoryTransaction(InventoryTransactionBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# ─── Analytics ───────────────────────────────────────────────────────────────

class CostPerAnimal(BaseModel):
    program_id: int
    program_name: str
    total_cost: float
    animals_treated: int
    cost_per_animal: float
    model_config = ConfigDict(from_attributes=True)
