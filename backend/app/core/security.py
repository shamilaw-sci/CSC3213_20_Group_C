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
    logger.info("==> get_current_user: token received (first 20 chars): %s", token[:20] if token else "NONE")

    try:
        user_response = supabase.auth.get_user(token)
        logger.info("==> auth.get_user succeeded, user=%s", user_response.user)
    except Exception as e:
        logger.error("==> auth.get_user FAILED: %s", e)
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {str(e)}")

    if not user_response.user:
        logger.error("==> user_response.user is None/falsy")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = user_response.user.id
    logger.info("==> user_id: %s", user_id)
    try:
        db_user = supabase.table("users").select("*, roles(role_name)").eq("id", user_id).single().execute()
        logger.info("==> db_user.data: %s", db_user.data)
    except Exception as e:
        logger.error("==> DB lookup FAILED: %s", e)
        raise HTTPException(status_code=500, detail=f"Database lookup failed: {str(e)}")

    if not db_user.data:
        logger.error("==> db_user.data is empty")
        raise HTTPException(status_code=403, detail="User record not found in system")

    return db_user.data

def check_user_role(allowed_roles: list[str]):
    async def role_checker(current_user: dict = Depends(get_current_user)):
        role_name = (current_user.get("roles", {}).get("role_name") or "").lower()
        logger.info("==> role check: role_name=%s, allowed=%s", role_name, allowed_roles)
        if role_name not in [r.lower() for r in allowed_roles]:
            logger.error("==> ROLE MISMATCH: '%s' not in %s", role_name, allowed_roles)
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return role_checker

def require_permission(permission: str):
    async def permission_checker(current_user: dict = Depends(get_current_user)):
        role_name = (current_user.get("roles", {}).get("role_name") or "")
        if not has_permission(role_name, permission):
            raise HTTPException(status_code=403, detail=f"Insufficient permissions. Requires {permission}")
        return current_user
    return permission_checker

