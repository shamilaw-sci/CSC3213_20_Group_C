// Report periods for /finance/reports. The organisation's financial year runs
// April to March, Sri Lanka's government and tax year.
//
// Dates are built and formatted in local time on purpose. toISOString() is
// UTC, and at UTC+5:30 local midnight on the 1st is still the previous day
// in UTC, so every period start would land on the last day of the month
// before.

export type PeriodPreset =
  | 'this-month'
  | 'last-month'
  | 'this-quarter'
  | 'last-quarter'
  | 'this-fy'
  | 'last-fy'
  | 'custom';

export interface Period {
  start: string; // YYYY-MM-DD
  end: string;   // YYYY-MM-DD, inclusive
}

export const PRESETS: { value: Exclude<PeriodPreset, 'custom'>; label: string }[] = [
  { value: 'this-month', label: 'This month' },
  { value: 'last-month', label: 'Last month' },
  { value: 'this-quarter', label: 'This quarter' },
  { value: 'last-quarter', label: 'Last quarter' },
  { value: 'this-fy', label: 'This FY' },
  { value: 'last-fy', label: 'Last FY' },
];

const FY_START_MONTH = 3; // April, 0-based

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function toISODate(d: Date): string {
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

// Whole months [year, month0] .. [year, month0 + count - 1]. Date normalises
// overflowing and negative months, so callers can step across year ends.
function months(year: number, month0: number, count: number): Period {
  return {
    start: toISODate(new Date(year, month0, 1)),
    end: toISODate(new Date(year, month0 + count, 0)),
  };
}

function fyStartYear(today: Date): number {
  return today.getMonth() >= FY_START_MONTH ? today.getFullYear() : today.getFullYear() - 1;
}

export function presetPeriod(preset: Exclude<PeriodPreset, 'custom'>, today: Date): Period {
  const y = today.getFullYear();
  const m = today.getMonth();
  const quarterStart = Math.floor(m / 3) * 3;

  switch (preset) {
    case 'this-month':
      return months(y, m, 1);
    case 'last-month':
      return months(y, m - 1, 1);
    // April-March years make the financial quarters (Apr-Jun, Jul-Sep, ...)
    // the same as calendar quarters, so no FY offset is needed here.
    case 'this-quarter':
      return months(y, quarterStart, 3);
    case 'last-quarter':
      return months(y, quarterStart - 3, 3);
    case 'this-fy':
      return months(fyStartYear(today), FY_START_MONTH, 12);
    case 'last-fy':
      return months(fyStartYear(today) - 1, FY_START_MONTH, 12);
  }
}

function parse(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}

// "Oct 2026", "Oct – Dec 2026", "FY 2026/27", else "3 Oct 2026 – 9 Nov 2026".
export function periodLabel({ start, end }: Period): string {
  const s = parse(start);
  const e = parse(end);
  const wholeMonths = s.getDate() === 1 && new Date(e.getFullYear(), e.getMonth() + 1, 0).getDate() === e.getDate();

  if (wholeMonths) {
    const span = (e.getFullYear() - s.getFullYear()) * 12 + e.getMonth() - s.getMonth() + 1;
    if (span === 12 && s.getMonth() === FY_START_MONTH) {
      return `FY ${s.getFullYear()}/${String(s.getFullYear() + 1).slice(2)}`;
    }
    if (span === 1) return `${MONTHS[s.getMonth()]} ${s.getFullYear()}`;
    if (s.getFullYear() === e.getFullYear()) {
      return `${MONTHS[s.getMonth()]} – ${MONTHS[e.getMonth()]} ${e.getFullYear()}`;
    }
    return `${MONTHS[s.getMonth()]} ${s.getFullYear()} – ${MONTHS[e.getMonth()]} ${e.getFullYear()}`;
  }

  const day = (d: Date) => `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
  return `${day(s)} – ${day(e)}`;
}

// "2026-04" -> "Apr 2026", for the monthly trend.
export function monthLabel(month: string, withYear = true): string {
  const [y, m] = month.split('-').map(Number);
  return withYear ? `${MONTHS[m - 1]} ${y}` : MONTHS[m - 1];
}
