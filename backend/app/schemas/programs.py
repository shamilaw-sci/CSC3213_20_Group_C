from pydantic import BaseModel, ConfigDict
from datetime import datetime, date
from typing import Optional


# --- Full program record, including the fields added in the Step 1 migration
# (start_date, end_date) and the DB-trigger-maintained total_cost.
# Kept separate from app.schemas.finance.Program so we never need to touch
# that shared file. ---
class ProgramDetail(BaseModel):
    id: int
    program_name: str
    total_animals_treated: int = 0
    status: str = "Active"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    total_cost: Optional[float] = 0

    model_config = ConfigDict(from_attributes=True)


# --- Financial summary for a program: Revenue (from financial_transactions)
# vs. total_cost (the DB-trigger-maintained field on `programs`). ---
class ProgramFinancials(BaseModel):
    program_id: int
    revenue: float
    total_cost: float
    profit: float


# --- What the client sends to assign a worker to a program ---
class ProgramAssignmentCreate(BaseModel):
    employee_id: int
    role_on_program: Optional[str] = None  # e.g. "Veterinarian", "Field Officer"


# --- Minimal employee info we embed inside a team member row ---
# (keeps this file independent from app.schemas.hr, so no cross-module coupling)
class EmployeeBasic(BaseModel):
    id: int
    first_name: str
    last_name: str


# --- What we return for each assigned worker ---
class ProgramAssignment(BaseModel):
    id: int
    program_id: int
    employee_id: int
    role_on_program: Optional[str] = None
    assigned_at: datetime
    employee_profile: Optional[EmployeeBasic] = None  # populated via Supabase join

    model_config = ConfigDict(from_attributes=True)