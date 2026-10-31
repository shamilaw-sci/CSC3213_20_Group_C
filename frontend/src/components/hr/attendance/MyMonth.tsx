'use client';

import { useState } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useMyAttendanceMonth } from '@/hooks/useHR';
import { cn } from '@/lib/utils';
import { DayCell } from '@/types';
import { DayDetailDialog } from './DayDetailDialog';
import { LEGEND, TONE_CLASS, hours, localDate, lookOf } from './dayStatus';

const MONTH = new Intl.DateTimeFormat('en-LK', { month: 'long', year: 'numeric' });
const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

// A person's own month, with the same statuses HR sees. Read-only: a wrong
// day is fixed by HR (and, from step 4, by a correction request).
export function MyMonth() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [open, setOpen] = useState<DayCell | null>(null);
  const { data, isLoading, error } = useMyAttendanceMonth(year, month);

  const step = (delta: number) => {
    const d = new Date(year, month - 1 + delta, 1);
    setYear(d.getFullYear());
    setMonth(d.getMonth() + 1);
  };

  if (error) return null; // no linked employee record: nothing to show

  const row = data?.employee;
  const leading = data ? (data.days[0].weekday + 6) % 7 : 0; // blanks before the 1st, Monday-first

  return (
    <Card className="border-border-brand bg-surface">
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle className="flex items-center gap-2">
          <CalendarDays className="h-5 w-5 text-accent" /> My month
        </CardTitle>
        <div className="flex items-center gap-1">
          <Button variant="outline" size="sm" onClick={() => step(-1)} aria-label="Previous month" className="h-8 w-8 border-border-brand p-0">
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="min-w-[130px] text-center text-sm font-semibold text-text-primary">{MONTH.format(new Date(year, month - 1, 1))}</span>
          <Button variant="outline" size="sm" onClick={() => step(1)} aria-label="Next month" className="h-8 w-8 border-border-brand p-0">
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading || !data || !row ? (
          <Skeleton className="h-56 w-full" />
        ) : (
          <>
            <div className="grid grid-cols-7 gap-1 text-center text-xs">
              {WEEKDAYS.map((w) => <div key={w} className="pb-1 font-semibold text-text-secondary">{w}</div>)}
              {Array.from({ length: leading }, (_, i) => <div key={`blank-${i}`} />)}
              {row.cells.map((c) => {
                const look = lookOf(c);
                return (
                  <button key={c.date} type="button" onClick={() => setOpen(c)} title={look.label}
                    aria-label={`${localDate(c.date).getDate()}: ${look.label}`}
                    className={cn('flex h-12 flex-col items-center justify-center rounded-md border border-border-brand hover:ring-2 hover:ring-accent/50',
                      c.date === data.today && 'ring-2 ring-accent')}>
                    <span className="text-[10px] text-text-muted">{localDate(c.date).getDate()}</span>
                    <span className={cn('mt-0.5 inline-flex min-w-6 justify-center rounded px-1 text-[10px] font-bold', look.code && TONE_CLASS[look.tone])}>
                      {look.code || ' '}
                    </span>
                  </button>
                );
              })}
            </div>

            <dl className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
              {[
                ['Present', row.totals.present],
                ['Late', row.totals.late],
                ['Absent', row.totals.absent],
                ['Leave days', row.totals.leave_days],
              ].map(([label, value]) => (
                <div key={label as string} className="rounded-md border border-border-brand bg-bg-subtle px-3 py-2">
                  <dt className="text-text-muted">{label}</dt>
                  <dd className="text-base font-semibold text-text-primary">{value}</dd>
                </div>
              ))}
            </dl>
            <p className="text-xs text-text-muted">
              {hours(row.totals.worked_minutes)} worked so far this month. Something wrong? Ask HR to correct it.
            </p>

            <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-text-secondary">
              {LEGEND.map((l) => (
                <span key={l.code} className="flex items-center gap-1">
                  <span className={cn('inline-flex min-w-5 justify-center rounded px-1 text-[10px] font-bold', TONE_CLASS[l.tone])}>{l.code}</span>
                  {l.label}
                </span>
              ))}
            </div>
          </>
        )}
      </CardContent>
      {open && row && (
        <DayDetailDialog key={open.date} cell={open} employeeId={row.employee_id} employeeName="My day" canEdit={false} onClose={() => setOpen(null)} />
      )}
    </Card>
  );
}
