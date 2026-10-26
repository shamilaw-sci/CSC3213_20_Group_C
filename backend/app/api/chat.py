import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from supabase import Client

from app.core.permissions import has_permission
from app.core.security import get_current_user
from app.core.supabase import get_supabase
from app.services.chat_tools import TOOLS
from app.services.llm import complete

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_TOOL_ROUNDS = 5

# Shown verbatim in the chat widget. Deliberately says nothing about the cause:
# staff can act on "try again", not on a provider status code.
UNAVAILABLE_MESSAGE = "The assistant is temporarily unavailable, please try again."

SYSTEM_PROMPT = """You are the assistant for VFF IMS, the internal management \
system for Vets For Future, a Sri Lankan animal welfare nonprofit.

Answer using the tools available to you. Rules:
- Never invent numbers. If a tool doesn't return data, say you don't have it.
- If you have no tool for what was asked, say so plainly and name the page \
that has it. Do not guess.
- Currency is LKR. Dates are YYYY-MM-DD.
- Be brief. Staff are checking facts, not reading reports."""


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[dict] = Field(default_factory=list, max_length=20)


@router.post("")
async def chat(
    req: ChatRequest,
    user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    role_name = (user.get("roles", {}) or {}).get("role_name") or ""
    allowed = {
        name for name, t in TOOLS.items()
        if has_permission(role_name, t["permission"])
    }

    if not allowed:
        raise HTTPException(403, "The assistant isn't available for your role.")

    schemas = [TOOLS[name]["schema"] for name in allowed]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *req.history,
        {"role": "user", "content": req.message},
    ]

    for _ in range(MAX_TOOL_ROUNDS):
        # Upstream failures (Gemini 503/429, timeouts, dropped connections)
        # used to escape as an unhandled 500 with a traceback. They are the
        # provider's problem, not a bug here, so they are logged without one
        # and surfaced as a 503 the widget can show.
        try:
            data = await complete(messages, schemas)
            msg = data["choices"][0]["message"]
        except httpx.HTTPStatusError as e:
            logger.warning("chat: LLM returned HTTP %s (%s)",
                           e.response.status_code, type(e).__name__)
            raise HTTPException(503, UNAVAILABLE_MESSAGE)
        except httpx.RequestError as e:
            logger.warning("chat: LLM request failed: %s: %r", type(e).__name__, e)
            raise HTTPException(503, UNAVAILABLE_MESSAGE)
        except (KeyError, IndexError, TypeError) as e:
            logger.warning("chat: malformed LLM response: %s: %r", type(e).__name__, e)
            raise HTTPException(503, UNAVAILABLE_MESSAGE)
        messages.append(msg)

        calls = msg.get("tool_calls")
        if not calls:
            return {"reply": msg.get("content", ""), "history": messages[1:]}

        for call in calls:
            name = call["function"]["name"]
            if name not in allowed:
                logger.warning("chat: blocked tool %s for role %s", name, role_name)
                result = {"error": "not authorized"}
            else:
                try:
                    args = json.loads(call["function"]["arguments"] or "{}")
                    result = TOOLS[name]["impl"](supabase, **args)
                except Exception as e:
                    logger.exception("chat: tool %s failed", name)
                    result = {"error": f"{type(e).__name__}: {e}"}

            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps(result, default=str),
            })

    return {"reply": "I couldn't work that out — try asking more specifically.",
            "history": messages[1:]}