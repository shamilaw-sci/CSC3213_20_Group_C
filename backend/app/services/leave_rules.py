"""
Leave rules: entitlements, counting days, and whether a request fits.

Pure functions over plain values and rows, so the statutory arithmetic is
testable on its own. Sources, from the Shop and Office Employees
(Regulation of Employment and Remuneration) Act, consolidated to 2024:

  s.6(1)(a)  First year of employment: annual holiday of 14 days if
             employment began January-March, 10 if April-June, 7 if
             July-September, 4 if October-December.
  s.6(1)(b)  Second and later years: 14 days.
  s.6(2)     The holiday for a year of employment "shall be taken in the
             year immediately succeeding". So nothing in the joining year,
             the table amount the year after, 14 from then on.
  s.6(3)     Up to 7 days' leave a year for private business, ill health or
             other reasonable cause (casual leave).
  s.6(4)(a)  In the first year, one day for each complete period of two
             months' service, which may be taken in that year.
  "year"     Twelve months from 1 January, i.e. the calendar year.

VFF policy layered on top (confirmed 2026-10-29) lives in the leave_types
rows: allowances, carry-forward, counting method, per-request caps.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Callable, Optional

HALF = Decimal("0.5")
ONE = Decimal("1.0")
ZERO = Decimal("0")

# s.6(1)(a): days by the quarter in which employment began.
FIRST_YEAR_ANNUAL = {1: 14, 2: 10, 3: 7, 4: 4}


def add_months(d: date, months: int) -> date:
    """d plus whole months, clamped to the month's end (31 Jan + 1 = 28/29 Feb)."""
    index = d.year * 12 + (d.month - 1) + months
    year, month0 = divmod(index, 12)
    month = month0 + 1
    next_month = date(year + (month == 12), (month % 12) + 1, 1)
    last_day = (next_month - timedelta(days=1)).day
    return date(year, month, min(d.day, last_day))


def complete_months(joined: date, through: date) -> int:
    """
    Complete months of service from `joined` up to and including `through`.
    Someone who joined on 15 March has two complete months at the end of
    14 May.
    """
    if through < joined:
        return 0
    months = 0
    while add_months(joined, months + 1) <= through + timedelta(days=1):
        months += 1
    return months


def annual_entitlement(joined: Optional[date], year: int, full_days: Decimal) -> Optional[Decimal]:
    """Annual leave available to take in `year`. None: join date unknown."""
    if joined is None:
        return None
    if joined.year >= year:
        return ZERO                                    # earned this year, taken next
    if joined.year == year - 1:
        quarter = (joined.month - 1) // 3 + 1
        return Decimal(FIRST_YEAR_ANNUAL[quarter])      # s.6(1)(a) via s.6(2)
    return Decimal(full_days)                           # s.6(1)(b)


