'use client';

import { useState } from 'react';
import { AlertTriangle, Check, ClipboardList, Plus, Scale, X } from 'lucide-react';
import ProtectedRoute from '@/components/layout/protected-route';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { LeaveForm, StatusBadge, dateRange, field, fmtDays } from '@/components/leave/LeaveForm';
import {
  useAdjustEntitlement, useApproveLeave, useEntitlements, useGenerateEntitlements, useLeaveRequests,
  useMyLeave, useRejectLeave, useSetDateJoined,
} from '@/hooks/useLeave';
import { useEmployees } from '@/hooks/useHR';
import { useAuthStore } from '@/store/useAuthStore';
import { hasPermission } from '@/lib/permissions';
import { cn } from '@/lib/utils';
import { LeaveBalance, LeaveRequest, LeaveStatus } from '@/types';

export default function HRLeavePage() {
  return (
    <ProtectedRoute requiredPermission="leave:approve">
      <Leave />
    </ProtectedRoute>
  );
}

function Leave() {
  const [tab, setTab] = useState<'requests' | 'entitlements'>('requests');
  return (
    <div className="space-y-6 pb-12">
      <div>
        <h1 className="text-3xl font-bold font-heading tracking-tight mb-2 text-text-primary">Leave</h1>
        <p className="text-text-secondary text-sm">Approve requests and manage each person&apos;s yearly allowance.</p>
      </div>
      <div className="flex w-fit gap-1 rounded-lg border border-border-brand bg-bg-subtle p-1" role="tablist">
        {([['requests', 'Requests', ClipboardList], ['entitlements', 'Entitlements', Scale]] as const).map(([value, label, Icon]) => (
          <button key={value} role="tab" aria-selected={tab === value} onClick={() => setTab(value)}
            className={cn('flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
              tab === value ? 'bg-surface text-accent shadow-xs' : 'text-text-secondary hover:text-text-primary')}>
            <Icon className="h-3.5 w-3.5" /> {label}
          </button>
        ))}
      </div>
      {tab === 'requests' ? <RequestsTab /> : <EntitlementsTab />}
    </div>
  );
}

// --------------------------------------------------------------------------
// Requests
// --------------------------------------------------------------------------

const FILTERS: (LeaveStatus | 'All')[] = ['Pending', 'Approved', 'Rejected', 'Cancelled', 'All'];

