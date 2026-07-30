from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from datetime import datetime, timedelta, timezone
from supabase import Client

# Internal App Imports
from app.core.supabase import get_supabase
from app.schemas.rescue_case import RescueCaseGeo, CaseStatus

router = APIRouter()


@router.get("/geo", response_model=list[RescueCaseGeo])
async def get_case_geo(
    status: Optional[CaseStatus] = Query(None, description="Filter by case status"),
    days: Optional[int] = Query(None, description="Only cases reported in the last N days"),
    supabase: Client = Depends(get_supabase)
):
    query = supabase.table("rescue_cases").select(
        "id, animal_type, status, lat, lng, reported_at"
    )

    if status:
        query = query.eq("status", status.value)

    if days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        query = query.gte("reported_at", cutoff)

    response = query.execute()
    return response.data or []