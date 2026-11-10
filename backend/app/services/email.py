# backend/app/services/email.py
#
# Transactional email via Brevo, for volunteer approvals, assignment notices
# and donation thank-you emails.
#
# FAIL-SOFT BY CONTRACT. Every function here returns a bool and never raises.
# Email is a notification, never a control: approving a volunteer and assigning
# them to a shift are the real acts, and both must succeed whether or not Brevo
# is reachable, keyed, or in a good mood. A caller that lets a failed send abort
# its own mutation has misunderstood this module.
#
# Brevo specifics that are easy to get wrong:
#   - The API key goes in an `api-key` header. NOT `Authorization: Bearer`.
#   - Success is 201 (or 202 for a scheduled send), not 200.
#   - The sender address must be one Brevo has verified, or every call 400s.
#
# Free tier is 300 emails/day shared across transactional and marketing. That is
# ample for approvals, but bulk-assigning twenty volunteers to a Saturday clinic
# spends twenty of it in one click. Deliverability is the bigger constraint:
# Gmail, Yahoo and Microsoft have required DKIM since February 2024, so sending
# from an unauthenticated free-tier sender lands in spam often enough that the
# roster's "Copy link" button is best understood as the primary channel and this
# module as the optimistic one.

import html
import logging
from typing import Optional

import httpx

from app.core import config

logger = logging.getLogger(__name__)


def volunteer_link(access_token: str) -> str:
    """The volunteer's personal page. Built from PUBLIC_APP_URL because the
    backend has no other way to know where the frontend is deployed."""
    return f"{config.PUBLIC_APP_URL}/my-assignments/{access_token}"


