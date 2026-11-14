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
    # Hidden (None) from users who may not see program costs (P3).
    total_cost: Optional[float] = 0
    # NULL on programs created before locations were recorded (migration 011).
    location: Optional[str] = None
    # The public listing (migration 035). Defaults cover the rows read before
    # the migration is applied.
    is_public: bool = False
    program_type: Optional[str] = None
    public_venue: Optional[str] = None
    public_schedule: Optional[str] = None
    public_notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# What the public is told a program is. Mirrors programs_program_type_known.
PROGRAM_TYPES = ("Sterilization", "Vaccination", "Free Clinic", "Awareness", "Other")


def _squash(v):
    """Collapse runs of whitespace; a blank string becomes None (cleared)."""
    if not isinstance(v, str):
        return v
    v = " ".join(v.split())
    return v or None


# --- PUT /{id}/public-listing: publish a program on the public /clinics page,
# change what it says, or take it down. The whole listing is sent each time,
# so clearing a field is sending it empty. Notes keep their line breaks. ---
class ProgramPublicListingUpdate(BaseModel):
    is_public: bool
    program_type: Optional[str] = None
    public_venue: Optional[str] = Field(None, max_length=200)
    public_schedule: Optional[str] = Field(None, max_length=200)
    public_notes: Optional[str] = Field(None, max_length=1000)

    @field_validator("public_venue", "public_schedule", "program_type", mode="before")
    @classmethod
    def _trim(cls, v):
        return _squash(v)

    @field_validator("public_notes", mode="before")
    @classmethod
    def _trim_notes(cls, v):
        if not isinstance(v, str):
            return v
        v = "\n".join(" ".join(line.split()) for line in v.strip().splitlines())
        return v or None

    @field_validator("program_type")
    @classmethod
    def _known_type(cls, v):
        if v is not None and v not in PROGRAM_TYPES:
            raise ValueError(f"program_type must be one of: {', '.join(PROGRAM_TYPES)}.")
        return v


# --- GET /public: one card on the public /clinics page. Only what a member of
# the public needs to turn up; no costs, team, volunteers or counts. ---
class PublicProgram(BaseModel):
    id: int
    program_name: str
    program_type: Optional[str] = None
    status: str
    location: Optional[str] = None
    public_venue: Optional[str] = None
    public_schedule: Optional[str] = None
    public_notes: Optional[str] = None
    start_date: Optional[date] = None


# --- POST /{id}/complete: the final count, recorded as the program closes.
# A whole number, zero allowed (a program can end having treated none);
# strict so 12.5 or "12" is refused rather than silently coerced.
# end_date: the day it ended, today if left out (P6). Not in the future and
# not before the start date (checked in the endpoint).
# confirm_open_items: complete even though the program still holds stock or
# has shifts after the end date (P4). ---
class ProgramCompleteRequest(BaseModel):
    total_animals_treated: int = Field(..., ge=0, strict=True)
    end_date: Optional[date] = None
    confirm_open_items: bool = False


# --- GET /{id}/open-items: what is still out when a program is completed. ---
class ProgramHeldStock(BaseModel):
    item_id: int
    item_name: Optional[str] = None
    outstanding: int


class ProgramUpcomingShift(BaseModel):
    shift_id: str
    title: str
    shift_date: date


class ProgramOpenItems(BaseModel):
    stock_held: List[ProgramHeldStock] = []
    shifts_after: List[ProgramUpcomingShift] = []


# --- GET /assignable-employees: just enough to pick a worker (P1). ---
class AssignableEmployee(BaseModel):
    id: int
    first_name: str
    last_name: str


# --- PATCH /{id}: the fields staff may edit after a program exists. Status
# moves through /start, /complete and /cancel instead. Name and planned start
# date can be corrected while the program is Upcoming (P5). ---
class ProgramUpdate(BaseModel):
    program_name: Optional[str] = Field(None, min_length=1, max_length=255)
    start_date: Optional[date] = None
    location: Optional[str] = Field(None, min_length=1, max_length=200)
    # Correcting the final count of a COMPLETED program (the API refuses it at
    # other stages, where it is not recorded yet).
    total_animals_treated: Optional[int] = Field(None, ge=0, strict=True)

    @field_validator("location", "program_name", mode="before")
    @classmethod
    def _trim_location(cls, v):
        return " ".join(v.split()) if isinstance(v, str) else v

    @model_validator(mode="after")
    def _something_to_change(self):
        if all(v is None for v in (self.program_name, self.start_date, self.location,
                                   self.total_animals_treated)):
            raise ValueError(
                "Nothing to update: send program_name, start_date, location or total_animals_treated."
            )
        return self


# --- One card on a lifecycle page (GET /api/programs?status=...): the
# program plus the figures shown on its face. cost_per_animal is
# total_cost / animals treated, None when no animals are recorded yet. ---
# Revenue and profit are None for users without finance:read, and total cost
# and cost per animal for users who may not see program costs (P3). ---
class ProgramSummary(ProgramDetail):
    team_count: int = 0
    volunteer_count: int = 0
    revenue: Optional[float] = 0
    profit: Optional[float] = 0
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
