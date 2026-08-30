# backend/app/services/case_classifier.py
import json
import logging
from app.services.llm import complete

logger = logging.getLogger(__name__)

VALID_URGENCY = {"Low", "Medium", "High", "Critical"}

CLASSIFY_PROMPT = """You triage animal rescue reports for a Sri Lankan animal \
welfare nonprofit. Given an animal type and description, classify urgency.

Critical: life-threatening, actively bleeding, hit by vehicle, suspected rabies
High: visible injury needing prompt care, distressed/aggressive animal
Medium: sick but stable, chronic-looking issue, needs a vet visit soon
Low: abandonment/neglect with no visible injury, general welfare check

Respond with ONLY a JSON object: {"urgency": "<level>", "reason": "<one short sentence>"}
No other text."""


async def classify_case_urgency(animal_type: str, description: str | None) -> dict:
    if not description:
        return {"urgency": "Medium", "reason": "No description provided — default urgency."}

    messages = [
        {"role": "system", "content": CLASSIFY_PROMPT},
        {"role": "user", "content": f"Animal: {animal_type}\nDescription: {description}"},
    ]

    try:
        data = await complete(messages)
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        urgency = parsed.get("urgency", "Medium")
        if urgency not in VALID_URGENCY:
            urgency = "Medium"
        return {"urgency": urgency, "reason": parsed.get("reason", "")}
    except Exception as e:
        logger.warning("case_classifier: classification failed, defaulting to Medium: %s", e)
        return {"urgency": "Medium", "reason": "Automatic classification unavailable."}