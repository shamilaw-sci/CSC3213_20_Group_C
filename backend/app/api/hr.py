from fastapi import APIRouter, HTTPException, Depends
from app.core.supabase import get_supabase
from app.schemas.hr import (EmployeeProfile, EmployeeProfileCreate, EmployeeProfileUpdate, AttendanceLog, AttendanceLogCreate, AttendanceLogUpdate,PayrollLedger, SRI_LANKA, CorrectionRequestIn, CorrectionDecisionIn)
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta, timezone
from supabase import Client
from app.core.security import require_any_permission, require_permission
from app.core.audit import log_audit_action
from app.core.permissions import UserRole
from app.services.employees import require_active
from app.services.payroll_status import is_frozen
from app.services.payroll_engine import PayLine, compute_run, drift, month_bounds
from app.services.reports import PDFGenerationError, generate_pdf
from decimal import Decimal
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
        payload = employee.model_dump()
        # Only sent when set, so creating an employee keeps working before
        # migration 026 adds the column.
        if not (payload.get("epf_number") or "").strip():
            payload.pop("epf_number", None)
        response = supabase.table("employee_profile").insert(payload).execute()
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

    changes = employee.model_dump(mode="json", exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No changes were sent.")
    if "epf_number" in changes:
        changes["epf_number"] = (changes["epf_number"] or "").strip() or None
    # The last day goes with being a leaver: reactivating clears it, and it
    # can't come before the join date. Payroll pro-rates the final month to it.
    if changes.get("status") == "Active":
        changes["date_left"] = None
    if changes.get("date_left"):
        left = date_cls.fromisoformat(changes["date_left"])
        joined = existing.data[0].get("date_joined")
        if joined and left < date_cls.fromisoformat(str(joined)[:10]):
            raise HTTPException(status_code=400, detail="The last working day can't be before the join date.")
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
    # Only days up to the approval date (confirmed 2026-11-12): payroll can be
    # approved from the 25th, and the rest of that month is still to happen.
    through = is_frozen(supabase, d)
    if through:
        raise HTTPException(
            status_code=409,
            detail=f"Payroll for {d.month}/{d.year} is approved; attendance up to "
                   f"{through.isoformat()} can no longer be changed.",
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


# --- ATTENDANCE CORRECTION REQUESTS ---
#
# Staff ask for a past day's times to be corrected; HR approves or rejects
# (confirmed 2026-10-29, details 2026-11-12). Schema: migration 028.

_CORRECTIONS = "attendance_correction_requests"


def _no_corrections_table(error: Exception) -> bool:
    """Migration 028 isn't applied yet."""
    text = str(error).lower()
    return "attendance_correction_requests" in text and any(
        k in text for k in ("42p01", "pgrst205", "does not exist", "could not find the table"))


def _corrections_unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="Attendance corrections aren't set up yet (database migration 028).")


def _tracked_from(supabase: Client, employee: dict) -> Optional[date]:
    """The employee's attendance tracked-from date: their override, or the organisation's."""
    own = employee.get("attendance_tracked_from")
    if own:
        return date_cls.fromisoformat(str(own)[:10])
    try:
        rows = supabase.table("attendance_settings").select("tracking_start_date").eq("id", 1).execute().data or []
    except Exception:
        return None  # before migration 027: tracked throughout
    return date_cls.fromisoformat(str(rows[0]["tracking_start_date"])[:10]) if rows and rows[0].get("tracking_start_date") else None


def _day_record(supabase: Client, employee_id: int, target: date) -> Optional[dict]:
    rows = supabase.table("attendance_log").select("*").eq("employee_id", employee_id) \
        .eq("target_date", target.isoformat()).execute().data or []
    return next((r for r in rows if r.get("employee_id") == employee_id
                 and str(r.get("target_date"))[:10] == target.isoformat()), None)


def _correction(supabase: Client, request_id: int) -> dict:
    rows = supabase.table(_CORRECTIONS).select("*").eq("id", request_id).execute().data or []
    row = next((r for r in rows if r.get("id") == request_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Correction request not found.")
    return row


def _merged_times(record: Optional[dict], clock_in, clock_out):
    """The day's times if the request were applied: requested ends replace stored ones."""
    stored_in = _parse_ts(record.get("clock_in")) if record else None
    stored_out = _parse_ts(record.get("clock_out")) if record else None
    return (_parse_ts(clock_in) if clock_in else stored_in,
            _parse_ts(clock_out) if clock_out else stored_out)


@router.post("/attendance/corrections")
async def request_correction(body: CorrectionRequestIn, user = Depends(require_permission('hr:attendance:self')),
                             supabase: Client = Depends(get_supabase)):
    """
    Ask HR to correct one's own past day. Any day from one's tracked-from date
    to yesterday that an approved payroll hasn't frozen; today has the clock
    buttons.
    """
    emp = get_employee_by_user_id(supabase, user['id'])
    require_active(emp, "request an attendance correction")
    target = body.target_date
    if body.clock_in is None and body.clock_out is None:
        raise HTTPException(status_code=400, detail="Give the clock-in, the clock-out or both.")
    if target >= _sl_today():
        raise HTTPException(status_code=400, detail="Corrections are for past days. Use the clock buttons for today.")
    joined = emp.get("date_joined")
    if joined and target < date_cls.fromisoformat(str(joined)[:10]):
        raise HTTPException(status_code=400, detail="That day is before you joined.")
    tracked = _tracked_from(supabase, emp)
    if tracked and target < tracked:
        raise HTTPException(status_code=400, detail=f"Attendance is tracked from {tracked.isoformat()}; earlier days can't be corrected.")
    _refuse_if_payroll_approved(supabase, target)

    record = _day_record(supabase, emp["id"], target)
    clock_in, clock_out = _merged_times(record, body.clock_in, body.clock_out)
    _check_times(target, clock_in, clock_out)
    if record and clock_in == _parse_ts(record.get("clock_in")) and clock_out == _parse_ts(record.get("clock_out")):
        raise HTTPException(status_code=400, detail="Those are already the recorded times.")

    try:
        open_ = [r for r in (supabase.table(_CORRECTIONS).select("id, status, employee_id, target_date")
                             .eq("employee_id", emp["id"]).eq("target_date", target.isoformat()).eq("status", "Pending")
                             .execute().data or [])
                 if r.get("status") == "Pending" and r.get("employee_id") == emp["id"]]
    except Exception as e:
        if _no_corrections_table(e):
            raise _corrections_unavailable()
        raise
    if open_:
        raise HTTPException(status_code=409, detail="You already have a correction waiting for this day. Withdraw it to send a new one.")

    row = {
        "employee_id": emp["id"],
        "target_date": target.isoformat(),
        "requested_clock_in": body.clock_in.isoformat() if body.clock_in else None,
        "requested_clock_out": body.clock_out.isoformat() if body.clock_out else None,
        "original_clock_in": record.get("clock_in") if record else None,
        "original_clock_out": record.get("clock_out") if record else None,
        "reason": body.reason,
        "requested_by": str(user["id"]),
    }
    try:
        created = supabase.table(_CORRECTIONS).insert(row).execute().data or []
    except Exception as e:
        if _is_unique_violation(e):
            raise HTTPException(status_code=409, detail="You already have a correction waiting for this day. Withdraw it to send a new one.")
        raise
    request = created[0] if created else row
    await log_audit_action(supabase, user_id=user["id"], action_type="ATTENDANCE_CORRECTION_REQUEST",
                           table_name=_CORRECTIONS, old_payload=None, new_payload=request)
    return request


@router.get("/attendance/corrections/me")
async def my_corrections(user = Depends(require_permission('hr:attendance:self')), supabase: Client = Depends(get_supabase)):
    emp = get_employee_by_user_id(supabase, user['id'])
    try:
        rows = supabase.table(_CORRECTIONS).select("*").eq("employee_id", emp["id"]) \
            .order("target_date", desc=True).limit(100).execute().data or []
    except Exception as e:
        if _no_corrections_table(e):
            return []
        raise
    return [r for r in rows if r.get("employee_id") == emp["id"]]


@router.post("/attendance/corrections/{request_id}/cancel")
async def cancel_correction(request_id: int, user = Depends(require_permission('hr:attendance:self')),
                            supabase: Client = Depends(get_supabase)):
    """Withdraw one's own request while it is still waiting."""
    emp = get_employee_by_user_id(supabase, user['id'])
    req = _correction(supabase, request_id)
    if req["employee_id"] != emp["id"]:
        raise HTTPException(status_code=403, detail="You can only withdraw your own requests.")
    if req["status"] != "Pending":
        raise HTTPException(status_code=409, detail=f"This request is already {req['status'].lower()}.")
    updated = supabase.table(_CORRECTIONS).update({"status": "Cancelled"}).eq("id", request_id).execute().data or []
    await log_audit_action(supabase, user_id=user["id"], action_type="ATTENDANCE_CORRECTION_CANCEL",
                           table_name=_CORRECTIONS, old_payload=req, new_payload={"status": "Cancelled"})
    return updated[0] if updated else {**req, "status": "Cancelled"}


@router.get("/attendance/corrections")
async def list_corrections(status: Optional[str] = None, user = Depends(require_permission('hr:attendance:manage')),
                           supabase: Client = Depends(get_supabase)):
    """Requests for HR, newest day first, with the employee's name and the day's current times."""
    q = supabase.table(_CORRECTIONS).select("*, employee_profile(first_name, last_name, user_id)")
    if status:
        q = q.eq("status", status)
    try:
        fetched = q.order("target_date", desc=True).limit(300).execute().data or []
    except Exception as e:
        if _no_corrections_table(e):
            return []
        raise
    rows = [r for r in fetched if not status or r.get("status") == status]
    for r in rows:
        p = r.pop("employee_profile", None) or {}
        r["employee_name"] = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip() or f"Employee {r['employee_id']}"
        r["employee_user_id"] = p.get("user_id")
        if r.get("status") == "Pending":
            current = _day_record(supabase, r["employee_id"], date_cls.fromisoformat(str(r["target_date"])[:10]))
            r["current_clock_in"] = current.get("clock_in") if current else None
            r["current_clock_out"] = current.get("clock_out") if current else None
            r["current_locked"] = bool(current.get("is_locked")) if current else False
    return rows


async def _decide_correction(supabase: Client, user: dict, request_id: int, approve: bool, note: Optional[str]) -> dict:
    req = _correction(supabase, request_id)
    # Nobody decides their own request, as with attendance edits and leave.
    _forbid_own_record(supabase, user, req["employee_id"])
    if str(req.get("requested_by")) == str(user["id"]):
        raise HTTPException(status_code=403, detail="You can't decide a request you made.")
    if req["status"] != "Pending":
        raise HTTPException(status_code=409, detail=f"This request is already {req['status'].lower()}.")
    target = date_cls.fromisoformat(str(req["target_date"])[:10])
    note = (note or "").strip() or None

    log_id = None
    if approve:
        _refuse_if_payroll_approved(supabase, target)
        record = _day_record(supabase, req["employee_id"], target)
        clock_in, clock_out = _merged_times(record, req.get("requested_clock_in"), req.get("requested_clock_out"))
        _check_times(target, clock_in, clock_out)
        times = {
            "clock_in": clock_in.isoformat() if clock_in else None,
            "clock_out": clock_out.isoformat() if clock_out else None,
            "worked_hours": _compute_worked_hours(clock_in, clock_out),
        }
        if record:
            # A locked record stays locked: approving is HR's review.
            saved = supabase.table("attendance_log").update(times).eq("id", record["id"]).execute().data or []
            log_id = record["id"]
            await log_audit_action(supabase, user_id=user["id"], action_type="ATTENDANCE_UPDATE",
                                   table_name="attendance_log", old_payload=record,
                                   new_payload=saved[0] if saved else {**record, **times})
        else:
            new = {"employee_id": req["employee_id"], "target_date": target.isoformat(), "is_locked": False, **times}
            try:
                saved = supabase.table("attendance_log").insert(new).execute().data or []
            except Exception as e:
                if _is_unique_violation(e):
                    raise HTTPException(status_code=409, detail="A record for this day was just created. Reload and try again.")
                raise
            log_id = saved[0]["id"] if saved else None
            await log_audit_action(supabase, user_id=user["id"], action_type="ATTENDANCE_CREATE",
                                   table_name="attendance_log", old_payload=None, new_payload=saved[0] if saved else new)
    elif not note:
        raise HTTPException(status_code=400, detail="Give a reason when rejecting, so the employee knows why.")

    update = {
        "status": "Approved" if approve else "Rejected",
        "decided_by": str(user["id"]),
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "decision_note": note,
        **({"attendance_log_id": log_id} if approve else {}),
    }
    updated = supabase.table(_CORRECTIONS).update(update).eq("id", request_id).execute().data or []
    await log_audit_action(supabase, user_id=user["id"],
                           action_type="ATTENDANCE_CORRECTION_APPROVE" if approve else "ATTENDANCE_CORRECTION_REJECT",
                           table_name=_CORRECTIONS, old_payload=req, new_payload=update)
    return updated[0] if updated else {**req, **update}


@router.post("/attendance/corrections/{request_id}/approve")
async def approve_correction(request_id: int, body: CorrectionDecisionIn = CorrectionDecisionIn(),
                             user = Depends(require_permission('hr:attendance:manage')),
                             supabase: Client = Depends(get_supabase)):
    return await _decide_correction(supabase, user, request_id, True, body.note)


@router.post("/attendance/corrections/{request_id}/reject")
async def reject_correction(request_id: int, body: CorrectionDecisionIn,
                            user = Depends(require_permission('hr:attendance:manage')),
                            supabase: Client = Depends(get_supabase)):
    return await _decide_correction(supabase, user, request_id, False, body.note)


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
    # PostgREST, when the function's new signature isn't there yet.
    ("Could not find the function", 503),
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


def _is_missing_column(error: Exception) -> bool:
    text = str(error).lower()
    return "42703" in text or ("column" in text and "does not exist" in text)


def _select_with_fallback(supabase: Client, table: str, columns: str, fallback: str, **eq):
    """
    Select `columns`, or `fallback` if a column is missing because migration
    026 isn't applied yet, so the payroll page still loads in between.
    """
    def run(cols):
        q = supabase.table(table).select(cols)
        for k, v in eq.items():
            q = q.eq(k, v)
        return q.execute().data or []
    try:
        return run(columns)
    except Exception as e:
        if not _is_missing_column(e):
            raise
        return run(fallback)


def _payroll_inputs(supabase: Client, month: int, year: int) -> tuple[list[dict], dict]:
    """
    What the engine needs for a month: every employee (leavers included;
    the engine decides who is paid) and each one's approved unpaid leave
    days in the month, as (date, fraction).
    """
    employees = _select_with_fallback(
        supabase, "employee_profile",
        "id, first_name, last_name, nic, epf_number, base_salary, status, date_joined, date_left",
        "id, first_name, last_name, nic, base_salary, status, date_joined",
    )
    first, last = month_bounds(month, year)
    unpaid_types = [t["id"] for t in (supabase.table("leave_types").select("id, is_paid").execute().data or [])
                    if t.get("is_paid") is False]
    unpaid: dict[int, list] = {}
    if unpaid_types:
        requests = [r for r in (supabase.table("leave_requests").select("id, employee_id, status, leave_type_id")
                                .eq("status", "Approved").in_("leave_type_id", unpaid_types)
                                .lte("start_date", last.isoformat()).gte("end_date", first.isoformat())
                                .execute().data or [])
                    if r.get("status") == "Approved" and r.get("leave_type_id") in unpaid_types]
        by_id = {r["id"]: r for r in requests}
        if by_id:
            days = supabase.table("leave_request_days").select("request_id, leave_date, fraction") \
                .in_("request_id", list(by_id)).gte("leave_date", first.isoformat()) \
                .lte("leave_date", last.isoformat()).execute().data or []
            for d in days:
                req = by_id.get(d["request_id"])
                leave_date = date_cls.fromisoformat(str(d["leave_date"])[:10])
                if req and first <= leave_date <= last:
                    unpaid.setdefault(req["employee_id"], []).append((leave_date, Decimal(str(d["fraction"]))))
    return employees, unpaid


def _compute(supabase: Client, month: int, year: int) -> list[PayLine]:
    employees, unpaid = _payroll_inputs(supabase, month, year)
    return compute_run(employees, unpaid, month, year)


def _stored_lines(supabase: Client, run_id: int) -> list[dict]:
    rows = _select_with_fallback(
        supabase, "payroll_ledger",
        "*, employee_profile(first_name, last_name, nic, epf_number)",
        "*, employee_profile(first_name, last_name, nic)",
        run_id=run_id,
    )
    out = []
    for r in rows:
        if r.get("run_id") not in (None, run_id):
            continue
        profile = r.pop("employee_profile", None) or {}
        name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
        line = {
            "id": r.get("id"),
            "employee_id": r.get("employee_id"),
            "employee_name": name or f"Employee {r.get('employee_id')}",
            "nic": profile.get("nic"),
            "epf_number": profile.get("epf_number"),
        }
        for k in ("days_in_month", "paid_days"):
            line[k] = r.get(k)
        for k in ("basic", "nopay_days", "nopay_deduction", "gross", "epf_employee", "epf_employer", "etf", "net_payable"):
            line[k] = None if r.get(k) is None else float(r[k])
        out.append(line)
    out.sort(key=lambda line: line["employee_name"].lower())
    return out


def _month_bounds(month: int, year: int) -> tuple[str, str]:
    start = f"{year}-{month:02d}-01"
    end = f"{year+1}-01-01" if month == 12 else f"{year}-{month+1:02d}-01"
    return start, end


def _validate_month(month: int, year: int) -> None:
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        raise HTTPException(status_code=400, detail="Choose a valid month and year.")


_RUN_AMOUNTS = ("total", "gross_total", "epf_employee_total", "epf_employer_total", "etf_total", "net_total")


def _audit_run(run: dict) -> dict:
    # Amounts as decimal strings: a whole-number float like 155000.0 comes
    # back from JSONB as 155000 and would make the audit hash unverifiable
    # (see the note in create_transaction in app/api/finance.py).
    return {**run, **{k: f"{float(run[k]):.2f}" for k in _RUN_AMOUNTS if run.get(k) is not None}}


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


def _payables(supabase: Client, run: Optional[dict]) -> list[dict]:
    """The approved run's ledger entries, with whether Finance has paid each."""
    if not run:
        return []
    wanted = [("Net salaries", run.get("finance_transaction_id"), run.get("net_total")),
              ("EPF (8% + 12%)", run.get("epf_transaction_id"),
               None if run.get("epf_employee_total") is None
               else float(run["epf_employee_total"]) + float(run.get("epf_employer_total") or 0)),
              ("ETF (3%)", run.get("etf_transaction_id"), run.get("etf_total"))]
    ids = [tx for _, tx, _ in wanted if tx]
    if not ids:
        return []
    rows = supabase.table("financial_transactions").select("id, status, amount").in_("id", ids).execute().data or []
    by_id = {r["id"]: r for r in rows}
    out = []
    for label, tx, _ in wanted:
        if tx:
            row = by_id.get(tx) or {}
            out.append({"label": label, "transaction_id": tx, "status": row.get("status"),
                        "amount": None if row.get("amount") is None else float(row["amount"])})
    return out


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
    The month's run with each line's breakdown, how a draft differs from
    computing it now, the approved run's payables, and how many attendance
    records in the month are still incomplete (a warning: absences are not
    deducted yet).
    """
    _validate_month(month, year)

    runs = supabase.table("payroll_runs") \
        .select(
            "*, generator:users!payroll_runs_generated_by_fkey(email), "
            "approver:users!payroll_runs_approved_by_fkey(email)"
        ) \
        .eq("payroll_month", month).eq("payroll_year", year).execute().data or []
    run = runs[0] if runs else None
    lines = _stored_lines(supabase, run["id"]) if run else []

    start, end = _month_bounds(month, year)
    logs = supabase.table("attendance_log").select("id, clock_in, clock_out") \
        .gte("target_date", start).lt("target_date", end).execute().data or []
    incomplete = sum(1 for log in logs if not (log.get("clock_in") and log.get("clock_out")))

    payables = _payables(supabase, run)
    # Paid once every payable is: the page's "Paid in Ledger" step.
    payment_status = None
    if payables:
        statuses = {p["status"] for p in payables}
        payment_status = "Cash" if statuses == {"Cash"} else "Voided" if "Voided" in statuses else "Receivable"

    return {
        "run": run,
        "lines": lines,
        "incomplete_attendance": incomplete,
        "drift": drift(lines, _compute(supabase, month, year)) if run and run.get("status") == "Draft" else None,
        "payables": payables,
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
    Create or refresh the month's Draft from the payroll engine. Nothing
    reaches the finance ledger until approve_payroll.
    """
    _validate_month(month, year)
    block = _generate_block(month, year)
    if block:
        raise HTTPException(status_code=400, detail=block)
    lines = _compute(supabase, month, year)
    try:
        result = supabase.rpc(
            "generate_payroll_draft",
            {"p_month": month, "p_year": year, "p_user": str(user["id"]),
             "p_lines": [line.as_row() for line in lines]},
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
    Approve a Draft: freezes it and posts three payables (net salaries, EPF,
    ETF) dated the last day of the month. Refused for whoever generated it,
    and for a draft that differs from computing it now.
    """
    runs = supabase.table("payroll_runs") \
        .select("id, payroll_month, payroll_year, status, generated_by, generated_at") \
        .eq("id", run_id).execute().data or []
    if not runs:
        raise HTTPException(status_code=404, detail=f"Payroll run {run_id} not found.")
    pending = runs[0]
    if pending.get("status") == "Draft":
        month, year = pending["payroll_month"], pending["payroll_year"]
        block = _approve_block(month, year)
        if block:
            raise HTTPException(status_code=400, detail=block)
        generator = pending.get("generated_by")
        if generator and str(generator) != str(user["id"]) and _role_changed_by(supabase, user["id"], generator):
            raise HTTPException(
                status_code=403,
                detail="Your role was changed in the last 24 hours by the person who generated this payroll, "
                       "so you can't approve it. Ask another approver.",
            )
        changes = drift(_stored_lines(supabase, run_id), _compute(supabase, month, year))
        if changes:
            raise HTTPException(
                status_code=409,
                detail=f"The payroll draft for {month}/{year} is out of date: {len(changes)} "
                       f"employee{'s have' if len(changes) != 1 else ' has'} changed since it was generated. "
                       "Regenerate it before approving.",
            )
    try:
        result = supabase.rpc(
            "approve_payroll_run",
            {"p_run_id": run_id, "p_user": str(user["id"]), "p_generated_at": pending.get("generated_at")},
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


# --- PAYSLIPS ---

def _payslip_pdf(run: dict, line: dict) -> StreamingResponse:
    period = _period(run["payroll_month"], run["payroll_year"])
    try:
        pdf = generate_pdf("payslip.html", {
            "report_title": f"Payslip, {period}",
            "period": period,
            "run": run,
            "line": line,
            "draft": run.get("status") != "Approved",
            # Lines from before the engine carry net pay only.
            "legacy": line.get("gross") is None,
        })
    except PDFGenerationError as e:
        raise HTTPException(status_code=500, detail=str(e))
    name = line["employee_name"].replace(" ", "_")
    return StreamingResponse(
        iter([pdf]), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="payslip_{run["payroll_year"]}-{run["payroll_month"]:02d}_{name}.pdf"'},
    )


def _run_and_line(supabase: Client, run_id: int, employee_id: int) -> tuple[dict, dict]:
    runs = supabase.table("payroll_runs").select("*").eq("id", run_id).execute().data or []
    run = next((r for r in runs if r.get("id") == run_id), None)
    if not run:
        raise HTTPException(status_code=404, detail="Payroll run not found.")
    line = next((l for l in _stored_lines(supabase, run_id) if l["employee_id"] == employee_id), None)
    if not line:
        raise HTTPException(status_code=404, detail="That employee is not on this payroll.")
    return run, line


@router.get("/payroll/runs/{run_id}/payslips/{employee_id}")
async def get_payslip(
    run_id: int,
    employee_id: int,
    user = Depends(require_any_permission('payroll:generate', 'payroll:approve')),
    supabase: Client = Depends(get_supabase),
):
    """Anyone's payslip for HR and approvers; a draft's is marked DRAFT."""
    run, line = _run_and_line(supabase, run_id, employee_id)
    return _payslip_pdf(run, line)


@router.get("/payroll/me/payslips")
async def my_payslips(user = Depends(require_permission('hr:attendance:self')), supabase: Client = Depends(get_supabase)):
    """One's own payslips, from approved runs only."""
    emp = get_employee_by_user_id(supabase, user['id'])
    rows = supabase.table("payroll_ledger").select("*, payroll_runs(id, payroll_month, payroll_year, status, approved_at)") \
        .eq("employee_id", emp["id"]).execute().data or []
    out = []
    for r in rows:
        run = r.get("payroll_runs") or {}
        if r.get("employee_id") != emp["id"] or run.get("status") != "Approved":
            continue
        out.append({
            "run_id": run["id"], "payroll_month": run["payroll_month"], "payroll_year": run["payroll_year"],
            "approved_at": run.get("approved_at"),
            "gross": None if r.get("gross") is None else float(r["gross"]),
            "net_payable": float(r.get("net_payable") or 0),
        })
    out.sort(key=lambda p: (p["payroll_year"], p["payroll_month"]), reverse=True)
    return out


@router.get("/payroll/me/payslips/{run_id}")
async def my_payslip(run_id: int, user = Depends(require_permission('hr:attendance:self')),
                     supabase: Client = Depends(get_supabase)):
    emp = get_employee_by_user_id(supabase, user['id'])
    run, line = _run_and_line(supabase, run_id, emp["id"])
    # A draft can still change; staff see a payslip once it is approved.
    if run.get("status") != "Approved":
        raise HTTPException(status_code=404, detail="That payslip isn't available yet.")
    return _payslip_pdf(run, line)
