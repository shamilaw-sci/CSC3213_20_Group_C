from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from app.core.supabase import get_supabase
from supabase import Client
from app.infrastructure.repositories import SupabaseUserRepository
from app.application.use_cases import RegisterUseCase, LoginUseCase
from app.core.ids import UuidPath
from app.core.security import require_permission
from app.core.audit import log_audit_action
from app.core.permissions import Permission, UserRole, has_permission

router = APIRouter()

# Every self-service signup gets this role. Role changes go through
# PUT /users/{id}/role, which requires admin:roles (Admin only).
SIGNUP_ROLE = "General Staff"


class UserRegister(BaseModel):
    # No role field. It used to accept role_id with a default of 2 (Director),
    # so any anonymous caller could register as Admin by sending role_id=1 —
    # and since the register pages sent `role` as a string, which the model
    # silently dropped, every web signup became a Director. A role_id in the
    # body is now ignored like any other unknown field.
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

@router.post("/register")
async def register(user_data: UserRegister, supabase: Client = Depends(get_supabase)):
    try:
        role_id = _signup_role_id(supabase)
        repository = SupabaseUserRepository(supabase)
        use_case = RegisterUseCase(repository)
        user = use_case.execute(user_data.email, user_data.password, role_id)

        # Registration is intentionally public, so the acting user is the
        # account being created rather than an administrator.
        await log_audit_action(
            supabase,
            user_id=user.id,
            action_type="USER_REGISTER",
            table_name="users",
            old_payload=None,
            new_payload={"id": user.id, "email": user_data.email, "role_id": role_id},
        )

        return {"message": "User registered successfully", "user_id": user.id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def _signup_role_id(supabase: Client) -> int:
    """The id of SIGNUP_ROLE, looked up by name rather than hardcoded.

    Role ids have already been gotten wrong once in this codebase (the seed
    script's), and a wrong hardcoded id here would silently grant a different
    role to every new account. If the role is missing, refuse the signup
    rather than fall back to anything.
    """
    rows = (
        supabase.table("roles").select("id").eq("role_name", SIGNUP_ROLE).execute().data or []
    )
    if len(rows) != 1:
        raise HTTPException(status_code=500, detail="Signup role is not configured")
    return rows[0]["id"]

@router.post("/login")
async def login(user_data: UserLogin, supabase: Client = Depends(get_supabase)):
    try:
        repository = SupabaseUserRepository(supabase)
        use_case = LoginUseCase(repository)
        access_token, refresh_token, user = use_case.execute(user_data.email, user_data.password)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "id": user.id,
                "email": user.email,
                "role": user.role_name
            }
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

def _is_last_admin(supabase: Client, target_role: str | None) -> bool:
    """Whether the target is the only remaining Admin account.

    Role changes and Admin deletions both need admin:roles, which only Admin
    holds, so losing the last Admin would leave nobody able to manage roles
    short of editing the database directly.
    """
    if target_role != UserRole.ADMIN.value:
        return False
    users = supabase.table("users").select("roles(role_name)").execute().data or []
    admins = sum(1 for u in users if (u.get("roles") or {}).get("role_name") == UserRole.ADMIN.value)
    return admins <= 1


class UpdateRoleRequest(BaseModel):
    role_id: int

@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: UuidPath,
    data: UpdateRoleRequest,
    # admin:roles, not admin:users: System Administrator holds admin:users and
    # would otherwise be able to grant itself Admin.
    current_user: dict = Depends(require_permission('admin:roles')),
    supabase: Client = Depends(get_supabase),
):
    try:
        # Capture the prior role before overwriting it, so the audit row records
        # what the role changed *from* and not merely that it changed.
        existing = supabase.table("users").select("id, email, role_id, roles(role_name)").eq("id", user_id).execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="User not found")
        row = existing.data[0]
        target_role = (row.get("roles") or {}).get("role_name")
        old_row = {k: v for k, v in row.items() if k != "roles"}

        # Re-saving the same role is a no-op, so only an actual change away
        # from Admin can remove the last one.
        if data.role_id != old_row.get("role_id") and _is_last_admin(supabase, target_role):
            raise HTTPException(status_code=409, detail="Can't change the role of the last Admin account")

        # Checked first so an unknown id is a plain 422, not the database's
        # foreign-key error passed through verbatim.
        if not supabase.table("roles").select("id").eq("id", data.role_id).execute().data:
            raise HTTPException(status_code=422, detail="Unknown role")

        response = supabase.table("users").update({"role_id": data.role_id}).eq("id", user_id).execute()

        await log_audit_action(
            supabase,
            user_id=current_user["id"],
            action_type="USER_ROLE_CHANGE",
            table_name="users",
            old_payload=old_row,
            new_payload=response.data[0] if response.data else {"id": user_id, "role_id": data.role_id},
        )

        return {"message": "User role updated successfully", "data": response.data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/users")
async def get_users(
    current_user: dict = Depends(require_permission('admin:users')),
    supabase: Client = Depends(get_supabase),
):
    try:
        response = supabase.table("users").select("*, roles(role_name)").execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: UuidPath,
    current_user: dict = Depends(require_permission('admin:users')),
    supabase: Client = Depends(get_supabase),
):
    try:
        # The row is about to stop existing, so the audit entry is the only
        # remaining record of what was deleted.
        existing = supabase.table("users").select("id, email, role_id, created_at, roles(role_name)").eq("id", user_id).execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="User not found")
        row = existing.data[0]
        target_role = (row.get("roles") or {}).get("role_name")
        old_row = {k: v for k, v in row.items() if k != "roles"}

        # Only Admin may delete an Admin account. admin:users alone would let a
        # System Administrator remove every Admin and leave nobody able to
        # change roles, since that needs admin:roles too.
        caller_role = (current_user.get("roles") or {}).get("role_name") or ""
        if target_role == UserRole.ADMIN.value and not has_permission(caller_role, Permission.ADMIN_ROLES.value):
            raise HTTPException(status_code=403, detail="Only an Admin can delete an Admin account")
        if _is_last_admin(supabase, target_role):
            raise HTTPException(status_code=409, detail="Can't delete the last Admin account")

        response = supabase.table("users").delete().eq("id", user_id).execute()

        await log_audit_action(
            supabase,
            user_id=current_user["id"],
            action_type="USER_DELETE",
            table_name="users",
            old_payload=old_row,
            new_payload=None,
        )

        return {"message": "User deleted successfully", "data": response.data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

