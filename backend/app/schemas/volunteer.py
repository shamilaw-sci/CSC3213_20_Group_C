# backend/app/schemas/volunteer.py

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from datetime import datetime, date, time
from enum import Enum
from uuid import UUID
from typing import Optional, Literal


class VolunteerStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    inactive = "inactive"


class AssignmentResponse(str, Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"


# Mirrors the CHECK constraints in db/migrations/004_volunteers.sql. Duplicated
# deliberately: the database constraint is the guarantee, this is the error
# message. Without it a bad value is a 500 from Postgres instead of a 422
# naming the offending field.
class Skill(str, Enum):
    animal_handling = "animal_handling"
    transport_driving = "transport_driving"
    veterinary = "veterinary"
    fostering = "fostering"
    fundraising = "fundraising"
    admin_office = "admin_office"
    media_photography = "media_photography"
    community_outreach = "community_outreach"


class Availability(str, Enum):
    weekday_mornings = "weekday_mornings"
    weekday_afternoons = "weekday_afternoons"
    weekday_evenings = "weekday_evenings"
    weekends = "weekends"
    on_call = "on_call"


# ---------------------------------------------------------------------------
# Public application
# ---------------------------------------------------------------------------

class VolunteerApply(BaseModel):
    """The public form. Note what is absent: status, access_token and every
    review field. A caller cannot propose their own approval state."""
    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=40)
    skills: list[Skill] = Field(default_factory=list)
    skills_other: Optional[str] = Field(default=None, max_length=500)
    availability: list[Availability] = Field(default_factory=list)

    @field_validator("skills", "availability")
    @classmethod
    def _dedupe(cls, v):
        # The form posts checkbox groups; a repeated value would otherwise be
        # stored twice and render twice on the roster.
        return list(dict.fromkeys(v))


class VolunteerApplyAccepted(BaseModel):
    """
    Deliberately says nothing about what happened.

    The same response is returned whether a row was inserted or the partial
    unique index rejected a duplicate live application, so the form cannot be
    used to test whether an address is already an approved volunteer.
    """
    message: str = "Thank you for applying. We will be in touch."


# ---------------------------------------------------------------------------
# Staff roster
# ---------------------------------------------------------------------------

class VolunteerOut(BaseModel):
    """Staff-facing. Carries access_token, so it must never be returned from a
    public route — see MyAssignments* below for what the volunteer sees."""
    id: UUID
    full_name: str
    email: str
    phone: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    skills_other: Optional[str] = None
    availability: list[str] = Field(default_factory=list)
    status: VolunteerStatus
    access_token: str
    link_shared_at: Optional[datetime] = None
    applied_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[UUID] = None
    staff_notes: Optional[str] = None


class VolunteerReview(BaseModel):
    """Approve or reject a pending application, deactivate an approved
    volunteer, or reactivate an inactive one (V2). Every other change is
    refused by the endpoint; see _REVIEW_TRANSITIONS in api/volunteers.py.

    'pending' is not a reachable target: an application starts there and review
    is a one-way door out of it. A rejected applicant can apply again instead.
    """
    status: Literal[
        VolunteerStatus.approved,
        VolunteerStatus.rejected,
        VolunteerStatus.inactive,
    ]
    staff_notes: Optional[str] = Field(default=None, max_length=1000)


# ---------------------------------------------------------------------------
# Shifts
# ---------------------------------------------------------------------------

class ShiftBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    location: Optional[str] = Field(default=None, max_length=300)
    # Wall-clock, matching the columns. See the migration for why not tz-aware.
    shift_date: date
    start_time: time
    end_time: time
    volunteers_needed: int = Field(default=1, ge=1, le=200)
    # The programme this shift is for (migration 022). Older shifts have none
    # and are matched to a programme by title.
    program_id: Optional[int] = None

    @field_validator("end_time")
    @classmethod
    def _ends_after_start(cls, v, info):
        start = info.data.get("start_time")
        if start is not None and v <= start:
            raise ValueError("end_time must be after start_time")
        return v


class ShiftCreate(ShiftBase):
    pass


class ShiftUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    location: Optional[str] = Field(default=None, max_length=300)
    shift_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    volunteers_needed: Optional[int] = Field(default=None, ge=1, le=200)
    is_cancelled: Optional[bool] = None


