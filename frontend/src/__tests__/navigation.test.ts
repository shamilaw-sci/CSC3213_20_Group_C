import { NAVIGATION_CONFIG, canSeeNavItem } from '../lib/navigation';
// A `type` import: Node strips types natively and fails on a type imported
// as if it were a value, which is what had stopped this file running at all.
import { type UserRole } from '../lib/permissions';

// Hand-written on purpose: deriving these from ROLE_PERMISSIONS would make the
// test tautological. Because the map is keyed by the UserRole union, adding a
// role without deciding what it can see is a compile error, not a silent gap.
const PERSONAL = ['Go to Website Home', 'Edit Profile', 'Account Settings', 'Support'];

const expectedItemsPerRole: Record<UserRole, string[]> = {
  'Admin': [
    'Overview', 'Employees', 'Attendance', 'Schedules & Holidays', 'Leave', 'Payroll', 'Overview', 'Ledger',
    'Reports', 'Stock', 'Issue', 'Returns',
    'Upcoming Programs', 'Active Programs', 'Completed Programs', 'Applications', 'Shifts', 'Donation details', 'Case Hotspots', 'Case Triage', 'Field Dispatch', 'My Attendance', 'My Leave', 'System Admin',
    ...PERSONAL
  ],
  // Ledger is read-only for Director: it needs finance:read, while adding,
  // editing and voiding inside it need finance:write, which oversight lacks.
  // My Attendance / My Leave: Director is an employee too (hr:attendance:self,
  // granted 2026-10-29); it reaches only their own records.
  // Payroll: Director approves it (payroll:approve) without generating it.
  // Attendance: the monthly grid, read-only (hr:attendance:read, 2026-10-31).
  'Director': [
    'Overview', 'Attendance', 'Payroll', 'Overview', 'Ledger', 'Reports', 'Stock',
    'Upcoming Programs', 'Active Programs', 'Completed Programs', 'Applications', 'Shifts', 'Donation details', 'Case Hotspots', 'Case Triage', 'Field Dispatch', 'My Attendance', 'My Leave', ...PERSONAL
  ],
  // Applications and Shifts: volunteers:read, because HR vets volunteer
  // applications (volunteers:approve).
  'HR Officer': [
    'Overview', 'Employees', 'Attendance', 'Schedules & Holidays', 'Leave', 'Payroll', 'Applications', 'Shifts',
    'Case Hotspots', 'Case Triage', 'Field Dispatch', 'My Attendance', 'My Leave', ...PERSONAL
  ],
  // The three program pages are expected: programs:read was granted so the
  // program picker on the transaction form renders names rather than numeric
  // ids, and every program page is gated on that same permission.
  'Finance Officer': [
    'Overview', 'Payroll', 'Overview', 'Ledger', 'Reports',
    'Stock', 'Upcoming Programs', 'Active Programs', 'Completed Programs', 'Donation details', 'My Attendance', 'My Leave', ...PERSONAL
  ],
  // Clinic and field operations: inventory, programs and rescue, no HR/finance.
  // Inventory through the Stock page only; Issue and Returns are for General
  // Staff and Admin (decided 2026-11-01).
  'Operations Lead': [
    'Overview', 'Stock', 'Upcoming Programs', 'Active Programs', 'Completed Programs', 'Applications', 'Shifts',
    'Case Hotspots', 'Case Triage', 'Field Dispatch', 'My Attendance', 'My Leave', ...PERSONAL
  ],
  // No Stock: General Staff issue and return through the Issue and Returns
  // pages only, and do not browse the catalogue or its movement log.
  'General Staff': [
    'Overview', 'Issue', 'Returns', 'Upcoming Programs', 'Active Programs', 'Completed Programs',
    'Case Hotspots', 'Case Triage', 'Field Dispatch', 'My Attendance', 'My Leave', ...PERSONAL
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
        if (canSeeNavItem(role, item)) {
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
