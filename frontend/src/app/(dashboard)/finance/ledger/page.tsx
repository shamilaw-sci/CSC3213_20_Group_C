'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowDownUp, Ban, CheckCircle2, ChevronLeft, ChevronRight, FileSpreadsheet,
  Loader2, Lock, Pencil, PlusCircle, Search, X,
} from 'lucide-react';
import { toast } from 'sonner';
import { useAuthStore } from '@/store/useAuthStore';
import { useLedger, usePrograms, useSettleTransaction } from '@/hooks/useFinance';
import { FinanceService } from '@/services/finance.service';
import { LedgerFilters, LedgerRow } from '@/types';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import ProtectedRoute from '@/components/layout/protected-route';
import { NewTransactionModal } from '@/components/finance/NewTransactionModal';
import { EditTransactionModal } from '@/components/finance/EditTransactionModal';
import { formatLKR } from '@/lib/formatters';
import { hasPermission } from '@/lib/permissions';
import { buildCsv, downloadCsv } from '@/lib/csv';
import { toISODate } from '@/lib/finance-periods';
import { cn } from '@/lib/utils';

const PAGE_SIZES = [25, 50, 100];

// The Description column: "Source-Program" (e.g. "Donation-Distemper outbreak"),
// or "Source-General" when the row has no program (e.g. "Stock in-General").
// The API builds it; the fallback covers a backend that does not send it yet.
const describeRow = (r: LedgerRow) =>
  r.description ?? `Manual-${r.program_id === null ? 'General' : r.program_name}`;

const control =
  'h-9 rounded-md border border-border-brand bg-surface px-2 text-xs text-text-primary outline-none focus:border-accent';

function filtersFromQuery(params: URLSearchParams): LedgerFilters {
  const pick = <T extends string>(key: string, allowed: readonly T[]) => {
    const value = params.get(key);
    return allowed.includes(value as T) ? (value as T) : undefined;
  };
  return {
    transaction_type: pick('type', ['Income', 'Expense'] as const),
    status: pick('status', ['Cash', 'Receivable', 'Voided'] as const),
    sort: pick('sort', ['newest', 'oldest'] as const) ?? 'newest',
  };
}

function StatusBadge({ row }: { row: LedgerRow }) {
  const income = row.transaction_type === 'Income';
  const label =
    row.status === 'Receivable' ? (income ? 'Receivable' : 'Payable')
    : row.status === 'Cash' ? (income ? 'Received' : 'Paid')
    : 'Voided';
  return (
    <span
      className={cn(
        'inline-block rounded-full px-2 py-0.5 text-[11px] font-medium',
        row.status === 'Cash' && 'bg-emerald-500/10 text-emerald-600',
        row.status === 'Receivable' && 'bg-amber-500/10 text-amber-600',
        row.status === 'Voided' && 'bg-bg-subtle text-text-muted',
      )}
    >
      {label}
    </span>
  );
}

// The nav hides the Ledger from roles without finance:read, but a URL typed
// by hand bypasses the nav, so the page checks for itself, as Reports does.
export default function LedgerPage() {
  return (
    <ProtectedRoute requiredPermission="finance:read">
      {/* useSearchParams needs a Suspense boundary, or the production build
          fails to prerender this route. */}
      <Suspense>
        <Ledger />
      </Suspense>
    </ProtectedRoute>
  );
}

