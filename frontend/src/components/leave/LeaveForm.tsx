'use client';

import { useState } from 'react';
import { AlertTriangle, CalendarCheck, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useLeavePreview, useLeaveTypes, useRequestLeave } from '@/hooks/useLeave';
import { LeaveBalance, LeaveInput, LeaveRequest, LeaveStatus } from '@/types';
import { toISODate } from '@/lib/finance-periods';
import { cn } from '@/lib/utils';

export const field =
  'h-9 w-full rounded-md border border-border-brand bg-surface px-2 text-sm text-text-primary outline-none focus:border-accent';

const DAY = new Intl.DateTimeFormat('en-LK', { weekday: 'short', day: 'numeric', month: 'short' });

export function localDate(iso: string) {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(y, m - 1, d);
}

export const fmtDays = (n: number | undefined) => (n === undefined ? '—' : Number.isInteger(n) ? String(n) : n.toFixed(1));

export function dateRange(r: Pick<LeaveRequest, 'start_date' | 'end_date' | 'half_day'>) {
  const start = DAY.format(localDate(r.start_date));
  if (r.start_date === r.end_date) return r.half_day === 'none' ? start : `${start} (${r.half_day === 'am' ? 'morning' : 'afternoon'})`;
  return `${start} – ${DAY.format(localDate(r.end_date))}`;
}

export function StatusBadge({ status }: { status: LeaveStatus }) {
  return (
    <span
      className={cn(
        'inline-block rounded-full px-2 py-0.5 text-[11px] font-medium',
        status === 'Pending' && 'bg-amber-500/10 text-amber-600',
        status === 'Approved' && 'bg-emerald-500/10 text-emerald-600',
        status === 'Rejected' && 'bg-rose-500/10 text-rose-500',
        status === 'Cancelled' && 'bg-bg-subtle text-text-muted',
      )}
    >
      {status}
    </span>
  );
}

