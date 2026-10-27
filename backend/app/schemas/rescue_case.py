from pydantic import BaseModel
from datetime import datetime
from enum import Enum
from uuid import UUID
from typing import Optional


class CaseStatus(str, Enum):
    reported = "Reported"
    in_treatment = "In Treatment"
    resolved = "Resolved"


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
    reported_at: datetime
    updated_at: datetime


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