from fastapi import APIRouter, HTTPException, Depends
from app.core.supabase import get_supabase
from app.schemas.hr import (EmployeeProfile, EmployeeProfileCreate, EmployeeProfileUpdate, AttendanceLog, AttendanceLogCreate, AttendanceLogUpdate,PayrollLedger, SRI_LANKA)
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta, timezone
from supabase import Client
from app.core.security import require_any_permission, require_permission
from app.core.audit import log_audit_action
from app.core.permissions import UserRole
from app.services.employees import require_active
from app.services.payroll_status import payroll_approved
from fastapi.responses import StreamingResponse
from datetime import date as date_cls
from fastapi import HTTPException
import io
import csv

router = APIRouter()

def get_employee_by_user_id(supabase: Client, user_id: str):
    response = supabase.table("employee_profile").select("*").eq("user_id", user_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="No linked employee profile found for this user.")
    return response.data[0]

@router.get("/employees", response_model=List[EmployeeProfile])
async def get_employees(user = Depends(require_permission('hr:manage')), supabase: Client = Depends(get_supabase)):
    # The linked login's email comes with each row: HR holds hr:manage, not
    # admin:users, so it cannot look the account up on its own.
    rows = supabase.table("employee_profile").select("*, users(email)").execute().data or []
    for row in rows:
        row["login_email"] = (row.pop("users", None) or {}).get("email")
    return rows


@router.get("/linkable-logins")
async def get_linkable_logins(user = Depends(require_permission('hr:manage')), supabase: Client = Depends(get_supabase)):
    """
    Login accounts HR can link to an employee: those not linked to one yet,
    minus System Administrator, which is not an employee role. Email and
    role only.
    """
    accounts = supabase.table("users").select("id, email, roles(role_name)").execute().data or []
    linked = _linked_user_ids(supabase)
    out = []
    for account in accounts:
        role = (account.get("roles") or {}).get("role_name")
        if account["id"] in linked or role == UserRole.SYSTEM_ADMINISTRATOR.value:
            continue
        out.append({"id": account["id"], "email": account.get("email"), "role": role})
    out.sort(key=lambda a: (a["email"] or "").lower())
    return out


def _linked_user_ids(supabase: Client) -> set:
    rows = supabase.table("employee_profile").select("id, user_id").execute().data or []
    return {r["user_id"] for r in rows if r.get("user_id")}


def _check_login(supabase: Client, user_id: str, employee_id: Optional[int] = None) -> None:
    """
    A login can be linked to one employee at most. Nothing in the schema says
    so, and get_employee_by_user_id takes the first match, so a second link
    would silently send that person's clock-ins to the wrong record.
    """
    accounts = supabase.table("users").select("id, roles(role_name)").eq("id", user_id).execute().data or []
    if not accounts:
        raise HTTPException(status_code=404, detail="That login account no longer exists.")
    if (accounts[0].get("roles") or {}).get("role_name") == UserRole.SYSTEM_ADMINISTRATOR.value:
        raise HTTPException(status_code=400, detail="System Administrator accounts can't be linked to an employee.")
    holders = supabase.table("employee_profile").select("id, first_name, last_name") \
        .eq("user_id", user_id).execute().data or []
    other = next((h for h in holders if h.get("id") != employee_id), None)
    if other:
        name = f"{other.get('first_name', '')} {other.get('last_name', '')}".strip()
        raise HTTPException(status_code=409, detail=f"That login is already linked to {name or 'another employee'}.")

def _nic_taken(nic: str) -> HTTPException:
    return HTTPException(status_code=409, detail=f"An employee with NIC {nic} already exists.")


def _ensure_nic_free(supabase: Client, nic: str, exclude_id: Optional[int] = None) -> None:
    # The column is UNIQUE, but a violation surfaced as a bare 500 and the
    # form could only say "Failed to add employee".
    rows = supabase.table("employee_profile").select("id").eq("nic", nic).execute().data or []
    if any(r.get("id") != exclude_id for r in rows):
        raise _nic_taken(nic)