async def _send(
    to_email: str,
    to_name: Optional[str],
    subject: str,
    html_content: str,
) -> bool:
    """
    Returns True if Brevo accepted the message.

    Every failure path — missing key, missing sender, timeout, non-2xx,
    malformed response — is logged and swallowed. The token is deliberately not
    logged anywhere in here, including on the error paths: it is the
    authorization for the volunteer's page, and an exception traceback landing
    in a log aggregator is exactly how such things leak.
    """
    if not config.BREVO_API_KEY or not config.BREVO_SENDER_EMAIL:
        logger.info(
            "Brevo not configured (key=%s, sender=%s); skipping '%s' to %s",
            bool(config.BREVO_API_KEY), bool(config.BREVO_SENDER_EMAIL),
            subject, to_email,
        )
        return False

    payload = {
        "sender": {
            "email": config.BREVO_SENDER_EMAIL,
            "name": config.BREVO_SENDER_NAME,
        },
        # Whatever address the From: is forced to be — on the free tier without
        # domain authentication that may be one Brevo issues rather than an
        # organisation address — a volunteer hitting reply should reach a human.
        "replyTo": {
            "email": config.BREVO_REPLY_TO,
            "name": config.BREVO_SENDER_NAME,
        },
        "to": [{"email": to_email, **({"name": to_name} if to_name else {})}],
        "subject": subject,
        "htmlContent": html_content,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{config.BREVO_BASE_URL}/smtp/email",
                headers={
                    "api-key": config.BREVO_API_KEY,
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                json=payload,
            )
        if response.status_code in (201, 202):
            return True

        # 400 here is nearly always an unverified sender; 401 a bad key; 429 the
        # daily cap. Logging the body makes those distinguishable without
        # needing to reproduce.
        logger.warning(
            "Brevo rejected '%s' to %s: HTTP %s %s",
            subject, to_email, response.status_code, response.text[:300],
        )
        return False
    except Exception as e:
        logger.warning("Brevo send failed for '%s' to %s: %s", subject, to_email, e)
        return False


_PERSONAL_LINK_NOTE = "This link is personal to you. Please don&rsquo;t forward it."


def _shell(heading: str, body: str, footer_note: str = _PERSONAL_LINK_NOTE) -> str:
    """Minimal inline-styled HTML. No external CSS or images: mail clients strip
    the former and block the latter, and a remote image would leak the open.
    `footer_note` is the last footer line; volunteer emails keep the default."""
    return (
        '<div style="font-family:system-ui,Segoe UI,Arial,sans-serif;'
        'max-width:560px;margin:0 auto;color:#1f2937;line-height:1.6">'
        f'<h2 style="color:#047857;margin-bottom:16px">{heading}</h2>'
        f"{body}"
        '<hr style="border:none;border-top:1px solid #e5e7eb;margin:28px 0">'
        '<p style="font-size:12px;color:#6b7280">'
        "Vets For Future — Sri Lanka&rsquo;s first organization specializing in "
        "humane animal population control.<br>"
        f"{footer_note}"
        "</p></div>"
    )


def _button(url: str, label: str) -> str:
    return (
        f'<p style="margin:24px 0"><a href="{html.escape(url, quote=True)}" '
        'style="background:#047857;color:#ffffff;padding:12px 22px;'
        'border-radius:6px;text-decoration:none;display:inline-block;'
        f'font-weight:600">{label}</a></p>'
        f'<p style="font-size:12px;color:#6b7280">If the button doesn&rsquo;t '
        f'work, paste this into your browser:<br>{html.escape(url)}</p>'
    )


async def send_volunteer_approved(
    to_email: str, full_name: str, access_token: str
) -> bool:
    """Welcome mail carrying the volunteer's personal link."""
    link = volunteer_link(access_token)
    first_name = html.escape(full_name.split()[0] if full_name.split() else full_name)
    return await _send(
        to_email,
        full_name,
        "You're approved — welcome to Vets For Future",
        _shell(
            f"Welcome, {first_name}!",
            "<p>Your application to volunteer with Vets For Future has been "
            "approved. Thank you for offering your time.</p>"
            "<p>Use the link below any time to see what you&rsquo;ve been asked "
            "to help with, and to let us know whether you can make it. There is "
            "no password — the link itself is your way in, so keep it to "
            "yourself.</p>"
            + _button(link, "View my assignments"),
        ),
    )


async def send_assignment_notice(
    to_email: str,
    full_name: str,
    access_token: str,
    assignment_title: str,
    when: Optional[str] = None,
    location: Optional[str] = None,
) -> bool:
    """Sent on each new assignment. `when` and `location` are pre-formatted by
    the caller, which owns how a wall-clock shift time should read."""
    link = volunteer_link(access_token)
    first_name = html.escape(full_name.split()[0] if full_name.split() else full_name)

    details = f"<p><strong>{html.escape(assignment_title)}</strong>"
    if when:
        details += f"<br>{html.escape(when)}"
    if location:
        details += f"<br>{html.escape(location)}"
    details += "</p>"

    return await _send(
        to_email,
        full_name,
        f"You've been assigned: {assignment_title}",
        _shell(
            f"Hello {first_name},",
            "<p>You&rsquo;ve been assigned to the following:</p>"
            + details
            + "<p>Please let us know whether you can make it — it takes one "
            "tap, and it helps us know who to expect.</p>"
            + _button(link, "Accept or decline"),
        ),
    )


async def send_donation_thank_you(
    to_email: str,
    full_name: str,
    amount: str,
    reference: str,
    program_name: Optional[str] = None,
) -> bool:
    """Thank-you mail after a donation is confirmed paid. Only named donors get
    one: an anonymous donation stores no email. `amount` is pre-formatted by the
    caller, e.g. "LKR 5,000.00"."""
    first_name = html.escape(full_name.split()[0] if full_name.split() else full_name)
    purpose = (
        f"the <strong>{html.escape(program_name)}</strong> program"
        if program_name
        else "our work wherever it is needed most"
    )
    return await _send(
        to_email,
        full_name,
        "Thank you for your donation to Vets For Future",
        _shell(
            f"Thank you, {first_name}!",
            f"<p>We have received your donation of <strong>{html.escape(amount)}</strong> "
            f"towards {purpose}.</p>"
            "<p>Every rupee goes to sterilization, vaccination and free clinic "
            "care for animals across Sri Lanka. Your support makes that work "
            "possible.</p>"
            f'<p style="font-size:13px;color:#6b7280">Donation reference: '
            f"{html.escape(reference)}</p>",
            footer_note="Please keep this email as your donation receipt.",
        ),
    )


_SHIFT_NOTICE = {
    "cancelled": (
        "Shift cancelled: {title}",
        "<p>The following shift has been <strong>cancelled</strong>. You don&rsquo;t "
        "need to come. Thank you for being ready to help.</p>",
    ),
    "changed": (
        "Shift changed: {title}",
        "<p>The details of a shift you&rsquo;re assigned to have changed. Here "
        "is how it looks now:</p>",
    ),
    "removed": (
        "You're no longer on: {title}",
        "<p>You&rsquo;ve been taken off the following shift. You don&rsquo;t "
        "need to come. Thank you for offering your time.</p>",
    ),
}


async def send_shift_notice(
    kind: str,
    to_email: str,
    full_name: str,
    access_token: str,
    assignment_title: str,
    when: Optional[str] = None,
    location: Optional[str] = None,
) -> bool:
    """Tell a volunteer that a shift they are on was cancelled ("cancelled"),
    had its date, time or place changed ("changed"), or that they were taken
    off it ("removed"). Fail-soft like every other sender here."""
    subject, intro = _SHIFT_NOTICE[kind]
    link = volunteer_link(access_token)
    first_name = html.escape(full_name.split()[0] if full_name.split() else full_name)

    details = f"<p><strong>{html.escape(assignment_title)}</strong>"
    if when:
        details += f"<br>{html.escape(when)}"
    if location:
        details += f"<br>{html.escape(location)}"
    details += "</p>"

    extra = (
        "<p>If you can no longer make it, please let us know.</p>"
        if kind == "changed" else ""
    )
    return await _send(
        to_email,
        full_name,
        subject.format(title=assignment_title),
        _shell(
            f"Hello {first_name},",
            intro + details + extra + _button(link, "View my assignments"),
        ),
    )


async def send_volunteer_new_link(
    to_email: str, full_name: str, access_token: str
) -> bool:
    """Sent when staff reset a volunteer's personal link (V7). The old link
    stops working at once."""
    link = volunteer_link(access_token)
    first_name = html.escape(full_name.split()[0] if full_name.split() else full_name)
    return await _send(
        to_email,
        full_name,
        "Your new Vets For Future volunteer link",
        _shell(
            f"Hello {first_name},",
            "<p>We&rsquo;ve given you a new personal link for your volunteer "
            "assignments. Your old link no longer works.</p>"
            + _button(link, "View my assignments"),
        ),
    )