export function BalanceCards({ balances }: { balances: LeaveBalance[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {balances.map((b) => (
        <div key={b.leave_type_id} className="rounded-lg border border-border-brand bg-surface p-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-text-secondary">{b.name}</p>
          {b.set_up ? (
            <>
              <p className="mt-1 text-2xl font-bold text-text-primary">
                {fmtDays(b.available)} <span className="text-sm font-normal text-text-secondary">of {fmtDays(b.total)} days left</span>
              </p>
              <p className="mt-1 text-xs text-text-muted">
                {fmtDays(b.approved)} taken{b.pending ? ` · ${fmtDays(b.pending)} pending` : ''}
                {b.carried_forward ? ` · ${fmtDays(b.carried_forward)} carried over` : ''}
              </p>
              {b.earned_to_date != null && b.entitled !== undefined && b.earned_to_date < b.entitled && (
                <p className="mt-1 text-xs text-text-muted">
                  {fmtDays(b.earned_to_date)} earned so far · {fmtDays(b.entitled)} by year end (one day per two complete months)
                </p>
              )}
            </>
          ) : (
            <p className="mt-1 text-sm text-text-muted">Not set up for this year yet.</p>
          )}
        </div>
      ))}
    </div>
  );
}

// --------------------------------------------------------------------------
// Request form
// --------------------------------------------------------------------------

export function LeaveForm({
  employees,
  onDone,
}: {
  // When given, HR files on someone's behalf and picks who.
  employees?: { id: number; name: string }[];
  onDone?: () => void;
}) {
  const { data: types } = useLeaveTypes();
  const today = toISODate(new Date());
  const [employeeId, setEmployeeId] = useState<number | undefined>(undefined);
  const [typeId, setTypeId] = useState<number | undefined>(undefined);
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState(today);
  const [half, setHalf] = useState<'none' | 'am' | 'pm'>('none');
  const [reason, setReason] = useState('');
  const { mutate: submit, isPending } = useRequestLeave();

  const type = types?.find((t) => t.id === typeId);
  const singleDay = start === end;
  const halfAllowed = !!type?.allow_half_day && singleDay;
  const effectiveHalf = halfAllowed ? half : 'none';

  const ready = !!typeId && !!start && !!end && end >= start && (!employees || !!employeeId);
  const body: LeaveInput | null = ready
    ? { leave_type_id: typeId!, start_date: start, end_date: end, half_day: effectiveHalf, reason: reason || undefined, employee_id: employeeId }
    : null;
  const { data: preview, isFetching } = useLeavePreview(body);

  const blocked = !body || !preview || preview.errors.length > 0 || isFetching;

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        {employees && (
          <label className="space-y-1 text-xs font-medium text-text-secondary sm:col-span-2">
            Employee
            <select value={employeeId ?? ''} onChange={(e) => setEmployeeId(Number(e.target.value) || undefined)} className={field}>
              <option value="">Choose…</option>
              {employees.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
            </select>
          </label>
        )}
        <label className="space-y-1 text-xs font-medium text-text-secondary sm:col-span-2">
          Type of leave
          <select value={typeId ?? ''} onChange={(e) => setTypeId(Number(e.target.value) || undefined)} className={field}>
            <option value="">Choose…</option>
            {types?.map((t) => <option key={t.id} value={t.id}>{t.name}{!t.is_paid ? ' (unpaid)' : ''}</option>)}
          </select>
        </label>
        <label className="space-y-1 text-xs font-medium text-text-secondary">
          From
          <input type="date" value={start} onChange={(e) => { setStart(e.target.value); if (e.target.value > end) setEnd(e.target.value); }} className={cn(field, 'font-mono')} />
        </label>
        <label className="space-y-1 text-xs font-medium text-text-secondary">
          To
          <input type="date" value={end} min={start} onChange={(e) => setEnd(e.target.value)} className={cn(field, 'font-mono')} />
        </label>
        {halfAllowed && (
          <label className="space-y-1 text-xs font-medium text-text-secondary sm:col-span-2">
            Length
            <select value={half} onChange={(e) => setHalf(e.target.value as typeof half)} className={field}>
              <option value="none">Full day</option>
              <option value="am">Morning only</option>
              <option value="pm">Afternoon only</option>
            </select>
          </label>
        )}
        <label className="space-y-1 text-xs font-medium text-text-secondary sm:col-span-2">
          Reason <span className="font-normal text-text-muted">(optional)</span>
          <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} className={field} />
        </label>
      </div>

      {body && (
        <div className="rounded-lg border border-border-brand bg-bg-subtle p-3 text-sm">
          {!preview ? (
            <p className="flex items-center gap-2 text-text-secondary"><Loader2 className="h-4 w-4 animate-spin" /> Counting days…</p>
          ) : (
            <div className={cn('space-y-2 transition-opacity', isFetching && 'opacity-60')}>
              <p className="flex items-center gap-2 text-text-primary">
                <CalendarCheck className="h-4 w-4 text-accent" />
                <span className="font-semibold">{fmtDays(preview.total)} {preview.total === 1 ? 'day' : 'days'}</span>
                {type && !type.counts_calendar_days && <span className="text-xs text-text-secondary">working days on your schedule; weekends and holidays don&apos;t count</span>}
              </p>
              {preview.days.length > 0 && preview.days.length <= 14 && (
                <p className="text-xs text-text-secondary">{preview.days.map((d) => DAY.format(localDate(d.date))).join(' · ')}</p>
              )}
              {Object.entries(preview.balances).map(([year, b]) => b && (
                <p key={year} className="text-xs text-text-secondary">
                  {year}: {fmtDays(b.available)} available → <span className="font-semibold text-text-primary">{fmtDays(b.after)}</span> after this
                </p>
              ))}
              {preview.errors.map((e) => (
                <p key={e} className="flex items-start gap-2 text-xs text-rose-500"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {e}</p>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="flex justify-end">
        <Button
          onClick={() => body && submit(body, { onSuccess: () => { setReason(''); onDone?.(); } })}
          disabled={blocked || isPending}
          className="bg-accent text-white hover:bg-accent/90"
        >
          {isPending ? 'Submitting…' : employees ? 'Record leave' : 'Request leave'}
        </Button>
      </div>
    </div>
  );
}
