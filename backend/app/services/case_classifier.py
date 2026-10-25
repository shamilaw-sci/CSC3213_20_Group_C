# backend/app/services/case_classifier.py
import json
import logging
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
        data = await complete(messages)
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
        logger.warning("case_classifier: classification failed, defaulting to Medium: %s", e)
        return {
            "urgency": "Medium",
            "reason": "Automatic classification unavailable.",
            "source": SOURCE_CLASSIFIER_ERROR,
        }
