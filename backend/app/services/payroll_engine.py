"""
The payroll engine, v1: one employee's pay for one month.

Pure, over rows already fetched. Rules (confirmed 2026-11-12):

  * A day's pay is base salary / 30, whatever the month's length.
  * A full month employed is paid the full base salary. A part month
    (joined or left during it) is paid days employed x the daily rate,
    never more than the base salary.
  * Approved leave of an unpaid type (no-pay leave) is deducted at the
    daily rate, for days inside the employed span, never below zero.
  * Absences from a closed month (month close, migration 029) are deducted
    in arrears, by the next payroll generated after closing, at the same
    daily rate (confirmed 2026-11-12). Half a day of leave with no clock-in
    for the other half is half a day's absence.
  * Gross = basic - no-pay deduction - absence deduction, never below zero.
    EPF: 8% of gross from the employee, 12% from the employer; ETF 3% from
    the employer.
  * Net pay = gross - employee EPF. Employer cost = gross + 12% + 3%.

Not yet: allowances, overtime and APIT.
"""

import calendar
from dataclasses import asdict, dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Optional

DAYS_PER_MONTH = Decimal(30)
EPF_EMPLOYEE = Decimal("0.08")
EPF_EMPLOYER = Decimal("0.12")
ETF = Decimal("0.03")
ZERO = Decimal("0")
CENT = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def _date(value) -> Optional[date]:
    return date.fromisoformat(str(value)[:10]) if value else None


def month_bounds(month: int, year: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def employed_span(month: int, year: int, joined: Optional[date], left: Optional[date]) -> Optional[tuple[date, date]]:
    """The days of the month the person was employed, or None if none."""
    first, last = month_bounds(month, year)
    start = max(first, joined) if joined else first
    end = min(last, left) if left else last
    return (start, end) if start <= end else None


def is_eligible(employee: dict, month: int, year: int) -> bool:
    """
    Paid for the month: employed on at least one of its days, and either
    Active or a leaver with a recorded last day. Someone deactivated without
    a last day (records from before date_left) is not paid, as before.
    """
    status = employee.get("status") or "Active"
    left = _date(employee.get("date_left"))
    if status != "Active" and left is None:
        return False
    return employed_span(month, year, _date(employee.get("date_joined")), left) is not None


@dataclass
class PayLine:
    employee_id: int
    employee_name: str
    days_in_month: int
    paid_days: int
    basic: Decimal
    nopay_days: Decimal
    nopay_deduction: Decimal
    absent_days: Decimal
    absence_deduction: Decimal
    gross: Decimal
    epf_employee: Decimal
    epf_employer: Decimal
    etf: Decimal
    net_payable: Decimal

    @property
    def employer_cost(self) -> Decimal:
        return self.gross + self.epf_employer + self.etf

    def as_row(self) -> dict:
        """JSON-safe, for the generate RPC and API responses."""
        out = asdict(self)
        for k, v in out.items():
            if isinstance(v, Decimal):
                out[k] = float(v)
        return out


def compute_line(employee: dict, month: int, year: int, unpaid_days: Iterable[tuple[date, Decimal]] = (),
                 absent_days=ZERO) -> Optional[PayLine]:
    """
    One employee's line, or None if they are not paid for the month.
    `unpaid_days` are (date, fraction) of approved unpaid leave; days outside
    the employed span are ignored. `absent_days` are absences recorded by an
    earlier month's close, deducted here in arrears.
    """
    if not is_eligible(employee, month, year):
        return None
    joined, left = _date(employee.get("date_joined")), _date(employee.get("date_left"))
    first, last = month_bounds(month, year)
    start, end = employed_span(month, year, joined, left)

    base = money(employee.get("base_salary") or 0)
    daily = base / DAYS_PER_MONTH
    days_in_month = (last - first).days + 1
    paid_days = (end - start).days + 1
    basic = base if paid_days == days_in_month else min(base, money(daily * paid_days))

    nopay = sum((Decimal(str(f)) for d, f in unpaid_days if start <= d <= end), ZERO)
    # Every employed day unpaid pays nothing: at base / 30, a wholly unpaid
    # February would otherwise still pay two days.
    deduction = basic if nopay >= paid_days else min(basic, money(daily * nopay))
    absent = Decimal(str(absent_days or 0))
    absence_deduction = min(basic - deduction, money(daily * absent))
    gross = basic - deduction - absence_deduction
    epf_employee = money(gross * EPF_EMPLOYEE)

    name = f"{employee.get('first_name', '')} {employee.get('last_name', '')}".strip()
    return PayLine(
        employee_id=employee["id"],
        employee_name=name or f"Employee {employee['id']}",
        days_in_month=days_in_month,
        paid_days=paid_days,
        basic=basic,
        nopay_days=nopay,
        nopay_deduction=deduction,
        absent_days=absent,
        absence_deduction=absence_deduction,
        gross=gross,
        epf_employee=epf_employee,
        epf_employer=money(gross * EPF_EMPLOYER),
        etf=money(gross * ETF),
        net_payable=gross - epf_employee,
    )


def compute_run(employees: list[dict], unpaid_by_employee: dict[int, list[tuple[date, Decimal]]],
                month: int, year: int, absences_by_employee: Optional[dict[int, Decimal]] = None) -> list[PayLine]:
    absences = absences_by_employee or {}
    lines = [compute_line(e, month, year, unpaid_by_employee.get(e["id"], []), absences.get(e["id"], ZERO))
             for e in employees]
    return sorted((l for l in lines if l is not None), key=lambda l: (l.employee_name.lower(), l.employee_id))


# Compared when deciding whether a stored draft still matches a fresh run.
COMPARED = ("paid_days", "basic", "nopay_days", "nopay_deduction", "gross",
            "epf_employee", "epf_employer", "etf", "net_payable")
# Added with month close; a stored line without them had none.
COMPARED_DEFAULT_ZERO = ("absent_days", "absence_deduction")


def drift(stored: list[dict], fresh: list[PayLine]) -> list[dict]:
    """
    How a stored draft differs from computing it now: 'added' (paid now, not
    on the draft), 'removed' (on the draft, not paid now) or 'changed' (on
    both, with a different figure: salary, days employed or no-pay leave).
    """
    by_id = {r["employee_id"]: r for r in stored}
    fresh_ids = {l.employee_id for l in fresh}
    out = []
    for line in fresh:
        row = by_id.get(line.employee_id)
        if row is None:
            out.append({"employee_id": line.employee_id, "employee_name": line.employee_name, "change": "added",
                        "draft_amount": None, "current_amount": float(line.net_payable)})
        elif (any(row.get(k) is None or money(row[k]) != money(getattr(line, k)) for k in COMPARED)
              or any(money(row.get(k) or 0) != money(getattr(line, k)) for k in COMPARED_DEFAULT_ZERO)):
            out.append({"employee_id": line.employee_id, "employee_name": line.employee_name, "change": "changed",
                        "draft_amount": float(money(row.get("net_payable") or 0)),
                        "current_amount": float(line.net_payable)})
    for row in stored:
        if row["employee_id"] not in fresh_ids:
            out.append({"employee_id": row["employee_id"],
                        "employee_name": row.get("employee_name") or f"Employee {row['employee_id']}",
                        "change": "removed", "draft_amount": float(money(row.get("net_payable") or 0)),
                        "current_amount": None})
    out.sort(key=lambda d: (d["change"], d["employee_name"].lower()))
    return out
