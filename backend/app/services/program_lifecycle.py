"""
Program lifecycle: Upcoming -> Active -> Completed, forward only. An
Upcoming program created by mistake can be Cancelled instead (migration 022).

The one place the rules live on the API side. db/migrations/010 adds the same
rule as a trigger, so a write that bypasses the API is refused too.

Before 010 is applied the live table still holds the legacy value
'In Progress', which meant "running". normalize_status() reads it as Active,
so the pages and transitions behave the same before and after the migration.
"""

from typing import Optional

UPCOMING = "Upcoming"
ACTIVE = "Active"
COMPLETED = "Completed"
CANCELLED = "Cancelled"

STATUSES = (UPCOMING, ACTIVE, COMPLETED, CANCELLED)

# Stored values that mean each lifecycle status, for filtering a table that may
# not have been migrated yet. Exact strings, because PostgREST .in_() is exact.
STORED_VALUES = {
    UPCOMING: [UPCOMING],
    ACTIVE: [ACTIVE, "In Progress"],
    COMPLETED: [COMPLETED],
    CANCELLED: [CANCELLED],
}

_NEXT = {UPCOMING: ACTIVE, ACTIVE: COMPLETED}

# Ended programs: nothing about them moves any more.
FINISHED = (COMPLETED, CANCELLED)


def normalize_status(value) -> str:
    """Map any stored value onto the lifecycle. Unknown or empty -> Active,
    which is what the column used to default to."""
    v = str(value or "").strip().lower()
    if v == "upcoming":
        return UPCOMING
    if v == "completed":
        return COMPLETED
    if v == "cancelled":
        return CANCELLED
    return ACTIVE


def next_status(current) -> Optional[str]:
    """The only status a program may move to next, or None when it is done."""
    return _NEXT.get(normalize_status(current))


# Shown when a write names the location column before migration 011 is run.
LOCATION_MIGRATION_MESSAGE = (
    "Program locations are not set up in the database yet. "
    "Run backend/db/migrations/011_program_location.sql in Supabase, then try again."
)


def is_missing_location_column(error: Exception) -> bool:
    """True when PostgREST refused a write because programs.location does not
    exist yet (PGRST204 'Could not find the 'location' column')."""
    text = str(error).lower()
    return "location" in text and ("pgrst204" in text or "column" in text)


# Shown when a feature needs db/migrations/022_program_fixes.sql.
PROGRAM_FIXES_MIGRATION_MESSAGE = (
    "This needs the programs update. Run backend/db/migrations/022_program_fixes.sql "
    "in Supabase, then try again."
)


def is_missing_shift_program_column(error: Exception) -> bool:
    """True when volunteer_shifts.program_id does not exist yet (before 022)."""
    text = str(error).lower()
    return "program_id" in text and ("pgrst204" in text or "42703" in text or "column" in text)


def is_cancelled_status_refused(error: Exception) -> bool:
    """True when the database refused 'Cancelled' (022 not applied)."""
    text = str(error).lower()
    return "programs_status_lifecycle" in text or "to cancelled" in text


def transition_error(current, target: str) -> Optional[str]:
    """None when `current` -> `target` is allowed, else a message for the user."""
    now = normalize_status(current)
    if next_status(now) == target or (now == UPCOMING and target == CANCELLED):
        return None
    if now == target:
        return f"This program is already {target}."
    if now == COMPLETED:
        return "This program is completed and cannot change status."
    if now == CANCELLED:
        return "This program was cancelled and cannot change status."
    if target == CANCELLED:
        return "Only an Upcoming program can be cancelled."
    if target == COMPLETED:
        return "Only an Active program can be marked as completed. Start it first."
    return f"A program cannot move from {now} to {target}."