def _is_unique_violation(e: Exception) -> bool:
    # Another request can take the NIC between the check and the write.
    return getattr(e, "code", None) == "23505" or "duplicate key" in str(e)


@router.post("/employees", response_model=EmployeeProfile)
async def create_employee(employee: EmployeeProfileCreate, user = Depends(require_permission('hr:manage')), supabase: Client = Depends(get_supabase)):
    _ensure_nic_free(supabase, employee.nic)
    if employee.user_id:
        _check_login(supabase, employee.user_id)
    try:
        response = supabase.table("employee_profile").insert(employee.model_dump()).execute()
    except Exception as e:
        if _is_unique_violation(e):
            raise _nic_taken(employee.nic)
        raise
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create employee")

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="EMPLOYEE_CREATE",
        table_name="employee_profile",
        old_payload=None,
        new_payload=response.data[0],
    )

    return response.data[0]

@router.put("/employees/{employee_id}", response_model=EmployeeProfile)
async def update_employee(employee_id: int, employee: EmployeeProfileUpdate, user = Depends(require_permission('hr:manage')), supabase: Client = Depends(get_supabase)):
    # Salary and role live on this row, so the prior values are the point of
    # the audit entry.
    existing = supabase.table("employee_profile").select("*").eq("id", employee_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Employee not found")

    changes = employee.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No changes were sent.")
    if "nic" in changes:
        _ensure_nic_free(supabase, changes["nic"], exclude_id=employee_id)
    if changes.get("user_id"):
        _check_login(supabase, changes["user_id"], employee_id=employee_id)

    try:
        response = supabase.table("employee_profile").update(changes).eq("id", employee_id).execute()
    except Exception as e:
        if _is_unique_violation(e):
            raise _nic_taken(changes["nic"])
        raise
    if not response.data:
        raise HTTPException(status_code=404, detail="Employee not found")

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="EMPLOYEE_UPDATE",
        table_name="employee_profile",
        old_payload=existing.data[0],
        new_payload=response.data[0],
    )

    return response.data[0]

# --- SELF SERVICE ATTENDANCE ---

# An overnight shift clocks out the morning after it clocked in. A record
# from yesterday that is still open is only closed by today's clock-out if it
# began within this long; past that it is a forgotten clock-out for HR to fix,
# not a shift, and closing it would book a 20-hour day.
OVERNIGHT_MAX = timedelta(hours=16)


def _sl_now() -> datetime:
    return datetime.now(SRI_LANKA)


def _sl_today() -> date:
    # Sri Lanka's date, not the server's: the deployed backend runs on UTC,
    # where a 05:00 clock-in in Colombo is still the previous day.
    return _sl_now().date()


def _parse_ts(value) -> Optional[datetime]:
    """A stored or submitted clock time as an aware datetime."""
    if value is None or isinstance(value, datetime):
        return value if value is None or value.tzinfo else value.replace(tzinfo=SRI_LANKA)
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.post("/attendance/clock-in")
async def clock_in(user = Depends(require_permission('hr:attendance:self')), supabase: Client = Depends(get_supabase)):
    emp = get_employee_by_user_id(supabase, user['id'])
    require_active(emp, "clock in")
    today = _sl_today().isoformat()

    existing = supabase.table("attendance_log").select("*").eq("employee_id", emp['id']).eq("target_date", today).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="Already clocked in for today.")

    record = {
        "employee_id": emp['id'],
        "target_date": today,
        "clock_in": datetime.now(timezone.utc).isoformat(),
        "is_locked": False
    }
    try:
        resp = supabase.table("attendance_log").insert(record).execute()
    except Exception as e:
        # A double click lands two requests between the check and the insert;
        # the unique index (migration 024) refuses the second.
        if _is_unique_violation(e):
            raise HTTPException(status_code=400, detail="Already clocked in for today.")
        raise

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="ATTENDANCE_CLOCK_IN",
        table_name="attendance_log",
        old_payload=None,
        new_payload=resp.data[0] if resp.data else record,
    )

    return resp.data[0]

