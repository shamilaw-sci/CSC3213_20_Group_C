# backend/app/services/payhere.py
#
# PayHere: checkout signing, payment notification checks, and asking PayHere
# whether an order was paid.
#
# A donation is only ever posted to the ledger after PayHere confirms it, in
# one of two ways:
#
#   1. notify_url. PayHere POSTs the result to our backend, signed with md5sig.
#      Needs a public URL, so it never arrives on localhost.
#   2. The thank-you page. When the donor comes back, the backend asks PayHere's
#      Retrieval API for the order. Works on localhost.
#
# The browser is never trusted: the return_url redirect itself proves nothing.
#
# Docs:
#   https://support.payhere.lk/api-&-mobile-sdk/checkout-api
#   https://support.payhere.lk/api-&-mobile-sdk/retrieval-api

import base64
import hashlib
import hmac
import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

import httpx

from app.core import config

logger = logging.getLogger(__name__)

# PayHere status_code values on a payment notification.
STATUS_SUCCESS = "2"
STATUS_PENDING = "0"
STATUS_CANCELLED = "-1"
STATUS_FAILED = "-2"
STATUS_CHARGEDBACK = "-3"


def is_configured() -> bool:
    """Checkout needs the merchant ID and secret."""
    return bool(config.PAYHERE_MERCHANT_ID and config.PAYHERE_MERCHANT_SECRET)


def can_verify_orders() -> bool:
    """Asking PayHere about an order needs the API key (App ID and secret)."""
    return bool(config.PAYHERE_APP_ID and config.PAYHERE_APP_SECRET)


def checkout_url() -> str:
    return f"{config.PAYHERE_BASE_URL}/pay/checkout"


def format_amount(amount: Decimal) -> str:
    """Two decimals, no thousands separator: what PayHere hashes and expects."""
    return f"{Decimal(amount).quantize(Decimal('0.01')):.2f}"


def _md5_upper(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest().upper()


def checkout_hash(order_id: str, amount: Decimal, currency: str = "LKR",
                  merchant_id: Optional[str] = None,
                  merchant_secret: Optional[str] = None) -> str:
    """
    The checkout hash: upper(md5(merchant_id + order_id + amount + currency +
    upper(md5(merchant_secret)))). Built here, never in the browser, because
    building it needs the merchant secret.
    """
    merchant_id = merchant_id or config.PAYHERE_MERCHANT_ID or ""
    merchant_secret = merchant_secret or config.PAYHERE_MERCHANT_SECRET or ""
    return _md5_upper(
        f"{merchant_id}{order_id}{format_amount(amount)}{currency}{_md5_upper(merchant_secret)}"
    )


def notification_is_genuine(form: dict, merchant_secret: Optional[str] = None,
                            merchant_id: Optional[str] = None) -> bool:
    """
    True when a notify_url POST really came from PayHere for our merchant:
    md5sig = upper(md5(merchant_id + order_id + payhere_amount +
    payhere_currency + status_code + upper(md5(merchant_secret)))).
    """
    merchant_secret = merchant_secret or config.PAYHERE_MERCHANT_SECRET
    merchant_id = merchant_id or config.PAYHERE_MERCHANT_ID
    if not merchant_secret or not merchant_id:
        return False
    if str(form.get("merchant_id", "")) != str(merchant_id):
        return False

    expected = _md5_upper(
        f"{form.get('merchant_id', '')}{form.get('order_id', '')}"
        f"{form.get('payhere_amount', '')}{form.get('payhere_currency', '')}"
        f"{form.get('status_code', '')}{_md5_upper(merchant_secret)}"
    )
    # Constant-time compare, so the check cannot be probed byte by byte.
    return hmac.compare_digest(expected, str(form.get("md5sig", "")).upper())


def to_decimal(value) -> Optional[Decimal]:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _site_headers() -> dict:
    """
    PayHere only answers API keys from the domains listed on the key ("Access
    denied for the domain" otherwise). A server call carries no browser Origin,
    so name the site the key was created for: PUBLIC_APP_URL, which is
    http://localhost:3000 while developing.
    """
    return {"Origin": config.PUBLIC_APP_URL, "Referer": f"{config.PUBLIC_APP_URL}/"}


async def _access_token(client: httpx.AsyncClient) -> Optional[str]:
    basic = base64.b64encode(
        f"{config.PAYHERE_APP_ID}:{config.PAYHERE_APP_SECRET}".encode()
    ).decode()
    response = await client.post(
        f"{config.PAYHERE_BASE_URL}/merchant/v1/oauth/token",
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
            **_site_headers(),
        },
        data={"grant_type": "client_credentials"},
    )
    if response.status_code != 200:
        logger.warning("PayHere token request failed: HTTP %s %s",
                       response.status_code, response.text[:300])
        return None
    return response.json().get("access_token")


