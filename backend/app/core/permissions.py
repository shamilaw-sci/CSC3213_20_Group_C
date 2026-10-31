from enum import Enum

# These names are the authorization keys: has_permission() looks a role up by
# the exact string stored in roles.role_name, so a name here that no row uses
# grants nothing to anybody. They must match the seven roles the application
# actually issues — see the role pickers in frontend admin and hr/employees
# pages, which are the source of truth for role ids 1-7.
class UserRole(str, Enum):
    ADMIN = 'Admin'
    DIRECTOR = 'Director'
    FINANCE_OFFICER = 'Finance Officer'
    HR_OFFICER = 'HR Officer'
    OPERATIONS_LEAD = 'Operations Lead'
    GENERAL_STAFF = 'General Staff'
    SYSTEM_ADMINISTRATOR = 'System Administrator'

class Permission(str, Enum):
    HR_MANAGE = 'hr:manage'
    HR_ATTENDANCE_SELF = 'hr:attendance:self'
    HR_ATTENDANCE_MANAGE = 'hr:attendance:manage'
    # See everyone's attendance (the monthly grid) without changing it.
    # Director, for oversight (confirmed 2026-10-31); HR edits via MANAGE.
    HR_ATTENDANCE_READ = 'hr:attendance:read'
    # Approve or reject leave requests and manage entitlements. HR Officer and
    # Admin (confirmed 2026-10-29). Holding it never lets anyone approve their
    # own request: app/api/leave.py refuses that regardless of role.
    LEAVE_APPROVE = 'leave:approve'
    PAYROLL_GENERATE = 'payroll:generate'
    PAYROLL_APPROVE = 'payroll:approve'
    FINANCE_READ = 'finance:read'
    FINANCE_WRITE = 'finance:write'
    # Authorizes spending a restricted (earmarked) program's funds past what was
    # raised for it. Deliberately NOT held by Finance Officer: that role creates
    # the expenses, and letting it clear its own shortfall would remove the only
    # second pair of eyes on the decision. Director is excluded for a mechanical
    # reason rather than a policy one — Director has no finance:write, so it
    # cannot reach POST /transactions where this is enforced, and granting
    # finance:write to make the override reachable would also hand Director
    # blanket create/edit/void power over the ledger.
    FINANCE_RESTRICTED_OVERRIDE = 'finance:restricted:override'
    INVENTORY_READ = 'inventory:read'
    INVENTORY_ISSUE = 'inventory:issue'
    PROGRAMS_READ = 'programs:read'
    PROGRAMS_MANAGE = 'programs:manage'
    ADMIN_USERS = 'admin:users'
    AUDIT_READ = 'audit:read'
    RESCUE_READ = 'rescue:read'
    RESCUE_MANAGE = 'rescue:manage'
    RESCUE_ASSIGN = 'rescue:assign'
    # Volunteers are non-staff with no login, so these govern access to other
    # people's personal contact details rather than to internal records —
    # which is why the read grant is narrower than it looks.
    VOLUNTEERS_READ = 'volunteers:read'
    # Vetting: approving or rejecting an application, and deactivating someone.
    # A judgement about a person.
    VOLUNTEERS_APPROVE = 'volunteers:approve'
    # Operations: creating shifts, assigning volunteers to shifts/cases/
    # programs, removing assignments. A judgement about scheduling.
    #
    # Split from APPROVE for the same reason rescue:manage is split from
    # rescue:assign — different decisions, different risk, plausibly different
    # people. Copying a volunteer's personal link is gated on APPROVE *or*
    # ASSIGN: sharing a link is contact, not vetting or scheduling, and gating
    # it on either alone creates the dead end where an HR Officer approves
    # someone and then cannot reach them.
    VOLUNTEERS_ASSIGN = 'volunteers:assign'

