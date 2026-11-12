'use client';

import { useState } from 'react';
import { Check, ClipboardEdit, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import {
  useApproveCorrection, useCancelCorrection, useCorrections, useMyCorrections, useRejectCorrection,
} from '@/hooks/useHR';
import { useAuthStore } from '@/store/useAuthStore';
import { cn } from '@/lib/utils';
import { CorrectionRequest, CorrectionStatus } from '@/types';
import { hhmm, localDate } from './dayStatus';

const DAY = new Intl.DateTimeFormat('en-LK', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
const field =
  'w-full rounded-md border border-border-brand bg-surface px-2 py-2 text-sm text-text-primary outline-none focus:border-accent';

function StatusBadge({ status }: { status: CorrectionStatus }) {
  return (
    <span className={cn('inline-block rounded-full px-2 py-0.5 text-[11px] font-medium',
      status === 'Pending' && 'bg-amber-500/10 text-amber-600',
      status === 'Approved' && 'bg-emerald-500/10 text-emerald-600',
      status === 'Rejected' && 'bg-rose-500/10 text-rose-500',
      status === 'Cancelled' && 'bg-bg-subtle text-text-muted')}>
      {status}
    </span>
  );
}

// "08:30–17:00", with the requested ends (null = unchanged) laid over the old ones.
function times(clockIn: string | null | undefined, clockOut: string | null | undefined) {
  return `${hhmm(clockIn ?? null)}–${hhmm(clockOut ?? null)}`;
}

function Change({ r, currentIn, currentOut }: { r: CorrectionRequest; currentIn: string | null | undefined; currentOut: string | null | undefined }) {
  return (
    <span className="font-mono text-xs">
      <span className="text-text-muted">{times(currentIn, currentOut)}</span>
      {' → '}
      <span className="text-text-primary">{times(r.requested_clock_in ?? currentIn, r.requested_clock_out ?? currentOut)}</span>
    </span>
  );
}

// --------------------------------------------------------------------------
// My Attendance: one's own requests
// --------------------------------------------------------------------------

export function MyCorrections() {
  const { data, isLoading, error } = useMyCorrections();
  const { mutate: withdraw, isPending, variables } = useCancelCorrection();
  if (error) return null; // not linked: My Attendance says so elsewhere

  return (
    <Card className="border-border-brand bg-surface">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ClipboardEdit className="h-5 w-5 text-accent" /> My correction requests
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {isLoading ? (
          <Skeleton className="m-4 h-16" />
        ) : !data?.length ? (
          <p className="px-6 pb-6 text-sm text-text-muted">
            None yet. To fix a wrong or missing time, open the day in My month and ask HR to correct it.
          </p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="bg-bg-subtle/60 text-[11px] uppercase tracking-wider text-text-secondary">
              <tr>
                <th className="px-4 py-2.5 font-semibold">Day</th>
                <th className="px-4 py-2.5 font-semibold">Change</th>
                <th className="px-4 py-2.5 font-semibold">Status</th>
                <th className="px-4 py-2.5"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-brand">
              {data.map((r) => (
                <tr key={r.id}>
                  <td className="px-4 py-2.5 text-text-primary">{DAY.format(localDate(r.target_date))}</td>
                  <td className="px-4 py-2.5">
                    <Change r={r} currentIn={r.original_clock_in} currentOut={r.original_clock_out} />
                    <p className="text-xs text-text-muted">{r.reason}</p>
                  </td>
                  <td className="px-4 py-2.5">
                    <StatusBadge status={r.status} />
                    {r.decision_note && <p className="mt-1 text-xs text-text-muted">{r.decision_note}</p>}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    {r.status === 'Pending' && (
                      <Button variant="ghost" size="sm" disabled={isPending && variables === r.id} onClick={() => withdraw(r.id)}
                        className="h-7 px-2 text-xs text-text-secondary hover:text-negative">
                        Withdraw
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------------------
// HR: the Corrections tab
// --------------------------------------------------------------------------

const FILTERS: (CorrectionStatus | 'All')[] = ['Pending', 'Approved', 'Rejected', 'Cancelled', 'All'];

export function CorrectionsTab() {
  const [status, setStatus] = useState<CorrectionStatus | 'All'>('Pending');
  const [rejecting, setRejecting] = useState<CorrectionRequest | null>(null);
  const [note, setNote] = useState('');
  const { data, isLoading } = useCorrections(status === 'All' ? undefined : status);
  const { user } = useAuthStore();
  const { mutate: approve, isPending: isApproving, variables: approvingVars } = useApproveCorrection();
  const { mutate: reject, isPending: isRejecting } = useRejectCorrection();

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1">
        {FILTERS.map((f) => (
          <button key={f} onClick={() => setStatus(f)} aria-pressed={status === f}
            className={cn('rounded-md px-3 py-1.5 text-xs font-semibold',
              status === f ? 'bg-accent/10 text-accent ring-1 ring-accent/40' : 'text-text-secondary hover:bg-bg-subtle')}>
            {f}
          </button>
        ))}
      </div>

      <Card className="bg-surface border border-border-brand rounded-card shadow-card">
        <CardContent className="p-0">
          {isLoading ? (
            <Skeleton className="m-4 h-32 bg-bg-subtle" />
          ) : !data?.length ? (
            <p className="py-12 text-center text-sm text-text-muted">
              {status === 'Pending' ? 'No corrections waiting for a decision.' : 'No requests.'}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-bg-subtle/60 text-[11px] uppercase tracking-wider text-text-secondary">
                  <tr>
                    <th className="px-4 py-2.5 font-semibold">Employee</th>
                    <th className="px-4 py-2.5 font-semibold">Day</th>
                    <th className="px-4 py-2.5 font-semibold">Change</th>
                    <th className="px-4 py-2.5 font-semibold">Reason</th>
                    <th className="px-4 py-2.5 font-semibold">Status</th>
                    <th className="px-4 py-2.5"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-brand">
                  {data.map((r) => {
                    const own = r.employee_user_id === user?.id || r.requested_by === user?.id;
                    const pending = r.status === 'Pending';
                    return (
                      <tr key={r.id}>
                        <td className="px-4 py-2.5 text-text-primary">{r.employee_name}</td>
                        <td className="whitespace-nowrap px-4 py-2.5 text-text-primary">{DAY.format(localDate(r.target_date))}</td>
                        <td className="px-4 py-2.5">
                          <Change r={r}
                            currentIn={pending ? r.current_clock_in : r.original_clock_in}
                            currentOut={pending ? r.current_clock_out : r.original_clock_out} />
                          {pending && r.current_locked && <p className="text-[11px] text-text-muted">Locked: stays locked once approved</p>}
                        </td>
                        <td className="max-w-[240px] px-4 py-2.5 text-text-secondary">{r.reason}</td>
                        <td className="px-4 py-2.5">
                          <StatusBadge status={r.status} />
                          {r.decision_note && <p className="mt-1 max-w-[200px] text-xs text-text-muted">{r.decision_note}</p>}
                        </td>
                        <td className="whitespace-nowrap px-4 py-2.5 text-right">
                          {pending && (own ? (
                            <span className="text-xs text-text-muted" title="Nobody decides their own correction.">Needs another HR officer</span>
                          ) : (
                            <div className="flex justify-end gap-1">
                              <Button size="sm" disabled={isApproving && approvingVars?.id === r.id} onClick={() => approve({ id: r.id })}
                                className="h-7 gap-1 bg-emerald-600 px-2 text-xs text-white hover:bg-emerald-600/90">
                                <Check className="h-3.5 w-3.5" /> Approve
                              </Button>
                              <Button size="sm" variant="outline" onClick={() => { setRejecting(r); setNote(''); }}
                                className="h-7 gap-1 border-border-brand px-2 text-xs text-text-secondary hover:text-negative">
                                <X className="h-3.5 w-3.5" /> Reject
                              </Button>
                            </div>
                          ))}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={!!rejecting} onOpenChange={(o) => !o && setRejecting(null)}>
        <DialogContent className="bg-surface border-border-brand">
          <DialogHeader>
            <DialogTitle>{rejecting ? `Reject ${rejecting.employee_name}'s correction?` : ''}</DialogTitle>
            <DialogDescription>
              {rejecting && `${DAY.format(localDate(rejecting.target_date))}. They'll see your reason on My Attendance.`}
            </DialogDescription>
          </DialogHeader>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={500}
            placeholder="Reason" aria-label="Reason" className={field} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejecting(null)} disabled={isRejecting}>Cancel</Button>
            <Button onClick={() => rejecting && reject({ id: rejecting.id, note }, { onSuccess: () => setRejecting(null) })}
              disabled={!note.trim() || isRejecting} className="bg-negative text-white hover:bg-negative/90">
              {isRejecting ? 'Rejecting…' : 'Reject'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
