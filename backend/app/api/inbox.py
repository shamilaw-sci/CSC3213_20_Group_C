# backend/app/api/inbox.py
#
# "Needs your action": the work waiting on the signed-in person, behind the
# bell in the top bar (confirmed 2026-11-13).
#
# Worked out from the data on every request rather than stored, so there is
# nothing to mark as read: an item goes away when the work is done. Each queue
# appears only to people whose permission lets them act on it, and only when
# it has something in it.
#
# Fail-soft per queue: a table missing before its migration, or a query that
# fails, drops that one queue (and logs it) instead of breaking the bell.

import logging
from datetime import date, timedelta
from typing import Callable, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from supabase import Client

from app.api.attendance_month import _tracking_start
from app.api.hr import _approve_block, _period, _sl_today
from app.api.inventory import expiring_items, low_stock_items
from app.core.permissions import has_permission
from app.core.security import get_current_user
from app.core.supabase import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter()

# Same window as the Stock page's expiry alert.
EXPIRY_WINDOW_DAYS = 30
URGENT = ("Critical", "High")


class InboxItem(BaseModel):
    key: str
    title: str
    count: int
    href: str
    # action: a decision waiting on you. alert: something going wrong that
    # someone with your role should look at.
    tone: Literal["action", "alert"]


class Inbox(BaseModel):
    items: list[InboxItem]
    total: int


def _plural(n: int, one: str, many: Optional[str] = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _own_employee_ids(supabase: Client, user_id: str) -> set:
    rows = supabase.table("employee_profile").select("id").eq("user_id", user_id).execute().data or []
    return {r["id"] for r in rows}


def _leave(supabase: Client, user: dict) -> Optional[InboxItem]:
    # Nobody decides their own leave (app/api/leave.py), so it isn't theirs to do.
    own = _own_employee_ids(supabase, str(user["id"]))
    rows = supabase.table("leave_requests").select("employee_id").eq("status", "Pending").execute().data or []
    n = sum(1 for r in rows if r.get("employee_id") not in own)
    return n and InboxItem(key="leave", title=f"{_plural(n, 'leave request')} to decide",
                           count=n, href="/hr/leave", tone="action")


def _corrections(supabase: Client, user: dict) -> Optional[InboxItem]:
    # Nobody decides their own correction either (app/api/hr.py).
    own = _own_employee_ids(supabase, str(user["id"]))
    rows = (
        supabase.table("attendance_correction_requests").select("employee_id, requested_by")
        .eq("status", "Pending").execute().data or []
    )
    n = sum(1 for r in rows
            if r.get("employee_id") not in own and str(r.get("requested_by")) != str(user["id"]))
    return n and InboxItem(key="corrections", title=f"{_plural(n, 'attendance correction')} to decide",
                           count=n, href="/hr/attendance", tone="action")


def _month_close(supabase: Client, user: dict) -> Optional[InboxItem]:
    """Last month, once it is over and tracked, should be closed so the next
    payroll deducts its absences."""
    first_of_this = _sl_today().replace(day=1)
    last_month_end = first_of_this - timedelta(days=1)
    start = _tracking_start(supabase)
    if start is not None and start > last_month_end:
        return None  # nothing tracked last month: nothing to close
    month, year = last_month_end.month, last_month_end.year
    rows = (
        supabase.table("attendance_month_closes").select("status")
        .eq("close_month", month).eq("close_year", year).execute().data or []
    )
    if rows and rows[0].get("status") == "Closed":
        return None
    return InboxItem(key="month_close", title=f"{_period(month, year)} attendance is not closed yet",
                     count=1, href="/hr/attendance", tone="action")


def _payroll(supabase: Client, user: dict) -> Optional[InboxItem]:
    rows = (
        supabase.table("payroll_runs").select("payroll_month, payroll_year")
        .eq("status", "Draft").execute().data or []
    )
    # Only drafts that can be approved today (not before the month allows it).
    ready = [r for r in rows if _approve_block(r["payroll_month"], r["payroll_year"]) is None]
    if not ready:
        return None
    if len(ready) == 1:
        title = f"Payroll for {_period(ready[0]['payroll_month'], ready[0]['payroll_year'])} to approve"
    else:
        title = f"{len(ready)} payroll drafts to approve"
    return InboxItem(key="payroll", title=title, count=len(ready), href="/hr/payroll", tone="action")


def _volunteers(supabase: Client, user: dict) -> Optional[InboxItem]:
    n = len(supabase.table("volunteers").select("id").eq("status", "pending").execute().data or [])
    return n and InboxItem(key="volunteers", title=f"{_plural(n, 'volunteer application')} to review",
                           count=n, href="/volunteers", tone="action")


def _low_stock(supabase: Client, user: dict) -> Optional[InboxItem]:
    n = len(low_stock_items(supabase))
    return n and InboxItem(key="low_stock", title=f"{_plural(n, 'item')} below reorder level",
                           count=n, href="/inventory/stock", tone="alert")


def _expiring(supabase: Client, user: dict) -> Optional[InboxItem]:
    items = expiring_items(supabase, EXPIRY_WINDOW_DAYS)
    if not items:
        return None
    today = str(_sl_today())
    expired = sum(1 for i in items if str(i.get("expire_date")) < today)
    title = f"{_plural(len(items), 'item')} expired or expiring within {EXPIRY_WINDOW_DAYS} days"
    if expired:
        title += f" ({expired} already expired)"
    return InboxItem(key="expiring", title=title, count=len(items), href="/inventory/stock", tone="alert")


def _urgent_cases(supabase: Client, user: dict) -> Optional[InboxItem]:
    rows = (
        supabase.table("rescue_cases").select("urgency")
        .eq("status", "Reported").is_("assigned_to", "null").execute().data or []
    )
    n = sum(1 for r in rows if r.get("urgency") in URGENT)
    return n and InboxItem(key="urgent_cases", title=f"{_plural(n, 'urgent rescue case')} nobody has claimed",
                           count=n, href="/case-triage", tone="alert")


# (who may act on it, how to count it), in the order the bell lists them.
# Low stock and expiry go to inventory:manage, the Stock page that restocks;
# Issue-only staff can't act on them.
QUEUES: list[tuple[Callable[[str], bool], Callable]] = [
    (lambda role: has_permission(role, "rescue:assign") or has_permission(role, "rescue:manage"), _urgent_cases),
    (lambda role: has_permission(role, "payroll:approve"), _payroll),
    (lambda role: has_permission(role, "leave:approve"), _leave),
    (lambda role: has_permission(role, "hr:attendance:manage"), _corrections),
    (lambda role: has_permission(role, "hr:attendance:manage"), _month_close),
    (lambda role: has_permission(role, "volunteers:approve"), _volunteers),
    (lambda role: has_permission(role, "inventory:manage"), _expiring),
    (lambda role: has_permission(role, "inventory:manage"), _low_stock),
]


@router.get("", response_model=Inbox)
async def get_inbox(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """What is waiting on the caller. Any signed-in user; each queue checks its
    own permission, so someone with none of them gets an empty inbox. Pure
    read, not audited."""
    role = (current_user.get("roles") or {}).get("role_name") or ""
    items = []
    for allowed, count in QUEUES:
        if not allowed(role):
            continue
        try:
            item = count(supabase, current_user)
        except Exception:
            logger.exception("Inbox queue %s failed; leaving it out", count.__name__)
            continue
        if item:
            items.append(item)
    return {"items": items, "total": sum(i.count for i in items)}
