'use client';

import { useState } from 'react';
import { Lock, LockOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { useLogAttendance, useUnlockAttendance, useUpdateAttendance } from '@/hooks/useHR';
import { DayCell } from '@/types';
import { cn } from '@/lib/utils';
import { TONE_CLASS, hhmm, hours, localDate, lookOf } from './dayStatus';

const LONG = new Intl.DateTimeFormat('en-LK', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
const field =
  'h-9 rounded-md border border-border-brand bg-surface px-2 text-sm text-text-primary outline-none focus:border-accent';

// HH:MM in Sri Lanka time, for a time input.
const toInput = (iso: string | null) => (iso ? hhmm(iso) : '');

// A Sri Lanka wall-clock time on a date, sent with its offset so it is
// stored as the moment it was, not as UTC.
const toIso = (date: string, time: string) => `${date}T${time}:00+05:30`;

export function DayDetailDialog({
  cell, employeeId, employeeName, canEdit, onClose,
}: {
  cell: DayCell; employeeId: number; employeeName: string; canEdit: boolean; onClose: () => void;
}) {
  const look = lookOf(cell);
  const [clockIn, setClockIn] = useState(toInput(cell.clock_in));
  const [clockOut, setClockOut] = useState(toInput(cell.clock_out));
  const { mutate: update, isPending: isUpdating } = useUpdateAttendance();
  const { mutate: create, isPending: isCreating } = useLogAttendance();
  const { mutate: unlock, isPending: isUnlocking } = useUnlockAttendance();

  const editable = canEdit && !cell.locked && !['not_employed', 'not_tracked', 'upcoming'].includes(cell.status);
  const changed = clockIn !== toInput(cell.clock_in) || clockOut !== toInput(cell.clock_out);

  const save = () => {
    if (cell.record_id) {
      update(
        {
          id: cell.record_id,
          ...(clockIn ? { clock_in: toIso(cell.date, clockIn) } : {}),
          ...(clockOut ? { clock_out: toIso(cell.date, clockOut) } : {}),
        },
        { onSuccess: onClose },
      );
    } else if (clockIn) {
      create(
        {
          employee_id: employeeId,
          target_date: cell.date,
          clock_in: toIso(cell.date, clockIn),
          clock_out: clockOut ? toIso(cell.date, clockOut) : null,
          worked_hours: null,
          is_locked: false,
        },
        { onSuccess: onClose },
      );
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-surface border-border-brand">
        <DialogHeader>
          <DialogTitle>{employeeName}</DialogTitle>
          <DialogDescription>{LONG.format(localDate(cell.date))}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-sm">
          <p className="flex items-center gap-2">
            <span className={cn('inline-flex min-w-8 justify-center rounded px-1.5 py-0.5 text-xs font-bold', TONE_CLASS[look.tone])}>
              {look.code || '·'}
            </span>
            <span className="font-medium text-text-primary">{look.label}</span>
          </p>
          <p className="text-text-secondary">{cell.reason}</p>

          <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 rounded-md border border-border-brand bg-bg-subtle p-3 text-xs">
            <dt className="text-text-muted">Schedule</dt>
            <dd className="text-text-primary">{cell.schedule_name ?? '—'}</dd>
            {cell.expected_start && (
              <>
                <dt className="text-text-muted">Expected</dt>
                <dd className="font-mono text-text-primary">{hhmm(cell.expected_start)}–{hhmm(cell.expected_end)}</dd>
              </>
            )}
            <dt className="text-text-muted">Clocked</dt>
            <dd className="font-mono text-text-primary">{hhmm(cell.clock_in)}–{hhmm(cell.clock_out)}</dd>
            {cell.worked_minutes > 0 && (
              <>
                <dt className="text-text-muted">Worked</dt>
                <dd className="text-text-primary">
                  {hours(cell.worked_minutes)}
                  {cell.expected_minutes > 0 && <span className="text-text-muted"> of {hours(cell.expected_minutes)} expected</span>}
                </dd>
              </>
            )}
            {cell.leave && (
              <>
                <dt className="text-text-muted">Leave</dt>
                <dd className="text-text-primary">{cell.leave.type_name}{cell.leave.fraction < 1 ? ` (${cell.leave.half_day === 'am' ? 'morning' : 'afternoon'})` : ''}</dd>
              </>
            )}
            {cell.leave_pending && (
              <>
                <dt className="text-text-muted">Requested</dt>
                <dd className="text-amber-600">{cell.leave_pending.type_name}, awaiting a decision</dd>
              </>
            )}
            {cell.locked && (
              <>
                <dt className="text-text-muted">Record</dt>
                <dd className="flex items-center gap-1 text-text-primary"><Lock className="h-3 w-3" /> Locked</dd>
              </>
            )}
          </dl>

          {editable && (
            <div className="space-y-2">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-text-secondary">
                {cell.record_id ? 'Correct the times' : 'Record times'} <span className="font-normal normal-case text-text-muted">(Sri Lanka time)</span>
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <input type="time" value={clockIn} onChange={(e) => setClockIn(e.target.value)} aria-label="Clock in" className={cn(field, 'font-mono')} />
                <span className="text-text-muted">to</span>
                <input type="time" value={clockOut} onChange={(e) => setClockOut(e.target.value)} aria-label="Clock out" className={cn(field, 'font-mono')} />
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          {canEdit && cell.locked && cell.record_id && (
            <Button variant="outline" disabled={isUnlocking} onClick={() => unlock(cell.record_id!, { onSuccess: onClose })}
              className="mr-auto gap-1.5 border-border-brand">
              <LockOpen className="h-4 w-4" /> Unlock to correct
            </Button>
          )}
          <Button variant="outline" onClick={onClose}>Close</Button>
          {editable && (
            <Button onClick={save} disabled={!changed || !clockIn || isUpdating || isCreating} className="bg-accent text-white hover:bg-accent/90">
              {isUpdating || isCreating ? 'Saving…' : 'Save'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
