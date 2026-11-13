from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from uuid import UUID
from typing import Literal, Optional


class CaseStatus(str, Enum):
    reported = "Reported"
    in_treatment = "In Treatment"
    resolved = "Resolved"


class CaseOutcome(str, Enum):
    """What "Resolved" meant for the animal. Fixed, so reports can count them;
    the same five values are CHECKed in 030_case_timeline_outcome.sql."""
    released = "Released"
    rehomed = "Rehomed"
    transferred = "Transferred"  # to a vet or another shelter
    died = "Died"
    not_found = "Not found"  # the animal could not be located


class RescueCaseGeo(BaseModel):
    id: str
    animal_type: str
    status: CaseStatus
    lat: float
    lng: float
    reported_at: datetime


class CaseCreate(BaseModel):
    animal_type: str
    description: Optional[str] = None
    lat: float
    lng: float
    photo_url: Optional[str] = None
    reported_by: Optional[UUID] = None  # left out entirely for anonymous public reports


class CaseStatusUpdate(BaseModel):
    new_status: CaseStatus
    assigned_to: Optional[UUID] = None  # staff can self-assign or assign a colleague
    # Required when moving a case into Resolved, refused on any other move.
    outcome: Optional[CaseOutcome] = None
    outcome_note: Optional[str] = Field(None, max_length=2000)

class OutbreakZoneCreate(BaseModel):
    animal_type: str
    title: str
    description: Optional[str] = None
    center_lat: float
    center_lng: float
    radius_km: float

class OutbreakZoneOut(BaseModel):
    id: UUID
    animal_type: str
    title: str
    description: Optional[str] = None
    center_lat: float
    center_lng: float
    radius_km: float
    declared_at: datetime
    is_active: bool
    resolved_at: Optional[datetime] = None

class CaseAssignee(BaseModel):
    """Who a case is assigned to — only what a card needs to show.

    Embedded per case rather than served as a staff directory: General Staff
    is the open-signup role and holds rescue:read, so a directory gated on it
    would hand every new registrant the staff list. Embedded, a viewer learns
    only who is on cases they can already see.
    """
    email: str
    # first + last from employee_profile; None when the user has no profile.
    display_name: Optional[str] = None


class AssigneeOption(CaseAssignee):
    """A user the assign dropdown may offer. rescue:assign holders only."""
    id: UUID
    role_name: str


class CaseOut(BaseModel):
    id: UUID
    animal_type: str
    description: Optional[str] = None
    status: CaseStatus
    urgency: str
    # Null on rows created before 005_urgency_reason.sql — there is no record
    # of how those were classified, so the UI shows nothing rather than guess.
    urgency_reason: Optional[str] = None
    urgency_source: Optional[str] = None
    lat: float
    lng: float
    photo_url: Optional[str] = None
    reported_by: Optional[UUID] = None
    assigned_to: Optional[UUID] = None
    # Filled by GET /cases only. Null when unassigned, and on every other
    # endpoint returning CaseOut — including the public report form, which
    # must never carry staff details.
    assignee: Optional[CaseAssignee] = None
    # Set only while Resolved. Null on cases resolved before
    # 030_case_timeline_outcome.sql, which never recorded one.
    outcome: Optional[CaseOutcome] = None
    resolved_at: Optional[datetime] = None
    reported_at: datetime
    updated_at: datetime


class OutcomeRecord(BaseModel):
    """An outcome for a case resolved before outcomes were recorded (030)."""
    outcome: CaseOutcome
    outcome_note: Optional[str] = Field(None, max_length=2000)


class CaseNoteCreate(BaseModel):
    body: str = Field(..., max_length=2000)


class CaseEventOut(BaseModel):
    """One line of a case's timeline.

    "reported" is never stored: it is the case's own reported_at, added to the
    front by GET /cases/{id}/timeline so older cases get one too. Its id is 0.

    "supplies" and "supplies_reversed" are not stored here either: they are
    the case's Stock Outs and their reversals (inventory_transactions,
    migration 031), id = the movement's id.
    """
    id: int
    event_type: Literal["reported", "note", "status", "assign", "outcome", "supplies", "supplies_reversed"]
    body: Optional[str] = None
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    outcome: Optional[CaseOutcome] = None
    assignee: Optional[CaseAssignee] = None
    # Null for the public report and for authors whose account has gone.
    author: Optional[CaseAssignee] = None
    # Supplies lines only.
    item_name: Optional[str] = None
    quantity: Optional[int] = None
    cost: Optional[float] = None
    created_at: datetime


class OutcomeLine(BaseModel):
    outcome: CaseOutcome
    cases: int
    supplies_cost: float


class CaseReport(BaseModel):
    """Cases resolved in one month (Sri Lanka time), by outcome, with what
    their supplies cost. A case counts in the month it was last resolved, and
    all its supplies count with it, whenever they were issued."""
    year: int
    month: int
    # Reported in the month, whatever has happened to them since.
    reported: int = 0
    resolved: int
    by_outcome: list[OutcomeLine]
    supplies_cost: float
    # None when nothing was resolved, rather than a misleading 0.
    average_cost: Optional[float] = None
    open_cases: int
    # Resolved before outcomes were recorded (030); in no month's figures.
    unrecorded_outcomes: int


class RouteStop(BaseModel):
    """One case in the optimized visiting order, with the leg that reaches it."""
    sequence: int  # 1-based, matches the numbered map markers
    case: CaseOut
    leg_distance_km: float       # from the previous stop (or the start, for #1)
    leg_duration_min: float
    cumulative_distance_km: float
    cumulative_duration_min: float


class OptimizedRoute(BaseModel):
    stops: list[RouteStop]
    total_distance_km: float
    total_duration_min: float
    # False when road routing was unavailable and these are straight-line
    # estimates. The UI surfaces this rather than passing off crow-flies
    # numbers as driving distances.
    used_road_distances: bool
    degraded_reason: Optional[str] = None
    truncated: bool = False