'use client';

import { AlertTriangle, Loader2, Lock, LockOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { useCloseMonth, useClosePreview, useReopenMonth } from '@/hooks/useHR';
import { localDate } from './dayStatus';

const MONTH = new Intl.DateTimeFormat('en-LK', { month: 'long', year: 'numeric' });
const DAY = new Intl.DateTimeFormat('en-LK', { day: 'numeric', month: 'short' });
const fmt = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));

/**
 * Close a past month (step 5): records each employee's payable absences,
 * which the next payroll deducts in arrears, and freezes the month. Or
 * reopen a closed one, until a payroll that took its absences is approved.
 */
export function CloseMonthDialog({ year, month, onClose }: { year: number; month: number; onClose: () => void }) {
  const period = MONTH.format(new Date(year, month - 1, 1));
  const { data, isLoading, error } = useClosePreview(year, month, true);
  const { mutate: close, isPending: isClosing } = useCloseMonth();
  const { mutate: reopen, isPending: isReopening } = useReopenMonth();
  const closed = data?.status === 'Closed';

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-surface border-border-brand sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{closed ? `${period} is closed` : `Close ${period}?`}</DialogTitle>
          <DialogDescription>
            {closed
              ? 'Its attendance is frozen and its absences are recorded for the next payroll.'
              : "Closing freezes the month's attendance and records each person's absences. The next payroll "
                + 'generated deducts them at base salary ÷ 30.'}
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <p className="flex items-center gap-2 text-sm text-text-secondary"><Loader2 className="h-4 w-4 animate-spin" /> Checking the month…</p>
        ) : error || !data ? (
          <p className="text-sm text-negative">Could not check the month.</p>
        ) : (
          <div className="space-y-3 text-sm">
            {!closed && data.blocks.length > 0 && (
              <div className="space-y-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-text-secondary">
                <p className="flex items-center gap-2 font-semibold text-text-primary">
                  <AlertTriangle className="h-4 w-4 text-amber-600" /> Not ready to close
                </p>
                <ul className="list-disc space-y-0.5 pl-5">{data.blocks.map((b) => <li key={b}>{b}</li>)}</ul>
                {(data.missing_clock_outs.length > 0 || data.pending_corrections.length > 0) && (
                  <ul className="space-y-0.5 pl-5 text-[11px]">
                    {data.missing_clock_outs.slice(0, 8).map((m) => (
                      <li key={`m-${m.employee_id}-${m.date}`}>{m.employee_name}, {DAY.format(localDate(m.date))}: missing clock-out</li>
                    ))}
                    {data.pending_corrections.slice(0, 8).map((p) => (
                      <li key={`c-${p.id}`}>{p.employee_name}, {DAY.format(localDate(p.date))}: correction waiting</li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            <div className="rounded-md border border-border-brand bg-bg-subtle p-3 text-xs">
              <p className="font-semibold text-text-primary">
                {data.absences.length
                  ? `${fmt(data.absent_days_total)} absent day${data.absent_days_total === 1 ? '' : 's'} across ${data.absences.length} employee${data.absences.length === 1 ? '' : 's'}`
                  : 'No absences to record.'}
              </p>
              {data.absences.length > 0 && (
                <ul className="mt-1 max-h-48 space-y-0.5 overflow-y-auto text-text-secondary">
                  {data.absences.map((a) => (
                    <li key={a.employee_id} className="flex justify-between gap-2">
                      <span>{a.employee_name}</span>
                      <span className="font-mono">{fmt(a.absent_days)} day{a.absent_days === 1 ? '' : 's'}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {closed && data.reopen_block && <p className="text-xs text-text-muted">{data.reopen_block}</p>}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          {data && closed ? (
            <Button onClick={() => reopen({ year, month }, { onSuccess: onClose })} disabled={!data.can_reopen || isReopening}
              variant="outline" className="gap-1.5 border-border-brand">
              <LockOpen className="h-4 w-4" /> {isReopening ? 'Reopening…' : 'Reopen month'}
            </Button>
          ) : (
            <Button onClick={() => close({ year, month }, { onSuccess: onClose })} disabled={!data?.can_close || isClosing}
              className="gap-1.5 bg-accent text-white hover:bg-accent/90">
              <Lock className="h-4 w-4" /> {isClosing ? 'Closing…' : 'Close month'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
