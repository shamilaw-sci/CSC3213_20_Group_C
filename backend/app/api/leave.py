"""
Leave: types, requests, approval and entitlements (attendance rework, step 2).

Rules are in app/services/leave_rules.py (the statutory arithmetic) and
app/services/work_calendar.py (which days are working days). This module
loads rows, applies those rules and writes. Schema: db/migrations/009_leave.sql.

Who may do what:
  hr:attendance:self   request and cancel one's own leave
  leave:approve        approve/reject, request on someone's behalf, entitlements
  hr:manage            record an employee's join date
Nobody approves or rejects a request for their own leave, or one they
submitted, whatever their role.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from supabase import Client

from app.core.audit import log_audit_action
from app.core.permissions import has_permission
from app.core.security import get_current_user, require_permission
from app.core.supabase import get_supabase
from app.services.employees import require_active
from app.services.leave_rules import (
    ZERO,
    Balance,
    LeaveType,
    carry_forward,
    casual_earned_to_date,
    check_request,
    days_by_year,
    entitlement_for,
    leave_days,
)
from app.services.work_calendar import resolve_day, schedule_for

router = APIRouter()

LIVE = ("Pending", "Approved")


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class LeaveIn(BaseModel):
    leave_type_id: int
    start_date: date
    end_date: date
    half_day: Literal["none", "am", "pm"] = "none"
    reason: Optional[str] = Field(default=None, max_length=500)
    # Set only when HR files on someone's behalf (needs leave:approve).
    employee_id: Optional[int] = None


class DecisionIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


class EntitlementAdjustIn(BaseModel):
    adjustment: Decimal = Field(ge=Decimal("-365"), le=Decimal("365"))
    note: Optional[str] = Field(default=None, max_length=200)


class DateJoinedIn(BaseModel):
    date_joined: date


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def _role(user: dict) -> str:
    return (user.get("roles") or {}).get("role_name") or ""


def _d(value) -> Decimal:
    return Decimal(str(value if value is not None else 0))


def _date(value) -> date:
    return date.fromisoformat(str(value)[:10])


def _my_employee(supabase: Client, user: dict) -> dict:
    rows = supabase.table("employee_profile").select("*").eq("user_id", str(user["id"])).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="No linked employee profile found for this user.")
    return rows[0]


def _employee(supabase: Client, employee_id: int) -> dict:
    rows = supabase.table("employee_profile").select("*").eq("id", employee_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Employee not found")
    return rows[0]


def _leave_type(supabase: Client, type_id: int) -> dict:
    rows = supabase.table("leave_types").select("*").eq("id", type_id).execute().data
    if not rows or not rows[0].get("is_active", True):
        raise HTTPException(status_code=404, detail="Leave type not found")
    return rows[0]


def _as_rule_type(row: dict) -> LeaveType:
    cap = row.get("max_days_per_request")
    return LeaveType(
        name=row["name"],
        uses_balance=bool(row.get("uses_balance")),
        allow_half_day=bool(row.get("allow_half_day")),
        max_days_per_request=_d(cap) if cap is not None else None,
        first_year_rule=row.get("first_year_rule") or "none",
    )


def _working_day_checker(supabase: Client, employee_id: int, start: date, end: date):
    """is_working_day(date) for one employee over a range, from 008's tables."""
    schedules = supabase.table("work_schedules").select("*, days:work_schedule_days(*)").execute().data or []
    by_id = {s["id"]: s for s in schedules}
    default_id = next((s["id"] for s in schedules if s.get("is_default")), None)
    assignments = supabase.table("employee_schedule_assignments").select("*") \
        .eq("employee_id", employee_id).execute().data or []
    holidays = supabase.table("holidays").select("holiday_date, name, is_day_off") \
        .gte("holiday_date", start.isoformat()).lte("holiday_date", end.isoformat()).execute().data or []
    by_date: dict[str, list] = {}
    for h in holidays:
        by_date.setdefault(str(h["holiday_date"])[:10], []).append(h)

    def is_working_day(d: date) -> bool:
        schedule = by_id.get(schedule_for(employee_id, d, assignments, default_id))
        return resolve_day(d, schedule, by_date.get(d.isoformat(), [])).working

    return is_working_day