@router.post("/attendance/clock-out")
async def clock_out(user = Depends(require_permission('hr:attendance:self')), supabase: Client = Depends(get_supabase)):
    emp = get_employee_by_user_id(supabase, user['id'])
    require_active(emp, "clock out")
    now = _sl_now()
    today = now.date()
    yesterday = today - timedelta(days=1)

    rows = supabase.table("attendance_log").select("*").eq("employee_id", emp['id']) \
        .in_("target_date", [today.isoformat(), yesterday.isoformat()]).execute().data or []
    todays = [r for r in rows if str(r["target_date"])[:10] == today.isoformat()]
    overnight = [
        r for r in rows
        if str(r["target_date"])[:10] == yesterday.isoformat() and r.get("clock_in") and not r.get("clock_out")
        and now - _parse_ts(r["clock_in"]) <= OVERNIGHT_MAX
    ]
    if todays:
        record = todays[0]
    elif overnight:
        record = overnight[0]
    else:
        raise HTTPException(status_code=400, detail="No active clock-in record found for today.")

    if record['is_locked']:
        raise HTTPException(status_code=403, detail="Attendance record is already locked.")
    if record['clock_out']:
        raise HTTPException(status_code=400, detail="Already clocked out.")

    # The same instant that chose the record, stored as UTC like clock-in.
    clock_out_time = now.astimezone(timezone.utc)
    worked_hours = _compute_worked_hours(_parse_ts(record['clock_in']), clock_out_time)

    # Clocking out does not lock. It used to, which left HR unable to correct
    # a wrong clock-out: update_attendance refuses locked rows and nothing
    # could unlock them. Locking is HR's step, per day, once reviewed.
    update_data = {
        "clock_out": clock_out_time.isoformat(),
        "worked_hours": worked_hours,
    }

    resp = supabase.table("attendance_log").update(update_data).eq("id", record['id']).execute()

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="ATTENDANCE_CLOCK_OUT",
        table_name="attendance_log",
        old_payload=record,
        new_payload=resp.data[0] if resp.data else update_data,
    )

    return resp.data[0]

@router.get("/attendance/me")
async def get_my_attendance(month: Optional[int] = None, year: Optional[int] = None, user = Depends(require_permission('hr:attendance:self')), supabase: Client = Depends(get_supabase)):
    emp = get_employee_by_user_id(supabase, user['id'])
    query = supabase.table("attendance_log").select("*").eq("employee_id", emp['id']).order("target_date", desc=True)

    if month and year:
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year+1}-01-01" if month == 12 else f"{year}-{month+1:02d}-01"
        query = query.gte("target_date", start_date).lt("target_date", end_date)

    resp = query.execute()
    return resp.data

# --- HR ATTENDANCE MANAGEMENT ---

@router.get("/attendance")
async def get_attendance(target_date: Optional[date] = None, month: Optional[int] = None, year: Optional[int] = None, user = Depends(require_permission('hr:attendance:manage')), supabase: Client = Depends(get_supabase)):
    query = supabase.table("attendance_log").select("*, employee_profile(*)")
    if target_date:
        query = query.eq("target_date", str(target_date))
    if month and year:
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year+1}-01-01" if month == 12 else f"{year}-{month+1:02d}-01"
        query = query.gte("target_date", start_date).lt("target_date", end_date)
    response = query.execute()
    return response.data


def _compute_worked_hours(clock_in, clock_out):
    if clock_in and clock_out:
        # Subtract real instants. Stripping the timezones (as this used to)
        # mixed a stored UTC time with a newly entered Sri Lanka time when
        # only one of the two was edited, putting worked hours 5.5 h out.
        # A naive value is a Sri Lanka wall-clock time. An overnight shift's
        # clock-out is stored on the next day, so the difference is positive;
        # it used to be stored on the same day and wrapped by 24 h here, which
        # also turned a typo (out 07:00 after in 09:10) into a 21.8-hour day.
        return round((_parse_ts(clock_out) - _parse_ts(clock_in)).total_seconds() / 3600, 2)
    return None


