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

class RescueHotspot(BaseModel):
    grid_lat: float
    grid_lng: float
    count: int
    animal_breakdown: dict[str, int]
    latest_report_at: datetime
    is_active_outbreak: bool
    outbreak_animal_types: list[str] = []

class CaseStatusUpdate(BaseModel):
    new_status: CaseStatus
    assigned_to: Optional[UUID] = None  # staff can self-assign or assign a colleague