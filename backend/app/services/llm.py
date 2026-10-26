import asyncio
import logging
import re
import time

import httpx
from app.core import config

logger = logging.getLogger(__name__)

# Indirection so tests can skip real backoff waits.
_sleep = asyncio.sleep

# A retry is only attempted if at least this much of the caller's deadline
# would remain for it. Less than that and it would almost certainly be cut off
# anyway — and on Gemini's free tier every attempt spends one of 20 daily
# requests, so a doomed retry is not free.
MIN_ATTEMPT_S = 2.0

# With no deadline, a server-requested wait longer than this is not honoured.
# Gemini answers a spent daily quota with a retryDelay of many hours.
MAX_UNBOUNDED_BACKOFF_S = 5.0


def _retry_after_s(response: httpx.Response) -> float | None:
    """The wait a 429 asks for: Retry-After, or Gemini's RetryInfo.retryDelay."""
    header = response.headers.get("retry-after")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, list):  # Gemini's OpenAI-compatible errors come wrapped in a list
        body = body[0] if body else {}
    if not isinstance(body, dict):
        return None
    for detail in (body.get("error") or {}).get("details") or []:
        match = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(detail.get("retryDelay", "")))
        if match:
            return float(match.group(1))
    return None


def _retry_backoff_s(exc: httpx.HTTPError) -> float | None:
    """Backoff before the one retry, or None if this failure is not worth one.

    Retried: connection failures (fast, often a blip) and 503 (provider
    overloaded, often clears in seconds). A 429 only when the server says how
    long to wait. NOT retried: ReadTimeout — the provider accepted the request
    and stalled, so a second attempt mostly stalls too — and every other status.
    """
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        return 0.5
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code == 503:
            return 1.0
        if exc.response.status_code == 429:
            return _retry_after_s(exc.response)
    return None


async def _post(payload: dict, timeout) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            f"{config.LLM_BASE_URL}chat/completions",
            headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
            json=payload,
        )
        r.raise_for_status()
        return r.json()


async def complete(
    messages: list[dict],
    tools: list[dict] | None = None,
    *,
    timeout: float | httpx.Timeout = 60,
    reasoning_effort: str | None = None,
    retry: bool = False,
    deadline: float | None = None,
) -> dict:
    """One chat completion.

    `retry` allows a single retry on the failures _retry_backoff_s accepts.
    `deadline` is a time.monotonic() value; a retry that would not leave
    MIN_ATTEMPT_S before it is skipped. It does not enforce the deadline —
    callers that need a hard cap wrap this in asyncio.wait_for.
    """
    payload = {"model": config.LLM_MODEL, "messages": messages}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort

    try:
        return await _post(payload, timeout)
    except httpx.HTTPError as e:
        backoff = _retry_backoff_s(e) if retry else None
        if backoff is None:
            raise
        if deadline is not None:
            if deadline - time.monotonic() < backoff + MIN_ATTEMPT_S:
                raise
        elif backoff > MAX_UNBOUNDED_BACKOFF_S:
            raise

        status = getattr(getattr(e, "response", None), "status_code", None)
        logger.info("llm: retrying once in %.1fs after %s%s",
                    backoff, type(e).__name__, f" {status}" if status else "")
        await _sleep(backoff)
        return await _post(payload, timeout)
