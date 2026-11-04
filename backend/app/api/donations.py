# backend/app/api/donations.py
#
# Public donations through PayHere, and the staff Donation details page.
#
# THE PUBLIC ROUTES USE get_public_supabase, ALWAYS, for the same reason as
# app/api/volunteers.py: donors have no login, and a stale staff token in the
# visitor's browser must never break the donate page. These routes run as
# service_role; there is no anon policy on donations (015_donations.sql).
#
# MONEY RULE. A donation reaches financial_transactions only through
# record_donation_payment() (015_donations.sql), and only after PayHere has
# confirmed the payment: either a signed notify_url POST, or the Retrieval API
# when the donor comes back to the thank-you page. That function posts one
# Income row (status Cash, source_type 'donation'), restricted to the program
# for a program donation (002_restricted_funds.sql), and never posts the same
# donation twice.

import logging
import secrets
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from supabase import Client

from app.core import config
from app.core.audit import log_audit_action
from app.core.security import require_permission
from app.core.supabase import get_public_supabase, get_supabase
from app.schemas.donations import (
    DonationCheckout, DonationCheckoutCreate, DonationConfirmation,
    DonationOut, DonationProgram, DonationPurpose, DonationStatus,
    DonationSummary, DonorContribution, MonthlyDonationTotal,
    ProgramDonationTotal,
)
from app.services import email as email_service
from app.services import payhere
from app.services.program_lifecycle import COMPLETED, STORED_VALUES, ACTIVE, UPCOMING, normalize_status

logger = logging.getLogger(__name__)

router = APIRouter()

CURRENCY = "LKR"

# PayHere's checkout always asks for a payer name, email, phone and address.
# An anonymous donor gives none, so the organisation's own contact details are
# sent instead. They go to PayHere only; nothing about the donor is stored.
_ORG_PAYER = {
    "first_name": "Anonymous",
    "last_name": "Donor",
    "phone": "0777226301",
    "address": "Vets For Future",
    "city": "Colombo",
    "country": "Sri Lanka",
}

NOT_SET_UP = "Online donations are not set up yet. Please try again later."


def _new_order_id() -> str:
    # Random, not the row id: the thank-you page confirms by order id with no
    # login, so ids must not be guessable in sequence.
    return f"VFF-{secrets.token_hex(6).upper()}"


def _money(value) -> Decimal:
    return Decimal(str(value if value is not None else 0)).quantize(Decimal("0.01"))


def _format_lkr(value) -> str:
    return f"LKR {_money(value):,.2f}"


def _program_name(supabase: Client, program_id: Optional[int]) -> Optional[str]:
    if program_id is None:
        return None
    rows = supabase.table("programs").select("program_name") \
        .eq("id", program_id).execute().data or []
    return rows[0]["program_name"] if rows else None


def _get_by_order(supabase: Client, order_id: str) -> dict:
    rows = supabase.table("donations").select("*, programs(program_name)") \
        .eq("gateway_ref", order_id).execute().data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Donation not found")
    return rows[0]


def _flatten(row: dict) -> dict:
    """Move the joined program name onto the row itself."""
    out = {k: v for k, v in row.items() if k != "programs"}
    out["program_name"] = (row.get("programs") or {}).get("program_name")
    return out


def _audit_safe(row: dict) -> dict:
    """The ledger facts of a donation, without the donor's contact details."""
    keep = ("id", "amount", "currency", "purpose", "program_id", "is_anonymous",
            "status", "gateway", "gateway_ref", "finance_transaction_id", "paid_at")
    return {k: row.get(k) for k in keep}


async def _record_payment(supabase: Client, donation: dict, amount: Decimal) -> dict:
    """
    Mark the donation paid and post it to the ledger, atomically, via
    record_donation_payment(). Safe to call twice: the second call changes
    nothing. Then sends the thank-you email, once.
    """
    already_paid = donation.get("status") == DonationStatus.paid.value

    supabase.rpc(
        "record_donation_payment",
        {"p_donation_id": donation["id"], "p_amount": str(_money(amount))},
    ).execute()

    row = _get_by_order(supabase, donation["gateway_ref"])

    if not already_paid and row.get("status") == DonationStatus.paid.value:
        # Public route, no staff member: a null user_id is the accurate record,
        # as for public volunteer applications.
        await log_audit_action(
            supabase,
            user_id=None,
            action_type="DONATION_PAID",
            table_name="donations",
            old_payload=None,
            new_payload=_audit_safe(row),
        )

    await _send_thank_you_once(supabase, row)
    return row


