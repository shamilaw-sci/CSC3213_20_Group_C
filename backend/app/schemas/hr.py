from pydantic import BaseModel, ConfigDict, field_validator
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List

class RoleBase(BaseModel):
    role_name: str

class Role(RoleBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class EmployeeProfileBase(BaseModel):
    first_name: str
    last_name: str
    nic: str
    base_salary: float
    status: str = "Active"
    user_id: Optional[str] = None

class EmployeeProfileCreate(EmployeeProfileBase):
    pass

class EmployeeProfile(EmployeeProfileBase):
    id: int
    # Read-only here: set through PATCH /leave/employees/{id}/date-joined.
    # Kept off EmployeeProfileBase on purpose, so the existing employee
    # create/update forms, which do not send it, cannot wipe it.
    date_joined: Optional[date] = None
    model_config = ConfigDict(from_attributes=True)

# Sri Lanka time, no daylight saving (same constant as COLOMBO in
# app/services/work_calendar.py).
SRI_LANKA = timezone(timedelta(hours=5, minutes=30))


def _as_sri_lanka_time(value: Optional[datetime]) -> Optional[datetime]:
    """
    A clock time with no timezone is a Sri Lanka wall-clock time. HR types
    times like 08:30 and the forms sent them without an offset, so Postgres
    stored them as 08:30 UTC and they read back as 14:00. Self-service
    clock-in already records real UTC and is unaffected.
    """
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=SRI_LANKA)
    return value


class AttendanceLogBase(BaseModel):
    employee_id: int
    target_date: date
    clock_in: Optional[datetime] = None
    clock_out: Optional[datetime] = None
    worked_hours: Optional[float] = None
    is_locked: bool = False

    @field_validator("clock_in", "clock_out")
    @classmethod
    def _sri_lanka_time(cls, value):
        return _as_sri_lanka_time(value)

class AttendanceLogCreate(AttendanceLogBase):
    pass

class AttendanceLog(AttendanceLogBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class PayrollLedgerBase(BaseModel):
    employee_id: int
    payroll_month: int
    payroll_year: int
    net_payable: float

class PayrollLedger(PayrollLedgerBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class AttendanceLogUpdate(BaseModel):
    clock_in: Optional[datetime] = None
    clock_out: Optional[datetime] = None

    @field_validator("clock_in", "clock_out")
    @classmethod
    def _sri_lanka_time(cls, value):
        return _as_sri_lanka_time(value)