class ShiftOut(ShiftBase):
    id: UUID
    is_cancelled: bool
    created_by: Optional[UUID] = None
    created_at: datetime
    # Set on create when the date falls outside the programme's dates (V9).
    # A note for the user, not stored.
    warning: Optional[str] = None


class ShiftConfirmation(BaseModel):
    """
    The roster's headline: "Saturday clinic — 6 assigned: 4 accepted, 1
    declined, 1 awaiting response". Surfacing this is the main operational
    point of the whole feature, so it is a first-class response model rather
    than something the UI derives by counting rows itself.
    """
    assigned: int
    accepted: int
    declined: int
    awaiting: int
    needed: int

    @property
    def shortfall(self) -> int:
        return max(0, self.needed - self.accepted)


class ShiftWithConfirmation(ShiftOut):
    confirmation: ShiftConfirmation


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------

AssignmentType = Literal["shift", "rescue_case", "program"]


class AssignmentCreate(BaseModel):
    """Exactly one target, mirroring the num_nonnulls CHECK on the table.

    Validated here as well as in the database so the caller gets a 422 naming
    the problem rather than a 500 carrying a raw constraint violation. A model
    validator, not a field validator (V3): a field validator does not run when
    its field is left out, so a body with no program_id skipped the check.
    """
    volunteer_id: UUID
    shift_id: Optional[UUID] = None
    rescue_case_id: Optional[UUID] = None
    program_id: Optional[int] = None

    @model_validator(mode="after")
    def _exactly_one_target(self):
        targets = [self.shift_id, self.rescue_case_id, self.program_id]
        if sum(t is not None for t in targets) != 1:
            raise ValueError(
                "exactly one of shift_id, rescue_case_id or program_id is required"
            )
        return self


class AssignmentOut(BaseModel):
    id: UUID
    volunteer_id: UUID
    shift_id: Optional[UUID] = None
    rescue_case_id: Optional[UUID] = None
    program_id: Optional[int] = None
    response: AssignmentResponse
    decline_reason: Optional[str] = None
    responded_at: Optional[datetime] = None
    assigned_by: Optional[UUID] = None
    assigned_at: datetime
    # Set on create when the shift already has as many volunteers as it needs
    # (V4: warn, don't block). A note for the user, not stored.
    warning: Optional[str] = None

    @property
    def assignment_type(self) -> AssignmentType:
        # Derived, never stored — a stored copy could disagree with the FKs.
        if self.shift_id is not None:
            return "shift"
        if self.rescue_case_id is not None:
            return "rescue_case"
        return "program"


# ---------------------------------------------------------------------------
# Tokenized volunteer view — the public shape
# ---------------------------------------------------------------------------

class MyAssignment(BaseModel):
    """
    One assignment as the volunteer sees it.

    Flattened on purpose. The staff shape nests the target's own row, which for
    a rescue case would carry reporter details and coordinates the volunteer has
    no business reading. This model names every field that crosses the boundary,
    so widening it is a deliberate edit rather than a side effect of someone
    adding a column to rescue_cases.
    """
    id: UUID
    assignment_type: AssignmentType
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    # Shift assignments have a when; case and program assignments may not.
    shift_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    is_cancelled: bool = False
    response: AssignmentResponse
    decline_reason: Optional[str] = None
    responded_at: Optional[datetime] = None
    assigned_at: datetime


class MyAssignmentsOut(BaseModel):
    """
    The tokenized page's whole payload.

    Carries the volunteer's first name only — enough to make the page feel
    addressed to them, without restating the email and phone number back to
    whoever is holding the link. No id, no token, no staff notes, no status
    history.
    """
    volunteer_name: str
    assignments: list[MyAssignment]


class AssignmentRespond(BaseModel):
    response: Literal[AssignmentResponse.accepted, AssignmentResponse.declined]
    decline_reason: Optional[str] = Field(default=None, max_length=500)

    @field_validator("decline_reason")
    @classmethod
    def _reason_only_on_decline(cls, v, info):
        if v and info.data.get("response") != AssignmentResponse.declined:
            raise ValueError("decline_reason is only valid when declining")
        return v
