import re
from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional, List

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

# Sri Lankan NIC: the old 9 digits plus V or X, or the 12-digit number issued
# since 2016.
NIC_PATTERN = re.compile(r"^(\d{9}[VX]|\d{12})$")

EmployeeStatus = Literal["Active", "Inactive"]


def _clean_nic(value: str) -> str:
    nic = value.strip().upper()
    if not NIC_PATTERN.match(nic):
        raise ValueError("NIC must be 9 digits followed by V or X, or 12 digits")
    return nic


def _clean_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError("must not be blank")
    if len(name) > 100:  # VARCHAR(100)
        raise ValueError("must be 100 characters or fewer")
    return name


# The rules below apply to what is written, not to EmployeeProfileBase:
# rows created before them (demo NICs like DEMO5V among them) must still
# read back through EmployeeProfile.
class EmployeeProfileCreate(EmployeeProfileBase):
    base_salary: float = Field(gt=0)
    status: EmployeeStatus = "Active"

    _names = field_validator("first_name", "last_name")(_clean_name)
    _nic = field_validator("nic")(_clean_nic)


class EmployeeProfileUpdate(BaseModel):
    """
    A partial update: only the fields sent are written. It used to take the
    full create model, whose user_id defaults to None, so any edit that left
    user_id out unlinked the employee from their login and they could no
    longer clock in.
    """
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    nic: Optional[str] = None
    base_salary: Optional[float] = Field(default=None, gt=0)
    status: Optional[EmployeeStatus] = None
    user_id: Optional[str] = None

    # Leaving a field out keeps it; sending null for one of these is refused
    # (the columns are NOT NULL). Only user_id may be cleared, to unlink.
    @field_validator("first_name", "last_name", "nic", "base_salary", "status", mode="before")
    @classmethod
    def _not_null(cls, value):
        if value is None:
            raise ValueError("cannot be cleared")
        return value

    _names = field_validator("first_name", "last_name")(_clean_name)
    _nic = field_validator("nic")(_clean_nic)

class EmployeeProfile(EmployeeProfileBase):
    id: int
    # Read-only here: set through PATCH /leave/employees/{id}/date-joined.
    # Kept off EmployeeProfileBase on purpose, so the existing employee
    # create/update forms, which do not send it, cannot wipe it.
    date_joined: Optional[date] = None
    # The linked login's email, filled in by GET /hr/employees only.
    login_email: Optional[str] = None
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