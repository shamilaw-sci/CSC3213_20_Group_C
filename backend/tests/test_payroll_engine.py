"""The payroll engine's arithmetic (app/services/payroll_engine.py)."""

import os
import sys
from datetime import date
from decimal import Decimal as D

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.payroll_engine import compute_line, compute_run, drift, is_eligible


def emp(base=60000, joined="2020-01-01", left=None, status="Active", id=1, name=("Kamala", "Silva")):
    return {"id": id, "first_name": name[0], "last_name": name[1], "base_salary": base,
            "date_joined": joined, "date_left": left, "status": status}


def test_a_full_month_pays_the_base_salary_with_epf_and_etf():
    line = compute_line(emp(60000), 11, 2026)
    assert line.basic == D("60000.00") and line.gross == D("60000.00")
    assert line.epf_employee == D("4800.00")      # 8%
    assert line.net_payable == D("55200.00")
    assert line.epf_employer == D("7200.00")      # 12%
    assert line.etf == D("1800.00")               # 3%
    assert line.employer_cost == D("69000.00")


@pytest.mark.parametrize("month", [2, 7])   # 28 and 31 days: a full month is a full month
def test_month_length_does_not_change_a_full_months_pay(month):
    assert compute_line(emp(60000), month, 2026).basic == D("60000.00")


def test_a_mid_month_joiner_is_paid_calendar_days_at_base_over_thirty():
    line = compute_line(emp(60000, joined="2026-11-16"), 11, 2026)   # 16-30 Nov: 15 days
    assert line.paid_days == 15 and line.days_in_month == 30
    assert line.basic == D("30000.00")                                # 15 x 2000


def test_a_leaver_is_paid_to_their_last_day_even_though_inactive():
    line = compute_line(emp(60000, left="2026-11-10", status="Inactive"), 11, 2026)
    assert line.paid_days == 10 and line.basic == D("20000.00")


def test_part_month_pay_never_exceeds_the_base_salary():
    # 1-31 July minus one day is 30 days x 2000 = 60000, not more.
    line = compute_line(emp(60000, joined="2026-07-02"), 7, 2026)
    assert line.basic == D("60000.00")


def test_no_pay_leave_is_deducted_at_the_daily_rate():
    line = compute_line(emp(60000), 11, 2026, [(date(2026, 11, 3), D(1)), (date(2026, 11, 4), D("0.5"))])
    assert line.nopay_days == D("1.5") and line.nopay_deduction == D("3000.00")
    assert line.gross == D("57000.00")
    assert line.epf_employee == D("4560.00") and line.net_payable == D("52440.00")


def test_no_pay_outside_the_employed_span_is_ignored():
    line = compute_line(emp(60000, joined="2026-11-16"), 11, 2026, [(date(2026, 11, 3), D(1))])
    assert line.nopay_days == D(0)


def test_pay_never_goes_below_zero():
    days = [(date(2026, 2, d), D(1)) for d in range(1, 29)]   # all 28 days of February unpaid (28 x 2000 < 60000)
    line = compute_line(emp(60000), 2, 2026, days)
    assert line.gross == D(0) and line.net_payable == D(0) and line.epf_employer == D(0)


def test_amounts_round_to_the_cent():
    line = compute_line(emp(65000), 11, 2026, [(date(2026, 11, 3), D(1))])
    assert line.nopay_deduction == D("2166.67")      # 65000 / 30
    assert line.epf_employee == D("5026.67")         # 8% of 62833.33


@pytest.mark.parametrize("employee, paid", [
    (emp(joined="2026-12-01"), False),                        # joined after the month
    (emp(left="2026-10-31", status="Inactive"), False),       # left before it
    (emp(status="Inactive"), False),                          # inactive, no last day recorded
    (emp(joined=None), True),                                 # no join date: as before
    (emp(left="2026-11-01", status="Inactive"), True),        # last day was the 1st
])
def test_who_is_paid_for_a_month(employee, paid):
    assert is_eligible(employee, 11, 2026) is paid


def test_a_run_lists_paid_employees_by_name():
    run = compute_run([emp(id=2, name=("Zara", "Perera")), emp(id=1), emp(id=3, joined="2027-01-01")], {}, 11, 2026)
    assert [l.employee_id for l in run] == [1, 2]


def test_drift_finds_added_removed_and_changed():
    fresh = compute_run([emp(id=1), emp(id=2, base=70000, name=("Amal", "Perera"))], {}, 11, 2026)
    stored = [
        {**fresh[0].as_row(), "net_payable": 1.0},          # Amal: figure differs
        {"employee_id": 9, "employee_name": "Gone Away", "net_payable": 50000},
    ]
    stored[0]["employee_id"] = 2
    changes = {(d["employee_name"], d["change"]) for d in drift(stored, fresh)}
    assert changes == {("Kamala Silva", "added"), ("Amal Perera", "changed"), ("Gone Away", "removed")}


def test_a_matching_draft_has_no_drift():
    fresh = compute_run([emp(id=1)], {}, 11, 2026)
    assert drift([l.as_row() for l in fresh], fresh) == []


def test_a_draft_from_before_the_engine_counts_as_changed():
    fresh = compute_run([emp(id=1)], {}, 11, 2026)
    legacy = [{"employee_id": 1, "employee_name": "Kamala Silva", "net_payable": 60000}]
    assert drift(legacy, fresh)[0]["change"] == "changed"
