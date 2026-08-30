from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from app.core.supabase import get_supabase
from supabase import Client
from typing import Optional
from app.infrastructure.repositories import SupabaseUserRepository
from app.application.use_cases import RegisterUseCase, LoginUseCase
from app.core.security import require_permission
from app.core.audit import log_audit_action

router = APIRouter()

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    role_id: Optional[int] = 2  # Default to 'Director' (id: 2)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

@router.post("/register")
async def register(user_data: UserRegister, supabase: Client = Depends(get_supabase)):
    try:
        repository = SupabaseUserRepository(supabase)
        use_case = RegisterUseCase(repository)
        user = use_case.execute(user_data.email, user_data.password, user_data.role_id)

        # Registration is intentionally public, so the acting user is the
        # account being created rather than an administrator.
        await log_audit_action(
            supabase,
            user_id=user.id,
            action_type="USER_REGISTER",
            table_name="users",
            old_payload=None,
            new_payload={"id": user.id, "email": user_data.email, "role_id": user_data.role_id},
        )

        return {"message": "User registered successfully", "user_id": user.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

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

class UpdateRoleRequest(BaseModel):
    role_id: int

@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    data: UpdateRoleRequest,
    current_user: dict = Depends(require_permission('admin:users')),
    supabase: Client = Depends(get_supabase),
):
    try:
        # Capture the prior role before overwriting it, so the audit row records
        # what the role changed *from* and not merely that it changed.
        existing = supabase.table("users").select("id, email, role_id").eq("id", user_id).execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="User not found")
        old_row = existing.data[0]

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
async def get_users(supabase: Client = Depends(get_supabase)):
    try:
        response = supabase.table("users").select("*, roles(role_name)").execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: dict = Depends(require_permission('admin:users')),
    supabase: Client = Depends(get_supabase),
):
    try:
        # The row is about to stop existing, so the audit entry is the only
        # remaining record of what was deleted.
        existing = supabase.table("users").select("id, email, role_id, created_at").eq("id", user_id).execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="User not found")
        old_row = existing.data[0]

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

