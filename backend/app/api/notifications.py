# backend/app/api/notifications.py
#
# The signed-in person's own updates (migration 032): list, mark one read,
# mark all read. Every query is filtered to the caller as well as guarded by
# RLS, so the routes are right even on a client that bypasses RLS.

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from supabase import Client

from app.core.security import get_current_user
from app.core.supabase import get_supabase

router = APIRouter()


class Notification(BaseModel):
    id: int
    kind: Literal["leave_decided", "correction_decided", "case_assigned", "payslip_ready"]
    title: str
    body: Optional[str] = None
    href: Optional[str] = None
    created_at: datetime
    read_at: Optional[datetime] = None


class NotificationList(BaseModel):
    items: list[Notification]
    unread: int


@router.get("", response_model=NotificationList)
async def list_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Newest first, with how many of all of them are unread."""
    me = str(current_user["id"])
    items = (
        supabase.table("notifications").select("*").eq("user_id", me)
        .order("created_at", desc=True).limit(limit).execute().data or []
    )
    unread = (
        supabase.table("notifications").select("id").eq("user_id", me).is_("read_at", "null")
        .execute().data or []
    )
    return {"items": items, "unread": len(unread)}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/{notification_id}/read", response_model=Notification)
async def mark_read(
    notification_id: int,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    me = str(current_user["id"])
    rows = (
        supabase.table("notifications").select("*").eq("id", notification_id).eq("user_id", me)
        .execute().data or []
    )
    # Someone else's notification is as good as missing.
    if not rows:
        raise HTTPException(status_code=404, detail="Notification not found")
    if rows[0].get("read_at"):
        return rows[0]
    updated = (
        supabase.table("notifications").update({"read_at": _now()})
        .eq("id", notification_id).eq("user_id", me).execute().data or []
    )
    return updated[0] if updated else {**rows[0], "read_at": _now()}


@router.post("/read-all")
async def mark_all_read(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    updated = (
        supabase.table("notifications").update({"read_at": _now()})
        .eq("user_id", str(current_user["id"])).is_("read_at", "null").execute().data or []
    )
    return {"marked": len(updated)}