MAX_SHIFT = timedelta(hours=24)


def _check_times(target_date: date, clock_in: Optional[datetime], clock_out: Optional[datetime]) -> None:
    """The rules for times HR records or corrects."""
    if clock_in is None:
        raise HTTPException(status_code=400, detail="A clock-in time is required.")
    if target_date > _sl_today():
        raise HTTPException(status_code=400, detail="Attendance can't be recorded for a future date.")
    if clock_in.astimezone(SRI_LANKA).date() != target_date:
        raise HTTPException(status_code=400, detail=f"The clock-in must be on {target_date.isoformat()} (Sri Lanka time).")
    now = _sl_now()
    if clock_in > now or (clock_out is not None and clock_out > now):
        raise HTTPException(status_code=400, detail="Clock times can't be in the future.")
    if clock_out is not None:
        if clock_out <= clock_in:
            raise HTTPException(
                status_code=400,
                detail="Clock-out must be after clock-in. For an overnight shift, put the clock-out on the next day.",
            )
        if clock_out - clock_in > MAX_SHIFT:
            raise HTTPException(status_code=400, detail="A shift can't be longer than 24 hours.")


def _refuse_if_payroll_approved(supabase: Client, d: date) -> None:
    # Approved pay was worked out from the month as it stood, so its
    # attendance is history from then. Only unlock used to check this, so a
    # record could still be added, edited and locked, and then never reopened.
    if payroll_approved(supabase, d.month, d.year):
        raise HTTPException(
            status_code=409,
            detail=f"Payroll for {d.month}/{d.year} is approved; its attendance can no longer be changed.",
        )


def _forbid_own_record(supabase: Client, user: dict, employee_id: int) -> None:
    # HR does not correct its own attendance, as with approving one's own
    # leave: someone else has to (confirmed 2026-11-11).
    mine = supabase.table("employee_profile").select("id").eq("user_id", str(user["id"])).execute().data or []
    if any(m.get("id") == employee_id for m in mine):
        raise HTTPException(status_code=403, detail="You can't change your own attendance. Ask another HR officer to do it.")


@router.post("/attendance", response_model=AttendanceLog)
async def log_attendance(attendance: AttendanceLogCreate, user = Depends(require_permission('hr:attendance:manage')), supabase: Client = Depends(get_supabase)):
    _forbid_own_record(supabase, user, attendance.employee_id)
    _check_times(attendance.target_date, attendance.clock_in, attendance.clock_out)
    _refuse_if_payroll_approved(supabase, attendance.target_date)

    existing = supabase.table("attendance_log").select("*") \
        .eq("employee_id", attendance.employee_id) \
        .eq("target_date", str(attendance.target_date)).execute()
    if existing.data:
        if existing.data[0]['is_locked']:
            raise HTTPException(status_code=403, detail="Record is locked and cannot be modified.")
        raise HTTPException(status_code=400, detail="A log already exists for this employee on this date. Edit it instead.")

    payload = attendance.model_dump(mode="json")
    payload["worked_hours"] = _compute_worked_hours(attendance.clock_in, attendance.clock_out)
    payload["is_locked"] = False

    try:
        response = supabase.table("attendance_log").insert(payload).execute()
    except Exception as e:
        if _is_unique_violation(e):
            raise HTTPException(status_code=400, detail="A log already exists for this employee on this date. Edit it instead.")
        raise
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to log attendance")

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="ATTENDANCE_CREATE",
        table_name="attendance_log",
        old_payload=None,
        new_payload=response.data[0],
    )

    return response.data[0]

