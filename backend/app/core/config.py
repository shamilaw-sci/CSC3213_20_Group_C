# backend/app/core/config.py
import logging
import os
from dotenv import load_dotenv

load_dotenv()

LLM_API_KEY: str = os.environ.get("LLM_API_KEY")
LLM_BASE_URL: str = os.environ.get(
    "LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
)
# gemini-2.5-flash was the default until Google withdrew it from new API keys
# (it now 404s), so a deploy without LLM_MODEL set silently defaulted every
# classification. Matches the model .env actually runs on.
LLM_MODEL: str = os.environ.get("LLM_MODEL", "gemini-3.5-flash")

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

# PayHere: online donations (https://support.payhere.lk/api-&-mobile-sdk/checkout-api).
#
# Unvalidated at import, like ORS and Brevo above: without these the donate
# page says online donations are not set up, and the rest of the API runs as
# normal.
#
# Sandbox accounts (sandbox.payhere.lk) are free and need no bank details.
# PAYHERE_SANDBOX=true / false always wins. When it is not set, the app is in
# sandbox only while it runs on localhost (D7): a real deployment that forgets
# the setting must not quietly take test payments, where AUTHORIZED also
# counts as paid.
def _payhere_sandbox_default() -> bool:
    raw = (os.environ.get("PAYHERE_SANDBOX") or "").strip().lower()
    if raw in ("true", "1", "yes"):
        return True
    if raw in ("false", "0", "no"):
        return False
    app_url = os.environ.get("PUBLIC_APP_URL", "http://localhost:3000").lower()
    return "localhost" in app_url or "127.0.0.1" in app_url


PAYHERE_SANDBOX: bool = _payhere_sandbox_default()
PAYHERE_BASE_URL: str = (
    "https://sandbox.payhere.lk" if PAYHERE_SANDBOX else "https://www.payhere.lk"
)
# Merchant ID and Merchant Secret: Integrations page, for the domain this runs
# on ("localhost" while developing). The secret signs every checkout and checks
# every payment notification, so it never leaves the backend.
PAYHERE_MERCHANT_ID: str | None = os.environ.get("PAYHERE_MERCHANT_ID") or None
PAYHERE_MERCHANT_SECRET: str | None = os.environ.get("PAYHERE_MERCHANT_SECRET") or None
# App ID and App Secret: Settings > API Keys. Used to ask PayHere whether an
# order was paid when the donor comes back to the thank-you page. That is how a
# payment is confirmed on localhost, where PayHere cannot reach notify_url.
PAYHERE_APP_ID: str | None = os.environ.get("PAYHERE_APP_ID") or None
PAYHERE_APP_SECRET: str | None = os.environ.get("PAYHERE_APP_SECRET") or None

# Where PayHere can reach this backend, for its server-to-server payment
# notification. On localhost PayHere cannot call it, so payments are confirmed
# through the thank-you page instead. Set it to a public URL (a deployment or an
# ngrok tunnel to port 8000) to get the notification as well.
PUBLIC_API_URL: str = os.environ.get("PUBLIC_API_URL", "http://localhost:8000").rstrip("/")

# PayHere's checkout always asks for a phone number and email. An anonymous
# donor gives none, so these organisation details are sent instead (D8).
# PayHere's receipt for an anonymous donation therefore goes to this email.
PAYHERE_ANON_PHONE: str = os.environ.get("PAYHERE_ANON_PHONE", "0777226301")
PAYHERE_ANON_EMAIL: str = os.environ.get("PAYHERE_ANON_EMAIL") or BREVO_REPLY_TO

logging.getLogger(__name__).info(
    "PayHere mode: %s (set PAYHERE_SANDBOX to change it)",
    "SANDBOX, test payments only" if PAYHERE_SANDBOX else "LIVE",
)
