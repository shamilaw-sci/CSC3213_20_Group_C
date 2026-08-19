# backend/app/api/rescue_cases.py

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from datetime import datetime, timedelta, timezone
from supabase import Client
from fastapi import UploadFile, File
import uuid
from collections import defaultdict
from app.core.security import require_permission
from app.core.security import has_permission
from app.schemas.rescue_case import CaseStatusUpdate
from app.core.supabase import get_supabase, get_public_supabase
from app.schemas.rescue_case import RescueCaseGeo, RescueHotspot, CaseStatus, CaseCreate, CaseOut

router = APIRouter()

GRID_SIZE = 0.02          # ~2km cells — tune coarser/finer as needed
MIN_CLUSTER_SIZE = 2       # cells with fewer reports than this are hidden entirely
OUTBREAK_THRESHOLD = 3     # same-animal-type reports needed to flag "active outbreak"
OUTBREAK_WINDOW_DAYS = 7   # within this many days


@router.get("/geo", response_model=list[RescueCaseGeo])
async def get_case_geo(
    status: Optional[CaseStatus] = Query(None, description="Filter by case status"),
    days: Optional[int] = Query(None, description="Only cases reported in the last N days"),
    supabase: Client = Depends(get_public_supabase),
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
    rows = response.data or []

    for row in rows:
        row["lat"] = round(row["lat"], 3)
        row["lng"] = round(row["lng"], 3)

    return rows


@router.post("/cases", response_model=CaseOut)
async def create_case(
    payload: CaseCreate,
    supabase: Client = Depends(get_public_supabase),
):
    response = supabase.table("rescue_cases").insert(
        payload.model_dump(exclude_none=True)
    ).execute()

    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to create case")

    return response.data[0]

@router.post("/upload-photo")
async def upload_case_photo(
    file: UploadFile = File(...),
    supabase: Client = Depends(get_public_supabase),
):
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(400, "Only JPEG, PNG, or WebP images are allowed")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:  # 5MB cap
        raise HTTPException(400, "Image must be under 5MB")

    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    path = f"{uuid.uuid4()}.{ext}"

    supabase.storage.from_("case-photos").upload(
        path, contents, {"content-type": file.content_type}
    )

    public_url = supabase.storage.from_("case-photos").get_public_url(path)
    return {"photo_url": public_url}

@router.get("/hotspots", response_model=list[RescueHotspot])
async def get_hotspots(
    days: Optional[int] = Query(30, description="Look back this many days"),
    supabase: Client = Depends(get_public_supabase),
):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = (
        supabase.table("rescue_cases")
        .select("animal_type, lat, lng, reported_at")
        .gte("reported_at", cutoff)
        .execute()
        .data
        or []
    )

    cells: dict[tuple[float, float], list[dict]] = defaultdict(list)
    for r in rows:
        cell_key = (
            round(r["lat"] / GRID_SIZE) * GRID_SIZE,
            round(r["lng"] / GRID_SIZE) * GRID_SIZE,
        )
        cells[cell_key].append(r)

    outbreak_cutoff = datetime.now(timezone.utc) - timedelta(days=OUTBREAK_WINDOW_DAYS)
    hotspots = []

    for (grid_lat, grid_lng), cases in cells.items():
        if len(cases) < MIN_CLUSTER_SIZE:
            continue  # too few reports — don't expose an isolated location

        breakdown: dict[str, int] = defaultdict(int)
        for c in cases:
            breakdown[c["animal_type"]] += 1

        latest = max(c["reported_at"] for c in cases)

        recent_same_type_counts = defaultdict(int)

        for c in cases:
            reported_dt = datetime.fromisoformat(c["reported_at"].replace("Z", "+00:00"))
            if reported_dt >= outbreak_cutoff:
                recent_same_type_counts[c["animal_type"]] += 1
        outbreak_types = [
            animal_type for animal_type, cnt in recent_same_type_counts.items()
            if cnt >= OUTBREAK_THRESHOLD
        ]
        hotspots.append(RescueHotspot(
            grid_lat=round(grid_lat, 4),
            grid_lng=round(grid_lng, 4),
            count=len(cases),
            animal_breakdown=dict(breakdown),
            latest_report_at=latest,
            is_active_outbreak=len(outbreak_types) > 0,
            outbreak_animal_types=outbreak_types,
        ))

    return hotspots

@router.get("/cases", response_model=list[CaseOut])
async def list_cases(
    status: Optional[CaseStatus] = Query(None, description="Filter by case status"),
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("rescue:read")),
):
    query = supabase.table("rescue_cases").select("*").order("reported_at", desc=True)
    if status:
        query = query.eq("status", status.value)

    response = query.execute()
    return response.data or []


@router.patch("/cases/{case_id}/status", response_model=CaseOut)
async def update_case_status(
    case_id: str,
    payload: CaseStatusUpdate,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("rescue:manage")),
):
    if payload.assigned_to is not None:
        role_name = (current_user.get("roles", {}).get("role_name") or "")
        is_self_assign = str(payload.assigned_to) == str(current_user["id"])
        if not is_self_assign and not has_permission(role_name, "rescue:assign"):
            raise HTTPException(403, "Only Director/HR Officer/Admin can assign cases to other staff")

    update_data = {"status": payload.new_status.value}
    if payload.assigned_to is not None:
        update_data["assigned_to"] = str(payload.assigned_to)

    response = supabase.table("rescue_cases").update(update_data).eq("id", case_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Case not found")
    return response.data[0]