@router.get("/attendance/export")
async def export_attendance(
    target_date: str,
    user = Depends(require_permission('hr:attendance:manage')),
    supabase: Client = Depends(get_supabase),
):
    try:
        parsed_date = date_cls.fromisoformat(target_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="target_date must be in YYYY-MM-DD format")

    logs = (
        supabase.table("attendance_log")
        .select("*, employee_profile(first_name, last_name)")
        .eq("target_date", parsed_date.isoformat())
        .execute()
    )

    def hhmm(value) -> str:
        # Sri Lanka wall-clock time, as the grid shows it. The raw value is a
        # UTC timestamp ("2026-07-29T03:00:00+00:00") that read as 03:00.
        dt = _parse_ts(value)
        if not dt:
            return ""
        local = dt.astimezone(SRI_LANKA)
        return local.strftime("%H:%M") + (" (next day)" if local.date() > parsed_date else "")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Employee", "Check In", "Check Out", "Worked Hours"])

    for log in logs.data or []:
        profile = log.get("employee_profile") or {}
        full_name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
        writer.writerow([
            full_name,
            hhmm(log.get("clock_in")),
            hhmm(log.get("clock_out")),
            log.get("worked_hours"),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=attendance_{parsed_date.isoformat()}.csv"}
    )

@router.put("/attendance/{attendance_id}", response_model=AttendanceLog)
async def update_attendance(attendance_id: int, attendance: AttendanceLogUpdate, user = Depends(require_permission('hr:attendance:manage')), supabase: Client = Depends(get_supabase)):
    existing = supabase.table("attendance_log").select("*").eq("id", attendance_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    current = existing.data[0]
    _forbid_own_record(supabase, user, current["employee_id"])
    if current["is_locked"]:
        raise HTTPException(status_code=400, detail="This record is locked and cannot be edited")
    record_date = date_cls.fromisoformat(str(current["target_date"])[:10])
    _refuse_if_payroll_approved(supabase, record_date)

    # A field sent as null is a deliberate clear: a wrong clock-out can be
    # removed (the record goes back to missing a clock-out). The clock-in
    # cannot be. Fields not sent keep their stored values.
    sent = attendance.model_fields_set
    if "clock_in" in sent and attendance.clock_in is None:
        raise HTTPException(status_code=400, detail="The clock-in can't be cleared.")
    clock_in = attendance.clock_in if "clock_in" in sent else _parse_ts(current.get("clock_in"))
    clock_out = attendance.clock_out if "clock_out" in sent else _parse_ts(current.get("clock_out"))
    _check_times(record_date, clock_in, clock_out)

    payload = attendance.model_dump(mode="json", exclude_unset=True)
    payload["worked_hours"] = _compute_worked_hours(clock_in, clock_out)

    response = supabase.table("attendance_log").update(payload).eq("id", attendance_id).execute()
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to update attendance")

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="ATTENDANCE_UPDATE",
        table_name="attendance_log",
        old_payload=current,
        new_payload=response.data[0],
    )

    return response.data[0]


@router.post("/attendance/lock-day")
async def lock_day_attendance(target_date: date, user = Depends(require_permission('hr:attendance:manage')), supabase: Client = Depends(get_supabase)):
    # Only complete records are locked. Locking a record with no clock-out
    # froze it with blank hours, and with nothing able to unlock it the
    # mistake was permanent. Incomplete ones are reported back instead.
    day = supabase.table("attendance_log").select("id, clock_in, clock_out, is_locked") \
        .eq("target_date", str(target_date)).execute().data or []
    lockable = [r["id"] for r in day if r.get("clock_in") and r.get("clock_out") and not r.get("is_locked")]
    incomplete = [r["id"] for r in day if not (r.get("clock_in") and r.get("clock_out"))]

    updated_count = 0
    if lockable:
        response = supabase.table("attendance_log").update({"is_locked": True}).in_("id", lockable).execute()
        updated_count = len(response.data) if response.data else 0

    # Locking a day is what makes those hours eligible for payroll, so it is a
    # financially meaningful action even though it edits no money directly.
    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="ATTENDANCE_LOCK_DAY",
        table_name="attendance_log",
        old_payload=None,
        new_payload={
            "target_date": str(target_date),
            "updated_count": updated_count,
            "skipped_incomplete": len(incomplete),
        },
    )

    return {
        "message": f"Attendance locked for {target_date}",
        "updated_count": updated_count,
        "skipped_incomplete": len(incomplete),
    }

