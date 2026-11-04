from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from datetime import date
from typing import Optional
from decimal import Decimal
from enum import Enum

# --- Program Schemas ---
class ProgramBase(BaseModel):
    program_name: str
    total_animals_treated: int = 0
    status: str = "Active"

class ProgramCreate(ProgramBase):
    # Accepted for backwards compatibility but IGNORED: every new program
    # starts as Upcoming (see create_program and the program lifecycle).
    status: str = "Upcoming"
    # Optional planned start; replaced by the real day when it is started.
    start_date: Optional[date] = None
    # Where it takes place. Required for every new program; trimmed, and a
    # blank or whitespace-only value is refused (422).
    location: str = Field(..., min_length=1, max_length=200)

    @field_validator("location", mode="before")
    @classmethod
    def _trim_location(cls, v):
        return v.strip() if isinstance(v, str) else v

class Program(ProgramBase):
    id: int
    location: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

# --- Enums (matching DB values exactly) ---
class TransactionType(str, Enum):
    INCOME = "Income"
    EXPENSE = "Expense"

class TransactionStatus(str, Enum):
    CASH = "Cash"
    RECEIVABLE = "Receivable"
    VOIDED = "Voided"

# --- Financial Transaction Schemas ---
class FinancialTransactionBase(BaseModel):
    transaction_date: date
    amount: Decimal = Field(..., max_digits=12, decimal_places=2)
    transaction_type: TransactionType
    status: TransactionStatus
    program_id: Optional[int] = None
    # Donor earmarked this money for program_id and it may not be spent
    # elsewhere. Defaults False so every existing caller and stored row is
    # unrestricted without change.
    is_restricted: bool = False

    @model_validator(mode="after")
    def _restricted_requires_program(self):
        """
        'Restricted' with no program asserts the money is earmarked without
        saying what for, which no downstream calculation can act on.

        This duplicates the CHECK in migration 002 on purpose: init.sql has
        drifted from the live database and its constraints are not replayed
        there, so the application layer is the enforcement that can be relied
        on today. See the note at the top of 002_restricted_funds.sql.
        """
        if self.is_restricted and self.program_id is None:
            raise ValueError("A restricted transaction must be linked to a program.")
        return self

class FinancialTransactionCreate(FinancialTransactionBase):
    pass


# --- Restricted Fund Schemas ---
class RestrictedBalance(BaseModel):
    """
    Drawdown position of one program's earmarked funds.

    float, not Decimal, on the way out. The comparison that decides whether an
    expense is allowed runs in Decimal inside compute_restricted_balance, which
    is where precision matters. Pydantic serializes Decimal to a JSON *string*,
    and every other finance endpoint (/aging, /summary/monthly) already returns
    JSON numbers that the frontend calls .toLocaleString() on — emitting
    "600.00" here would break that silently.
    """
    program_id: int
    raised: float
    spent: float
    remaining: float

# Add this tiny class right above your FinancialTransaction class
class LinkedProgram(BaseModel):
    program_name: str

# Update your existing response model to include the linked program
class FinancialTransaction(FinancialTransactionBase):
    id: int
    programs: Optional[LinkedProgram] = None  # This catches the joined data!
    # Where the row came from (migration 013): donation, stock_in, payroll or
    # manual. Response only: it is set by the database (default 'manual') and
    # by the Stock In / payroll triggers, never by the client.
    source_type: Optional[str] = None
    # The Stock In movement a stock_in row was posted for (migration 016).
    # NULL on every other row, and set only by the database.
    inventory_transaction_id: Optional[int] = None

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={Decimal: float}
    )


class VoidTransactionRequest(BaseModel):
    """
    Optional body of PATCH /transactions/{id}/void. The reason is written to
    the audit entry. It is required for a Stock In expense: voiding one
    leaves the stock it paid for in Inventory, so the record has to say why.
    """
    reason: Optional[str] = Field(default=None, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def _blank_reason_is_none(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value


class StockMovementRef(BaseModel):
    """The Stock In behind a stock_in expense, for the void warning: what to
    correct in Inventory if the expense is voided."""
    inventory_transaction_id: int
    item_name: Optional[str] = None
    quantity: int
    transaction_date: Optional[date] = None
    total_cost: float