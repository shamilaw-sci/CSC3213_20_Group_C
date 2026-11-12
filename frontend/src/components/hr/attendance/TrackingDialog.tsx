'use client';

import { useState } from 'react';
import { AlertTriangle, Ban } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { useSetTracking, useTrackingImpact } from '@/hooks/useHR';
import { cn } from '@/lib/utils';
import { localDate } from './dayStatus';

const LONG = new Intl.DateTimeFormat('en-LK', { day: 'numeric', month: 'long', year: 'numeric' });
const MONTH = new Intl.DateTimeFormat('en-LK', { month: 'long', year: 'numeric' });
const field =
  'h-9 rounded-md border border-border-brand bg-surface px-2 text-sm text-text-primary outline-none focus:border-accent';

export const longDate = (iso: string | null) => (iso ? LONG.format(localDate(iso)) : '—');

// Changing when attendance tracking starts, for everyone or for one person.
// The impact is fetched before anything is saved, so HR sees how many
// absences a move earlier would create. The backend refuses a move that
// would bring a month with approved payroll into tracking; the dialog shows
// that up front and disables Save.
export function TrackingDialog({
  current, employee, orgDate, onClose,
}: {
  current: string | null;
  employee?: { id: number; name: string; overridden: boolean };
  orgDate?: string | null;
  onClose: () => void;
}) {
  const [date, setDate] = useState(current ?? '');
  const [clearing, setClearing] = useState(false);
  const proposed = clearing ? null : date || null;
  const changed = clearing || (!!date && date !== current);
  const { data: impact, isFetching, error } = useTrackingImpact(proposed, employee?.id, changed);
  const { mutate: save, isPending } = useSetTracking();

  const blocked = (impact?.blocked_months.length ?? 0) > 0;
  const range = impact?.first && impact.last ? `${longDate(impact.first)} to ${longDate(impact.last)}` : '';

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-surface border-border-brand">
        <DialogHeader>
          <DialogTitle>{employee ? `Tracking for ${employee.name}` : 'Attendance tracking start'}</DialogTitle>
          <DialogDescription>
            Days before this date show as Not tracked: they are not counted, never need attention and are never sent to payroll.
            {employee && ` Without their own date, ${employee.name} follows the organisation's (${longDate(orgDate ?? null)}).`}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-sm">
          <label className="flex flex-wrap items-center gap-2 text-xs font-medium text-text-secondary">
            Tracked from
            <input type="date" value={clearing ? '' : date} disabled={clearing} onChange={(e) => setDate(e.target.value)}
              className={cn(field, 'font-mono')} aria-label="Tracked from" />
          </label>
          {employee?.overridden && (
            <label className="flex items-center gap-2 text-xs text-text-secondary">
              <input type="checkbox" checked={clearing} onChange={(e) => setClearing(e.target.checked)} className="accent-[var(--color-accent)]" />
              Follow the organisation date again
            </label>
          )}

          {changed && (
            <div className="rounded-md border border-border-brand bg-bg-subtle p-3 text-xs">
              {isFetching && !impact ? (
                <p className="text-text-muted">Working out what changes…</p>
              ) : error ? (
                <p className="text-rose-600">{(error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Could not work out the impact.'}</p>
              ) : impact && impact.direction === 'same' ? (
                <p className="text-text-muted">No change.</p>
              ) : impact && blocked ? (
                <p className="flex gap-2 text-rose-600">
                  <Ban className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>
                    {`Payroll for ${impact.blocked_months.map((b) => MONTH.format(new Date(b.year, b.month - 1, 1))).join(', ')} is `
                      + `already approved, and this would turn days up to ${longDate(impact.blocked_months.map((b) => b.frozen_through).sort().slice(-1)[0])} `
                      + 'into absences. Choose a later date.'}
                  </span>
                </p>
              ) : impact && impact.direction === 'earlier' ? (
                <p className="flex gap-2 text-amber-700 dark:text-amber-400">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>
                    Starts tracking {range}: {impact.working_days} working day{impact.working_days === 1 ? '' : 's'} across{' '}
                    {impact.employees} employee{impact.employees === 1 ? '' : 's'}.{' '}
                    {impact.absences + impact.missing_clock_outs > 0
                      ? `${impact.absences} absence${impact.absences === 1 ? '' : 's'} and ${impact.missing_clock_outs} missing clock-out${impact.missing_clock_outs === 1 ? '' : 's'} will appear in needs attention, and absences can reach payroll when the month is closed.`
                      : 'No absences or missing clock-outs would appear.'}
                  </span>
                </p>
              ) : impact ? (
                <p className="text-text-secondary">
                  Stops tracking {range}
                  {impact.working_days > 0
                    ? `: ${impact.working_days} working day${impact.working_days === 1 ? '' : 's'} so far, including ${impact.absences} absence${impact.absences === 1 ? '' : 's'}, will show as Not tracked.`
                    : '.'}
                </p>
              ) : null}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            onClick={() => save({ employeeId: employee?.id, date: proposed }, { onSuccess: onClose })}
            disabled={!changed || !impact || isFetching || blocked || impact.direction === 'same' || isPending}
            className="bg-accent text-white hover:bg-accent/90"
          >
            {isPending ? 'Saving…' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
