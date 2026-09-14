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

# NOTE: Must stay in sync with frontend/src/lib/permissions.ts
ROLE_PERMISSIONS = {
    UserRole.ADMIN.value: [
        Permission.HR_MANAGE.value, Permission.HR_ATTENDANCE_SELF.value, Permission.HR_ATTENDANCE_MANAGE.value,
        Permission.PAYROLL_GENERATE.value, Permission.PAYROLL_APPROVE.value, Permission.FINANCE_READ.value,
        Permission.FINANCE_WRITE.value, Permission.FINANCE_RESTRICTED_OVERRIDE.value,
        Permission.INVENTORY_READ.value, Permission.INVENTORY_ISSUE.value,
        Permission.PROGRAMS_READ.value, Permission.PROGRAMS_MANAGE.value, Permission.ADMIN_USERS.value, Permission.AUDIT_READ.value,
        Permission.RESCUE_READ.value, Permission.RESCUE_MANAGE.value, Permission.RESCUE_ASSIGN.value
    ],
    UserRole.DIRECTOR.value: [
        Permission.FINANCE_READ.value, Permission.PAYROLL_APPROVE.value, Permission.PROGRAMS_READ.value,
        Permission.INVENTORY_READ.value, Permission.AUDIT_READ.value,
        Permission.RESCUE_READ.value, Permission.RESCUE_ASSIGN.value
    ],
    UserRole.HR_OFFICER.value: [
        Permission.HR_MANAGE.value, Permission.HR_ATTENDANCE_MANAGE.value, Permission.HR_ATTENDANCE_SELF.value,
        Permission.PAYROLL_GENERATE.value,
        Permission.RESCUE_READ.value, Permission.RESCUE_ASSIGN.value
    ],
    UserRole.FINANCE_OFFICER.value: [
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
    UserRole.OPERATIONS_LEAD.value: [
        Permission.HR_ATTENDANCE_SELF.value,
        Permission.INVENTORY_READ.value, Permission.INVENTORY_ISSUE.value,
        Permission.PROGRAMS_READ.value, Permission.PROGRAMS_MANAGE.value,
        Permission.RESCUE_READ.value, Permission.RESCUE_MANAGE.value
    ],
    # The default role for every new signup, and the field staff who work rescue
    # cases. This set is carried over verbatim from the former 'Staff' key: the
    # grants were always correct, but the name matched no role any user could
    # hold, so in practice this role had no permissions at all.
    UserRole.GENERAL_STAFF.value: [
        Permission.HR_ATTENDANCE_SELF.value, Permission.PROGRAMS_READ.value, Permission.INVENTORY_ISSUE.value,
        Permission.RESCUE_READ.value, Permission.RESCUE_MANAGE.value
    ],
    # Technical administration, not business access. Manages accounts and reads
    # the audit chain; has no reason to read salaries, the ledger or case data,
    # so separation of duties keeps those out. Narrower than Admin on purpose —
    # the two are not interchangeable despite the admin login accepting both.
    UserRole.SYSTEM_ADMINISTRATOR.value: [
        Permission.ADMIN_USERS.value, Permission.AUDIT_READ.value
    ]
}

def has_permission(role: str, permission: str) -> bool:
    role_perms = ROLE_PERMISSIONS.get(role, [])
    return permission in role_perms