def _live_days(supabase: Client, employee_id: int, leave_type_id: Optional[int] = None,
               exclude_request: Optional[int] = None) -> list[dict]:
    """Day rows of the employee's Pending/Approved requests, with each request's status."""
    q = supabase.table("leave_requests").select("id, status, leave_type_id") \
        .eq("employee_id", employee_id).in_("status", list(LIVE))
    if leave_type_id is not None:
        q = q.eq("leave_type_id", leave_type_id)
    # Status is re-checked here as well as in the query: a cancelled or
    # rejected request counted against a balance would wrongly block leave.
    requests = [r for r in (q.execute().data or []) if r["status"] in LIVE and r["id"] != exclude_request]
    if not requests:
        return []
    status = {r["id"]: r for r in requests}
    rows = supabase.table("leave_request_days").select("*").in_("request_id", list(status)).execute().data or []
    return [
        {**r, "status": status[r["request_id"]]["status"], "leave_type_id": status[r["request_id"]]["leave_type_id"]}
        for r in rows if r["request_id"] in status
    ]


def _joined(employee: dict) -> Optional[date]:
    return _date(employee["date_joined"]) if employee.get("date_joined") else None


def _balance(supabase: Client, employee_id: int, leave_type_id: int, year: int,
             live: list[dict], rule: str = "none", joined: Optional[date] = None) -> Optional[Balance]:
    """
    `rule` and `joined` matter only for first-year casual leave, which is
    capped at what has been earned by today (casual_earned_to_date). Every
    caller that checks or shows a balance passes them, so the cap applies to
    previews, requests, approvals and the balance cards alike.
    """
    rows = supabase.table("leave_entitlements").select("*").eq("employee_id", employee_id) \
        .eq("leave_type_id", leave_type_id).eq("year", year).execute().data
    if not rows:
        return None
    e = rows[0]
    in_year = [r for r in live if _date(r["leave_date"]).year == year and r["leave_type_id"] == leave_type_id]
    return Balance(
        entitled=_d(e["entitled_days"]),
        carried_forward=_d(e.get("carried_forward")),
        adjustment=_d(e.get("adjustment")),
        approved=sum((_d(r["fraction"]) for r in in_year if r["status"] == "Approved"), ZERO),
        pending=sum((_d(r["fraction"]) for r in in_year if r["status"] == "Pending"), ZERO),
        earned_to_date=casual_earned_to_date(joined, year, date.today()) if rule == "soe_casual" else None,
    )


def _assess(supabase: Client, employee: dict, body: LeaveIn, exclude_request: Optional[int] = None) -> dict:
    """Days, per-year balances and errors for a proposed request."""
    if body.end_date < body.start_date:
        raise HTTPException(status_code=400, detail="The end date is before the start date.")
    if body.half_day != "none" and body.start_date != body.end_date:
        raise HTTPException(status_code=400, detail="A half day must start and end on the same date.")
    if (body.end_date - body.start_date).days > 366:
        raise HTTPException(status_code=400, detail="A single request can cover at most a year.")

    lt_row = _leave_type(supabase, body.leave_type_id)
    lt = _as_rule_type(lt_row)
    is_working = _working_day_checker(supabase, employee["id"], body.start_date, body.end_date)
    days = leave_days(body.start_date, body.end_date, body.half_day,
                      bool(lt_row.get("counts_calendar_days")), is_working)

    live = _live_days(supabase, employee["id"], exclude_request=exclude_request)

    # Overlap with any other live request, of any type: readable message first;
    # the database's exclusion constraint makes it hold under races too.
    clash = {r["leave_date"] for r in live}
    overlapping = sorted(str(d) for d, _ in days if d.isoformat() in clash)
    years = sorted(days_by_year(days)) or [body.start_date.year]
    joined = _joined(employee)
    balances = {y: _balance(supabase, employee["id"], body.leave_type_id, y, live, lt.first_year_rule, joined)
                for y in years}

    check = check_request(lt, days, body.half_day, balances)
    errors = list(check.errors)
    if overlapping:
        errors.insert(0, f"You already have leave requested or approved on {', '.join(overlapping[:3])}"
                         f"{' and more' if len(overlapping) > 3 else ''}.")

    return {
        "leave_type": lt_row,
        "days": [{"date": d.isoformat(), "fraction": float(f)} for d, f in days],
        "total": float(sum((f for _, f in days), ZERO)),
        "balances": {
            str(y): None if b is None else {
                "total": float(b.total), "approved": float(b.approved), "pending": float(b.pending),
                "available": float(b.available),
                "after": float(b.available - days_by_year(days).get(y, ZERO)),
            } for y, b in balances.items()
        } if lt.uses_balance else {},
        "errors": errors,
        "_days": days,
    }


