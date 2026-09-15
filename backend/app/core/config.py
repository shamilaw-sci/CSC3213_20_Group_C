# backend/app/core/config.py
import os
from dotenv import load_dotenv

load_dotenv()

LLM_API_KEY: str = os.environ.get("LLM_API_KEY")
LLM_BASE_URL: str = os.environ.get(
    "LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
)
LLM_MODEL: str = os.environ.get("LLM_MODEL", "gemini-2.5-flash")

if not LLM_API_KEY:
    raise ValueError("LLM_API_KEY not found in environment variables")

# OpenRouteService — road-distance routing for field dispatch.
# https://openrouteservice.org/dev/#/signup (free tier, no credit card:
# 2000 directions/day, 500 matrix/day, 40/min).
#
# Deliberately NOT validated the way LLM_API_KEY is above. Routing is an
# enhancement, not a dependency: without a key the dispatch endpoint falls back
# to straight-line distances and still returns a usable visiting order, so
# refusing to boot over a missing key would take the whole API down to disable
# one optional feature.
ORS_API_KEY: str | None = os.environ.get("ORS_API_KEY") or None
ORS_BASE_URL: str = os.environ.get("ORS_BASE_URL", "https://api.openrouteservice.org")