async def _send_thank_you_once(supabase: Client, row: dict) -> None:
    """
    Thank-you email for a paid, named donation, at most once.

    The notification and the thank-you page can both confirm the same payment
    at the same moment, so the send is claimed first by setting
    thank_you_sent_at only where it is still NULL. Whoever wins the claim
    sends. A failed send releases the claim, so a later confirmation retries.
    Fail-soft, as every email here is: the donation is already recorded.
    """
    if row.get("status") != DonationStatus.paid.value or row.get("is_anonymous"):
        return
    if not row.get("donor_email") or row.get("thank_you_sent_at"):
        return

    try:
        claimed = supabase.table("donations") \
            .update({"thank_you_sent_at": datetime.now(timezone.utc).isoformat()}) \
            .eq("id", row["id"]) \
            .is_("thank_you_sent_at", "null") \
            .execute().data
    except Exception as e:
        logger.warning("Could not claim thank-you email for donation %s: %s", row["id"], e)
        return
    if not claimed:
        return  # someone else is sending it

    sent = await email_service.send_donation_thank_you(
        to_email=row["donor_email"],
        full_name=row.get("donor_name") or "Friend",
        amount=_format_lkr(row["amount"]),
        reference=row["gateway_ref"],
        program_name=(row.get("programs") or {}).get("program_name") or row.get("program_name"),
    )
    if not sent:
        try:
            supabase.table("donations").update({"thank_you_sent_at": None}) \
                .eq("id", row["id"]).execute()
        except Exception as e:
            logger.warning("Could not release thank-you claim for donation %s: %s", row["id"], e)


def _confirmation(row: dict) -> DonationConfirmation:
    return DonationConfirmation(
        order_id=row["gateway_ref"],
        status=row["status"],
        amount=row["amount"],
        purpose=row["purpose"],
        program_name=(row.get("programs") or {}).get("program_name"),
        is_anonymous=bool(row.get("is_anonymous")),
    )


# ===========================================================================
# Public: the donate page
# ===========================================================================

@router.get("/programs", response_model=List[DonationProgram])
async def donation_programs(
    supabase: Client = Depends(get_public_supabase),
):
    """
    Programs a donor can give to: Upcoming and Active. Completed programs are
    left out, because money earmarked for a finished program could never be
    spent. Names and dates only.
    """
    stored = STORED_VALUES[UPCOMING] + STORED_VALUES[ACTIVE]
    rows = supabase.table("programs") \
        .select("id, program_name, status, start_date, end_date") \
        .in_("status", stored) \
        .order("program_name") \
        .execute().data or []
    return [
        {**r, "status": normalize_status(r.get("status"))}
        for r in rows
        if normalize_status(r.get("status")) != COMPLETED
    ]


@router.post("/checkout", response_model=DonationCheckout)
async def create_checkout(
    payload: DonationCheckoutCreate,
    supabase: Client = Depends(get_public_supabase),
):
    """
    Save the donation as pending and return the signed PayHere checkout form.
    Nothing reaches the ledger here; that happens only once PayHere confirms.
    """
    if not payhere.is_configured():
        raise HTTPException(status_code=503, detail=NOT_SET_UP)

    program_name = None
    if payload.purpose == DonationPurpose.program:
        rows = supabase.table("programs").select("id, program_name, status") \
            .eq("id", payload.program_id).execute().data or []
        if not rows or normalize_status(rows[0].get("status")) == COMPLETED:
            raise HTTPException(
                status_code=400,
                detail="That program is not taking donations. Please choose another.",
            )
        program_name = rows[0]["program_name"]

    order_id = _new_order_id()
    row = {
        **payload.model_dump(mode="json", exclude_none=True),
        "amount": str(_money(payload.amount)),
        "currency": CURRENCY,
        "gateway": "payhere",
        "gateway_ref": order_id,
        # Not taken from the caller; set here so a schema change cannot let a
        # donor submit their own donation as paid.
        "status": DonationStatus.pending.value,
    }

    try:
        inserted = supabase.table("donations").insert(row).execute().data
    except Exception as e:
        logger.error("Donation insert failed: %s", e)
        raise HTTPException(status_code=500, detail="Could not start your donation. Please try again.")
    if not inserted:
        raise HTTPException(status_code=500, detail="Could not start your donation. Please try again.")

    amount = payhere.format_amount(payload.amount)
    if payload.is_anonymous:
        payer = {**_ORG_PAYER, "email": config.BREVO_REPLY_TO}
    else:
        names = (payload.donor_name or "").split(None, 1)
        payer = {
            **_ORG_PAYER,
            "first_name": names[0],
            "last_name": names[1] if len(names) > 1 else "-",
            "email": str(payload.donor_email),
            "phone": payload.donor_phone or _ORG_PAYER["phone"],
            "address": "Not provided",
        }

    item = f"Donation - {program_name}" if program_name else "Donation - General fund"

    fields = {
        "merchant_id": config.PAYHERE_MERCHANT_ID,
        "return_url": f"{config.PUBLIC_APP_URL}/donate/thank-you?order_id={order_id}",
        "cancel_url": f"{config.PUBLIC_APP_URL}/donate?cancelled={order_id}",
        "notify_url": f"{config.PUBLIC_API_URL}/api/donations/payhere/notify",
        "order_id": order_id,
        "items": item[:100],
        "currency": CURRENCY,
        "amount": amount,
        **payer,
        "hash": payhere.checkout_hash(order_id, payload.amount, CURRENCY),
    }

    return DonationCheckout(order_id=order_id, action_url=payhere.checkout_url(), fields=fields)