# Payment statuses that mean the money was taken. PayHere's docs list RECEIVED
# for a completed payment. The sandbox shows successful test payments as
# AUTHORIZED instead (seen 2026-11-03), so in sandbox mode that counts too. In
# live mode only RECEIVED does.
def _paid_statuses() -> set[str]:
    return {"RECEIVED", "AUTHORIZED"} if config.PAYHERE_SANDBOX else {"RECEIVED"}


async def search_order(order_id: str) -> dict:
    """
    Raw Retrieval API answer for one order, for order_is_paid() and for
    scripts/check_payhere_order.py. Never raises; problems come back as
    {"error": "..."} so they can be logged or printed.
    """
    if not can_verify_orders():
        return {"error": "PAYHERE_APP_ID / PAYHERE_APP_SECRET are not set in backend/.env"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            token = await _access_token(client)
            if not token:
                return {"error": "PayHere refused the App ID / App Secret (token request failed)"}
            response = await client.get(
                f"{config.PAYHERE_BASE_URL}/merchant/v1/payment/search",
                params={"order_id": order_id},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    **_site_headers(),
                },
            )
        if response.status_code != 200:
            return {"error": f"payment search HTTP {response.status_code}: {response.text[:300]}"}
        return response.json()
    except Exception as e:
        return {"error": f"payment search failed: {e}"}


def paid_in_full(body: dict, order_id: str, amount: Decimal, currency: str = "LKR") -> bool:
    """
    True when a Retrieval API answer lists a completed payment for exactly this
    order, in this currency, for exactly this amount.
    """
    # status 1 = payments found; 0 pending; -1 none; -2 declined.
    if body.get("status") != 1:
        return False

    expected = Decimal(amount).quantize(Decimal("0.01"))
    for payment in body.get("data") or []:
        if str(payment.get("order_id")) != order_id:
            continue
        if str(payment.get("status", "")).strip().upper() not in _paid_statuses():
            continue
        if str(payment.get("currency", "")).upper() != currency:
            continue
        # PayHere's own example shows `amount` and `amount_detail.gross`
        # disagreeing, so accept the payment if either is the full amount.
        paid = {to_decimal(payment.get("amount")),
                to_decimal((payment.get("amount_detail") or {}).get("gross"))}
        if expected in paid:
            return True
    return False


async def order_is_paid(order_id: str, amount: Decimal, currency: str = "LKR") -> bool:
    """
    Ask PayHere whether `order_id` was paid in full. Any error counts as "not
    confirmed yet" and is logged with what PayHere said, so a payment that is
    not being recorded can be explained from the backend log.
    """
    body = await search_order(order_id)
    if paid_in_full(body, order_id, amount, currency):
        return True

    if body.get("error"):
        logger.warning("PayHere check for %s: %s", order_id, body["error"])
    else:
        seen = [
            {k: p.get(k) for k in ("order_id", "status", "currency", "amount")}
            | {"gross": (p.get("amount_detail") or {}).get("gross")}
            for p in body.get("data") or []
        ]
        logger.warning(
            "PayHere check for %s: not confirmed (expected %s %s). PayHere said status=%s msg=%s payments=%s",
            order_id, currency, amount, body.get("status"), body.get("msg"), seen,
        )
    return False
