from pydantic import BaseModel
from datetime import datetime
from enum import Enum
from uuid import UUID
from typing import Optional


class CaseStatus(str, Enum):
    reported = "Reported"
    assigned = "Assigned"
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


class CaseOut(BaseModel):
    id: UUID
    animal_type: str
    description: Optional[str] = None
    status: CaseStatus
    lat: float
    lng: float
    photo_url: Optional[str] = None
    reported_by: Optional[UUID] = None
    assigned_to: Optional[UUID] = None
    reported_at: datetime
    updated_at: datetime


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