def casual_entitlement(joined: Optional[date], year: int, full_days: Decimal) -> Optional[Decimal]:
    """
    Casual leave for `year`. In the joining year this is the most that can
    build up by 31 December; casual_earned_to_date() is what may be used now.
    """
    if joined is None:
        return None
    if joined.year > year:
        return ZERO
    if joined.year == year:
        return Decimal(min(complete_months(joined, date(year, 12, 31)) // 2, int(full_days)))
    return Decimal(full_days)


def casual_accrued(joined: Optional[date], through: date) -> Optional[Decimal]:
    """
    Casual leave built up by `through`, in the joining year only (s.6(4)(a));
    None in later years, where the whole allowance is available at once.
    """
    if joined is None or joined.year != through.year:
        return None
    return Decimal(complete_months(joined, through) // 2)


def casual_earned_to_date(joined: Optional[date], year: int, today: date) -> Optional[Decimal]:
    """
    The cap on usable casual leave for `year`, as of `today`. VFF policy
    (confirmed 2026-10-31): in the joining year casual leave accrues to date,
    one day per complete two months worked so far, so nobody takes casual
    leave they have not earned yet, whatever dates the leave is for.

    None means no cap: any year other than the current joining year. A past
    joining year has finished, so all of it has been earned.
    """
    if joined is None or joined.year != year or today.year != year:
        return None
    return casual_accrued(joined, today)


def fixed_entitlement(joined: Optional[date], year: int, full_days: Decimal) -> Decimal:
    """Allowances with no first-year rule (sick): full, unless not yet joined."""
    if joined is not None and joined.year > year:
        return ZERO
    return Decimal(full_days)


def entitlement_for(rule: str, joined: Optional[date], year: int, full_days) -> Optional[Decimal]:
    full = Decimal(str(full_days or 0))
    if rule == "soe_annual":
        return annual_entitlement(joined, year, full)
    if rule == "soe_casual":
        return casual_entitlement(joined, year, full)
    return fixed_entitlement(joined, year, full)


def carry_forward(previous_remaining: Decimal, cap) -> Decimal:
    """Unused days moved to next year, never negative, never over the cap."""
    return min(max(Decimal(previous_remaining), ZERO), Decimal(str(cap or 0)))


# --------------------------------------------------------------------------
# Counting a request's days
# --------------------------------------------------------------------------

def leave_days(
    start: date,
    end: date,
    half_day: str,
    counts_calendar_days: bool,
    is_working_day: Callable[[date], bool],
) -> list[tuple[date, Decimal]]:
    """
    The days a request uses. Working-day types skip the employee's rest days
    and VFF holidays (via is_working_day, backed by resolve_day); calendar-day
    types count every date. A half day is half of one date.
    """
    days = []
    d = start
    while d <= end:
        if counts_calendar_days or is_working_day(d):
            days.append((d, HALF if half_day != "none" else ONE))
        d += timedelta(days=1)
    return days


def days_by_year(days: list[tuple[date, Decimal]]) -> dict[int, Decimal]:
    out: dict[int, Decimal] = {}
    for d, fraction in days:
        out[d.year] = out.get(d.year, ZERO) + fraction
    return out


# --------------------------------------------------------------------------
# Does a request fit?
# --------------------------------------------------------------------------

@dataclass
class Balance:
    """One employee's position for one leave type and year."""
    entitled: Decimal = ZERO
    carried_forward: Decimal = ZERO
    adjustment: Decimal = ZERO
    approved: Decimal = ZERO
    pending: Decimal = ZERO
    # Set for casual leave in the current joining year: how much of
    # `entitled` has been earned so far. None: all of it.
    earned_to_date: Optional[Decimal] = None

    @property
    def usable_entitlement(self) -> Decimal:
        if self.earned_to_date is None:
            return self.entitled
        return min(self.entitled, self.earned_to_date)

    @property
    def total(self) -> Decimal:
        return self.usable_entitlement + self.carried_forward + self.adjustment

    @property
    def available(self) -> Decimal:
        """What a new request may still use: pending requests are reserved."""
        return self.total - self.approved - self.pending

    @property
    def remaining(self) -> Decimal:
        """Unused once approved leave is counted; the basis for carry-forward."""
        return self.total - self.approved


@dataclass
class LeaveType:
    name: str
    uses_balance: bool
    allow_half_day: bool
    max_days_per_request: Optional[Decimal] = None
    first_year_rule: str = "none"


@dataclass
class Check:
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def check_request(
    leave_type: LeaveType,
    days: list[tuple[date, Decimal]],
    half_day: str,
    balances: dict[int, Optional[Balance]],
) -> Check:
    """
    `balances` holds, per year the request touches, the employee's balance
    for this type EXCLUDING this request (None: no entitlement row that
    year). First-year casual accrual is already inside the balance
    (Balance.earned_to_date), so it is checked here like any other limit.
    """
    check = Check()
    if half_day != "none" and not leave_type.allow_half_day:
        check.errors.append(f"{leave_type.name} cannot be taken as a half day.")
    if not days:
        check.errors.append("There are no working days in this range.")
        return check

    total = sum((f for _, f in days), ZERO)
    cap = leave_type.max_days_per_request
    if cap is not None and total > Decimal(str(cap)):
        check.errors.append(f"{leave_type.name} is at most {Decimal(str(cap)).normalize()} days per request; this is {total.normalize()}.")

    if leave_type.uses_balance:
        for year, wanted in sorted(days_by_year(days).items()):
            balance = balances.get(year)
            if balance is None:
                check.errors.append(
                    f"No {leave_type.name.lower()} entitlement has been set up for {year} yet. Ask HR to generate it."
                )
            elif wanted > balance.available:
                message = (
                    f"Only {max(balance.available, ZERO).normalize()} days of {leave_type.name.lower()} are available in {year}; "
                    f"this request needs {wanted.normalize()}."
                )
                if balance.earned_to_date is not None and balance.earned_to_date < balance.entitled:
                    message += (
                        f" In the first year casual leave is earned as you go, one day per two complete months "
                        f"worked (Shop and Office Employees Act s.6(4)(a)): {balance.earned_to_date.normalize()} "
                        f"earned so far of {balance.entitled.normalize()} by year end."
                    )
                check.errors.append(message)
    return check
