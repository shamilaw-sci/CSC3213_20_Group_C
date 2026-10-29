// The seven roles the application actually issues (role ids 1-7, per the role
// pickers in the admin and hr/employees pages). These strings are authorization
// keys matched against user.role, so a name here that no user can hold grants
// nothing — which is exactly what the former 'Staff' entry did.
export type UserRole =
  | 'Admin'
  | 'Director'
  | 'Finance Officer'
  | 'HR Officer'
  | 'Operations Lead'
  | 'General Staff'
  | 'System Administrator';

export type Permission = 
  | 'hr:manage'
  | 'hr:attendance:self'
  | 'hr:attendance:manage'
  // Approve leave and manage entitlements, never for the approver themselves
  | 'leave:approve'
  | 'payroll:generate'
  | 'payroll:approve'
  | 'finance:read'
  | 'finance:write'
  | 'finance:restricted:override'
  | 'inventory:read'
  | 'inventory:issue'
  | 'programs:read'
  | 'programs:manage'
  | 'admin:users'
  | 'audit:read'
  | 'rescue:read'
  | 'rescue:manage'
  | 'rescue:assign'
  // Volunteers are non-staff with no login. volunteers:read governs access to
  // their personal contact details, :approve is the vetting decision (accept or
  // reject an application), :assign is the scheduling one (shifts, cases,
  // programs). Split for the same reason rescue:manage and rescue:assign are.
  // Copying a personal volunteer link is gated on :approve OR :assign, since
  // sharing a link is contact rather than vetting or scheduling.
  //
  // NOTE: no apostrophes in this block. test_restricted_funds.py parses this
  // union with a regex on single-quoted strings, so a stray apostrophe in a
  // comment silently corrupts what it thinks the backend declared.
  | 'volunteers:read'
  | 'volunteers:approve'
  | 'volunteers:assign';

// NOTE: Must stay in sync with backend/app/core/permissions.py
export const ROLE_PERMISSIONS: Record<UserRole, Permission[]> = {
  Admin: [
    'hr:manage', 'hr:attendance:self', 'hr:attendance:manage', 'leave:approve',
    'payroll:generate', 'payroll:approve', 'finance:read',
    'finance:write', 'finance:restricted:override',
    'inventory:read', 'inventory:issue',
    'programs:read', 'programs:manage', 'admin:users', 'audit:read',
    'rescue:read', 'rescue:manage', 'rescue:assign',
    'volunteers:read', 'volunteers:approve', 'volunteers:assign'
  ],
  // volunteers:approve but not :assign — oversight of who the organisation
  // takes on, without running the shift rota. Consistent with this role's
  // read-heavy grants plus payroll:approve: it signs off on people and money,
  // it does not do the scheduling.
  Director: [
    // Self-service: own attendance, schedule and leave only (confirmed 2026-10-29).
    'hr:attendance:self',
    'finance:read', 'payroll:approve', 'programs:read',
    'inventory:read', 'audit:read', 'rescue:read' , 'rescue:assign',
    'volunteers:read', 'volunteers:approve'
  ],
  // Vetting and onboarding a person is squarely HR, so this role approves
  // volunteer applications. It does not staff shifts — that is operations.
  'HR Officer': [
    'hr:manage', 'hr:attendance:manage', 'hr:attendance:self', 'leave:approve',
    'payroll:generate' , 'rescue:read', 'rescue:assign',
    'volunteers:read', 'volunteers:approve'
  ],
  'Finance Officer': [
    // Self-service: own attendance, schedule and leave only (confirmed 2026-10-29).
    'hr:attendance:self',
    'finance:read', 'finance:write', 'payroll:generate',
    'inventory:read', 'programs:read'
  ],
  // Clinic and field operations, per the RBAC table on the support page.
  // programs:manage because leading a clinic means running the programs;
  // this is the first role other than Admin to hold it. Deliberately no
  // rescue:assign — handing work to another person stays with
  // Admin/Director/HR Officer. Self-assignment is unaffected.
  //
  // volunteers:assign but not :approve — this role runs the clinics volunteers
  // are staffed onto, so it owns the rota. Whether someone is taken on at all
  // stays a vetting decision with HR/Director/Admin.
  'Operations Lead': [
    'hr:attendance:self', 'inventory:read', 'inventory:issue',
    'programs:read', 'programs:manage',
    'rescue:read', 'rescue:manage',
    'volunteers:read', 'volunteers:assign'
  ],
  // Default role for every new signup, and the field staff who work rescue
  // cases. Carried over verbatim from the former 'Staff' key, which matched no
  // role any user could hold and so granted nothing in practice.
  //
  // Deliberately NO volunteers:read. This is the role every new account gets,
  // so granting it would expose non-employees' names, emails and phone numbers
  // to anyone who registers. Default-deny on third-party PII.
  'General Staff': [
    'hr:attendance:self', 'programs:read', 'inventory:issue',
    'rescue:read', 'rescue:manage'
  ],
  // Technical administration, not business access: accounts and the audit
  // chain, but no payroll, ledger or case data. Narrower than Admin on
  // purpose, despite the admin login accepting both.
  //
  // No volunteer permissions for that same reason — a roster of third-party
  // contact details is business data, and granting it here would make this the
  // only role that breaches its own stated boundary.
  'System Administrator': [
    'admin:users', 'audit:read'
  ]
};

export function hasPermission(role: string, permission: Permission): boolean {
  if (!role || !(role in ROLE_PERMISSIONS)) return false;
  return ROLE_PERMISSIONS[role as UserRole].includes(permission);
}

// One permission, or a list meaning "any of these". Mirrors the backend's
// require_any_permission, for pages two different roles reach for different
// reasons, e.g. Payroll: HR generates (payroll:generate), Director approves
// (payroll:approve).
export function hasAnyPermission(role: string, required: Permission | Permission[]): boolean {
  const list = Array.isArray(required) ? required : [required];
  return list.some((p) => hasPermission(role, p));
}
