# backend/app/services/board_events.py
#
# Tells open case-triage boards that the case list changed, so they refetch.
#
# A ping, not a feed. The message carries no case data and no case id: the
# board refetches GET /rescue_cases/cases, which is where rescue:read is
# enforced. Supabase Realtime postgres_changes is deliberately not used —
# rescue_cases RLS is permissive for every authenticated user (authorization
# lives in FastAPI), so subscribing to the table would push full rows to
# accounts that hold no rescue permission.
#
# Private channel. Migration 006 lets `authenticated` receive on this topic and
# gives no role an INSERT policy, so only this module, sending with the
# service_role key, can publish. The anon key is in every browser bundle, and a
# public channel would let anyone holding it make every open board refetch.
#
# REST, not a socket. supabase-py 2.3.0 ships with realtime disabled, and a
# serverless function on Vercel cannot hold a connection open between
# requests anyway. One POST per mutation, awaited inline: work scheduled after
# the response (BackgroundTasks, create_task) may be frozen or killed when the
# function is suspended.

import logging

import httpx

from app.core.supabase import key as SERVICE_KEY, url as SUPABASE_URL

logger = logging.getLogger(__name__)

BOARD_TOPIC = "rescue-board"
BOARD_EVENT = "cases_changed"

# Inline on the request path, including the public report form, so the bound
# matters more than delivery: a missed ping costs at most one polling interval
# on the board, a slow one delays every case create.
BROADCAST_TIMEOUT = httpx.Timeout(1.5, connect=1.0)


async def _post(body: dict) -> None:
    async with httpx.AsyncClient(timeout=BROADCAST_TIMEOUT) as client:
        response = await client.post(
            f"{SUPABASE_URL}/realtime/v1/api/broadcast",
            headers={"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}"},
            json=body,
        )
        response.raise_for_status()


async def notify_board_changed() -> None:
    """Ping open boards. Never raises: a failed ping must not fail the mutation."""
    body = {"messages": [{
        "topic": BOARD_TOPIC,
        "event": BOARD_EVENT,
        "payload": {},
        "private": True,
    }]}
    try:
        await _post(body)
    except Exception as e:
        # Type and repr, not str(e): httpx timeouts stringify to "".
        logger.warning("board_events: broadcast failed: %s: %r", type(e).__name__, e)
