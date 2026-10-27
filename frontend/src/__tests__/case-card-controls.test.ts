// Which triage-card controls each role gets. Permissions come from the real
// hasPermission and role names, so this is the HR Officer the board actually
// renders for, not a hand-built pair of booleans.
//
//   node --import ./src/__tests__/resolve-ts.mjs src/__tests__/case-card-controls.test.ts
import assert from 'node:assert/strict';
import { cardControls } from '../lib/case-card-controls';
import { hasPermission, type UserRole } from '../lib/permissions';
import type { AssigneeOption } from '../types';

let failures = 0;
function test(name: string, fn: () => void) {
  try {
    fn();
    console.log(`ok   ${name}`);
  } catch (e) {
    failures++;
    console.error(`FAIL ${name}\n     ${(e as Error).message}`);
  }
}

// Shape of GET /rescue_cases/assignees.
const ASSIGNEES: AssigneeOption[] = [
  { id: 'a1', email: 'admin@vff.org', display_name: null, role_name: 'Admin' },
  { id: 'a2', email: 'nimal@vff.org', display_name: 'Nimal Perera', role_name: 'General Staff' },
  { id: 'a3', email: 'ops@vff.org', display_name: 'Kamala Silva', role_name: 'Operations Lead' },
];

const REPORTED = { status: 'Reported' as const, assigned_to: undefined };
const IN_TREATMENT = { status: 'In Treatment' as const, assigned_to: 'a2' };
const RESOLVED = { status: 'Resolved' as const, assigned_to: 'a2' };

type CardCase = Parameters<typeof cardControls>[0];

function as(role: UserRole, c: CardCase = REPORTED, assignees: AssigneeOption[] | undefined = ASSIGNEES) {
  return cardControls(c, hasPermission(role, 'rescue:manage'), hasPermission(role, 'rescue:assign'), assignees);
}

test('HR Officer holds rescue:assign without rescue:manage (the premise)', () => {
  assert.equal(hasPermission('HR Officer', 'rescue:assign'), true);
  assert.equal(hasPermission('HR Officer', 'rescue:manage'), false);
});

test('HR Officer sees the assign dropdown, listing exactly what /assignees returned', () => {
  const c = as('HR Officer');
  assert.deepEqual(c.assignOptions, [
    { value: 'a1', label: 'admin@vff.org (Admin)' },
    { value: 'a2', label: 'Nimal Perera (General Staff)' },
    { value: 'a3', label: 'Kamala Silva (Operations Lead)' },
  ]);
});

test('HR Officer can reassign an In Treatment case', () => {
  assert.equal(as('HR Officer', IN_TREATMENT).assignOptions?.length, 3);
});

test('HR Officer cannot drag, self-assign, or change status', () => {
  const c = as('HR Officer');
  assert.equal(c.draggable, false);
  assert.equal(c.showAssignToMe, false);
  assert.equal(c.showStatusSelect, false);
});

test('Director (also assign-without-manage) gets the same dropdown', () => {
  assert.deepEqual(as('Director').assignOptions, as('HR Officer').assignOptions);
});

test('Admin gets every control', () => {
  const c = as('Admin');
  assert.equal(c.draggable, true);
  assert.equal(c.showAssignToMe, true);
  assert.equal(c.showStatusSelect, true);
  assert.equal(c.assignOptions?.length, 3);
});

test('General Staff manages but cannot assign others: no dropdown', () => {
  const c = as('General Staff');
  assert.equal(c.assignOptions, null);
  assert.equal(c.draggable, true);
  assert.equal(c.showAssignToMe, true);
});

test('no rescue role: nothing', () => {
  assert.deepEqual(as('Finance Officer'), {
    draggable: false, showAssignToMe: false, showStatusSelect: false, assignOptions: null,
  });
});

test('no dropdown on a Resolved case, or before /assignees has loaded', () => {
  assert.equal(as('HR Officer', RESOLVED).assignOptions, null);
  // Direct call: as(..., undefined) would fall back to its default list.
  assert.equal(cardControls(REPORTED, false, true, undefined).assignOptions, null);
  assert.equal(as('HR Officer', REPORTED, []).assignOptions, null);
});

test('"Assign to me" only on an open, unassigned case', () => {
  assert.equal(as('Admin', IN_TREATMENT).showAssignToMe, false);
  assert.equal(as('Admin', RESOLVED).showAssignToMe, false);
});

if (failures) {
  console.error(`\n${failures} failed`);
  process.exit(1);
}
