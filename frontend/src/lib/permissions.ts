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
  | 'rescue:assign';

// NOTE: Must stay in sync with backend/app/core/permissions.py
export const ROLE_PERMISSIONS: Record<UserRole, Permission[]> = {
  Admin: [
    'hr:manage', 'hr:attendance:self', 'hr:attendance:manage',
    'payroll:generate', 'payroll:approve', 'finance:read',
    'finance:write', 'finance:restricted:override',
    'inventory:read', 'inventory:issue',
    'programs:read', 'programs:manage', 'admin:users', 'audit:read',
    'rescue:read', 'rescue:manage', 'rescue:assign'
  ],
  Director: [
    'finance:read', 'payroll:approve', 'programs:read',
    'inventory:read', 'audit:read', 'rescue:read' , 'rescue:assign'
  ],
  'HR Officer': [
    'hr:manage', 'hr:attendance:manage', 'hr:attendance:self',
    'payroll:generate' , 'rescue:read', 'rescue:assign'
  ],
  'Finance Officer': [
    'finance:read', 'finance:write', 'payroll:generate',
    'inventory:read', 'programs:read'
  ],
  // Clinic and field operations, per the RBAC table on the support page.
  // programs:manage because leading a clinic means running the programs;
  // this is the first role other than Admin to hold it. Deliberately no
  // rescue:assign — handing work to another person stays with
  // Admin/Director/HR Officer. Self-assignment is unaffected.
  'Operations Lead': [
    'hr:attendance:self', 'inventory:read', 'inventory:issue',
    'programs:read', 'programs:manage',
    'rescue:read', 'rescue:manage'
  ],
  // Default role for every new signup, and the field staff who work rescue
  // cases. Carried over verbatim from the former 'Staff' key, which matched no
  // role any user could hold and so granted nothing in practice.
  'General Staff': [
    'hr:attendance:self', 'programs:read', 'inventory:issue',
    'rescue:read', 'rescue:manage'
  ],
  // Technical administration, not business access: accounts and the audit
  // chain, but no payroll, ledger or case data. Narrower than Admin on
  // purpose, despite the admin login accepting both.
  'System Administrator': [
    'admin:users', 'audit:read'
  ]
};

export function hasPermission(role: string, permission: Permission): boolean {
  if (!role || !(role in ROLE_PERMISSIONS)) return false;
  return ROLE_PERMISSIONS[role as UserRole].includes(permission);
}
