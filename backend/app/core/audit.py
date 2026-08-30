# backend/app/core/audit.py
#
# The single canonical audit logger. A second copy of this module previously
# lived at app/services/audit.py; it has been removed. Import from here only.

from typing import Any, Optional
from supabase import Client
from datetime import datetime, timezone
import json
import hashlib
import logging

logger = logging.getLogger(__name__)

# Chained onto by the first row of a chain, so "there is no previous row" is
# itself a verifiable state rather than an ambiguous NULL.
GENESIS = "GENESIS"


def canonicalize(value: Any) -> Any:
    """
    Round-trip a payload through JSON so the value that gets hashed is exactly
    the value that gets stored.

    Without this, a date or Decimal would hash as its Python repr on the way in
    but come back from JSONB as a plain string or float, and every row would
    fail verification through no fault of anyone tampering.
    """
    return json.loads(json.dumps(value, default=str))


def normalize_timestamp(value: Any) -> str:
    """
    Postgres may hand a timestamptz back in a different textual form than the
    one we sent (trailing Z vs +00:00, differing offsets). Parse and re-emit in
    UTC so insert-time and verify-time hashing agree on the same string.
    """
    if value is None:
        return ""
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        # Unparseable timestamps hash as their literal text rather than
        # raising — verification should report a mismatch, not crash.
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def compute_hash(
    prev_hash: Optional[str],
    user_id: Optional[str],
    action_type: str,
    table_name: str,
    old_payload: Any,
    new_payload: Any,
    timestamp: Any,
) -> str:
    """
    SHA-256 over a canonical JSON object. sort_keys=True means the field order
    of the dict can never affect the digest.
    """
    payload = json.dumps(
        {
            "prev_hash": prev_hash,
            "user_id": str(user_id) if user_id is not None else None,
            "action_type": action_type,
            "table_name": table_name,
            "old_payload": canonicalize(old_payload),
            "new_payload": canonicalize(new_payload),
            "timestamp": normalize_timestamp(timestamp),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def log_audit_action(
    supabase: Client,
    user_id: Optional[str],
    action_type: str,
    table_name: str,
    old_payload: Optional[Any] = None,
    new_payload: Optional[Any] = None,
):
    """
    Append a tamper-evident row to system_audit_logs.

    Fail-soft by contract: if anything here raises, the error is logged and
    swallowed. Audit logging must never break the user-facing request it is
    recording.
    """
    try:
        last = (
            supabase.table("system_audit_logs")
            .select("hash")
            .order("id", desc=True)
            .limit(1)
            .execute()
        )

        # `or GENESIS` rather than a plain lookup: rows predating hash-chaining
        # have a NULL hash, and chaining onto NULL would produce a chain that
        # can never verify. Starting a fresh chain at GENESIS is the honest
        # representation of "everything before this point was unchained".
        prev_hash = (last.data[0].get("hash") if last.data else None) or GENESIS

        timestamp = datetime.now(timezone.utc).isoformat()

        # Canonicalize once and use the same values for both the digest and the
        # insert, so the stored row is precisely what was hashed.
        old_c = canonicalize(old_payload)
        new_c = canonicalize(new_payload)

        row_hash = compute_hash(
            prev_hash, user_id, action_type, table_name, old_c, new_c, timestamp
        )

        supabase.table("system_audit_logs").insert(
            {
                "user_id": str(user_id) if user_id is not None else None,
                "action_type": action_type,
                "table_name": table_name,
                "old_payload": old_c,
                "new_payload": new_c,
                "timestamp": timestamp,
                "prev_hash": prev_hash,
                "hash": row_hash,
            }
        ).execute()
    except Exception as e:
        logger.error("Failed to log audit action %s on %s: %s", action_type, table_name, e)
        # Deliberately not re-raised.