@router.post("/attendance/lock")
async def lock_attendance(target_date: date, user = Depends(require_permission('hr:attendance:manage')), supabase: Client = Depends(get_supabase)):
    # Kept for backward compatibility with older UI if any
    return await lock_day_attendance(target_date, user, supabase)

@router.post("/attendance/{attendance_id}/unlock", response_model=AttendanceLog)
async def unlock_attendance(attendance_id: int, user = Depends(require_permission('hr:attendance:manage')), supabase: Client = Depends(get_supabase)):
    """
    Reopen a locked record for correction.

    Refused once that month's payroll is approved: approved pay was worked
    out from the month as it stood, so its attendance is history from then.
    """
    existing = supabase.table("attendance_log").select("*").eq("id", attendance_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    record = existing.data[0]
    _forbid_own_record(supabase, user, record["employee_id"])
    if not record.get("is_locked"):
        raise HTTPException(status_code=400, detail="This record is not locked.")

    _refuse_if_payroll_approved(supabase, date_cls.fromisoformat(str(record["target_date"])[:10]))

    response = supabase.table("attendance_log").update({"is_locked": False}).eq("id", attendance_id).execute()
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to unlock attendance")

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="ATTENDANCE_UNLOCK",
        table_name="attendance_log",
        old_payload=record,
        new_payload=response.data[0],
    )

    return response.data[0]


# --- PAYROLL PIPELINE ---
#
# A month's payroll is a payroll_runs row: Draft when generated, Approved when
# a second person signs it off, and only then posted to the finance ledger.
# The transactional work lives in two SQL functions; see
# db/migrations/007_payroll_runs.sql for why.

# Sentences the SQL functions RAISE, mapped to HTTP statuses. PostgREST wraps
# the message in JSON, so the endpoint matches on these and returns the
# sentence alone rather than the wrapper.
_RPC_ERRORS = (
    ("is already approved", 409),
    ("must be approved by someone other than", 403),
    ("not found", 404),
    ("No active employees found", 404),
    ("has nothing to pay", 400),
    ("is out of date", 409),
)

_MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

# When a month's payroll may be generated and approved (confirmed
# 2026-11-11). Generated once the month has started; approved once it is
# over, or from the 25th of the month itself, when salaries are prepared.
# Never a month still to come: November was approved on the 3rd, and a
# December draft existed in mid-November, which approving would have posted
# to the ledger a month and a half early.
APPROVE_FROM_DAY = 25

# An approver whose role the generator changed this recently may not approve
# that run. November's draft was generated, a General Staff account promoted
# to Admin 22 minutes later, and the payroll approved by it a minute after
# that: the two-person rule held on paper while one person did both.
ROLE_CHANGE_COOLDOWN = timedelta(hours=24)


def _period(month: int, year: int) -> str:
    return f"{_MONTH_NAMES[month - 1]} {year}"


def _generate_block(month: int, year: int) -> Optional[str]:
    today = _sl_today()
    if (year, month) > (today.year, today.month):
        return f"Payroll for {_period(month, year)} can't be generated before the month starts."
    return None


def _approve_block(month: int, year: int) -> Optional[str]:
    today = _sl_today()
    if (year, month) > (today.year, today.month):
        return f"Payroll for {_period(month, year)} can't be approved before the month starts."
    if (year, month) == (today.year, today.month) and today.day < APPROVE_FROM_DAY:
        return f"Payroll for {_period(month, year)} can be approved from {APPROVE_FROM_DAY} {_MONTH_NAMES[month - 1]}."
    return None


def _role_changed_by(supabase: Client, approver_id: str, generator_id: str) -> bool:
    """Whether the generator changed the approver's role within the cooldown."""
    cutoff = (_sl_now() - ROLE_CHANGE_COOLDOWN).astimezone(timezone.utc).isoformat()
    rows = supabase.table("system_audit_logs").select("old_payload, new_payload") \
        .eq("action_type", "USER_ROLE_CHANGE").eq("user_id", str(generator_id)) \
        .gte("timestamp", cutoff).execute().data or []
    for row in rows:
        target = (row.get("new_payload") or {}).get("id") or (row.get("old_payload") or {}).get("id")
        if target is not None and str(target) == str(approver_id):
            return True
    return False


