// Report period presets and CSV escaping.
//
//   node --import ./src/__tests__/resolve-ts.mjs src/__tests__/finance-reports.test.ts
import assert from 'node:assert/strict';
import { presetPeriod, periodLabel, toISODate } from '../lib/finance-periods';
import { buildCsv, csvCell } from '../lib/csv';

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

const OCT_28_2026 = new Date(2026, 9, 28);
const FEB_10_2026 = new Date(2026, 1, 10);

test('toISODate uses local time, not UTC', () => {
  // At UTC+5:30, local midnight on 1 Apr is 31 Mar in UTC.
  assert.equal(toISODate(new Date(2026, 3, 1)), '2026-04-01');
});

test('this month / last month', () => {
  assert.deepEqual(presetPeriod('this-month', OCT_28_2026), { start: '2026-10-01', end: '2026-10-31' });
  assert.deepEqual(presetPeriod('last-month', OCT_28_2026), { start: '2026-09-01', end: '2026-09-30' });
});

test('last month crosses the year boundary', () => {
  assert.deepEqual(presetPeriod('last-month', new Date(2026, 0, 15)), { start: '2025-12-01', end: '2025-12-31' });
});

test('quarters', () => {
  assert.deepEqual(presetPeriod('this-quarter', OCT_28_2026), { start: '2026-10-01', end: '2026-12-31' });
  assert.deepEqual(presetPeriod('last-quarter', OCT_28_2026), { start: '2026-07-01', end: '2026-09-30' });
  assert.deepEqual(presetPeriod('last-quarter', FEB_10_2026), { start: '2025-10-01', end: '2025-12-31' });
});

test('financial year runs April to March', () => {
  assert.deepEqual(presetPeriod('this-fy', OCT_28_2026), { start: '2026-04-01', end: '2027-03-31' });
  assert.deepEqual(presetPeriod('last-fy', OCT_28_2026), { start: '2025-04-01', end: '2026-03-31' });
});

test('January to March belong to the FY that started the April before', () => {
  assert.deepEqual(presetPeriod('this-fy', FEB_10_2026), { start: '2025-04-01', end: '2026-03-31' });
});

test('FY starts on 1 April exactly', () => {
  assert.equal(presetPeriod('this-fy', new Date(2026, 2, 31)).start, '2025-04-01');
  assert.equal(presetPeriod('this-fy', new Date(2026, 3, 1)).start, '2026-04-01');
});

test('period labels', () => {
  assert.equal(periodLabel({ start: '2026-10-01', end: '2026-10-31' }), 'Oct 2026');
  assert.equal(periodLabel({ start: '2026-10-01', end: '2026-12-31' }), 'Oct – Dec 2026');
  assert.equal(periodLabel({ start: '2026-04-01', end: '2027-03-31' }), 'FY 2026/27');
  assert.equal(periodLabel({ start: '2025-11-01', end: '2026-01-31' }), 'Nov 2025 – Jan 2026');
  assert.equal(periodLabel({ start: '2026-10-03', end: '2026-11-09' }), '3 Oct 2026 – 9 Nov 2026');
});

test('csv quotes commas, quotes and newlines', () => {
  assert.equal(csvCell('Rescue, North'), '"Rescue, North"');
  assert.equal(csvCell('The "big" one'), '"The ""big"" one"');
  assert.equal(csvCell('two\nlines'), '"two\nlines"');
});

test('csv neutralises formula injection in text but keeps negative numbers', () => {
  assert.equal(csvCell('=HYPERLINK("http://x")'), `"'=HYPERLINK(""http://x"")"`);
  assert.equal(csvCell('@SUM(A1)'), "'@SUM(A1)");
  assert.equal(csvCell('-cmd'), "'-cmd");
  assert.equal(csvCell(-300), '-300');
  assert.equal(csvCell(null), '');
});

test('buildCsv joins rows with CRLF', () => {
  assert.equal(buildCsv(['a', 'b'], [[1, 'x'], [2, null]]), 'a,b\r\n1,x\r\n2,');
});

if (failures) {
  console.error(`\n${failures} failed`);
  process.exit(1);
}
