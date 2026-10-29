"""
Work schedules and holidays: when is someone meant to be working?

Everything here is pure, over rows already fetched, so the rules are testable
without a database. The attendance grid, correction requests and month close
(steps 3-5 of the attendance rework) all ask resolve_day(); none of them
should re-derive a working day on their own.

Schema: db/migrations/008_work_schedules_holidays.sql.
Holiday data: db/holidays/<year>.csv (see the README there for sources).
"""

import csv
import math
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional

HOLIDAY_DIR = Path(__file__).resolve().parents[2] / "db" / "holidays"

# All clock times are Sri Lanka local time. Sri Lanka has no daylight saving,
# so a fixed offset is exact.
COLOMBO = timezone(timedelta(hours=5, minutes=30))

POYA_MARKER = "Full Moon Poya Day"


# --------------------------------------------------------------------------
# Holiday policy
# --------------------------------------------------------------------------

def is_poya(name: str) -> bool:
    """
    A Full Moon Poya Day itself, not the "Day Following Vesak Full Moon Poya
    Day", which is a mercantile holiday in its own right.
    """
    return POYA_MARKER.lower() in name.lower() and not name.lower().startswith("day following")


def vff_day_off(is_mercantile: bool, poya: bool) -> bool:
    """
    VFF's policy, confirmed 2026-10-29: days off are the mercantile holidays
    and every Full Moon Poya Day. Poya days are public and bank holidays but
    not mercantile ones in law, so the rule names both. Other public holidays
    (e.g. Good Friday, Deepawali) appear in the calendar as working days.
    """
    return is_mercantile or poya


def load_holiday_file(year: int, directory: Path = HOLIDAY_DIR) -> list[dict]:
    """Rows of db/holidays/<year>.csv, shaped like the holidays table."""
    path = directory / f"{year}.csv"
    if not path.exists():
        raise FileNotFoundError(f"No holiday file for {year}. Add db/holidays/{year}.csv from that year's gazette.")

    rows = []
    with path.open(encoding="utf-8", newline="") as f:
        for raw in csv.DictReader(f):
            d = date.fromisoformat(raw["date"].strip())
            if d.year != year:
                raise ValueError(f"{path.name}: {d} is not in {year}.")
            name = raw["name"].strip()
            mercantile = raw["mercantile"].strip() == "1"
            poya = is_poya(name)
            rows.append({
                "holiday_date": d.isoformat(),
                "name": name,
                "is_public": raw["public"].strip() == "1",
                "is_bank": raw["bank"].strip() == "1",
                "is_mercantile": mercantile,
                "is_poya": poya,
                "is_day_off": vff_day_off(mercantile, poya),
                "source": raw["source"].strip(),
            })
    return rows


# --------------------------------------------------------------------------
# Full moons: a cross-check on Poya dates, never a source of them
# --------------------------------------------------------------------------

def _julian_to_utc(jd: float) -> datetime:
    return datetime(2000, 1, 1, 12, tzinfo=timezone.utc) + timedelta(days=jd - 2451545.0)


def full_moons(year: int) -> list[datetime]:
    """
    Instants (UTC) of the astronomical full moons around `year`.

    Jean Meeus, Astronomical Algorithms (2nd ed.), ch. 49, with the periodic
    terms down to 0.0001 day. Accurate to a few minutes, which is ample for
    a check with a one-day tolerance. Terrestrial vs universal time (about a
    minute) is ignored.
    """
    rad = math.radians
    moons = []
    k0 = math.floor((year - 2000) * 12.3685) - 1
    for i in range(16):
        k = k0 + i + 0.5
        t = k / 1236.85
        jde = (2451550.09766 + 29.530588861 * k + 0.00015437 * t**2
               - 0.000000150 * t**3 + 0.00000000073 * t**4)
        e = 1 - 0.002516 * t - 0.0000074 * t**2
        m = rad(2.5534 + 29.10535670 * k - 0.0000014 * t**2 - 0.00000011 * t**3)
        mp = rad(201.5643 + 385.81693528 * k + 0.0107582 * t**2 + 0.00001238 * t**3 - 0.000000058 * t**4)
        f = rad(160.7108 + 390.67050284 * k - 0.0016118 * t**2 - 0.00000227 * t**3 + 0.000000011 * t**4)
        om = rad(124.7746 - 1.56375588 * k + 0.0020672 * t**2 + 0.00000215 * t**3)
        jde += (
            -0.40614 * math.sin(mp)
            + 0.17302 * e * math.sin(m)
            + 0.01614 * math.sin(2 * mp)
            + 0.01043 * math.sin(2 * f)
            + 0.00734 * e * math.sin(mp - m)
            - 0.00515 * e * math.sin(mp + m)
            + 0.00209 * e * e * math.sin(2 * m)
            - 0.00111 * math.sin(mp - 2 * f)
            - 0.00057 * math.sin(mp + 2 * f)
            + 0.00056 * e * math.sin(2 * mp + m)
            - 0.00042 * math.sin(3 * mp)
            + 0.00042 * e * math.sin(m + 2 * f)
            + 0.00038 * e * math.sin(m - 2 * f)
            - 0.00024 * e * math.sin(2 * mp - m)
            - 0.00017 * math.sin(om)
        )
        moons.append(_julian_to_utc(jde))
    return moons


