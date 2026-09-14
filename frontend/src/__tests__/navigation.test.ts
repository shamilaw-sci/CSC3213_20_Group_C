import { NAVIGATION_CONFIG, NavItem } from '../lib/navigation';
import { UserRole, hasPermission } from '../lib/permissions';

// Hand-written on purpose: deriving these from ROLE_PERMISSIONS would make the
// test tautological. Because the map is keyed by the UserRole union, adding a
// role without deciding what it can see is a compile error, not a silent gap.
const PERSONAL = ['Go to Website Home', 'Edit Profile', 'Account Settings', 'Support'];

const expectedItemsPerRole: Record<UserRole, string[]> = {
  'Admin': [
    'Overview', 'Employees', 'Attendance', 'Payroll', 'Overview', 'Ledger',
    'Receivables', 'Payables', 'Reports', 'Stock', 'Issue', 'Returns',
    'Active Programs', 'Case Hotspots', 'Case Triage', 'My Attendance', 'System Admin',
    ...PERSONAL
  ],
  // No Ledger: that needs finance:write, which oversight deliberately lacks.
  // No My Attendance: Director has no hr:attendance:self.
  'Director': [
    'Overview', 'Overview', 'Receivables', 'Payables', 'Reports', 'Stock',
    'Active Programs', 'Case Hotspots', 'Case Triage', ...PERSONAL
  ],
  'HR Officer': [
    'Overview', 'Employees', 'Attendance', 'Payroll',
    'Case Hotspots', 'Case Triage', 'My Attendance', ...PERSONAL
  ],
  // Active Programs is expected: programs:read was granted so the program
  // picker on the transaction form renders names rather than numeric ids.
  'Finance Officer': [
    'Overview', 'Payroll', 'Overview', 'Ledger', 'Receivables', 'Payables', 'Reports',
    'Stock', 'Active Programs', ...PERSONAL
  ],
  // Clinic and field operations: inventory, programs and rescue, no HR/finance.
  'Operations Lead': [
    'Overview', 'Stock', 'Issue', 'Returns', 'Active Programs',
    'Case Hotspots', 'Case Triage', 'My Attendance', ...PERSONAL
  ],
  // No Stock: General Staff can issue inventory but not browse the catalogue.
  'General Staff': [
    'Overview', 'Issue', 'Returns', 'Active Programs',
    'Case Hotspots', 'Case Triage', 'My Attendance', ...PERSONAL
  ],
  // Technical administration only. The short list is the point: no payroll,
  // no ledger, no case data.
  'System Administrator': [
    'Overview', 'System Admin', ...PERSONAL
  ]
};

function runTest() {
  let passed = true;
  
  for (const [roleStr, expected] of Object.entries(expectedItemsPerRole)) {
    const role = roleStr as UserRole;
    
    // Mock user matching frontend User type
    const user = { id: 'test', email: 'test@vff', roles: { role_name: role } };
    
    // Filter navigation
    const allowedLabels: string[] = [];
    for (const section of NAVIGATION_CONFIG) {
      for (const item of section.items) {
        if (!item.requiredPermission || hasPermission(role, item.requiredPermission)) {
          allowedLabels.push(item.label);
        }
      }
    }
    
    // Compare
    const missing = expected.filter(l => !allowedLabels.includes(l));
    const extra = allowedLabels.filter(l => !expected.includes(l));
    
    if (missing.length > 0 || extra.length > 0) {
      console.error(`❌ [FAIL] ${role}`);
      if (missing.length > 0) console.error(`   Missing: ${missing.join(', ')}`);
      if (extra.length > 0) console.error(`   Extra: ${extra.join(', ')}`);
      passed = false;
    } else {
      console.log(`✅ [PASS] ${role}`);
    }
  }
  
  if (!passed) {
    console.error('\nTests failed!');
    process.exit(1);
  } else {
    console.log('\nAll navigation tests passed!');
  }
}

runTest();