def _subject(supabase: Client, user: dict, body: LeaveIn) -> dict:
    """
    The employee a request is for: oneself, or anyone for leave:approve
    holders. Never a deactivated employee, whoever is asking.
    """
    if body.employee_id is None:
        if not has_permission(_role(user), "hr:attendance:self"):
            raise HTTPException(status_code=403, detail="Insufficient permissions. Requires hr:attendance:self")
        employee = _my_employee(supabase, user)
    else:
        if not has_permission(_role(user), "leave:approve"):
            mine = supabase.table("employee_profile").select("id").eq("user_id", str(user["id"])).execute().data
            if not mine or mine[0]["id"] != body.employee_id:
                raise HTTPException(status_code=403, detail="Only HR can request leave on someone else's behalf.")
        employee = _employee(supabase, body.employee_id)
    require_active(employee, "request leave")
    return employee


def _public(assessment: dict) -> dict:
    return {k: v for k, v in assessment.items() if not k.startswith("_")}


def _audit(row: dict) -> dict:
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in row.items()}


# --------------------------------------------------------------------------
# Types and self-service
# --------------------------------------------------------------------------

@router.get("/types")
async def leave_types(user=Depends(get_current_user), supabase: Client = Depends(get_supabase)):
    return supabase.table("leave_types").select("*").eq("is_active", True).order("sort_order").execute().data or []


def _summary(supabase: Client, employee: dict, year: int) -> list[dict]:
    """Balance per balance-tracked leave type for one employee and year."""
    types = supabase.table("leave_types").select("*").eq("is_active", True).eq("uses_balance", True) \
        .order("sort_order").execute().data or []
    live = _live_days(supabase, employee["id"])
    out = []
    joined = _joined(employee)
    for t in types:
        b = _balance(supabase, employee["id"], t["id"], year, live, t.get("first_year_rule") or "none", joined)
        out.append({
            "leave_type_id": t["id"], "code": t["code"], "name": t["name"],
            "set_up": b is not None,
            **({} if b is None else {
                # entitled is the year's allowance; earned_to_date, when set,
                # is how much of it can be used yet (first-year casual).
                "entitled": float(b.entitled),
                "earned_to_date": None if b.earned_to_date is None else float(b.usable_entitlement),
                "carried_forward": float(b.carried_forward),
                "adjustment": float(b.adjustment), "total": float(b.total),
                "approved": float(b.approved), "pending": float(b.pending), "available": float(b.available),
            }),
        })
    return out


@router.get("/me")
async def my_leave(year: Optional[int] = None, user=Depends(require_permission("hr:attendance:self")),
                   supabase: Client = Depends(get_supabase)):
    employee = _my_employee(supabase, user)
    year = year or date.today().year
    requests = supabase.table("leave_requests").select("*, leave_types(name, code)") \
        .eq("employee_id", employee["id"]).order("start_date", desc=True).limit(100).execute().data or []
    return {
        "employee_id": employee["id"],
        "date_joined": employee.get("date_joined"),
        "year": year,
        "balances": _summary(supabase, employee, year),
        "requests": requests,
    }


@router.post("/preview")
async def preview(body: LeaveIn, user=Depends(get_current_user), supabase: Client = Depends(get_supabase)):
    return _public(_assess(supabase, _subject(supabase, user, body), body))