@router.post("/payhere/notify")
async def payhere_notify(
    request: Request,
    supabase: Client = Depends(get_public_supabase),
):
    """
    PayHere's server-to-server payment result. Only reachable when the backend
    has a public URL (PUBLIC_API_URL). Every request is checked against md5sig,
    so a forged POST cannot mark a donation paid.

    Always answers 200 with a short body: PayHere does not read it, and a
    distinguishable error would only help someone probing the route.
    """
    form = dict(await request.form())
    order_id = str(form.get("order_id", ""))

    if not payhere.notification_is_genuine(form):
        logger.warning("PayHere notification rejected (bad signature) for order %s", order_id)
        return {"ok": False}

    try:
        donation = _get_by_order(supabase, order_id)
    except HTTPException:
        logger.warning("PayHere notification for unknown order %s", order_id)
        return {"ok": False}

    status_code = str(form.get("status_code", ""))

    if status_code == payhere.STATUS_SUCCESS:
        paid = payhere.to_decimal(form.get("payhere_amount"))
        if (str(form.get("payhere_currency", "")).upper() != CURRENCY
                or paid is None or paid != _money(donation["amount"])):
            logger.error("PayHere amount mismatch for order %s: %s %s",
                         order_id, form.get("payhere_amount"), form.get("payhere_currency"))
            return {"ok": False}
        try:
            await _record_payment(supabase, donation, paid)
        except Exception as e:
            logger.error("Recording donation %s failed: %s", order_id, e)
            return {"ok": False}
        return {"ok": True}

    if status_code in (payhere.STATUS_CANCELLED, payhere.STATUS_FAILED):
        new_status = (DonationStatus.cancelled if status_code == payhere.STATUS_CANCELLED
                      else DonationStatus.failed).value
        # Only a pending donation changes: a paid one stays paid.
        supabase.table("donations").update({"status": new_status}) \
            .eq("id", donation["id"]).eq("status", DonationStatus.pending.value).execute()

    # 0 (pending) and -3 (chargeback) change nothing here. A chargeback needs a
    # person to reverse the ledger row, so it is logged for finance staff.
    if status_code == payhere.STATUS_CHARGEDBACK:
        logger.error("PayHere chargeback for donation %s; reverse it in the ledger", order_id)

    return {"ok": True}


@router.post("/confirm/{order_id}", response_model=DonationConfirmation)
async def confirm_donation(
    order_id: str,
    supabase: Client = Depends(get_public_supabase),
):
    """
    Called by the thank-you page. If the donation is still pending, ask PayHere
    whether it was paid, and record it if so. The redirect back from PayHere
    proves nothing by itself, so this never takes the browser's word for it.
    Returns no donor details.
    """
    donation = _get_by_order(supabase, order_id)

    if donation["status"] == DonationStatus.pending.value:
        if await payhere.order_is_paid(order_id, _money(donation["amount"]), CURRENCY):
            try:
                donation = await _record_payment(supabase, donation, _money(donation["amount"]))
            except Exception as e:
                logger.error("Recording donation %s failed: %s", order_id, e)
                raise HTTPException(
                    status_code=500,
                    detail="Your payment went through, but we could not record it yet. Please refresh in a moment.",
                )
    elif donation["status"] == DonationStatus.paid.value:
        # Retry a thank-you email that failed the first time.
        await _send_thank_you_once(supabase, donation)

    return _confirmation(donation)


