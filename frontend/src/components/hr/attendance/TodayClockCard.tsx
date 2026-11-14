'use client';

import { useState } from 'react';
import { CheckCircle2, Clock, Link2Off, Lock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useClockIn, useClockOut, useMyAttendance } from '@/hooks/useHR';
import { addDays, colomboDate, hhmm } from './dayStatus';

// Same as OVERNIGHT_MAX in backend/app/api/hr.py: yesterday's open record is
// a shift still running only if it began within this long. Past that it is a
// forgotten clock-out, which HR corrects.
const OVERNIGHT_MAX_MS = 16 * 60 * 60 * 1000;

/**
 * Clock in and out for today, on My Day and My Attendance. One copy: the
 * dashboard's own used to treat an unlocked record as still running, so
 * after clocking out it offered Clock Out again.
 */
export function TodayClockCard({ title }: { title: string }) {
  // All of one's records, not just this month's: an overnight shift that
  // began on the last day of the month is still open on the 1st.
  const { data: logs, isLoading, error } = useMyAttendance();
  const { mutate: clockIn, isPending: isClockingIn } = useClockIn();
  const { mutate: clockOut, isPending: isClockingOut } = useClockOut();
  // Read once per visit; the card is about today, not the second.
  const [now] = useState(() => Date.now());

  const today = colomboDate(new Date(now));
  const yesterday = addDays(today, -1);
  const todayRecord = logs?.find((l) => l.target_date === today);
  const overnight = todayRecord ? undefined : logs?.find((l) =>
    l.target_date === yesterday && l.clock_in && !l.clock_out
    && now - new Date(l.clock_in).getTime() <= OVERNIGHT_MAX_MS);
  const record = todayRecord ?? overnight;

  const notLinked = (error as { response?: { status?: number } } | null)?.response?.status === 404;

  return (
    <Card className="border-border-brand bg-surface">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Clock className="w-5 h-5 text-accent" />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col items-center justify-center py-6 space-y-6">
        {isLoading ? (
          <Skeleton className="w-full h-32 rounded-lg" />
        ) : notLinked ? (
          <div className="text-center space-y-2">
            <Link2Off className="w-10 h-10 text-text-muted mx-auto" />
            <p className="text-sm text-text-secondary">
              Your login isn&apos;t linked to an employee record, so you can&apos;t clock in yet. Ask HR to link it.
            </p>
          </div>
        ) : error ? (
          <p className="text-sm text-negative">Could not load today&apos;s attendance. Refresh to try again.</p>
        ) : !record ? (
          <>
            <p className="text-text-secondary">You haven&apos;t clocked in yet.</p>
            <Button
              onClick={() => clockIn()}
              disabled={isClockingIn}
              className="w-full bg-accent text-bg-brand hover:bg-accent/90"
              size="lg"
            >
              {isClockingIn ? 'Clocking In...' : 'Clock In Now'}
            </Button>
          </>
        ) : record.clock_out ? (
          <div className="text-center space-y-2">
            {record.is_locked
              ? <Lock className="w-12 h-12 text-emerald-500 mx-auto" />
              : <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto" />}
            <p className="font-medium text-emerald-500">Attendance Completed</p>
            <p className="text-sm text-text-secondary">In: {hhmm(record.clock_in)} | Out: {hhmm(record.clock_out)}</p>
            <p className="text-xs text-text-secondary">{record.worked_hours ?? 0} hours worked</p>
          </div>
        ) : (
          <>
            <div className="text-center space-y-2">
              <div className="animate-pulse bg-emerald-500/20 text-emerald-500 px-3 py-1 rounded-full text-sm font-medium inline-block mb-2">
                Active Session
              </div>
              <p className="text-sm text-text-secondary">
                Clocked in at {hhmm(record.clock_in)}{overnight ? ' yesterday' : ''}
              </p>
            </div>
            <Button
              onClick={() => clockOut()}
              disabled={isClockingOut}
              className="w-full bg-rose-500 text-white hover:bg-rose-600"
              size="lg"
            >
              {isClockingOut ? 'Clocking Out...' : 'Clock Out'}
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}
