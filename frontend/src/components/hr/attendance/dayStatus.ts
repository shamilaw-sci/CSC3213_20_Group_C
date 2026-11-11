import { DayCell } from '@/types';

// One place for how a day looks, shared by the HR grid, the day detail and
// staff's own month. Every status has a letter as well as a colour, so the
// grid never relies on colour alone.

export type Tone = 'good' | 'warn' | 'bad' | 'leave' | 'off' | 'info' | 'none';

export interface Look {
  code: string;
  label: string;
  tone: Tone;
}

export function lookOf(c: DayCell): Look {
  switch (c.status) {
    case 'present': {
      if (c.late_minutes && c.left_early_minutes) return { code: 'LE', label: 'Late and left early', tone: 'warn' };
      if (c.late_minutes) return { code: 'L', label: `Late (${c.late_minutes} min)`, tone: 'warn' };
      if (c.left_early_minutes) return { code: 'E', label: `Left early (${c.left_early_minutes} min)`, tone: 'warn' };
      return { code: 'P', label: c.leave ? `Present, ${c.leave.type_name.toLowerCase()} half day` : 'Present', tone: 'good' };
    }
    case 'absent':
      return { code: 'A', label: c.leave_pending ? 'Absent, leave awaiting a decision' : 'Absent', tone: 'bad' };
    case 'missing_clock_out':
      return { code: 'MC', label: 'Missing clock-out', tone: 'bad' };
    case 'in_progress':
      return { code: '•', label: 'Clocked in now', tone: 'info' };
    case 'leave':
      return { code: 'LV', label: c.leave ? c.leave.type_name : 'Leave', tone: 'leave' };
    case 'holiday':
      return { code: 'H', label: c.holidays.join(', ') || 'Holiday', tone: 'off' };
    case 'rest':
      return { code: '', label: 'Rest day', tone: 'off' };
    case 'worked_off_day':
      return { code: 'W', label: c.holidays.length ? `Worked on ${c.holidays.join(', ')}` : 'Worked on a rest day', tone: 'info' };
    case 'upcoming':
      return { code: c.leave ? 'LV' : '', label: c.leave ? `${c.leave.type_name} (upcoming)` : 'Upcoming', tone: c.leave ? 'leave' : 'none' };
    case 'not_employed':
      return { code: '', label: 'Not yet employed', tone: 'none' };
  }
}

export const TONE_CLASS: Record<Tone, string> = {
  good: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400',
  warn: 'bg-amber-500/20 text-amber-700 dark:text-amber-400',
  bad: 'bg-rose-500/20 text-rose-600 dark:text-rose-400',
  leave: 'bg-sky-500/15 text-sky-700 dark:text-sky-400',
  off: 'bg-bg-subtle text-text-muted',
  info: 'bg-violet-500/15 text-violet-700 dark:text-violet-400',
  none: 'text-text-muted',
};

export const LEGEND: { code: string; label: string; tone: Tone }[] = [
  { code: 'P', label: 'Present', tone: 'good' },
  { code: 'L', label: 'Late', tone: 'warn' },
  { code: 'E', label: 'Left early', tone: 'warn' },
  { code: 'A', label: 'Absent', tone: 'bad' },
  { code: 'MC', label: 'Missing clock-out', tone: 'bad' },
  { code: 'LV', label: 'Leave', tone: 'leave' },
  { code: 'H', label: 'Holiday', tone: 'off' },
  { code: 'W', label: 'Worked a day off', tone: 'info' },
];

const TIME = new Intl.DateTimeFormat('en-LK', { timeZone: 'Asia/Colombo', hour: '2-digit', minute: '2-digit', hour12: false });

export const hhmm = (iso: string | null) => (iso ? TIME.format(new Date(iso)) : '—');

const DAY = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Colombo', year: 'numeric', month: '2-digit', day: '2-digit' });

// A date in Sri Lanka as YYYY-MM-DD, whatever the viewer's time zone: the
// date attendance is filed under.
export const colomboDate = (at: Date = new Date()) => DAY.format(at);

// YYYY-MM-DD plus n days.
export function addDays(iso: string, n: number) {
  const d = localDate(iso);
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function hours(minutes: number) {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h}h ${m}m` : `${h}h`;
}

export function localDate(iso: string) {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(y, m - 1, d);
}
