# backend/app/api/rescue_cases.py

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from datetime import datetime, timedelta, timezone
from supabase import Client
from fastapi import UploadFile, File
import uuid
from app.core.security import require_permission
from app.core.security import has_permission
from app.core.supabase import get_supabase, get_public_supabase
from app.schemas.rescue_case import (
    RescueCaseGeo, CaseStatus, CaseCreate, CaseOut, CaseStatusUpdate,
    OutbreakZoneCreate, OutbreakZoneOut,
)
from app.services.case_classifier import classify_case_urgency

router = APIRouter()


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
    classification = await classify_case_urgency(payload.animal_type, payload.description)

    response = supabase.table("rescue_cases").insert({
        **payload.model_dump(exclude_none=True),
        "urgency": classification["urgency"],
    }).execute()

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
    current_user: dict = Depends(require_permission("rescue:read")),
):
    existing = (
        supabase.table("rescue_cases")
        .select("status, assigned_to")
        .eq("id", case_id)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Case not found")

    role_name = (current_user.get("roles", {}).get("role_name") or "")
    current_status = existing.data[0]["status"]
    current_assignee = existing.data[0]["assigned_to"]

    # Claiming a freshly reported case is the act of assigning, so rescue:assign covers
    # it on its own — claiming a case also starts it, moving it straight to In Treatment.
    # Every other status move (including reopening a Resolved case) is case management.
    is_assignment_handoff = (
        current_status == CaseStatus.reported.value
        and payload.new_status == CaseStatus.in_treatment
        and payload.assigned_to is not None
    )
    if payload.new_status.value != current_status and not is_assignment_handoff:
        if not has_permission(role_name, "rescue:manage"):
            raise HTTPException(403, "You do not have permission to change case status")

    if payload.assigned_to is not None:
        is_self_assign = str(payload.assigned_to) == str(current_user["id"])
        if not is_self_assign and not has_permission(role_name, "rescue:assign"):
            raise HTTPException(403, "Only Director/HR Officer/Admin can assign cases to other staff")

    # Reported is the only stage a case can sit in unclaimed. Leaving it requires
    # an assignee — either one already on the case or one supplied here — so a
    # raw drag or a direct API call can't produce an "In Treatment"/"Resolved"
    # case nobody owns.
    if payload.new_status != CaseStatus.reported:
        if current_assignee is None and payload.assigned_to is None:
            raise HTTPException(400, "A case must have an assignee to move past Reported")

    update_data = {"status": payload.new_status.value}
    if payload.new_status == CaseStatus.reported:
        # Moving back to Reported always releases the claim.
        update_data["assigned_to"] = None
    elif payload.assigned_to is not None:
        update_data["assigned_to"] = str(payload.assigned_to)

    response = supabase.table("rescue_cases").update(update_data).eq("id", case_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Case not found")
    return response.data[0]


@router.get("/outbreak-zones", response_model=list[OutbreakZoneOut])
async def get_outbreak_zones(
    supabase: Client = Depends(get_public_supabase),
):
    """Public — active outbreak zones only. No individual case data exposed."""
    response = (
        supabase.table("outbreak_zones")
        .select("*")
        .eq("is_active", True)
        .order("declared_at", desc=True)
        .execute()
    )
    return response.data or []


@router.post("/outbreak-zones", response_model=OutbreakZoneOut)
async def declare_outbreak_zone(
    payload: OutbreakZoneCreate,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("rescue:assign")),
):
    response = supabase.table("outbreak_zones").insert({
        **payload.model_dump(),
        "declared_by": current_user["id"],
    }).execute()

    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to declare outbreak zone")
    return response.data[0]


@router.patch("/outbreak-zones/{zone_id}/resolve", response_model=OutbreakZoneOut)
async def resolve_outbreak_zone(
    zone_id: str,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("rescue:assign")),
):
    response = (
        supabase.table("outbreak_zones")
        .update({"is_active": False, "resolved_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", zone_id)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Zone not found")
    return response.data[0]