@router.post("/cancel/{order_id}", response_model=DonationConfirmation)
async def cancel_donation(
    order_id: str,
    supabase: Client = Depends(get_public_supabase),
):
    """The donor pressed cancel on PayHere. A pending donation becomes
    cancelled; a paid one is never touched."""
    donation = _get_by_order(supabase, order_id)
    if donation["status"] == DonationStatus.pending.value:
        supabase.table("donations").update({"status": DonationStatus.cancelled.value}) \
            .eq("id", donation["id"]).eq("status", DonationStatus.pending.value).execute()
        donation = _get_by_order(supabase, order_id)
    return _confirmation(donation)


# ===========================================================================
# Staff: Donation details page
# ===========================================================================

@router.get("", response_model=List[DonationOut])
async def list_donations(
    status: Optional[DonationStatus] = None,
    purpose: Optional[DonationPurpose] = None,
    user=Depends(require_permission("finance:read")),
    supabase: Client = Depends(get_supabase),
):
    query = supabase.table("donations").select("*, programs(program_name)")
    if status:
        query = query.eq("status", status.value)
    if purpose:
        query = query.eq("purpose", purpose.value)
    rows = query.order("created_at", desc=True).execute().data or []
    return [_flatten(r) for r in rows]


@router.get("/summary", response_model=DonationSummary)
async def donation_summary(
    user=Depends(require_permission("finance:read")),
    supabase: Client = Depends(get_supabase),
):
    """Analytics for the Donation details page, from paid donations only."""
    rows = supabase.table("donations").select("*, programs(program_name)") \
        .execute().data or []
    return build_summary(rows)


def build_summary(rows: list[dict]) -> dict:
    """
    Pure function over donation rows, so the figures can be tested without a
    database. Only paid rows count as money raised. Named donors are grouped by
    email, ignoring case, so one person giving twice is one donor; their name
    is taken from their latest donation. Anonymous donations stay anonymous:
    they are counted together and never grouped into a donor.
    """
    paid = [r for r in rows if r.get("status") == DonationStatus.paid.value]
    pending_count = sum(1 for r in rows if r.get("status") == DonationStatus.pending.value)

    zero = Decimal("0.00")
    total = sum((_money(r["amount"]) for r in paid), zero)
    named = [r for r in paid if not r.get("is_anonymous")]
    anonymous = [r for r in paid if r.get("is_anonymous")]

    by_program: dict[int, dict] = {}
    for r in paid:
        if r.get("purpose") == DonationPurpose.program.value and r.get("program_id") is not None:
            entry = by_program.setdefault(r["program_id"], {
                "program_id": r["program_id"],
                "program_name": (r.get("programs") or {}).get("program_name")
                                or f"Program {r['program_id']}",
                "total": zero, "count": 0,
            })
            entry["total"] += _money(r["amount"])
            entry["count"] += 1

    donors: dict[str, dict] = {}
    for r in sorted(named, key=lambda r: r.get("paid_at") or r.get("created_at") or ""):
        key = (r.get("donor_email") or "").strip().lower()
        if not key:
            continue
        when = r.get("paid_at") or r.get("created_at")
        entry = donors.setdefault(key, {
            "donor_name": r.get("donor_name") or key,
            "donor_email": r.get("donor_email"),
            "total": zero, "count": 0,
            "first_donation_at": when, "last_donation_at": when,
        })
        entry["donor_name"] = r.get("donor_name") or entry["donor_name"]
        entry["total"] += _money(r["amount"])
        entry["count"] += 1
        entry["last_donation_at"] = when

    monthly: dict[str, dict] = defaultdict(lambda: {"total": zero, "count": 0})
    for r in paid:
        month = str(r.get("paid_at") or r.get("created_at") or "")[:7]
        if month:
            monthly[month]["total"] += _money(r["amount"])
            monthly[month]["count"] += 1

    return {
        "total_raised": total,
        "donation_count": len(paid),
        "average_donation": (total / len(paid)).quantize(Decimal("0.01")) if paid else zero,
        "largest_donation": max((_money(r["amount"]) for r in paid), default=zero),
        "named_total": sum((_money(r["amount"]) for r in named), zero),
        "named_count": len(named),
        "unique_donors": len(donors),
        "anonymous_total": sum((_money(r["amount"]) for r in anonymous), zero),
        "anonymous_count": len(anonymous),
        "program_total": sum((_money(r["amount"]) for r in paid
                              if r.get("purpose") == DonationPurpose.program.value), zero),
        "general_total": sum((_money(r["amount"]) for r in paid
                              if r.get("purpose") == DonationPurpose.general.value), zero),
        "pending_count": pending_count,
        "by_program": sorted(by_program.values(), key=lambda p: p["total"], reverse=True),
        "donors": sorted(donors.values(), key=lambda d: d["total"], reverse=True),
        "monthly": [
            {"month": m, **v} for m, v in sorted(monthly.items())
        ],
    }