@router.post("/requests")
async def create_request(body: LeaveIn, user=Depends(get_current_user), supabase: Client = Depends(get_supabase)):
    employee = _subject(supabase, user, body)
    assessment = _assess(supabase, employee, body)
    if assessment["errors"]:
        raise HTTPException(status_code=400, detail=assessment["errors"][0])

    row = {
        "employee_id": employee["id"],
        "leave_type_id": body.leave_type_id,
        "start_date": body.start_date.isoformat(),
        "end_date": body.end_date.isoformat(),
        "half_day": body.half_day,
        "days": assessment["total"],
        "reason": body.reason,
        "requested_by": str(user["id"]),
    }
    try:
        created = supabase.table("leave_requests").insert(row).execute().data
    except Exception as e:
        if "leave_requests_no_overlap" in str(e) or "23P01" in str(e):
            raise HTTPException(status_code=409, detail="This overlaps leave already requested or approved.")
        raise
    request = created[0]

    day_rows = [{"request_id": request["id"], "leave_date": d.isoformat(), "fraction": float(f)}
                for d, f in assessment["_days"]]
    try:
        supabase.table("leave_request_days").insert(day_rows).execute()
    except Exception:
        # Without its days the request would be invisible to balances and
        # attendance, so it is withdrawn rather than left half-written.
        supabase.table("leave_requests").delete().eq("id", request["id"]).execute()
        raise HTTPException(status_code=500, detail="The request could not be saved. Please try again.")

    await log_audit_action(supabase, user_id=user["id"], action_type="LEAVE_REQUEST",
                           table_name="leave_requests", old_payload=None, new_payload=_audit(request))
    return request


