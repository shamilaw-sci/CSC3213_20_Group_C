# backend/app/services/notifications.py
#
# Personal updates (migration 032): a message to one person when something
# about them is decided. Called from the decision points in leave.py, hr.py
# and rescue_cases.py.
#
# A notification is a courtesy, never a control: every write is fail-soft, so
# a decision that has been made is never reported as failed because its
# message could not be stored. Nobody is notified of their own action.

import logging
from datetime import date
from typing import Iterable, Optional

from postgrest.types import ReturnMethod
from supabase import Client

logger = logging.getLogger(__name__)


def short_date(value) -> str:
    """'3 Dec 2026'."""
    d = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    return f"{d.day} {d.strftime('%b')} {d.year}"


def date_range(start, end) -> str:
    return short_date(start) if str(start)[:10] == str(end)[:10] else f"{short_date(start)} to {short_date(end)}"


def notify(supabase: Client, recipients: Iterable[Optional[str]], *, actor_id, kind: str, title: str,
           body: Optional[str] = None, href: Optional[str] = None) -> None:
    """One message to each recipient (user ids), except the actor."""
    rows = [
        {"user_id": str(uid), "kind": kind, "title": title[:200],
         "body": body[:600] if body else None, "href": href}
        for uid in dict.fromkeys(str(u) for u in recipients if u)
        if uid != str(actor_id)
    ]
    if not rows:
        return
    try:
        # Minimal: the writer may not read the recipient's row back (RLS), so
        # asking for it would turn a saved insert into an error.
        supabase.table("notifications").insert(rows, returning=ReturnMethod.minimal).execute()
    except Exception:
        logger.exception("Could not store %s notification(s) of kind %s", len(rows), kind)


def users_of_employees(supabase: Client, employee_ids: Iterable[int]) -> list[str]:
    """The logins linked to these employees; employees without one are skipped."""
    ids = sorted({e for e in employee_ids if e is not None})
    if not ids:
        return []
    try:
        rows = supabase.table("employee_profile").select("id, user_id").in_("id", ids).execute().data or []
    except Exception:
        logger.exception("Could not look up the logins of employees %s", ids)
        return []
    return [r["user_id"] for r in rows if r.get("user_id")]
