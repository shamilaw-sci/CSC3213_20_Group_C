'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  AlertTriangle, ArrowRight, CheckCircle2, Circle, FileClock, Loader2, RefreshCw, ShieldCheck, Users,
} from 'lucide-react';
import { useApprovePayroll, usePayrollRun, useRunPayroll } from '@/hooks/useHR';
import { useAuthStore } from '@/store/useAuthStore';
import ProtectedRoute from '@/components/layout/protected-route';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { hasPermission } from '@/lib/permissions';
import { formatLKR } from '@/lib/formatters';
import { cn } from '@/lib/utils';
import { colomboDate } from '@/components/hr/attendance/dayStatus';
import { PayrollDrift } from '@/types';

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const control =
  'h-9 rounded-md border border-border-brand bg-surface px-2 text-sm text-text-primary outline-none focus:border-accent';

function when(iso: string | null | undefined) {
  if (!iso) return '';
  return new Intl.DateTimeFormat('en-LK', {
    timeZone: 'Asia/Colombo', day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(new Date(iso));
}

// Generate -> Approve -> Paid (in the Ledger). Shows where this month is.
function Steps({ status, paid }: { status: 'none' | 'Draft' | 'Approved'; paid: boolean }) {
  const steps = [
    { label: 'Draft generated', done: status !== 'none' },
    { label: 'Approved', done: status === 'Approved' },
    // Done once Finance marks the payable paid; it never used to show.
    { label: 'Paid in Ledger', done: status === 'Approved' && paid },
  ];
  return (
    <ol className="flex flex-wrap items-center gap-2 text-xs">
      {steps.map((s, i) => (
        <li key={s.label} className="flex items-center gap-2">
          <span className={cn('flex items-center gap-1.5 font-medium', s.done ? 'text-positive' : 'text-text-muted')}>
            {s.done ? <CheckCircle2 className="h-4 w-4" /> : <Circle className="h-4 w-4" />}
            {s.label}
          </span>
          {i < steps.length - 1 && <ArrowRight className="h-3.5 w-3.5 text-text-muted" />}
        </li>
      ))}
    </ol>
  );
}

const CHANGE_LABEL: Record<PayrollDrift['change'], string> = {
  added: 'not on the draft',
  removed: 'no longer employed or not yet joined',
  salary: 'salary changed',
};

// What changed since the draft was generated. Approval is refused until the
// draft is regenerated: it used to post the old figures without a word.
function DriftNotice({ drift, canGenerate }: { drift: PayrollDrift[]; canGenerate: boolean }) {
  return (
    <div className="space-y-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-text-secondary">
      <p className="flex items-center gap-2 font-semibold text-text-primary">
        <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600" />
        This draft is out of date. {canGenerate ? 'Regenerate it' : 'Ask HR to regenerate it'} before it can be approved.
      </p>
      <ul className="space-y-1 pl-6">
        {drift.map((d) => (
          <li key={`${d.change}-${d.employee_id}`} className="list-disc">
            <span className="text-text-primary">{d.employee_name}</span>: {CHANGE_LABEL[d.change]}
            {d.change === 'salary' && d.draft_amount !== null && d.current_amount !== null
              && ` (${formatLKR(d.draft_amount)} on the draft, ${formatLKR(d.current_amount)} now)`}
            {d.change === 'added' && d.current_amount !== null && ` (${formatLKR(d.current_amount)})`}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function HRPayrollPage() {
  return (
    // Either permission: HR generates, Director approves.
    <ProtectedRoute requiredPermission={['payroll:generate', 'payroll:approve']}>
      <Payroll />
    </ProtectedRoute>
  );
}

function Payroll() {
  // Sri Lanka's month, as the server judges what can be generated and approved.
  const [thisYear, thisMonth] = colomboDate().split('-').map(Number);
  const [month, setMonth] = useState(thisMonth);
  const [year, setYear] = useState(thisYear);
  const [confirming, setConfirming] = useState(false);

  const { user } = useAuthStore();
  const role = user?.role as string;
  const canGenerate = hasPermission(role, 'payroll:generate');
  const canApprove = hasPermission(role, 'payroll:approve');
  const canOpenLedger = hasPermission(role, 'finance:read');

  const { data, isLoading, error } = usePayrollRun(month, year);
  const { mutate: generate, isPending: isGenerating } = useRunPayroll();
  const { mutate: approve, isPending: isApproving } = useApprovePayroll();

  const run = data?.run ?? null;
  const lines = data?.lines ?? [];
  const status = run ? run.status : 'none';
  const period = `${MONTHS[month - 1]} ${year}`;

  // The server refuses these too; saying so here saves a failed click.
  const generatedByMe = !!run?.generated_by && run.generated_by === user?.id;
  const drift = data?.drift ?? [];
  const paid = data?.payment_status === 'Cash';
  const approveBlocked = !!data?.approve_block || drift.length > 0 || generatedByMe;

  return (
    <div className="space-y-6 pb-12">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-3xl font-bold font-heading tracking-tight mb-2 text-text-primary">Payroll</h1>
          <p className="text-text-secondary text-sm">
            HR generates a draft, a second person approves it, and only then is it posted to the Ledger.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={month} onChange={(e) => setMonth(Number(e.target.value))} aria-label="Month" className={control}>
            {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
          <select value={year} onChange={(e) => setYear(Number(e.target.value))} aria-label="Year" className={control}>
            {[thisYear - 1, thisYear, thisYear + 1].map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
      </div>

      {error ? (
        <p className="rounded-lg border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-500">
          Failed to load payroll for {period}.
        </p>
      ) : isLoading || !data ? (
        <Skeleton className="h-64 w-full bg-bg-subtle" />
      ) : (
        <>
          <Card className="bg-surface border border-border-brand rounded-card shadow-card">
            <CardHeader className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <CardTitle className="text-base font-semibold font-heading text-text-primary">{period}</CardTitle>
                <CardDescription className="mt-2"><Steps status={status} paid={paid} /></CardDescription>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {canGenerate && status !== 'Approved' && !data.generate_block && (
                  <Button
                    variant={run ? 'outline' : 'default'}
                    onClick={() => generate({ month, year })}
                    disabled={isGenerating}
                    className={cn('gap-2', !run && 'bg-accent text-white hover:bg-accent/90 font-semibold')}
                  >
                    {isGenerating ? <Loader2 className="h-4 w-4 animate-spin" /> : run ? <RefreshCw className="h-4 w-4" /> : <FileClock className="h-4 w-4" />}
                    {run ? 'Regenerate draft' : 'Generate draft'}
                  </Button>
                )}
                {canApprove && status === 'Draft' && (
                  <Button
                    onClick={() => setConfirming(true)}
                    disabled={approveBlocked || isApproving}
                    title={
                      generatedByMe ? 'You generated this draft; someone else must approve it.'
                        : drift.length ? 'The draft is out of date; it has to be regenerated first.'
                        : data.approve_block ?? undefined
                    }
                    className="gap-2 bg-emerald-600 text-white hover:bg-emerald-600/90 font-semibold"
                  >
                    <ShieldCheck className="h-4 w-4" /> Approve
                  </Button>
                )}
              </div>
            </CardHeader>

            <CardContent className="space-y-4">
              {canGenerate && status !== 'Approved' && data.generate_block && (
                <p className="rounded-lg border border-border-brand bg-bg-subtle p-3 text-xs text-text-secondary">{data.generate_block}</p>
              )}
              {run?.status === 'Draft' && canApprove && data.approve_block && (
                <p className="rounded-lg border border-border-brand bg-bg-subtle p-3 text-xs text-text-secondary">{data.approve_block}</p>
              )}
              {run?.status === 'Draft' && drift.length > 0 && <DriftNotice drift={drift} canGenerate={canGenerate} />}
              {data.incomplete_attendance > 0 && status !== 'Approved' && (
                <p className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-text-secondary">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                  <span>
                    {data.incomplete_attendance} attendance record{data.incomplete_attendance === 1 ? ' has' : 's have'}{' '}
                    no clock-out this month. Pay is a fixed monthly salary, so this doesn&apos;t change the amounts, but the
                    records should be completed in Attendance.
                  </span>
                </p>
              )}

              {!run ? (
                <div className="py-10 text-center text-sm text-text-muted">
                  No payroll for {period} yet.
                  {!canGenerate && ' HR generates the draft; it will appear here for approval.'}
                </div>
              ) : (
                <>
                  <dl className="grid gap-4 text-sm sm:grid-cols-3">
                    <div className="rounded-lg border border-border-brand bg-bg-subtle p-4">
                      <dt className="text-xs font-semibold uppercase tracking-wider text-text-secondary">Total</dt>
                      <dd className="mt-1 text-2xl font-bold font-mono text-text-primary">{formatLKR(Number(run.total))}</dd>
                    </div>
                    <div className="rounded-lg border border-border-brand bg-bg-subtle p-4">
                      <dt className="text-xs font-semibold uppercase tracking-wider text-text-secondary">Employees</dt>
                      <dd className="mt-1 flex items-center gap-2 text-2xl font-bold text-text-primary">
                        <Users className="h-5 w-5 text-text-muted" /> {lines.length}
                      </dd>
                    </div>
                    <div className="rounded-lg border border-border-brand bg-bg-subtle p-4 text-xs text-text-secondary">
                      <dt className="font-semibold uppercase tracking-wider">Record</dt>
                      <dd className="mt-1 space-y-1">
                        <p>
                          Generated {when(run.generated_at)}
                          {run.generator?.email && <> by <span className="text-text-primary">{run.generator.email}</span></>}
                        </p>
                        {run.status === 'Approved' && (
                          <p>
                            Approved {when(run.approved_at)}
                            {run.approver?.email && <> by <span className="text-text-primary">{run.approver.email}</span></>}
                          </p>
                        )}
                      </dd>
                    </div>
                  </dl>

                  {run.status === 'Approved' && (
                    <p className="flex flex-wrap items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-text-secondary">
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      Approved and frozen.
                      {!run.finance_transaction_id
                        ? <> Generated before approvals existed; its expense was posted directly at the time.</>
                        : paid
                          ? <> Posted to the Ledger as #{run.finance_transaction_id} and marked paid.</>
                          : data.payment_status === 'Voided'
                            ? <> Its Ledger entry #{run.finance_transaction_id} has been voided.</>
                            : <> Posted to the Ledger as payable #{run.finance_transaction_id}; Finance marks it paid once salaries are transferred.</>}
                      {canOpenLedger && run.finance_transaction_id && !paid && (
                        <Link
                          href="/finance/ledger?status=Receivable&type=Expense&sort=oldest"
                          className="font-semibold text-accent hover:underline"
                        >
                          Open payables in the Ledger
                        </Link>
                      )}
                    </p>
                  )}

                  <div className="overflow-x-auto rounded-lg border border-border-brand">
                    <table className="w-full text-left text-sm">
                      <thead className="bg-bg-subtle/60 text-[11px] uppercase tracking-wider text-text-secondary">
                        <tr>
                          <th className="px-4 py-3 font-semibold">Employee</th>
                          <th className="px-4 py-3 font-semibold">NIC</th>
                          <th className="px-4 py-3 text-right font-semibold">Net pay</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border-brand">
                        {lines.map((l) => (
                          <tr key={l.id}>
                            <td className="px-4 py-3 text-text-primary">{l.employee_name}</td>
                            <td className="px-4 py-3 font-mono text-xs text-text-secondary">{l.nic ?? '—'}</td>
                            <td className="px-4 py-3 text-right font-mono tabular-nums text-text-primary">{formatLKR(l.net_payable)}</td>
                          </tr>
                        ))}
                      </tbody>
                      <tfoot className="border-t-2 border-border-brand">
                        <tr>
                          <td className="px-4 py-3 font-semibold text-text-primary" colSpan={2}>Total</td>
                          <td className="px-4 py-3 text-right font-mono font-semibold tabular-nums text-text-primary">
                            {formatLKR(Number(run.total))}
                          </td>
                        </tr>
                      </tfoot>
                    </table>
                  </div>

                  {run.status === 'Draft' && (
                    <p className="text-xs text-text-muted">
                      Net pay is each employee&apos;s base salary. Regenerate after correcting a salary in Employees;
                      the draft is replaced, not duplicated.
                      {canApprove && generatedByMe && ' You generated this draft, so someone else must approve it.'}
                    </p>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        </>
      )}

      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent className="bg-surface border-border-brand">
          <DialogHeader>
            <DialogTitle>Approve payroll for {period}?</DialogTitle>
            <DialogDescription>
              {run && (
                <>
                  {formatLKR(Number(run.total))} for {lines.length} employee{lines.length === 1 ? '' : 's'}. Approving freezes
                  this payroll and posts the total to the Ledger as a payable dated the last day of {MONTHS[month - 1]}.
                  It can&apos;t be regenerated afterwards.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirming(false)} disabled={isApproving}>Cancel</Button>
            <Button
              onClick={() => run && approve(run.id, { onSettled: () => setConfirming(false) })}
              disabled={isApproving}
              className="bg-emerald-600 text-white hover:bg-emerald-600/90"
            >
              {isApproving ? 'Approving…' : 'Approve and post'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
