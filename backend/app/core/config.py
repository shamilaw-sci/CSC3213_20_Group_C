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

# Brevo — transactional email for volunteer approvals and assignment notices.
# https://developers.brevo.com/reference/sendtransacemail
#
# Unvalidated at import, for the same reason as ORS_API_KEY above and more so:
# email here is a notification, never a control. Every send is fail-soft (see
# app/services/email.py), so a missing key degrades the feature to "staff copy
# the link and send it by WhatsApp" — which is the fallback the roster UI is
# built around anyway, because Brevo's free tier sending from an
# unauthenticated sender lands in spam often enough to expect it.
BREVO_API_KEY: str | None = os.environ.get("BREVO_API_KEY") or None
BREVO_BASE_URL: str = os.environ.get("BREVO_BASE_URL", "https://api.brevo.com/v3")

# Must be a sender Brevo has verified, or every send is rejected with a 400.
# On the free tier without domain authentication this may have to be an address
# Brevo issues rather than a vetsforfuture.org one — which is why REPLY_TO
# exists separately: whatever the From: has to say, a volunteer hitting reply
# should reach a human here.
BREVO_SENDER_EMAIL: str | None = os.environ.get("BREVO_SENDER_EMAIL") or None
BREVO_SENDER_NAME: str = os.environ.get("BREVO_SENDER_NAME", "Vets For Future")
BREVO_REPLY_TO: str = os.environ.get("BREVO_REPLY_TO", "vetsforfuturesl@gmail.com")

# The frontend origin, needed to build a volunteer's personal link. The backend
# has no other way to know where it is deployed, and a link built against the
# wrong origin is worse than no email at all — it looks legitimate and 404s.
PUBLIC_APP_URL: str = os.environ.get("PUBLIC_APP_URL", "http://localhost:3000").rstrip("/")