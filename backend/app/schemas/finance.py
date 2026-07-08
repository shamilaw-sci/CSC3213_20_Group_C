from pydantic import BaseModel, ConfigDict
from datetime import date
from typing import Optional

class ProgramBase(BaseModel):
    program_name: str
    total_animals_treated: int = 0
    status: str = "Active"
    budget_amount: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

class ProgramCreate(ProgramBase):
    pass


class Program(ProgramBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class FinancialTransactionBase(BaseModel):
    transaction_date: date
    amount: float
    transaction_type: str  # Enum: Income, Expense
    status: str           # Enum: Cash, Receivable
    program_id: Optional[int] = None

class FinancialTransactionCreate(FinancialTransactionBase):
    pass

class FinancialTransaction(FinancialTransactionBase):
    id: int
    model_config = ConfigDict(from_attributes=True)
