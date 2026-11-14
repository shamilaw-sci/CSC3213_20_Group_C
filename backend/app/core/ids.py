"""Path parameters that name a uuid row.

Typed as plain str, a malformed id went straight to PostgREST, which rejects it
with 400, and that surfaced as a 500 (or the raw database error) instead of a
client error. UuidPath checks the shape first, so FastAPI answers 422, and the
handler still receives the str it already works with.
"""

from typing import Annotated

from fastapi import Path

UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"

UuidPath = Annotated[str, Path(pattern=UUID_PATTERN)]