def _draft_drift(supabase: Client, run_id: int) -> Optional[list]:
    """How a draft differs from generating it now; None if that can't be told."""
    try:
        rows = supabase.rpc("payroll_draft_drift", {"p_run_id": run_id}).execute().data or []
    except Exception:
        # Migration 025 not applied yet. Approval still works as before it.
        return None
    out = [{
        "employee_id": r.get("employee_id"),
        "employee_name": r.get("employee_name") or f"Employee {r.get('employee_id')}",
        "change": r.get("change"),
        "draft_amount": None if r.get("draft_amount") is None else float(r["draft_amount"]),
        "current_amount": None if r.get("current_amount") is None else float(r["current_amount"]),
    } for r in rows]
    out.sort(key=lambda d: (d["change"] or "", d["employee_name"].lower()))
    return out


def _month_bounds(month: int, year: int) -> tuple[str, str]:
    start = f"{year}-{month:02d}-01"
    end = f"{year+1}-01-01" if month == 12 else f"{year}-{month+1:02d}-01"
    return start, end


def _validate_month(month: int, year: int) -> None:
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        raise HTTPException(status_code=400, detail="Choose a valid month and year.")


def _audit_run(run: dict) -> dict:
    # total as a decimal string: a whole-number float like 155000.0 comes
    # back from JSONB as 155000 and would make the audit hash unverifiable
    # (see the note in create_transaction in app/api/finance.py).
    return {**run, "total": f"{float(run.get('total') or 0):.2f}"}


def _rpc_error(e: Exception) -> HTTPException:
    """Turn a SQL function's RAISE EXCEPTION into an HTTP error."""
    # postgrest's APIError carries the raised text in .message; fall back to
    # str() for anything else.
    msg = getattr(e, "message", None) or str(e)
    for needle, status in _RPC_ERRORS:
        if needle in msg:
            return HTTPException(status_code=status, detail=msg)
    return HTTPException(status_code=500, detail=f"Payroll operation failed: {msg}")


def _single(data):
    """An RPC returning one composite row may come back as a dict or a list."""
    if isinstance(data, list):
        return data[0] if data else None
    return data


@router.get("/payroll", response_model=List[PayrollLedger])
async def get_payroll(month: int, year: int, user = Depends(require_permission('finance:read')), supabase: Client = Depends(get_supabase)):
    response = supabase.table("payroll_ledger").select("*").eq("payroll_month", month).eq("payroll_year", year).execute()
    return response.data


@router.get("/payroll/run")
async def get_payroll_run(
    month: int,
    year: int,
    user = Depends(require_any_permission('payroll:generate', 'payroll:approve')),
    supabase: Client = Depends(get_supabase),
):
    """
    The month's run, its lines with employee names, and how many attendance
    records in the month are still incomplete (a warning, not a gate: pay is a
    fixed monthly salary).
    """
    _validate_month(month, year)

    runs = supabase.table("payroll_runs") \
        .select(
            "*, generator:users!payroll_runs_generated_by_fkey(email), "
            "approver:users!payroll_runs_approved_by_fkey(email)"
        ) \
        .eq("payroll_month", month).eq("payroll_year", year).execute().data or []
    run = runs[0] if runs else None

    lines = []
    if run:
        rows = supabase.table("payroll_ledger") \
            .select("*, employee_profile(first_name, last_name, nic)") \
            .eq("run_id", run["id"]).execute().data or []
        for r in rows:
            profile = r.get("employee_profile") or {}
            name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
            lines.append({
                "id": r.get("id"),
                "employee_id": r.get("employee_id"),
                "employee_name": name or f"Employee {r.get('employee_id')}",
                "nic": profile.get("nic"),
                "net_payable": float(r.get("net_payable") or 0),
            })
        lines.sort(key=lambda line: line["employee_name"].lower())

    start, end = _month_bounds(month, year)
    logs = supabase.table("attendance_log").select("id, clock_in, clock_out") \
        .gte("target_date", start).lt("target_date", end).execute().data or []
    incomplete = sum(1 for log in logs if not (log.get("clock_in") and log.get("clock_out")))

    # Whether Finance has paid the approved payable. The page's last step,
    # "Paid in Ledger", never showed as done, even for a paid month.
    payment_status = None
    if run and run.get("finance_transaction_id"):
        tx = supabase.table("financial_transactions").select("status") \
            .eq("id", run["finance_transaction_id"]).execute().data or []
        payment_status = tx[0].get("status") if tx else None

    return {
        "run": run,
        "lines": lines,
        "incomplete_attendance": incomplete,
        "drift": _draft_drift(supabase, run["id"]) if run and run.get("status") == "Draft" else None,
        "payment_status": payment_status,
        "generate_block": _generate_block(month, year),
        "approve_block": _approve_block(month, year),
    }