function Ledger() {
  const { user } = useAuthStore();
  const canWrite = hasPermission(user?.role as string, 'finance:write');
  const queryClient = useQueryClient();

  // Links can open the Ledger pre-filtered, e.g. the Finance Officer
  // dashboard's ?status=Receivable&type=Income&sort=oldest, which replaced
  // the separate Receivables page. Read once, as the starting state.
  const searchParams = useSearchParams();
  const [filters, setFilters] = useState<LedgerFilters>(() => filtersFromQuery(searchParams));
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  // Every filter change goes back to page 1: page 4 of the old result set
  // means nothing in the new one.
  const updateFilters = (patch: Partial<LedgerFilters>) => {
    setFilters((f) => ({ ...f, ...patch }));
    setPage(1);
  };

  // Search waits for a pause in typing rather than refetching per keystroke.
  useEffect(() => {
    const id = setTimeout(() => {
      const q = search.trim() || undefined;
      setFilters((f) => (f.q === q ? f : { ...f, q }));
      setPage((p) => (p === 1 ? p : 1));
    }, 300);
    return () => clearTimeout(id);
  }, [search]);

  const { data, isLoading, isFetching, error } = useLedger(filters, page, pageSize);
  const { data: programs } = usePrograms();

  const [showNew, setShowNew] = useState(false);
  const [editing, setEditing] = useState<LedgerRow | null>(null);
  const [voiding, setVoiding] = useState<LedgerRow | null>(null);
  const [exporting, setExporting] = useState(false);

  const { mutate: settle, isPending: isSettling, variables: settlingId } = useSettleTransaction();
  const { mutate: voidTransaction, isPending: isVoiding } = useMutation({
    mutationFn: (id: number) => FinanceService.voidTransaction(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['financeSummary'] });
      queryClient.invalidateQueries({ queryKey: ['restrictedBalance'] });
      setVoiding(null);
    },
    onError: () => toast.error('Failed to void the transaction'),
  });

  const activeFilters =
    !!filters.start_date || !!filters.end_date || !!filters.transaction_type || !!filters.status ||
    !!filters.program || filters.restricted !== undefined || !!filters.q;

  const clearFilters = () => {
    setSearch('');
    setFilters({ sort: filters.sort });
    setPage(1);
  };

  // Exports every row the filters match, not just the page on screen.
  const exportCsv = async () => {
    setExporting(true);
    try {
      const all = await FinanceService.getLedger(filters, 1, pageSize, true);
      downloadCsv(
        `ledger_${toISODate(new Date())}.csv`,
        buildCsv(
          ['ID', 'Date', 'Type', 'Restricted', 'Description', 'Status', 'Amount', 'Balance'],
          all.rows.map((r) => [
            r.id, r.transaction_date, r.transaction_type, r.is_restricted ? 'Yes' : 'No',
            describeRow(r), r.status, r.amount, r.balance,
          ]),
        ),
      );
    } catch {
      toast.error('Failed to export the ledger');
    } finally {
      setExporting(false);
    }
  };

  const rows = data?.rows ?? [];
  const first = data && data.total ? (data.page - 1) * pageSize + 1 : 0;
  const last = first ? first + rows.length - 1 : 0;

  return (
    <div className="space-y-6 pb-12">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-3xl font-bold font-heading tracking-tight mb-2 text-text-primary">General Ledger</h1>
          <p className="text-text-secondary text-sm">Every transaction, with a running balance.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={exportCsv}
            disabled={exporting || !data?.total}
            className="border-border-brand text-text-primary gap-2"
          >
            {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileSpreadsheet className="h-4 w-4" />}
            Export CSV
          </Button>
          {canWrite && (
            <Button onClick={() => setShowNew(true)} className="bg-accent text-white hover:bg-accent/90 gap-2 font-semibold">
              <PlusCircle className="h-4 w-4" /> New Entry
            </Button>
          )}
        </div>
      </div>

      {/* Filters: one row, above the table they filter. */}
      <Card className="bg-surface border border-border-brand rounded-card shadow-card">
        <CardContent className="flex flex-wrap items-center gap-2 p-3">
          <div className="relative min-w-[200px] flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-text-muted" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search description, amount, status or #id"
              aria-label="Search the ledger"
              className={cn(control, 'w-full pl-8')}
            />
          </div>

          <input
            type="date"
            value={filters.start_date ?? ''}
            max={filters.end_date}
            onChange={(e) => updateFilters({ start_date: e.target.value || undefined })}
            aria-label="From date"
            className={cn(control, 'font-mono')}
          />
          <span className="text-xs text-text-muted">to</span>
          <input
            type="date"
            value={filters.end_date ?? ''}
            min={filters.start_date}
            onChange={(e) => updateFilters({ end_date: e.target.value || undefined })}
            aria-label="To date"
            className={cn(control, 'font-mono')}
          />

          <select
            value={filters.transaction_type ?? ''}
            onChange={(e) => updateFilters({ transaction_type: (e.target.value || undefined) as LedgerFilters['transaction_type'] })}
            aria-label="Type"
            className={control}
          >
            <option value="">All types</option>
            <option value="Income">Income</option>
            <option value="Expense">Expense</option>
          </select>

          <select
            value={filters.status ?? ''}
            onChange={(e) => updateFilters({ status: (e.target.value || undefined) as LedgerFilters['status'] })}
            aria-label="Status"
            className={control}
          >
            <option value="">All statuses</option>
            <option value="Cash">Settled</option>
            <option value="Receivable">Open (receivable / payable)</option>
            <option value="Voided">Voided</option>
          </select>

          <select
            value={filters.program ?? ''}
            onChange={(e) => updateFilters({ program: e.target.value || undefined })}
            aria-label="Program"
            className={cn(control, 'max-w-[180px]')}
          >
            <option value="">All programs</option>
            <option value="general">General Operations</option>
            {programs?.map((p) => (
              <option key={p.id} value={String(p.id)}>{p.program_name}</option>
            ))}
          </select>

          <label className="flex h-9 cursor-pointer items-center gap-1.5 rounded-md border border-border-brand px-2 text-xs text-text-secondary">
            <input
              type="checkbox"
              checked={filters.restricted === true}
              onChange={(e) => updateFilters({ restricted: e.target.checked ? true : undefined })}
              className="accent-[var(--color-accent)]"
            />
            <Lock className="h-3 w-3" /> Restricted only
          </label>

          <button
            type="button"
            onClick={() => updateFilters({ sort: filters.sort === 'oldest' ? 'newest' : 'oldest' })}
            className={cn(control, 'flex items-center gap-1.5 text-text-secondary hover:text-text-primary')}
          >
            <ArrowDownUp className="h-3.5 w-3.5" /> {filters.sort === 'oldest' ? 'Oldest first' : 'Newest first'}
          </button>

          {activeFilters && (
            <button
              type="button"
              onClick={clearFilters}
              className="flex h-9 items-center gap-1 px-2 text-xs font-semibold text-accent hover:underline"
            >
              <X className="h-3.5 w-3.5" /> Clear
            </button>
          )}
        </CardContent>
      </Card>

      {/* Totals for everything the filters match, not just this page. */}
      {data && (
        <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 text-sm">
          <span className="text-text-secondary">
            <span className="font-semibold text-text-primary">{data.total.toLocaleString()}</span>{' '}
            {data.total === 1 ? 'entry' : 'entries'}
          </span>
          <span className="text-text-secondary">Income <span className="font-mono text-text-primary">{formatLKR(data.totals.income)}</span></span>
          <span className="text-text-secondary">Expenditure <span className="font-mono text-text-primary">{formatLKR(data.totals.expense)}</span></span>
          <span className="text-text-secondary">
            Net{' '}
            <span className={cn('font-mono font-semibold', data.totals.net < 0 ? 'text-negative' : 'text-text-primary')}>
              {formatLKR(data.totals.net)}
            </span>
          </span>
          {isFetching && !isLoading && <Loader2 className="h-3.5 w-3.5 animate-spin text-text-muted" />}
        </div>
      )}

      <Card className="bg-surface border border-border-brand rounded-card shadow-card overflow-hidden">
        <CardContent className="p-0">
          {error && !data ? (
            <p className="p-6 text-sm text-rose-500">Failed to load the ledger. Please try again.</p>
          ) : isLoading ? (
            <div className="space-y-3 p-4">
              {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-10 w-full bg-bg-subtle" />)}
            </div>
          ) : rows.length === 0 ? (
            <div className="py-12 text-center text-sm text-text-muted">
              {activeFilters ? 'No transactions match these filters.' : 'No transactions recorded yet.'}
            </div>
          ) : (
            <div className={cn('overflow-x-auto transition-opacity', isFetching && 'opacity-60')}>
              <table className="w-full text-left text-sm">
                <thead className="bg-bg-subtle/60 text-[11px] uppercase tracking-wider text-text-secondary">
                  <tr>
                    <th className="px-4 py-3 font-semibold">Date</th>
                    <th className="px-4 py-3 font-semibold">Type</th>
                    <th className="px-4 py-3 font-semibold">Description</th>
                    <th className="px-4 py-3 font-semibold">Status</th>
                    <th className="px-4 py-3 text-right font-semibold">Amount</th>
                    <th
                      className="px-4 py-3 text-right font-semibold"
                      title="Income minus expenditure across the whole ledger after this entry, pending items included"
                    >
                      Balance
                    </th>
                    {canWrite && <th className="px-4 py-3"><span className="sr-only">Actions</span></th>}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-brand">
                  {rows.map((r) => {
                    const voided = r.status === 'Voided';
                    const income = r.transaction_type === 'Income';
                    return (
                      <tr key={r.id} className={cn('hover:bg-bg-subtle/50', voided && 'text-text-muted')}>
                        <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-text-secondary">
                          {r.transaction_date}
                          <span className="ml-2 text-text-muted">#{r.id}</span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="inline-flex items-center gap-1 text-xs font-medium text-text-primary">
                            {r.transaction_type}
                            {r.is_restricted && <Lock className="h-3 w-3 text-accent" aria-label="Restricted" />}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-text-primary">{describeRow(r)}</td>
                        <td className="px-4 py-3"><StatusBadge row={r} /></td>
                        <td
                          className={cn(
                            'whitespace-nowrap px-4 py-3 text-right font-mono tabular-nums',
                            voided ? 'line-through' : income ? 'text-positive' : 'text-text-primary',
                          )}
                        >
                          {income ? '+' : '−'}{formatLKR(r.amount)}
                        </td>
                        <td
                          className={cn(
                            'whitespace-nowrap px-4 py-3 text-right font-mono tabular-nums',
                            r.balance !== null && r.balance < 0 ? 'text-negative' : 'text-text-secondary',
                          )}
                        >
                          {r.balance === null ? '—' : formatLKR(r.balance)}
                        </td>
                        {canWrite && (
                          <td className="whitespace-nowrap px-4 py-3 text-right">
                            {!voided && (
                              <div className="flex justify-end gap-1">
                                {r.status === 'Receivable' && (
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    disabled={isSettling}
                                    onClick={() => settle(r.id)}
                                    title={income ? 'Mark as received' : 'Mark as paid'}
                                    className="h-7 gap-1 px-2 text-xs text-text-secondary hover:text-positive"
                                  >
                                    {isSettling && settlingId === r.id
                                      ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                      : <CheckCircle2 className="h-3.5 w-3.5" />}
                                    {income ? 'Received' : 'Paid'}
                                  </Button>
                                )}
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => setEditing(r)}
                                  aria-label={`Edit transaction ${r.id}`}
                                  className="h-7 w-7 p-0 text-text-secondary hover:text-text-primary"
                                >
                                  <Pencil className="h-3.5 w-3.5" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => setVoiding(r)}
                                  aria-label={`Void transaction ${r.id}`}
                                  className="h-7 w-7 p-0 text-text-secondary hover:text-negative"
                                >
                                  <Ban className="h-3.5 w-3.5" />
                                </Button>
                              </div>
                            )}
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>

        {data && data.total > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border-brand px-4 py-3 text-xs text-text-secondary">
            <span>
              Showing <span className="font-semibold text-text-primary">{first}–{last}</span> of{' '}
              <span className="font-semibold text-text-primary">{data.total.toLocaleString()}</span>
            </span>
            <div className="flex items-center gap-2">
              <select
                value={pageSize}
                onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
                aria-label="Rows per page"
                className={cn(control, 'h-8')}
              >
                {PAGE_SIZES.map((n) => <option key={n} value={n}>{n} per page</option>)}
              </select>
              <Button
                variant="outline"
                size="sm"
                disabled={data.page <= 1}
                onClick={() => setPage((p) => p - 1)}
                aria-label="Previous page"
                className="h-8 w-8 border-border-brand p-0"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="min-w-[70px] text-center">Page {data.page} of {data.pages}</span>
              <Button
                variant="outline"
                size="sm"
                disabled={data.page >= data.pages}
                onClick={() => setPage((p) => p + 1)}
                aria-label="Next page"
                className="h-8 w-8 border-border-brand p-0"
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </Card>

      <p className="text-xs text-text-muted">
        Balance is income minus expenditure across the whole ledger after each entry, including items not yet
        received or paid. It is not affected by the filters above.
      </p>

      <NewTransactionModal open={showNew} onClose={() => setShowNew(false)} />
      <EditTransactionModal transaction={editing} onClose={() => setEditing(null)} />

      <Dialog open={!!voiding} onOpenChange={(o) => !o && setVoiding(null)}>
        <DialogContent className="bg-surface border-border-brand">
          <DialogHeader>
            <DialogTitle>Void transaction #{voiding?.id}?</DialogTitle>
            <DialogDescription>
              {voiding && (
                <>
                  {voiding.transaction_type} of {formatLKR(voiding.amount)} on {voiding.transaction_date} ({describeRow(voiding)}).
                  Voiding keeps it on the ledger as a reversal. Voided transactions can&apos;t be edited or restored.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setVoiding(null)} disabled={isVoiding}>Cancel</Button>
            <Button
              onClick={() => voiding && voidTransaction(voiding.id)}
              disabled={isVoiding}
              className="bg-negative text-white hover:bg-negative/90"
            >
              {isVoiding ? 'Voiding…' : 'Void transaction'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