# NOTE: Must stay in sync with frontend/src/lib/permissions.ts
ROLE_PERMISSIONS = {
    UserRole.ADMIN.value: [
        Permission.HR_MANAGE.value, Permission.HR_ATTENDANCE_SELF.value, Permission.HR_ATTENDANCE_MANAGE.value,
        Permission.LEAVE_APPROVE.value, Permission.HR_ATTENDANCE_READ.value,
        Permission.PAYROLL_GENERATE.value, Permission.PAYROLL_APPROVE.value, Permission.FINANCE_READ.value,
        Permission.FINANCE_WRITE.value, Permission.FINANCE_RESTRICTED_OVERRIDE.value,
        Permission.INVENTORY_READ.value, Permission.INVENTORY_ISSUE.value,
        Permission.PROGRAMS_READ.value, Permission.PROGRAMS_MANAGE.value, Permission.ADMIN_USERS.value, Permission.AUDIT_READ.value,
        Permission.RESCUE_READ.value, Permission.RESCUE_MANAGE.value, Permission.RESCUE_ASSIGN.value,
        Permission.VOLUNTEERS_READ.value, Permission.VOLUNTEERS_APPROVE.value, Permission.VOLUNTEERS_ASSIGN.value
    ],
    # volunteers:approve but not :assign — oversight of who the organisation
    # takes on, without running the shift rota. Consistent with the rest of this
    # role's grants, which are read-heavy plus payroll:approve: Director signs
    # off on people and money, it does not do the scheduling.
    UserRole.DIRECTOR.value: [
        # Self-service (clock in/out, own schedule, request own leave): staff
        # in this role are employees too (confirmed 2026-10-29). It reaches
        # only the holder's own records, so it adds no business-data access.
        Permission.HR_ATTENDANCE_SELF.value, Permission.HR_ATTENDANCE_READ.value,
        Permission.FINANCE_READ.value, Permission.PAYROLL_APPROVE.value, Permission.PROGRAMS_READ.value,
        Permission.INVENTORY_READ.value, Permission.AUDIT_READ.value,
        Permission.RESCUE_READ.value, Permission.RESCUE_ASSIGN.value,
        Permission.VOLUNTEERS_READ.value, Permission.VOLUNTEERS_APPROVE.value
    ],
    # Vetting and onboarding a person is squarely HR, so this role approves
    # applications. It does not staff shifts — that is operations.
    UserRole.HR_OFFICER.value: [
        Permission.HR_MANAGE.value, Permission.HR_ATTENDANCE_MANAGE.value, Permission.HR_ATTENDANCE_SELF.value,
        Permission.LEAVE_APPROVE.value,
        Permission.PAYROLL_GENERATE.value,
        Permission.RESCUE_READ.value, Permission.RESCUE_ASSIGN.value,
        Permission.VOLUNTEERS_READ.value, Permission.VOLUNTEERS_APPROVE.value
    ],
    UserRole.FINANCE_OFFICER.value: [
        # Self-service (clock in/out, own schedule, request own leave): staff
        # in this role are employees too (confirmed 2026-10-29). It reaches
        # only the holder's own records, so it adds no business-data access.
        Permission.HR_ATTENDANCE_SELF.value,
        Permission.FINANCE_READ.value, Permission.FINANCE_WRITE.value, Permission.PAYROLL_GENERATE.value,
        Permission.INVENTORY_READ.value,
        # Not a widening of what this role can see: GET /finance/transactions
        # already returns programs(program_name) under finance:read, so a
        # Finance Officer reads program names throughout the ledger. Without
        # this they were the one role that could not list programs, so the
        # program picker on the transaction form rendered bare numeric ids —
        # and this is the role that books program-linked expenses. Choosing
        # the wrong program misdirects a restricted-fund drawdown.
        Permission.PROGRAMS_READ.value
    ],
    # Clinic and field operations. Programs and inventory per the RBAC table on
    # the support page ("Clinic management and program tracking"); programs:manage
    # because leading a clinic means running the programs, not just watching them.
    # This is the first role other than Admin to hold programs:manage.
    #
    # Deliberately NOT rescue:assign. An Operations Lead is arguably the most
    # natural dispatcher in the org, but handing work to another person stays
    # with Admin/Director/HR Officer for now. Self-assignment is unaffected:
    # update_case_status allows it regardless of this permission.
    #
    # volunteers:assign but not :approve — this is the role that runs the
    # clinics volunteers are staffed onto, so it owns the rota. Whether someone
    # is taken on at all stays a vetting decision with HR/Director/Admin.
    UserRole.OPERATIONS_LEAD.value: [
        Permission.HR_ATTENDANCE_SELF.value,
        Permission.INVENTORY_READ.value, Permission.INVENTORY_ISSUE.value,
        Permission.PROGRAMS_READ.value, Permission.PROGRAMS_MANAGE.value,
        Permission.RESCUE_READ.value, Permission.RESCUE_MANAGE.value,
        Permission.VOLUNTEERS_READ.value, Permission.VOLUNTEERS_ASSIGN.value
    ],
    # The default role for every new signup, and the field staff who work rescue
    # cases. This set is carried over verbatim from the former 'Staff' key: the
    # grants were always correct, but the name matched no role any user could
    # hold, so in practice this role had no permissions at all.
    #
    # Deliberately NO volunteers:read. Field staff working a clinic would find
    # the roster useful, but this is the role every new account gets by default,
    # so granting it would expose the names, emails and phone numbers of
    # non-employees to anyone who registers. Default-deny on third-party PII.
    # If "who is coming to my clinic" turns out to be a real need, a shift-level
    # view is the narrower answer, not roster access.
    UserRole.GENERAL_STAFF.value: [
        Permission.HR_ATTENDANCE_SELF.value, Permission.PROGRAMS_READ.value, Permission.INVENTORY_ISSUE.value,
        Permission.RESCUE_READ.value, Permission.RESCUE_MANAGE.value
    ],
    # Technical administration, not business access. Manages accounts and reads
    # the audit chain; has no reason to read salaries, the ledger or case data,
    # so separation of duties keeps those out. Narrower than Admin on purpose —
    # the two are not interchangeable despite the admin login accepting both.
    #
    # No volunteer permissions, for exactly that reason. A volunteer roster is
    # business data holding third-party contact details; granting it here would
    # make System Administrator the only role that breaches its own stated
    # boundary. A sysadmin who genuinely needs to act on volunteers should use
    # an Admin account, which is the visible, auditable way to do it.
    UserRole.SYSTEM_ADMINISTRATOR.value: [
        Permission.ADMIN_USERS.value, Permission.AUDIT_READ.value
    ]
}

def has_permission(role: str, permission: str) -> bool:
    role_perms = ROLE_PERMISSIONS.get(role, [])
    return permission in role_perms