@router.post("/payroll/generate")
async def generate_monthly_payroll(
    month: int,
    year: int,
    user = Depends(require_permission('payroll:generate')),
    supabase: Client = Depends(get_supabase)
):
    """
    Create or refresh the month's Draft. Nothing reaches the finance ledger
    until approve_payroll.

    Attendance no longer blocks this. Pay is a fixed monthly salary, so an
    unlocked or incomplete record does not change it; it used to stop the
    whole organisation's payroll over one forgotten clock-out.
    """
    _validate_month(month, year)
    block = _generate_block(month, year)
    if block:
        raise HTTPException(status_code=400, detail=block)
    try:
        result = supabase.rpc(
            "generate_payroll_draft",
            {"p_month": month, "p_year": year, "p_user": str(user["id"])},
        ).execute()
    except Exception as e:
        raise _rpc_error(e)

    run = _single(result.data)
    if not run:
        raise HTTPException(status_code=500, detail="Payroll generation returned no run.")

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="PAYROLL_DRAFT_GENERATE",
        table_name="payroll_runs",
        old_payload=None,
        new_payload=_audit_run(run),
    )
    return run


@router.post("/payroll/runs/{run_id}/approve")
async def approve_payroll(
    run_id: int,
    user = Depends(require_permission('payroll:approve')),
    supabase: Client = Depends(get_supabase),
):
    """
    Approve a Draft: freezes it and posts its total to the ledger as a payable
    dated the last day of the month. The SQL function refuses an approval by
    whoever generated the run, and of a draft that is out of date.
    """
    runs = supabase.table("payroll_runs").select("id, payroll_month, payroll_year, status, generated_by") \
        .eq("id", run_id).execute().data or []
    if not runs:
        raise HTTPException(status_code=404, detail=f"Payroll run {run_id} not found.")
    pending = runs[0]
    if pending.get("status") == "Draft":
        block = _approve_block(pending["payroll_month"], pending["payroll_year"])
        if block:
            raise HTTPException(status_code=400, detail=block)
        generator = pending.get("generated_by")
        if generator and str(generator) != str(user["id"]) and _role_changed_by(supabase, user["id"], generator):
            raise HTTPException(
                status_code=403,
                detail="Your role was changed in the last 24 hours by the person who generated this payroll, "
                       "so you can't approve it. Ask another approver.",
            )
    try:
        result = supabase.rpc(
            "approve_payroll_run",
            {"p_run_id": run_id, "p_user": str(user["id"])},
        ).execute()
    except Exception as e:
        raise _rpc_error(e)

    run = _single(result.data)
    if not run:
        raise HTTPException(status_code=500, detail="Payroll approval returned no run.")

    await log_audit_action(
        supabase,
        user_id=user["id"],
        action_type="PAYROLL_APPROVE",
        table_name="payroll_runs",
        old_payload=None,
        new_payload=_audit_run(run),
    )
    return run