function RequestsTab() {
  const [status, setStatus] = useState<LeaveStatus | 'All'>('Pending');
  const [recording, setRecording] = useState(false);
  const [rejecting, setRejecting] = useState<LeaveRequest | null>(null);
  const [note, setNote] = useState('');
  const { data: requests, isLoading } = useLeaveRequests(status === 'All' ? undefined : status);
  const { data: me } = useMyLeave();
  const { data: employees } = useEmployees();
  const { user } = useAuthStore();
  const { mutate: approve, isPending: isApproving, variables: approvingVars } = useApproveLeave();
  const { mutate: reject, isPending: isRejecting } = useRejectLeave();

  // The server refuses these too; disabling them here explains why up front.
  const ownReason = (r: LeaveRequest) =>
    me && r.employee_id === me.employee_id ? 'This is your own leave; someone else must decide it.'
      : r.requested_by && r.requested_by === user?.id ? 'You filed this request; someone else must decide it.'
        : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1">
          {FILTERS.map((f) => (
            <button key={f} onClick={() => setStatus(f)} aria-pressed={status === f}
              className={cn('rounded-md px-3 py-1.5 text-xs font-semibold',
                status === f ? 'bg-accent/10 text-accent ring-1 ring-accent/40' : 'text-text-secondary hover:bg-bg-subtle')}>
              {f}
            </button>
          ))}
        </div>
        <Button variant="outline" onClick={() => setRecording(true)} className="gap-2 border-border-brand">
          <Plus className="h-4 w-4" /> Record leave for someone
        </Button>
      </div>

      <Card className="bg-surface border border-border-brand rounded-card shadow-card">
        <CardContent className="p-0">
          {isLoading ? (
            <Skeleton className="m-4 h-32 bg-bg-subtle" />
          ) : !requests?.length ? (
            <p className="py-12 text-center text-sm text-text-muted">
              {status === 'Pending' ? 'Nothing waiting for a decision.' : 'No requests.'}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-bg-subtle/60 text-[11px] uppercase tracking-wider text-text-secondary">
                  <tr>
                    <th className="px-4 py-2.5 font-semibold">Employee</th>
                    <th className="px-4 py-2.5 font-semibold">Type</th>
                    <th className="px-4 py-2.5 font-semibold">Dates</th>
                    <th className="px-4 py-2.5 text-right font-semibold">Days</th>
                    <th className="px-4 py-2.5 font-semibold">Reason</th>
                    <th className="px-4 py-2.5 font-semibold">Status</th>
                    <th className="px-4 py-2.5"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-brand">
                  {requests.map((r) => {
                    const own = ownReason(r);
                    return (
                      <tr key={r.id}>
                        <td className="px-4 py-2.5 text-text-primary">{r.employee_name}</td>
                        <td className="px-4 py-2.5 text-text-secondary">{r.leave_types?.name}</td>
                        <td className="whitespace-nowrap px-4 py-2.5 text-text-primary">{dateRange(r)}</td>
                        <td className="px-4 py-2.5 text-right font-mono tabular-nums">{fmtDays(Number(r.days))}</td>
                        <td className="max-w-[220px] truncate px-4 py-2.5 text-text-secondary" title={r.reason ?? undefined}>{r.reason ?? '—'}</td>
                        <td className="px-4 py-2.5">
                          <StatusBadge status={r.status} />
                          {r.decision_note && <p className="mt-1 max-w-[200px] text-xs text-text-muted">{r.decision_note}</p>}
                        </td>
                        <td className="whitespace-nowrap px-4 py-2.5 text-right">
                          {r.status === 'Pending' && (
                            own ? (
                              <span className="text-xs text-text-muted" title={own}>Needs another approver</span>
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
                            )
                          )}
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

      <Dialog open={recording} onOpenChange={setRecording}>
        <DialogContent className="bg-surface border-border-brand sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Record leave for someone</DialogTitle>
            <DialogDescription>For leave staff can&apos;t request themselves, such as maternity. It still needs a second person to approve it.</DialogDescription>
          </DialogHeader>
          <LeaveForm
            employees={(employees ?? []).filter((e) => e.status === 'Active').map((e) => ({ id: e.id, name: `${e.first_name} ${e.last_name}` }))}
            onDone={() => setRecording(false)}
          />
        </DialogContent>
      </Dialog>

      <Dialog open={!!rejecting} onOpenChange={(o) => !o && setRejecting(null)}>
        <DialogContent className="bg-surface border-border-brand">
          <DialogHeader>
            <DialogTitle>Reject {rejecting?.employee_name}&apos;s leave?</DialogTitle>
            <DialogDescription>{rejecting && `${rejecting.leave_types?.name}, ${dateRange(rejecting)}. They'll see your reason.`}</DialogDescription>
          </DialogHeader>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={500}
            placeholder="Reason" className={cn(field, 'h-auto py-2')} />
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

// --------------------------------------------------------------------------
// Entitlements
// --------------------------------------------------------------------------

function JoinDateRow({ employeeId, name, canEdit }: { employeeId: number; name: string; canEdit: boolean }) {
  const [value, setValue] = useState('');
  const { mutate: save, isPending } = useSetDateJoined();
  return (
    <li className="flex flex-wrap items-center gap-2 py-1.5">
      <span className="min-w-[160px] text-text-primary">{name}</span>
      {canEdit && (
        <>
          <input type="date" value={value} onChange={(e) => setValue(e.target.value)} aria-label={`Join date for ${name}`}
            className={cn(field, 'h-8 w-auto font-mono')} />
          <Button size="sm" disabled={!value || isPending} onClick={() => save({ employeeId, date: value })}
            className="h-8 bg-accent px-3 text-xs text-white hover:bg-accent/90">Save</Button>
        </>
      )}
    </li>
  );
}

function EntitlementsTab() {
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const [adjusting, setAdjusting] = useState<{ name: string; balance: LeaveBalance } | null>(null);
  const [adjustment, setAdjustment] = useState('0');
  const [adjustNote, setAdjustNote] = useState('');
  const { data, isLoading } = useEntitlements(year);
  const { mutate: generate, isPending: isGenerating } = useGenerateEntitlements();
  const { mutate: adjust, isPending: isAdjusting } = useAdjustEntitlement();
  // The viewer's own row: nobody adjusts their own allowance (the server refuses).
  const { data: me } = useMyLeave();
  const { user } = useAuthStore();
  const canSetJoinDate = hasPermission(user?.role as string, 'hr:manage');
  const columns = data?.employees[0]?.balances ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <select value={year} onChange={(e) => setYear(Number(e.target.value))} aria-label="Year" className={cn(field, 'w-auto')}>
          {[thisYear - 1, thisYear, thisYear + 1].map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
        <Button onClick={() => generate(year)} disabled={isGenerating} className="bg-accent text-white hover:bg-accent/90">
          {isGenerating ? 'Generating…' : `Generate ${year} entitlements`}
        </Button>
      </div>

      {data && data.needs_date_joined.length > 0 && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm">
          <p className="flex items-center gap-2 font-semibold text-text-primary">
            <AlertTriangle className="h-4 w-4 text-amber-600" />
            {data.needs_date_joined.length} {data.needs_date_joined.length === 1 ? 'person has' : 'people have'} no join date
          </p>
          <p className="mt-1 text-xs text-text-secondary">
            Annual and casual leave depend on when someone joined (Shop and Office Employees Act s.6), so they are not set up
            for these people. Add the date, then generate again; nothing already set up is changed.
          </p>
          <ul className="mt-2 divide-y divide-amber-500/20">
            {data.needs_date_joined.map((e) => (
              <JoinDateRow key={e.employee_id} employeeId={e.employee_id} name={e.employee_name} canEdit={canSetJoinDate} />
            ))}
          </ul>
        </div>
      )}

      <Card className="bg-surface border border-border-brand rounded-card shadow-card">
        <CardContent className="p-0">
          {isLoading ? (
            <Skeleton className="m-4 h-32 bg-bg-subtle" />
          ) : !data?.employees.length ? (
            <p className="py-12 text-center text-sm text-text-muted">No active employees.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-bg-subtle/60 text-[11px] uppercase tracking-wider text-text-secondary">
                  <tr>
                    <th className="px-4 py-2.5 font-semibold">Employee</th>
                    <th className="px-4 py-2.5 font-semibold">Joined</th>
                    {columns.map((c) => <th key={c.leave_type_id} className="px-4 py-2.5 font-semibold">{c.name}</th>)}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-brand">
                  {data.employees.map((e) => (
                    <tr key={e.employee_id}>
                      <td className="px-4 py-2.5 text-text-primary">{e.employee_name}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-text-secondary">{e.date_joined ?? '—'}</td>
                      {e.balances.map((b) => (
                        <td key={b.leave_type_id} className="px-4 py-2.5">
                          {b.set_up && me?.employee_id === e.employee_id ? (
                            <span title="Your own allowance; another HR officer adjusts it.">
                              <span className="font-mono tabular-nums text-text-primary">{fmtDays(b.available)}</span>
                              <span className="text-xs text-text-muted"> / {fmtDays(b.total)}</span>
                            </span>
                          ) : b.set_up ? (
                            <button onClick={() => { setAdjusting({ name: e.employee_name, balance: b }); setAdjustment(String(b.adjustment ?? 0)); setAdjustNote(b.note ?? ''); }}
                              className="text-left hover:underline" title="Adjust">
                              <span className="font-mono tabular-nums text-text-primary">{fmtDays(b.available)}</span>
                              <span className="text-xs text-text-muted"> / {fmtDays(b.total)}</span>
                              {!!b.pending && <span className="block text-[10px] text-amber-600">{fmtDays(b.pending)} pending</span>}
                            </button>
                          ) : (
                            <span className="text-xs text-text-muted">not set up</span>
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
      <p className="text-xs text-text-muted">
        Shown as days available / total. Total = allowance + carried over + adjustment. Click a figure to adjust it.
      </p>

      <Dialog open={!!adjusting} onOpenChange={(o) => !o && setAdjusting(null)}>
        <DialogContent className="bg-surface border-border-brand">
          <DialogHeader>
            <DialogTitle>{adjusting?.name}: {adjusting?.balance.name}, {year}</DialogTitle>
            <DialogDescription>
              {adjusting && `Allowance ${fmtDays(adjusting.balance.entitled)}, carried over ${fmtDays(adjusting.balance.carried_forward)}. An adjustment adds or removes days on top, with a note for the record.`}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-[120px_1fr]">
            <label className="space-y-1 text-xs font-medium text-text-secondary">
              Adjustment
              <input type="number" step="0.5" value={adjustment} onChange={(e) => setAdjustment(e.target.value)} className={field} />
            </label>
            <label className="space-y-1 text-xs font-medium text-text-secondary">
              Note
              <input value={adjustNote} onChange={(e) => setAdjustNote(e.target.value)} maxLength={200} className={field} placeholder="e.g. Approved by Director, email 3 Nov" />
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAdjusting(null)} disabled={isAdjusting}>Cancel</Button>
            <Button
              onClick={() => adjusting?.balance.entitlement_id &&
                adjust({ id: adjusting.balance.entitlement_id, adjustment: Number(adjustment), note: adjustNote || undefined },
                  { onSuccess: () => setAdjusting(null) })}
              disabled={isAdjusting || Number.isNaN(Number(adjustment))}
              className="bg-accent text-white hover:bg-accent/90">
              {isAdjusting ? 'Saving…' : 'Save'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
