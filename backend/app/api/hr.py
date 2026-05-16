from fastapi import APIRouter, HTTPException, Depends
from app.core.supabase import get_supabase
from app.schemas.hr import EmployeeProfile, EmployeeProfileCreate, AttendanceLog, AttendanceLogCreate, PayrollLedger
from typing import List, Optional
from datetime import date
from supabase import Client
from app.core.security import check_user_role, get_current_user

router = APIRouter()

# ==========================================
# 1. EMPLOYEE PROFILES MANAGEMENT
# ==========================================

@router.get("/employees", response_model=List[EmployeeProfile])
async def get_employees(
    user = Depends(check_user_role(["Admin", "Director", "HR"])), # 🔒 SECURED
    supabase: Client = Depends(get_supabase)
):
    response = supabase.table("employee_profile").select("*").execute()
    return response.data

@router.post("/employees", response_model=EmployeeProfile)
async def create_employee(
    employee: EmployeeProfileCreate, 
    user = Depends(check_user_role(["Admin", "Director", "HR"])), # 🔒 SECURED
    supabase: Client = Depends(get_supabase)
):
    response = supabase.table("employee_profile").insert(employee.model_dump()).execute()
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create employee")
    return response.data[0]

@router.put("/employees/{employee_id}", response_model=EmployeeProfile)
async def update_employee(
    employee_id: int, 
    employee: EmployeeProfileCreate, 
    user = Depends(check_user_role(["Admin", "Director"])), # 🔒 SECURED (Higher restriction)
    supabase: Client = Depends(get_supabase)
):
    response = supabase.table("employee_profile").update(employee.model_dump()).eq("id", employee_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Employee not found")
    return response.data[0]


# ==========================================
# 2. AUTOMATED TIME-TRACKING & ATTENDANCE
# ==========================================

@router.get("/attendance", response_model=List[AttendanceLog])
async def get_attendance(
    target_date: Optional[date] = None, 
    user = Depends(check_user_role(["Admin", "Director", "HR"])), # 🔒 SECURED
    supabase: Client = Depends(get_supabase)
):
    # Changed from 'attendance_log' to 'attendance_logs' for cross-module mapping
    query = supabase.table("attendance_logs").select("*")
    if target_date:
        query = query.eq("target_date", str(target_date))
    response = query.execute()
    return response.data

@router.post("/attendance", response_model=AttendanceLog)
async def log_attendance(
    attendance: AttendanceLogCreate, 
    user = Depends(check_user_role(["Admin", "Director", "HR"])), # 🔒 SECURED
    supabase: Client = Depends(get_supabase)
):
    """
    Allows authorized HR/Management staff to log worked hours for a specific date.
    Ensures duplicate logs for the same day are blocked.
    """
    # 1. Check if an attendance entry already exists for this employee on this date
    existing = supabase.table("attendance_logs") \
        .select("*") \
        .eq("employee_id", attendance.employee_id) \
        .eq("target_date", str(attendance.target_date)) \
        .execute()
        
    if existing.data:
        raise HTTPException(status_code=400, detail="Attendance already logged for this date.")

    # 2. Insert the new time-tracking entry into the database
    response = supabase.table("attendance_logs").insert(attendance.model_dump()).execute()

    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to log attendance")

    return response.data[0]

@router.post("/attendance/lock")
async def lock_attendance(
    target_date: date, 
    user = Depends(check_user_role(["Admin", "Director"])), # 🔒 SECURED (Only leadership can lock)
    supabase: Client = Depends(get_supabase)
):
    """
    Locks the timesheets for a specific date so they cannot be altered during payroll.
    """
    response = supabase.table("attendance_logs").update({"is_locked": True}).eq("target_date", str(target_date)).execute()
    return {"message": "Attendance records locked successfully", "data": response.data}


# ==========================================
# 3. PAYROLL LEDGER HISTORICAL VIEWS
# ==========================================

@router.get("/payroll", response_model=List[PayrollLedger])
async def get_payroll(
    month: int, 
    year: int, 
    user = Depends(check_user_role(["Admin", "Director", "HR"])), # 🔒 SECURED
    supabase: Client = Depends(get_supabase)
):
    response = supabase.table("payroll_ledger").select("*").eq("payroll_month", month).eq("payroll_year", year).execute()
    return response.data