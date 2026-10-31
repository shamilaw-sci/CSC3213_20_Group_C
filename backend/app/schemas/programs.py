from pydantic import BaseModel, ConfigDict
from datetime import datetime, date, time
from typing import List, Optional


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


# --- Volunteers who accepted work on a program (GET /{id}/volunteers). ---
# No email, phone or access_token: programs:read reaches Finance Officer,
# which has no volunteers:read, so contact details stay behind that gate.
class ProgramVolunteerShift(BaseModel):
    shift_id: str
    title: str
    shift_date: date
    start_time: time
    end_time: time
    location: Optional[str] = None
    responded_at: Optional[datetime] = None


class ProgramVolunteer(BaseModel):
    volunteer_id: str
    full_name: str
    skills: List[str] = []
    skills_other: Optional[str] = None
    # True when the volunteer accepted a direct assignment to the program
    # itself, rather than (or as well as) one of its shifts.
    program_assignment: bool = False
    shifts: List[ProgramVolunteerShift] = []