@router.post("/requests/{request_id}/cancel")
async def cancel_request(request_id: int, user=Depends(get_current_user), supabase: Client = Depends(get_supabase)):
    rows = supabase.table("leave_requests").select("*").eq("id", request_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Leave request not found")
    req = rows[0]

    is_hr = has_permission(_role(user), "leave:approve")
    mine = supabase.table("employee_profile").select("id").eq("user_id", str(user["id"])).execute().data
    is_owner = bool(mine) and mine[0]["id"] == req["employee_id"]
    if not (is_hr or is_owner):
        raise HTTPException(status_code=403, detail="You can only cancel your own leave.")
    if req["status"] not in LIVE:
        raise HTTPException(status_code=409, detail=f"This request is already {req['status'].lower()}.")
    # Staff may withdraw approved leave only before it starts; after that,
    # changing what happened is HR's call.
    if req["status"] == "Approved" and not is_hr and _date(req["start_date"]) <= date.today():
        raise HTTPException(status_code=409, detail="Approved leave that has started can only be changed by HR.")

    updated = supabase.table("leave_requests").update({"status": "Cancelled"}).eq("id", request_id).execute().data
    await log_audit_action(supabase, user_id=user["id"], action_type="LEAVE_CANCEL",
                           table_name="leave_requests", old_payload=_audit(req), new_payload={"status": "Cancelled"})
    return updated[0] if updated else {**req, "status": "Cancelled"}


# --------------------------------------------------------------------------
# Approval
# --------------------------------------------------------------------------

def _forbid_own(supabase: Client, user: dict, req: dict) -> None:
    """Nobody decides a request for their own leave, or one they filed."""
    if str(req.get("requested_by")) == str(user["id"]):
        raise HTTPException(status_code=403, detail="You cannot decide a leave request you submitted yourself.")
    mine = supabase.table("employee_profile").select("id").eq("user_id", str(user["id"])).execute().data
    if mine and mine[0]["id"] == req["employee_id"]:
        raise HTTPException(status_code=403, detail="You cannot approve or reject your own leave.")


@router.get("/requests")
async def list_requests(status: Optional[str] = None, year: Optional[int] = None,
                        user=Depends(require_permission("leave:approve")),
                        supabase: Client = Depends(get_supabase)):
    q = supabase.table("leave_requests").select(
        "*, leave_types(name, code), employee_profile(first_name, last_name)"
    )
    if status:
        q = q.eq("status", status)
    if year:
        q = q.lte("start_date", f"{year}-12-31").gte("end_date", f"{year}-01-01")
    rows = q.order("start_date", desc=True).limit(500).execute().data or []
    for r in rows:
        p = r.get("employee_profile") or {}
        r["employee_name"] = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
    return rows


async def _decide(supabase: Client, user: dict, request_id: int, approve: bool, note: Optional[str]) -> dict:
    rows = supabase.table("leave_requests").select("*").eq("id", request_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Leave request not found")
    req = rows[0]
    _forbid_own(supabase, user, req)
    if req["status"] != "Pending":
        raise HTTPException(status_code=409, detail=f"This request is already {req['status'].lower()}.")

    if approve:
        # Balances may have moved since submission (another approval, an HR
        # adjustment). Approved leave alone must fit; pending ones do not
        # block, since this is the one being decided.
        lt_row = _leave_type(supabase, req["leave_type_id"])
        if lt_row.get("uses_balance"):
            employee = _employee(supabase, req["employee_id"])
            live = _live_days(supabase, req["employee_id"], exclude_request=request_id)
            own = supabase.table("leave_request_days").select("*").eq("request_id", request_id).execute().data or []
            for year, wanted in sorted(days_by_year([(_date(r["leave_date"]), _d(r["fraction"])) for r in own]).items()):
                b = _balance(supabase, req["employee_id"], req["leave_type_id"], year, live,
                             lt_row.get("first_year_rule") or "none", _joined(employee))
                if b is None or wanted > b.remaining:
                    have = ZERO if b is None else b.remaining
                    raise HTTPException(status_code=409, detail=(
                        f"Approving would exceed the {year} {lt_row['name'].lower()} balance: "
                        f"{have.normalize()} days left, request needs {wanted.normalize()}."))
    elif not (note and note.strip()):
        raise HTTPException(status_code=400, detail="Give a reason when rejecting, so the employee knows why.")

    update = {
        "status": "Approved" if approve else "Rejected",
        "decided_by": str(user["id"]),
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "decision_note": note,
    }
    updated = supabase.table("leave_requests").update(update).eq("id", request_id).execute().data
    await log_audit_action(supabase, user_id=user["id"], action_type="LEAVE_APPROVE" if approve else "LEAVE_REJECT",
                           table_name="leave_requests", old_payload=_audit(req), new_payload=update)
    return updated[0] if updated else {**req, **update}


@router.post("/requests/{request_id}/approve")
async def approve_request(request_id: int, body: DecisionIn = DecisionIn(),
                          user=Depends(require_permission("leave:approve")),
                          supabase: Client = Depends(get_supabase)):
    return await _decide(supabase, user, request_id, True, body.note)


@router.post("/requests/{request_id}/reject")
async def reject_request(request_id: int, body: DecisionIn,
                         user=Depends(require_permission("leave:approve")),
                         supabase: Client = Depends(get_supabase)):
    return await _decide(supabase, user, request_id, False, body.note)


# --------------------------------------------------------------------------
# Entitlements
# --------------------------------------------------------------------------

def _active_employees(supabase: Client) -> list[dict]:
    rows = supabase.table("employee_profile").select("id, first_name, last_name, status, date_joined") \
        .order("first_name").execute().data or []
    return [e for e in rows if (e.get("status") or "Active") == "Active"]


def _name(e: dict) -> str:
    return f"{e.get('first_name', '')} {e.get('last_name', '')}".strip()


@router.get("/entitlements")
async def list_entitlements(year: int, user=Depends(require_permission("leave:approve")),
                            supabase: Client = Depends(get_supabase)):
    employees = _active_employees(supabase)
    out = []
    for e in employees:
        out.append({
            "employee_id": e["id"],
            "employee_name": _name(e),
            "date_joined": e.get("date_joined"),
            "balances": _summary(supabase, e, year),
        })
    entitlement_rows = supabase.table("leave_entitlements").select("id, employee_id, leave_type_id, note") \
        .eq("year", year).execute().data or []
    ids = {(r["employee_id"], r["leave_type_id"]): r for r in entitlement_rows}
    for row in out:
        for b in row["balances"]:
            hit = ids.get((row["employee_id"], b["leave_type_id"]))
            b["entitlement_id"] = hit["id"] if hit else None
            b["note"] = hit.get("note") if hit else None
    return {
        "year": year,
        "employees": out,
        "needs_date_joined": [{"employee_id": e["id"], "employee_name": _name(e)}
                              for e in employees if not e.get("date_joined")],
    }


@router.post("/entitlements/generate")
async def generate_entitlements(year: int, user=Depends(require_permission("leave:approve")),
                                supabase: Client = Depends(get_supabase)):
    """
    Create the year's missing entitlement rows from the rules. Existing rows,
    including any HR has adjusted, are never touched. Employees whose
    entitlement depends on an unknown join date get no row for that type and
    are listed, so HR can fill the date in and generate again.
    """
    if not 2000 <= year <= 2100:
        raise HTTPException(status_code=400, detail="Choose a year between 2000 and 2100.")
    types = supabase.table("leave_types").select("*").eq("is_active", True).eq("uses_balance", True).execute().data or []
    existing = supabase.table("leave_entitlements").select("employee_id, leave_type_id") \
        .eq("year", year).execute().data or []
    have = {(r["employee_id"], r["leave_type_id"]) for r in existing}

    created, flagged = [], {}
    for e in _active_employees(supabase):
        joined = _date(e["date_joined"]) if e.get("date_joined") else None
        for t in types:
            if (e["id"], t["id"]) in have:
                continue
            days = entitlement_for(t.get("first_year_rule") or "none", joined, year, t.get("default_days"))
            if days is None:
                flagged.setdefault(e["id"], {"employee_id": e["id"], "employee_name": _name(e), "leave_types": []})
                flagged[e["id"]]["leave_types"].append(t["name"])
                continue

            carried = ZERO
            if _d(t.get("carry_forward_max")) > 0:
                live = _live_days(supabase, e["id"], leave_type_id=t["id"])
                previous = _balance(supabase, e["id"], t["id"], year - 1, live)
                if previous is not None:
                    carried = carry_forward(previous.remaining, t.get("carry_forward_max"))

            created.append({
                "employee_id": e["id"], "leave_type_id": t["id"], "year": year,
                "entitled_days": float(days), "carried_forward": float(carried),
                "updated_by": str(user["id"]),
            })

    if created:
        supabase.table("leave_entitlements").insert(created).execute()

    await log_audit_action(supabase, user_id=user["id"], action_type="LEAVE_ENTITLEMENTS_GENERATE",
                           table_name="leave_entitlements", old_payload=None,
                           new_payload={"year": year, "created": len(created),
                                        "needs_date_joined": [f["employee_id"] for f in flagged.values()]})
    return {"year": year, "created": len(created), "skipped_existing": len(have),
            "needs_date_joined": list(flagged.values())}


@router.put("/entitlements/{entitlement_id}")
async def adjust_entitlement(entitlement_id: int, body: EntitlementAdjustIn,
                             user=Depends(require_permission("leave:approve")),
                             supabase: Client = Depends(get_supabase)):
    rows = supabase.table("leave_entitlements").select("*").eq("id", entitlement_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Entitlement not found")
    update = {"adjustment": float(body.adjustment), "note": body.note, "updated_by": str(user["id"]),
              "updated_at": datetime.now(timezone.utc).isoformat()}
    saved = supabase.table("leave_entitlements").update(update).eq("id", entitlement_id).execute().data
    await log_audit_action(supabase, user_id=user["id"], action_type="LEAVE_ENTITLEMENT_ADJUST",
                           table_name="leave_entitlements", old_payload=_audit(rows[0]),
                           new_payload={**update, "adjustment": str(body.adjustment)})
    return saved[0] if saved else {**rows[0], **update}


@router.patch("/employees/{employee_id}/date-joined")
async def set_date_joined(employee_id: int, body: DateJoinedIn, user=Depends(require_permission("hr:manage")),
                          supabase: Client = Depends(get_supabase)):
    employee = _employee(supabase, employee_id)
    if body.date_joined > date.today() + timedelta(days=366):
        raise HTTPException(status_code=400, detail="That join date is more than a year away.")
    supabase.table("employee_profile").update({"date_joined": body.date_joined.isoformat()}) \
        .eq("id", employee_id).execute()
    await log_audit_action(supabase, user_id=user["id"], action_type="EMPLOYEE_DATE_JOINED",
                           table_name="employee_profile",
                           old_payload={"date_joined": employee.get("date_joined")},
                           new_payload={"date_joined": body.date_joined.isoformat()})
    return {"employee_id": employee_id, "date_joined": body.date_joined.isoformat()}
