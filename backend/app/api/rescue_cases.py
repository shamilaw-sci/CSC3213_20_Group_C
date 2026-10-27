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
from app.core.audit import log_audit_action
from app.schemas.rescue_case import (
    RescueCaseGeo, CaseStatus, CaseCreate, CaseOut, CaseStatusUpdate,
    OutbreakZoneCreate, OutbreakZoneOut, OptimizedRoute,
)
from app.services.case_classifier import classify_case_urgency
from app.services.route_optimizer import optimize_route

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
        "urgency_reason": classification["reason"],
        "urgency_source": classification["source"],
    }).execute()

    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to create case")

    # Public endpoint: reports come from anonymous members of the public, so a
    # null user_id here is the accurate record, not a missing attribution.
    await log_audit_action(
        supabase,
        user_id=None,
        action_type="RESCUE_CASE_CREATE",
        table_name="rescue_cases",
        old_payload=None,
        new_payload=response.data[0],
    )

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


@router.get("/my-route", response_model=OptimizedRoute)
async def get_my_route(
    lat: float = Query(..., ge=-90, le=90, description="Staff member's current latitude"),
    lng: float = Query(..., ge=-180, le=180, description="Staff member's current longitude"),
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("rescue:read")),
):
    """
    An efficient visiting order for the caller's own open cases.

    Gated on rescue:read rather than a dedicated permission: this exposes a
    strict subset of what GET /cases already returns to the same user, so a
    separate permission would be granted to exactly the same roles and add a
    second thing to keep in sync for no access-control gain.

    Scoped to assigned_to = the caller. Not a parameter, deliberately — there is
    no route-for-another-user case, and accepting a user id here would need its
    own authorization check to stop staff enumerating each other's workloads.

    Pure read, so nothing is written to the audit log.
    """
    response = (
        supabase.table("rescue_cases")
        .select("*")
        .eq("assigned_to", str(current_user["id"]))
        .neq("status", CaseStatus.resolved.value)
        .order("reported_at", desc=False)
        .execute()
    )

    cases = response.data or []

    # A case with no coordinates cannot be routed to. Dropping it beats failing
    # the whole request, and beats sending (0, 0) to the routing engine — which
    # would silently anchor the tour in the Atlantic.
    routable = [c for c in cases if c.get("lat") is not None and c.get("lng") is not None]

    result = await optimize_route((lat, lng), routable)
    return result


@router.patch("/cases/{case_id}/status", response_model=CaseOut)
async def update_case_status(
    case_id: str,
    payload: CaseStatusUpdate,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("rescue:read")),
):
    existing = (
        supabase.table("rescue_cases")
        # Full row rather than just the two fields the permission checks need,
        # so the audit entry records the case as it actually stood beforehand.
        .select("*")
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

    updated = response.data[0]
    before = existing.data[0]

    # Status change and assignment are gated on different permissions
    # (rescue:manage vs rescue:assign) precisely because they are different
    # kinds of act. The audit trail keeps that distinction rather than
    # flattening one endpoint into one action type. A single request that does
    # both emits both entries.
    if updated.get("status") != before.get("status"):
        await log_audit_action(
            supabase,
            user_id=current_user["id"],
            action_type="RESCUE_CASE_STATUS_UPDATE",
            table_name="rescue_cases",
            old_payload=before,
            new_payload=updated,
        )

    if updated.get("assigned_to") != before.get("assigned_to"):
        await log_audit_action(
            supabase,
            user_id=current_user["id"],
            action_type="RESCUE_CASE_ASSIGN",
            table_name="rescue_cases",
            old_payload={"id": case_id, "assigned_to": before.get("assigned_to")},
            new_payload={"id": case_id, "assigned_to": updated.get("assigned_to")},
        )

    return updated


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

    # Declaring a zone publishes it to the public map, so it is a public-facing
    # act worth attributing.
    await log_audit_action(
        supabase,
        user_id=current_user["id"],
        action_type="OUTBREAK_ZONE_DECLARE",
        table_name="outbreak_zones",
        old_payload=None,
        new_payload=response.data[0],
    )

    return response.data[0]


@router.patch("/outbreak-zones/{zone_id}/resolve", response_model=OutbreakZoneOut)
async def resolve_outbreak_zone(
    zone_id: str,
    supabase: Client = Depends(get_supabase),
    current_user: dict = Depends(require_permission("rescue:assign")),
):
    existing = (
        supabase.table("outbreak_zones")
        .select("*")
        .eq("id", zone_id)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Zone not found")

    response = (
        supabase.table("outbreak_zones")
        .update({"is_active": False, "resolved_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", zone_id)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Zone not found")

    await log_audit_action(
        supabase,
        user_id=current_user["id"],
        action_type="OUTBREAK_ZONE_RESOLVE",
        table_name="outbreak_zones",
        old_payload=existing.data[0],
        new_payload=response.data[0],
    )

    return response.data[0]