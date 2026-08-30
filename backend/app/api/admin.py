from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from supabase import Client
from app.core.supabase import get_supabase
from app.core.security import require_permission
from app.core.audit import compute_hash, GENESIS

router = APIRouter()

@router.get("/audit-logs")
async def get_audit_logs(
    limit: int = 50,
    user = Depends(require_permission('audit:read')),
    supabase: Client = Depends(get_supabase)
):
    try:
        response = supabase.table("system_audit_logs") \
            .select("*, users(email, roles(role_name))") \
            .order("timestamp", desc=True) \
            .limit(limit) \
            .execute()
        return response.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/audit-logs/verify")
async def verify_audit_chain(
    user = Depends(require_permission('audit:read')),
    supabase: Client = Depends(get_supabase)
):
    """
    Walk the audit chain in id order, recomputing each row's digest from its
    stored fields plus the previous row's hash.

    Two things are checked per row: that the recomputed digest matches the
    stored one (the row's own contents are intact), and that its prev_hash
    matches the previous row's hash (no row has been deleted or reordered).
    Checking only the first would miss a deletion entirely.
    """
    try:
        response = supabase.table("system_audit_logs") \
            .select("*") \
            .order("id", desc=False) \
            .execute()
        rows = response.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Rows written before hash-chaining have no digest. They are reported
    # rather than silently ignored, and rather than being treated as tampered —
    # they were never chained, which is a different claim from "altered".
    unchained = [r for r in rows if not r.get("hash")]
    chained = [r for r in rows if r.get("hash")]

    prev_hash = GENESIS

    for row in chained:
        if row.get("prev_hash") != prev_hash:
            return {
                "valid": False,
                "tampered_row_id": row["id"],
                "message": (
                    f"Broken chain at row {row['id']}: prev_hash is "
                    f"{row.get('prev_hash')!r} but the preceding row hashes to "
                    f"{prev_hash!r}. A row was likely deleted, reordered or inserted."
                ),
                "verified_count": chained.index(row),
                "unchained_legacy_rows": len(unchained),
            }

        expected = compute_hash(
            row.get("prev_hash"),
            row.get("user_id"),
            row.get("action_type"),
            row.get("table_name"),
            row.get("old_payload"),
            row.get("new_payload"),
            row.get("timestamp"),
        )

        if expected != row["hash"]:
            return {
                "valid": False,
                "tampered_row_id": row["id"],
                "message": (
                    f"Row {row['id']} does not match its stored hash — its "
                    f"contents have been altered since it was written."
                ),
                "verified_count": chained.index(row),
                "unchained_legacy_rows": len(unchained),
            }

        prev_hash = row["hash"]

    return {
        "valid": True,
        "count": len(chained),
        "unchained_legacy_rows": len(unchained),
    }


@router.get("/stats")
async def get_system_stats(
    user = Depends(require_permission('admin:users')),
    supabase: Client = Depends(get_supabase)
):
    try:
        # Get users with their roles
        response = supabase.table("users").select("roles(role_name)").execute()
        users = response.data or []
        
        # Aggregate counts
        role_counts = {}
        for u in users:
            role = u.get("roles", {}).get("role_name", "Unknown")
            role_counts[role] = role_counts.get(role, 0) + 1
            
        return {
            "total_users": len(users),
            "role_counts": role_counts,
            "status": "healthy"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
