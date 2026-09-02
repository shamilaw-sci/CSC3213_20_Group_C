from enum import Enum

class UserRole(str, Enum):
    ADMIN = 'Admin'
    DIRECTOR = 'Director'
    HR_OFFICER = 'HR Officer'
    FINANCE_OFFICER = 'Finance Officer'
    STAFF = 'Staff'

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
    UserRole.STAFF.value: [
        Permission.HR_ATTENDANCE_SELF.value, Permission.PROGRAMS_READ.value, Permission.INVENTORY_ISSUE.value,
        Permission.RESCUE_READ.value, Permission.RESCUE_MANAGE.value
    ]
}

def has_permission(role: str, permission: str) -> bool:
    role_perms = ROLE_PERMISSIONS.get(role, [])
    return permission in role_perms
