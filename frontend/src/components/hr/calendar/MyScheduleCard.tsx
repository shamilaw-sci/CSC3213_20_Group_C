'use client';

import { CalendarDays, Moon } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useMySchedule } from '@/hooks/useWorkCalendar';
import { WeekStrip } from './SchedulesTab';

const DAY = new Intl.DateTimeFormat('en-LK', { weekday: 'short', day: 'numeric', month: 'short' });
const TIME = new Intl.DateTimeFormat('en-LK', { timeZone: 'Asia/Colombo', hour: '2-digit', minute: '2-digit', hour12: false });

function localDate(iso: string) {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(y, m - 1, d);
}

// Staff's own view: the hours they are expected to keep, today, and the next
// days off. Read-only; HR changes these on Schedules & Holidays.
export function MyScheduleCard() {
  const { data, isLoading, error } = useMySchedule();

  if (error) return null; // no linked employee profile: nothing to show

  return (
    <Card className="border-border-brand bg-surface">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarDays className="h-5 w-5 text-accent" /> My schedule
        </CardTitle>
        {data?.schedule && (
          <CardDescription>
            {data.schedule.name} · {data.schedule.grace_minutes} min grace
            {!data.schedule.observes_holidays && ' · works through holidays'}
          </CardDescription>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading || !data ? (
          <Skeleton className="h-24 w-full" />
        ) : !data.schedule ? (
          <p className="text-sm text-text-secondary">No schedule has been set up yet.</p>
        ) : (
          <>
            <WeekStrip days={data.schedule.days} />
            <p className="text-sm text-text-secondary">
              Today:{' '}
              <span className="font-medium text-text-primary">
                {data.today.reason === 'holiday'
                  ? `Day off (${data.today.holidays.join(', ')})`
                  : data.today.working && data.today.start && data.today.end
                    ? `${TIME.format(new Date(data.today.start))}–${TIME.format(new Date(data.today.end))}`
                    : 'Not a working day'}
              </span>
            </p>
            {data.upcoming_holidays.length > 0 && (
              <div>
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-text-secondary">Next days off</p>
                <ul className="space-y-1 text-sm">
                  {data.upcoming_holidays.map((h) => (
                    <li key={h.id} className="flex items-center gap-2">
                      <span className="w-24 shrink-0 font-mono text-xs text-text-secondary">{DAY.format(localDate(h.holiday_date))}</span>
                      {h.is_poya && <Moon className="h-3.5 w-3.5 text-sky-600" aria-label="Poya day" />}
                      <span className="text-text-primary">{h.name}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
