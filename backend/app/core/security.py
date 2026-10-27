import logging
from fastapi import Security, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.supabase import get_supabase
from supabase import Client
from app.core.permissions import has_permission

logger = logging.getLogger(__name__)

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security), supabase: Client = Depends(get_supabase)):
    token = credentials.credentials

    try:
        user_response = supabase.auth.get_user(token)
    except Exception as e:
        logger.warning("auth.get_user failed: %s", e)
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if not user_response.user:
        logger.warning("auth.get_user returned no user")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = user_response.user.id
    logger.debug("resolved user_id=%s", user_id)

    try:
        db_user = supabase.table("users").select("*, roles(role_name)").eq("id", user_id).single().execute()
    except Exception as e:
        logger.error("user lookup failed for %s: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Database lookup failed")

    if not db_user.data:
        logger.warning("no user record for %s", user_id)
        raise HTTPException(status_code=403, detail="User record not found in system")

    logger.debug("user %s role=%s", user_id,
                 (db_user.data.get("roles") or {}).get("role_name"))

    return db_user.data

def check_user_role(allowed_roles: list[str]):
    async def role_checker(current_user: dict = Depends(get_current_user)):
        role_name = (current_user.get("roles", {}).get("role_name") or "").lower()
        if role_name not in [r.lower() for r in allowed_roles]:
            logger.warning("role check failed: '%s' not in %s", role_name, allowed_roles)
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return role_checker

def require_permission(permission: str):
    async def permission_checker(current_user: dict = Depends(get_current_user)):
        role_name = (current_user.get("roles", {}).get("role_name") or "")
        if not has_permission(role_name, permission):
            logger.warning("permission denied: role '%s' lacks %s", role_name, permission)
            raise HTTPException(status_code=403, detail=f"Insufficient permissions. Requires {permission}")
        return current_user
    return permission_checker


def require_any_permission(*permissions: str):
    """Allow the caller if they hold ANY of these permissions.

    Exists for acts that legitimately belong to two different roles without
    either implying the other. Copying a volunteer's personal link is the
    motivating case: it is gated on volunteers:approve OR volunteers:assign,
    because sharing a link is contact rather than a vetting or a scheduling
    decision. Requiring approve alone would leave an Operations Lead unable to
    reach the volunteers they just rostered; requiring assign alone would leave
    an HR Officer who just approved someone unable to send them their link.
    """
    async def permission_checker(current_user: dict = Depends(get_current_user)):
        role_name = (current_user.get("roles", {}).get("role_name") or "")
        if not any(has_permission(role_name, p) for p in permissions):
            logger.warning(
                "permission denied: role '%s' holds none of %s", role_name, permissions
            )
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Requires one of: {', '.join(permissions)}",
            )
        return current_user
    return permission_checker