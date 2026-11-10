# backend/app/schemas/donations.py

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, model_validator


class DonationPurpose(str, Enum):
    program = "program"   # earmarked for one program (restricted funds)
    general = "general"   # wherever it is needed most


class DonationStatus(str, Enum):
    pending = "pending"
    paid = "paid"
    failed = "failed"
    cancelled = "cancelled"
    # Was paid, then its ledger row was voided in Finance (migration 023, D3).
    refunded = "refunded"


# Mirrors the amount CHECK in db/migrations/015_donations.sql, so a bad amount
# is a 422 naming the field rather than a 500 from Postgres.
MIN_DONATION = Decimal("100")
MAX_DONATION = Decimal("999999.99")


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------

class DonationProgram(BaseModel):
    """A program shown in the donate page dropdown: Upcoming or Active only."""
    id: int
    program_name: str
    status: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class DonationCheckoutCreate(BaseModel):
    """
    The public donate form. Note what is absent: status, gateway_ref and
    every ledger field. A caller cannot mark their own donation as paid.
    """
    amount: Decimal = Field(ge=MIN_DONATION, le=MAX_DONATION, decimal_places=2)
    purpose: DonationPurpose
    program_id: Optional[int] = None
    is_anonymous: bool = False
    donor_name: Optional[str] = Field(default=None, max_length=150)
    donor_email: Optional[EmailStr] = None
    donor_phone: Optional[str] = Field(default=None, max_length=30)
    message: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _check(self):
        if self.purpose == DonationPurpose.program and self.program_id is None:
            raise ValueError("Choose the program you would like to support.")
        if self.purpose == DonationPurpose.general:
            self.program_id = None

        if self.is_anonymous:
            # Anonymous means nothing about the donor is stored, even if the
            # form had details typed in before the toggle was switched on.
            self.donor_name = None
            self.donor_email = None
            self.donor_phone = None
        else:
            self.donor_name = (self.donor_name or "").strip() or None
            self.donor_phone = (self.donor_phone or "").strip() or None
            if not self.donor_name:
                raise ValueError("Please tell us your name, or choose to donate anonymously.")
            if not self.donor_email:
                raise ValueError("Please give your email address, or choose to donate anonymously.")

        self.message = (self.message or "").strip() or None
        return self


class DonationCheckout(BaseModel):
    """What the browser needs to post the donor to PayHere's checkout page.
    `fields` is posted as-is, as a form; it includes the hash we signed."""
    order_id: str
    action_url: str
    fields: dict[str, str]


class DonationConfirmation(BaseModel):
    """What the thank-you page shows. No donor details: anyone holding the
    order id can call the confirm route."""
    order_id: str
    status: DonationStatus
    amount: Decimal
    purpose: DonationPurpose
    program_name: Optional[str] = None
    is_anonymous: bool


# ---------------------------------------------------------------------------
# Staff: Donation details page
# ---------------------------------------------------------------------------

class DonationOut(BaseModel):
    id: int
    amount: Decimal
    currency: str
    purpose: DonationPurpose
    program_id: Optional[int] = None
    program_name: Optional[str] = None
    is_anonymous: bool
    donor_name: Optional[str] = None
    donor_email: Optional[str] = None
    donor_phone: Optional[str] = None
    message: Optional[str] = None
    status: DonationStatus
    gateway: str
    gateway_ref: Optional[str] = None
    finance_transaction_id: Optional[int] = None
    thank_you_sent_at: Optional[datetime] = None
    created_at: datetime
    paid_at: Optional[datetime] = None
    refunded_at: Optional[datetime] = None
    # Something PayHere reported that needs a person: a chargeback or a
    # payment for the wrong amount (D3, D4).
    gateway_note: Optional[str] = None
    # Pending for over a day: the donor almost certainly left PayHere without
    # paying. Worked out when read, not stored (D4).
    expired: bool = False


class DonorContribution(BaseModel):
    """One named donor, grouped by email address."""
    donor_name: str
    donor_email: str
    total: Decimal
    count: int
    first_donation_at: Optional[datetime] = None
    last_donation_at: Optional[datetime] = None


class ProgramDonationTotal(BaseModel):
    program_id: int
    program_name: str
    total: Decimal
    count: int


class MonthlyDonationTotal(BaseModel):
    month: str  # YYYY-MM
    total: Decimal
    count: int


class DonationSummary(BaseModel):
    """Analytics over PAID donations only. Pending, failed and cancelled
    donations never reached the ledger, so they are not money raised."""
    total_raised: Decimal
    donation_count: int
    average_donation: Decimal
    largest_donation: Decimal
    named_total: Decimal
    named_count: int
    unique_donors: int
    anonymous_total: Decimal
    anonymous_count: int
    program_total: Decimal
    general_total: Decimal
    # Pending for less than a day; older ones count as expired (D4).
    pending_count: int
    expired_count: int = 0
    refunded_count: int = 0
    refunded_total: Decimal = Decimal("0.00")
    # Donations with a PayHere problem staff should look at.
    flagged_count: int = 0
    by_program: list[ProgramDonationTotal]
    donors: list[DonorContribution]
    monthly: list[MonthlyDonationTotal]
