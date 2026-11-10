// frontend/src/app/(dashboard)/donations/page.tsx
//
// Donation details: analytics at the top, then every donor's contribution,
// then every donation. Only paid donations count as money raised; pending,
// failed and cancelled ones are listed but never added to a total, because
// they never reached the ledger.
'use client';

import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { AlertTriangle, Download, EyeOff, Lock, RefreshCw, Search } from 'lucide-react';
import ProtectedRoute from '@/components/layout/protected-route';
import {
  DonationsService,
  type Donation,
  type DonationPurpose,
  type DonationStatus,
} from '@/services/donations.service';
import { KPICard } from '@/components/shared/kpi-card';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { formatDate, formatLKR, formatTime } from '@/lib/formatters';
import { buildCsv, downloadCsv } from '@/lib/csv';
import { cn, getErrorMessage } from '@/lib/utils';

const STATUS_STYLE: Record<DonationStatus, string> = {
  paid: 'bg-green-500/10 text-positive border-green-500/20',
  pending: 'bg-amber-500/10 text-amber-600 border-amber-500/20',
  failed: 'bg-red-500/10 text-negative border-red-500/20',
  cancelled: 'bg-bg-subtle text-text-secondary border-border-brand',
  refunded: 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20',
};

const STATUS_LABEL: Record<DonationStatus, string> = {
  paid: 'Paid',
  pending: 'Awaiting payment',
  failed: 'Failed',
  cancelled: 'Cancelled',
  refunded: 'Refunded',
};

// The list filter also offers "expired": pending rows over a day old.
type StatusFilter = DonationStatus | 'expired' | '';

const PAGE_SIZE = 200;

function statusLabel(d: Donation): string {
  return d.expired ? 'Expired (never paid)' : STATUS_LABEL[d.status];
}

const control =
  'h-9 rounded-md border border-border-brand bg-surface px-2 text-sm text-text-primary';

const tableHead =
  'bg-bg-subtle/60 [&_th]:text-[11px] [&_th]:uppercase [&_th]:tracking-wider [&_th]:font-semibold [&_th]:text-text-secondary [&_th:first-child]:pl-5 [&_th:last-child]:pr-5';

function money(value: string | number | null | undefined): string {
  return formatLKR(Number(value ?? 0));
}

function monthLabel(ym: string): string {
  const [y, m] = ym.split('-').map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString('en-GB', { month: 'short', year: '2-digit' });
}

function donorLabel(d: Donation): string {
  return d.is_anonymous ? 'Anonymous' : d.donor_name || '—';
}

export default function DonationDetailsPage() {
  return (
    <ProtectedRoute requiredPermission="finance:read">
      <DonationDetails />
    </ProtectedRoute>
  );
}

