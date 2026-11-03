// Where a finance row came from: the Description text and the edit lock.
//
//   node --import ./src/__tests__/resolve-ts.mjs src/__tests__/finance-source.test.ts
import assert from 'node:assert/strict';
import { describeTransaction, isAutoPosted, sourceOf } from '../lib/finance-source';

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

test('a row read before migration 013 counts as manual', () => {
  assert.equal(sourceOf({ program_id: null }), 'manual');
  assert.equal(isAutoPosted({ program_id: null }), false);
});

test('stock in, payroll and donation rows are auto-posted; manual rows are not', () => {
  for (const source of ['stock_in', 'payroll', 'donation'] as const) {
    assert.equal(isAutoPosted({ source_type: source, program_id: null }), true, source);
  }
  assert.equal(isAutoPosted({ source_type: 'manual', program_id: 3 }), false);
});

test('the ledger API description is used as sent', () => {
  assert.equal(
    describeTransaction({ source_type: 'manual', program_id: 3, description: 'Donation-Rabies Drive' }),
    'Donation-Rabies Drive',
  );
});

test('without one it is built the same way as the backend: Source-Program', () => {
  assert.equal(describeTransaction({ source_type: 'stock_in', program_id: null }), 'Stock in-General');
  assert.equal(
    describeTransaction({ source_type: 'donation', program_id: 3, programs: { program_name: 'Rabies Drive' } }),
    'Donation-Rabies Drive',
  );
  assert.equal(
    describeTransaction({ source_type: 'manual', program_id: 3, program_name: 'Galle Clinic' }),
    'Manual-Galle Clinic',
  );
  assert.equal(describeTransaction({ program_id: 9 }), 'Manual-Program #9');
});

if (failures) {
  console.error(`\n${failures} failing`);
  process.exit(1);
}