def poya_warnings(rows: list[dict], tolerance_days: int = 1) -> list[str]:
    """
    Poya rows more than `tolerance_days` from any full moon (Colombo date).

    A typo check only. The official Poya can differ from the astronomical
    full moon by a day, so a one-day difference is normal and not reported.
    """
    years = {date.fromisoformat(r["holiday_date"]).year for r in rows if r.get("is_poya")}
    moon_dates = [m.astimezone(COLOMBO).date() for y in years for m in full_moons(y)]
    warnings = []
    for r in rows:
        if not r.get("is_poya"):
            continue
        d = date.fromisoformat(r["holiday_date"])
        nearest = min(abs((d - md).days) for md in moon_dates)
        if nearest > tolerance_days:
            warnings.append(
                f"{r['name']} on {d.isoformat()} is {nearest} days from the nearest full moon. Check it against the gazette."
            )
    return warnings


# --------------------------------------------------------------------------
# Resolving a day
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class DayPlan:
    """What a given employee was meant to do on a given date."""
    working: bool
    # 'scheduled' | 'rest_day' | 'holiday'
    reason: str
    schedule_id: Optional[int] = None
    schedule_name: Optional[str] = None
    start: Optional[datetime] = None   # Colombo time
    end: Optional[datetime] = None     # Colombo time; next day for overnight shifts
    break_minutes: int = 0
    grace_minutes: int = 0
    holidays: tuple[str, ...] = field(default_factory=tuple)

    @property
    def expected_minutes(self) -> int:
        if not self.working or not self.start or not self.end:
            return 0
        return max(int((self.end - self.start).total_seconds() // 60) - self.break_minutes, 0)

    @property
    def late_after(self) -> Optional[datetime]:
        """Clock-ins after this are late."""
        return self.start + timedelta(minutes=self.grace_minutes) if self.start else None


def _to_time(value) -> time:
    if isinstance(value, time):
        return value
    return time.fromisoformat(str(value)[:8])


def schedule_for(employee_id: int, on: date, assignments: list[dict], default_schedule_id: Optional[int]) -> Optional[int]:
    """
    The schedule in force for an employee on a date: the assignment with the
    latest effective_from on or before it, else the default.
    """
    best = None
    for a in assignments:
        if a.get("employee_id") != employee_id:
            continue
        starts = date.fromisoformat(str(a["effective_from"])[:10])
        if starts <= on and (best is None or starts > best[0]):
            best = (starts, a["schedule_id"])
    return best[1] if best else default_schedule_id


def resolve_day(on: date, schedule: Optional[dict], holidays_on_date: list[dict]) -> DayPlan:
    """
    `schedule` is a work_schedules row with its `days` (work_schedule_days
    rows) attached; None means no schedule exists at all, treated as not
    working rather than guessing hours.

    Holidays win over the weekly pattern only when they are VFF days off and
    the schedule observes holidays (the rescue rota does not).
    """
    if schedule is None:
        return DayPlan(working=False, reason="rest_day")

    base = dict(schedule_id=schedule.get("id"), schedule_name=schedule.get("name"),
                grace_minutes=int(schedule.get("grace_minutes") or 0))

    days_off = tuple(h["name"] for h in holidays_on_date if h.get("is_day_off"))
    if days_off and schedule.get("observes_holidays", True):
        return DayPlan(working=False, reason="holiday", holidays=days_off, **base)

    day = next((d for d in schedule.get("days") or [] if int(d["weekday"]) == on.isoweekday()), None)
    if day is None:
        return DayPlan(working=False, reason="rest_day", holidays=days_off, **base)

    start = datetime.combine(on, _to_time(day["start_time"]), COLOMBO)
    end = datetime.combine(on, _to_time(day["end_time"]), COLOMBO)
    if end <= start:
        end += timedelta(days=1)  # overnight shift

    return DayPlan(
        working=True, reason="scheduled", start=start, end=end,
        break_minutes=int(day.get("break_minutes") or 0), holidays=days_off, **base,
    )