function DonationDetails() {
  const [status, setStatus] = useState<StatusFilter>('');
  // How many of the newest donations to load. "Load more" adds a page.
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [purpose, setPurpose] = useState<DonationPurpose | ''>('');
  const [q, setQ] = useState('');
  const queryClient = useQueryClient();

  // Asks PayHere about a donation still awaiting payment, the same check the
  // thank-you page makes. For a donor who paid but closed the page before it
  // finished confirming. Records nothing unless PayHere confirms the payment.
  const checkPayment = useMutation({
    mutationFn: (orderId: string) => DonationsService.confirm(orderId),
    onSuccess: (result) => {
      if (result.status === 'paid') toast.success('Payment confirmed and recorded in the ledger.');
      else if (result.status === 'pending') toast.info('PayHere has not confirmed this payment yet.');
      else toast.info(`This donation is ${result.status}.`);
      queryClient.invalidateQueries({ queryKey: ['donations'] });
    },
    onError: (err) => toast.error(getErrorMessage(err) || "Couldn't check this payment."),
  });

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['donations', 'summary'],
    queryFn: DonationsService.summary,
  });
  const { data: donations = [], isLoading: listLoading, isFetching: listFetching } = useQuery({
    queryKey: ['donations', 'list', limit],
    queryFn: () => DonationsService.list({ limit }),
    placeholderData: (previous) => previous,
  });
  const mayHaveMore = donations.length >= limit;

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return donations.filter((d) =>
      (!status
        || (status === 'expired' ? !!d.expired
          : status === 'pending' ? d.status === 'pending' && !d.expired
          : d.status === status)) &&
      (!purpose || d.purpose === purpose) &&
      (!needle || [donorLabel(d), d.donor_email, d.program_name, d.gateway_ref]
        .some((v) => (v || '').toLowerCase().includes(needle)))
    );
  }, [donations, status, purpose, q]);

  const chartData = (summary?.monthly ?? []).slice(-12).map((m) => ({
    name: monthLabel(m.month),
    total: Number(m.total),
    count: m.count,
  }));

  const programMax = Math.max(1, ...(summary?.by_program ?? []).map((p) => Number(p.total)));

  function exportCsv() {
    const csv = buildCsv(
      ['Date', 'Reference', 'Donor', 'Email', 'Phone', 'Purpose', 'Program', 'Amount (LKR)', 'Status', 'Ledger transaction'],
      filtered.map((d) => [
        formatDate(d.paid_at || d.created_at),
        d.gateway_ref,
        donorLabel(d),
        d.donor_email,
        d.donor_phone,
        d.purpose === 'program' ? 'Specific program' : 'General',
        d.program_name,
        Number(d.amount),
        statusLabel(d),
        d.finance_transaction_id,
      ])
    );
    downloadCsv(`donations-${new Date().toISOString().slice(0, 10)}.csv`, csv);
  }

  const loadingValue = '—';

  return (
    <div className="space-y-8 pb-12">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold font-heading tracking-tight mb-2 text-text-primary">
            Donation Details
          </h1>
          <p className="text-text-secondary text-sm">
            Every donation made through the website. Paid donations are recorded in the finance ledger as income.
          </p>
        </div>
      </div>

      {/* KPI strip: paid donations only */}
      <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        <KPICard title="Total Raised" value={summaryLoading ? loadingValue : money(summary?.total_raised)} />
        <KPICard title="Donations" value={summaryLoading ? loadingValue : summary?.donation_count ?? 0} />
        <KPICard title="Named Donors" value={summaryLoading ? loadingValue : summary?.unique_donors ?? 0} />
        <KPICard title="Average Donation" value={summaryLoading ? loadingValue : money(summary?.average_donation)} />
      </div>
      <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        <KPICard title="For Specific Programs" value={summaryLoading ? loadingValue : money(summary?.program_total)} />
        <KPICard title="General Fund" value={summaryLoading ? loadingValue : money(summary?.general_total)} />
        <KPICard title="Anonymous Donations" value={summaryLoading ? loadingValue : money(summary?.anonymous_total)} />
        <KPICard title="Largest Donation" value={summaryLoading ? loadingValue : money(summary?.largest_donation)} />
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Raised per month */}
        <Card className="lg:col-span-3 bg-surface border border-border-brand rounded-card shadow-card">
          <CardHeader className="px-5 pt-5 pb-2">
            <CardTitle className="text-base font-semibold font-heading text-text-primary">
              Raised per month
            </CardTitle>
            <CardDescription className="text-text-secondary text-xs">
              Paid donations, last 12 months with activity.
            </CardDescription>
          </CardHeader>
          <CardContent className="h-[260px] px-2 pb-4">
            {summaryLoading ? (
              <Skeleton className="h-full w-full bg-bg-subtle" />
            ) : chartData.length === 0 ? (
              <p className="h-full flex items-center justify-center text-sm text-text-muted">
                No paid donations yet.
              </p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" opacity={0.3} vertical={false} />
                  <XAxis dataKey="name" stroke="var(--color-text-secondary)" fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis
                    stroke="var(--color-text-secondary)"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(value) => `Rs.${value / 1000}k`}
                  />
                  <Tooltip
                    cursor={{ fill: 'var(--color-border)', opacity: 0.2 }}
                    formatter={(value, _name, item) => [
                      `${formatLKR(Number(value))} (${item?.payload?.count ?? 0} donations)`,
                      'Raised',
                    ]}
                    contentStyle={{
                      backgroundColor: 'var(--color-surface)',
                      border: '1px solid var(--color-border)',
                      borderRadius: '8px',
                      fontFamily: 'var(--font-mono)',
                    }}
                    itemStyle={{ color: 'var(--color-text-primary)' }}
                  />
                  <Bar dataKey="total" fill="#EF9F27" radius={[4, 4, 0, 0]} maxBarSize={36} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Raised per program */}
        <Card className="lg:col-span-2 bg-surface border border-border-brand rounded-card shadow-card">
          <CardHeader className="px-5 pt-5 pb-2">
            <CardTitle className="text-base font-semibold font-heading text-text-primary flex items-center gap-2">
              <Lock className="w-4 h-4 text-text-secondary" /> Given to specific programs
            </CardTitle>
            <CardDescription className="text-text-secondary text-xs">
              Restricted funds: each amount can only be spent on its program.
            </CardDescription>
          </CardHeader>
          <CardContent className="px-5 pb-5 space-y-3">
            {summaryLoading ? (
              [1, 2, 3].map((i) => <Skeleton key={i} className="h-8 w-full bg-bg-subtle" />)
            ) : (summary?.by_program ?? []).length === 0 ? (
              <p className="py-8 text-center text-sm text-text-muted">No program donations yet.</p>
            ) : (
              summary!.by_program.map((p) => (
                <div key={p.program_id} className="space-y-1">
                  <div className="flex items-baseline justify-between gap-3 text-sm">
                    <span className="truncate text-text-primary">{p.program_name}</span>
                    <span className="font-mono text-text-primary whitespace-nowrap">{money(p.total)}</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-bg-subtle overflow-hidden">
                    <div
                      className="h-full rounded-full bg-[#EF9F27]"
                      style={{ width: `${(Number(p.total) / programMax) * 100}%` }}
                    />
                  </div>
                  <span className="text-[11px] text-text-muted">
                    {p.count} donation{p.count === 1 ? '' : 's'}
                  </span>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      {/* Contributions per donor */}
      <Card className="bg-surface border border-border-brand rounded-card shadow-card overflow-hidden">
        <CardHeader className="px-5 pt-5 pb-0">
          <CardTitle className="text-base font-semibold font-heading text-text-primary">
            Contributions by donor
          </CardTitle>
          <CardDescription className="text-text-secondary text-xs mt-1">
            Named donors, grouped by email address, largest first. Anonymous donations are shown together on the last row.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0 pt-4">
          {summaryLoading ? (
            <div className="space-y-3 p-5">
              {[1, 2, 3].map((i) => <Skeleton key={i} className="h-10 w-full bg-bg-subtle" />)}
            </div>
          ) : (summary?.donors.length ?? 0) === 0 && (summary?.anonymous_count ?? 0) === 0 ? (
            <p className="py-12 text-center text-sm text-text-muted">No paid donations yet.</p>
          ) : (
            <Table>
              <TableHeader className={tableHead}>
                <TableRow>
                  <TableHead>Donor</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead className="text-right">Donations</TableHead>
                  <TableHead>Last donation</TableHead>
                  <TableHead className="text-right">Total given</TableHead>
                  <TableHead className="text-right">Share</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody className="[&_td:first-child]:pl-5 [&_td:last-child]:pr-5">
                {summary!.donors.map((d) => (
                  <TableRow key={d.donor_email.toLowerCase()}>
                    <TableCell className="font-medium">{d.donor_name}</TableCell>
                    <TableCell className="text-sm text-text-secondary break-all">{d.donor_email}</TableCell>
                    <TableCell className="text-right font-mono">{d.count}</TableCell>
                    <TableCell className="text-sm text-text-secondary">{formatDate(d.last_donation_at)}</TableCell>
                    <TableCell className="text-right font-mono font-semibold">{money(d.total)}</TableCell>
                    <TableCell className="text-right font-mono text-text-secondary">
                      {Number(summary!.total_raised) > 0
                        ? `${((Number(d.total) / Number(summary!.total_raised)) * 100).toFixed(1)}%`
                        : '—'}
                    </TableCell>
                  </TableRow>
                ))}
                {summary!.anonymous_count > 0 && (
                  <TableRow className="bg-bg-subtle/40">
                    <TableCell className="font-medium">
                      <span className="inline-flex items-center gap-1.5">
                        <EyeOff className="w-3.5 h-3.5 text-text-secondary" /> Anonymous donors
                      </span>
                    </TableCell>
                    <TableCell className="text-sm text-text-muted">Not stored</TableCell>
                    <TableCell className="text-right font-mono">{summary!.anonymous_count}</TableCell>
                    <TableCell className="text-sm text-text-muted">—</TableCell>
                    <TableCell className="text-right font-mono font-semibold">{money(summary!.anonymous_total)}</TableCell>
                    <TableCell className="text-right font-mono text-text-secondary">
                      {Number(summary!.total_raised) > 0
                        ? `${((Number(summary!.anonymous_total) / Number(summary!.total_raised)) * 100).toFixed(1)}%`
                        : '—'}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Every donation */}
      <Card className="bg-surface border border-border-brand rounded-card shadow-card overflow-hidden">
        <CardHeader className="px-5 pt-5 pb-0">
          <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4">
            <div>
              <CardTitle className="text-base font-semibold font-heading text-text-primary">
                All donations
              </CardTitle>
              <CardDescription className="text-text-secondary text-xs mt-1">
                {summary && summary.pending_count > 0
                  ? `${summary.pending_count} awaiting payment: started on the website but not yet confirmed by PayHere, so not in the ledger.`
                  : 'Paid donations link to their ledger transaction.'}
                {summary && (summary.expired_count ?? 0) > 0 &&
                  ` ${summary.expired_count} expired: left PayHere without paying more than a day ago.`}
                {summary && (summary.refunded_count ?? 0) > 0 &&
                  ` ${summary.refunded_count} refunded (${money(summary.refunded_total)}): their ledger row was voided.`}
              </CardDescription>
              {summary && (summary.flagged_count ?? 0) > 0 && (
                <p className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-red-500/30 bg-red-500/10 px-2 py-1 text-xs text-negative">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  {summary.flagged_count} donation{summary.flagged_count === 1 ? ' needs' : 's need'} checking: see the red notes below.
                </p>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-muted" />
                <input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Donor, email, program, reference"
                  aria-label="Search donations"
                  className={cn(control, 'pl-7 w-56')}
                />
              </div>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as StatusFilter)}
                aria-label="Status"
                className={control}
              >
                <option value="">All statuses</option>
                <option value="paid">Paid</option>
                <option value="pending">Awaiting payment</option>
                <option value="expired">Expired (never paid)</option>
                <option value="failed">Failed</option>
                <option value="cancelled">Cancelled</option>
                <option value="refunded">Refunded</option>
              </select>
              <select
                value={purpose}
                onChange={(e) => setPurpose(e.target.value as DonationPurpose | '')}
                aria-label="Purpose"
                className={control}
              >
                <option value="">All purposes</option>
                <option value="program">Specific program</option>
                <option value="general">General fund</option>
              </select>
              <Button variant="outline" size="sm" onClick={exportCsv} disabled={filtered.length === 0} className="gap-1.5">
                <Download className="w-3.5 h-3.5" /> Export CSV
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0 pt-4">
          {listLoading ? (
            <div className="space-y-3 p-5">
              {[1, 2, 3].map((i) => <Skeleton key={i} className="h-10 w-full bg-bg-subtle" />)}
            </div>
          ) : filtered.length === 0 ? (
            <p className="py-12 text-center text-sm text-text-muted">No donations match these filters.</p>
          ) : (
            <Table>
              <TableHeader className={tableHead}>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Donor</TableHead>
                  <TableHead>Purpose</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Reference</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody className="[&_td:first-child]:pl-5 [&_td:last-child]:pr-5">
                {filtered.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell className="text-sm whitespace-nowrap align-top">
                      <div>{formatDate(d.paid_at || d.created_at)}</div>
                      <div className="text-xs text-text-muted font-mono">{formatTime(d.paid_at || d.created_at)}</div>
                    </TableCell>
                    <TableCell className="align-top">
                      {d.is_anonymous ? (
                        <span className="inline-flex items-center gap-1.5 text-text-secondary">
                          <EyeOff className="w-3.5 h-3.5" /> Anonymous
                        </span>
                      ) : (
                        <div className="max-w-[220px]">
                          <div className="font-medium">{d.donor_name}</div>
                          <div className="text-xs text-text-secondary break-all">{d.donor_email}</div>
                          {d.donor_phone && <div className="text-xs text-text-muted">{d.donor_phone}</div>}
                        </div>
                      )}
                      {d.message && (
                        <div className="mt-1 max-w-[220px] text-xs italic text-text-muted">&ldquo;{d.message}&rdquo;</div>
                      )}
                    </TableCell>
                    <TableCell className="text-sm align-top">
                      {d.purpose === 'program' ? (
                        <span className="inline-flex items-center gap-1.5">
                          <Lock className="w-3 h-3 text-text-secondary" /> {d.program_name || `Program ${d.program_id}`}
                        </span>
                      ) : (
                        <span className="text-text-secondary">General fund</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right font-mono font-semibold align-top">{money(d.amount)}</TableCell>
                    <TableCell className="align-top">
                      <Badge
                        variant="outline"
                        className={cn('font-medium', d.expired ? STATUS_STYLE.cancelled : STATUS_STYLE[d.status])}
                      >
                        {statusLabel(d)}
                      </Badge>
                      {d.gateway_note && d.status !== 'refunded' && (
                        <div className="mt-1 max-w-[240px] flex items-start gap-1 text-xs text-negative">
                          <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
                          <span>{d.gateway_note}</span>
                        </div>
                      )}
                      {d.status === 'pending' && d.gateway_ref && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="mt-1 h-7 px-2 text-xs gap-1"
                          disabled={checkPayment.isPending}
                          onClick={() => checkPayment.mutate(d.gateway_ref!)}
                        >
                          <RefreshCw className={cn('w-3 h-3', checkPayment.isPending && checkPayment.variables === d.gateway_ref && 'animate-spin')} />
                          Check payment
                        </Button>
                      )}
                    </TableCell>
                    <TableCell className="align-top text-xs font-mono text-text-secondary">
                      <div>{d.gateway_ref}</div>
                      {d.finance_transaction_id && (
                        <div className="text-text-muted">Ledger #{d.finance_transaction_id}</div>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {mayHaveMore && (
            <div className="flex items-center justify-center gap-3 border-t border-border-brand p-4 text-xs text-text-secondary">
              Showing the newest {donations.length} donations. Search and filters apply to these.
              <Button
                variant="outline" size="sm"
                disabled={listFetching}
                onClick={() => setLimit((n) => n + PAGE_SIZE)}
              >
                {listFetching ? 'Loading...' : 'Load more'}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
