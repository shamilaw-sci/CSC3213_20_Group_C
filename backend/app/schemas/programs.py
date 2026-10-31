from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
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
    # NULL on programs created before locations were recorded (migration 011).
    location: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# --- POST /{id}/complete: the final count, recorded as the program closes.
# A whole number, zero allowed (a program can end having treated none);
# strict so 12.5 or "12" is refused rather than silently coerced. ---
class ProgramCompleteRequest(BaseModel):
    total_animals_treated: int = Field(..., ge=0, strict=True)


# --- PATCH /{id}: the fields staff may edit after a program exists. Only
# location for now; status moves through /start and /complete instead. ---
class ProgramUpdate(BaseModel):
    location: Optional[str] = Field(None, min_length=1, max_length=200)
    # Correcting the final count of a COMPLETED program (the API refuses it at
    # other stages, where it is not recorded yet).
    total_animals_treated: Optional[int] = Field(None, ge=0, strict=True)

    @field_validator("location", mode="before")
    @classmethod
    def _trim_location(cls, v):
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _something_to_change(self):
        if self.location is None and self.total_animals_treated is None:
            raise ValueError("Nothing to update: send location and/or total_animals_treated.")
        return self


# --- One card on a lifecycle page (GET /api/programs?status=...): the
# program plus the figures shown on its face. cost_per_animal is
# total_cost / animals treated, None when no animals are recorded yet. ---
class ProgramSummary(ProgramDetail):
    team_count: int = 0
    volunteer_count: int = 0
    revenue: float = 0
    profit: float = 0
    cost_per_animal: Optional[float] = None


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
