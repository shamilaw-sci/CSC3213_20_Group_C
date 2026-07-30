from pydantic import BaseModel
from datetime import datetime
from enum import Enum


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