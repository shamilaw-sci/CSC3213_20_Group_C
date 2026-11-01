"""
Which volunteers have accepted work on a programme.

volunteer_shifts has no program_id column. A shift belongs to a programme when
its title is the programme's name, which is what the New shift form stores
(it picks the title from a dropdown of active programmes). That link lives in
shift_belongs_to_program alone, so replacing it with a real program_id later
is a one-function change.

Everything here is plain Python over rows already fetched, so the rules are
testable without a database and do not depend on which filters the query
applied: the endpoint may over-fetch, and this module still decides.
"""

from typing import Iterable

ACCEPTED = "accepted"


def _normalise(name) -> str:
    return " ".join(str(name or "").split()).casefold()


def shift_belongs_to_program(shift: dict, program: dict) -> bool:
    """Exact name match, ignoring case and surrounding/repeated whitespace."""
    program_name = _normalise(program.get("program_name"))
    return bool(program_name) and _normalise(shift.get("title")) == program_name


def build_program_volunteers(
    program: dict,
    shifts: Iterable[dict],
    assignments: Iterable[dict],
) -> list[dict]:
    """
    One entry per volunteer who accepted either a shift for this programme or
    a direct programme assignment.

    Excluded: pending or declined responses, cancelled shifts, and shifts for
    any other programme. `assignments` rows carry the joined volunteer as
    `volunteers` ({full_name, skills, skills_other}).
    """
    program_shifts = {
        s["id"]: s for s in shifts
        if not s.get("is_cancelled") and shift_belongs_to_program(s, program)
    }

    by_volunteer: dict[str, dict] = {}
    seen: set = set()
    for a in assignments:
        # The endpoint runs two queries (shift and direct-program targets);
        # never count one assignment twice if both happen to return it.
        if a.get("id") in seen:
            continue
        seen.add(a.get("id"))
        if a.get("response") != ACCEPTED:
            continue

        shift = program_shifts.get(a.get("shift_id")) if a.get("shift_id") else None
        direct = a.get("program_id") is not None and a.get("program_id") == program.get("id")
        if shift is None and not direct:
            continue

        person = a.get("volunteers") or {}
        entry = by_volunteer.setdefault(str(a["volunteer_id"]), {
            "volunteer_id": a["volunteer_id"],
            "full_name": person.get("full_name") or "Unknown volunteer",
            "skills": person.get("skills") or [],
            "skills_other": person.get("skills_other"),
            "program_assignment": False,
            "shifts": [],
        })
        if direct:
            entry["program_assignment"] = True
        if shift is not None:
            entry["shifts"].append({
                "shift_id": shift["id"],
                "title": shift.get("title"),
                "shift_date": shift.get("shift_date"),
                "start_time": shift.get("start_time"),
                "end_time": shift.get("end_time"),
                "location": shift.get("location"),
                "responded_at": a.get("responded_at"),
            })

    out = list(by_volunteer.values())
    for entry in out:
        entry["shifts"].sort(key=lambda s: (str(s["shift_date"]), str(s["start_time"])))
    out.sort(key=lambda e: e["full_name"].casefold())
    return out
