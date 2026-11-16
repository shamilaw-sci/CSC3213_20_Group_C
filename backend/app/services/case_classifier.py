# backend/app/services/case_classifier.py
import asyncio
import json
import logging
import time

import httpx
from app.services.llm import complete

logger = logging.getLogger(__name__)

VALID_URGENCY = {"Low", "Medium", "High", "Critical"}

# Every return carries a source so a fail-soft default can never be mistaken
# for a real classification downstream. Values must match the CHECK constraint
# in db/migrations/005_urgency_reason.sql.
SOURCE_AI = "ai"
SOURCE_NO_DESCRIPTION = "default_no_description"
SOURCE_CLASSIFIER_ERROR = "default_classifier_error"
SOURCE_INVALID_LABEL = "default_invalid_label"

# The prompt asks for one short sentence; this only guards against a model
# that ignores that, so a runaway answer can't bloat the row and the card.
MAX_REASON_LEN = 300

# create_case classifies BEFORE it inserts, so this whole wait sits inside the
# public report request. If that request outlives the serverless function limit
# the report is lost outright — far worse than a labelled default.
#
# ASSUMES A 10 s VERCEL FUNCTION LIMIT — confirm against the dashboard before
# deploy. 6 s for classification leaves ~4 s for cold start, the insert, and
# the audit row's read-then-write. If the real limit is higher this can grow;
# if it is lower, it MUST shrink.
#
# Measured on gemini-3.5-flash (2026-10-26, free tier): successes took 5-60 s
# with default thinking; with reasoning_effort="none" the few that succeeded
# took 2-13 s, so most classifications hit this cap and defaulted. On
# gemini-3.5-flash-lite (2026-11-16) every one finished in 2 s or less. A
# default that still happens is labelled on the board and flagged by the
# chatbot.
CLASSIFY_BUDGET_S = 6.0
CLASSIFY_TIMEOUT = httpx.Timeout(5.0, connect=2.0)

# gemini-3.5-flash-lite (the default since 2026-11-16) rejects "none" with a
# 400, which defaulted every case. On it, "low" classified 8 test reports
# across all four levels correctly, each in 1.3-2.0 s; "minimal" was also 8/8
# but took up to 5 s, close to the budget above. If LLM_MODEL is changed,
# check this value is accepted: a rejected one defaults every case, and the
# log names the status.
CLASSIFY_REASONING_EFFORT = "low"

CLASSIFY_PROMPT = """You triage animal rescue reports for a Sri Lankan animal \
welfare nonprofit. Given an animal type and description, classify urgency.

Critical: life-threatening, actively bleeding, hit by vehicle, suspected rabies
High: visible injury needing prompt care, distressed/aggressive animal
Medium: sick but stable, chronic-looking issue, needs a vet visit soon
Low: abandonment/neglect with no visible injury, general welfare check

Respond with ONLY a JSON object: {"urgency": "<level>", "reason": "<one short sentence>"}
No other text."""


async def classify_case_urgency(animal_type: str, description: str | None) -> dict:
    """Returns {"urgency", "reason", "source"}. Never raises — a failed
    classification must not block a public report."""
    if not description:
        return {
            "urgency": "Medium",
            "reason": "No description provided — default urgency.",
            "source": SOURCE_NO_DESCRIPTION,
        }

    messages = [
        {"role": "system", "content": CLASSIFY_PROMPT},
        {"role": "user", "content": f"Animal: {animal_type}\nDescription: {description}"},
    ]

    try:
        # wait_for is the hard cap; deadline lets complete() skip a retry
        # that could not finish inside it rather than spend quota on one.
        data = await asyncio.wait_for(
            complete(
                messages,
                timeout=CLASSIFY_TIMEOUT,
                reasoning_effort=CLASSIFY_REASONING_EFFORT,
                retry=True,
                deadline=time.monotonic() + CLASSIFY_BUDGET_S,
            ),
            CLASSIFY_BUDGET_S,
        )
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        urgency = parsed.get("urgency")
        reason = parsed.get("reason")
        reason = reason.strip()[:MAX_REASON_LEN] if isinstance(reason, str) else ""

        if urgency not in VALID_URGENCY:
            # The model's reason argues for a label we are not using, so
            # storing it next to "Medium" would misrepresent the decision.
            logger.warning("case_classifier: invalid urgency label %r, defaulting to Medium", urgency)
            return {
                "urgency": "Medium",
                "reason": "Classifier returned an unrecognised urgency — default urgency.",
                "source": SOURCE_INVALID_LABEL,
            }

        return {"urgency": urgency, "reason": reason or None, "source": SOURCE_AI}
    except Exception as e:
        # Type and repr, not str(e): httpx timeouts stringify to "", which
        # logged a failure with no clue what failed. No traceback — this is
        # an expected, handled path.
        logger.warning(
            "case_classifier: classification failed, defaulting to Medium: %s: %r",
            type(e).__name__, e,
        )
        return {
            "urgency": "Medium",
            "reason": "Automatic classification unavailable.",
            "source": SOURCE_CLASSIFIER_ERROR,
        }
