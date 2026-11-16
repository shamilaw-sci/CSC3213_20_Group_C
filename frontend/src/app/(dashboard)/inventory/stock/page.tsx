'use client';

import { Fragment, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { format, parseISO } from 'date-fns';
import {
  AlertTriangle,
  ArrowDownCircle,
  ArrowUpCircle,
  CalendarClock,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Package,
  Pencil,
  Plus,
  RotateCcw,
  Search,
  Undo2,
  type LucideIcon,
} from 'lucide-react';

import {
  useAllBatches,
  useInventoryItems,
  useInventoryMonthTransactions,
  useLowStockItems,
  useExpiringItems,
} from '@/hooks/useInventory';
import { FinanceService } from '@/services/finance.service';
import { useAuthStore } from '@/store/useAuthStore';
import { hasPermission } from '@/lib/permissions';
import { formatLKR } from '@/lib/formatters';
import { DEFAULT_REORDER_LEVEL, isActiveProgram, todayISO } from '@/lib/inventory';
import ProtectedRoute from '@/components/layout/protected-route';
import { KPICard } from '@/components/shared/kpi-card';
import {
  AddItemDialog,
  EditItemDialog,
  MovementDialog,
  ReverseMovementDialog,
  type MovementKind,
} from '@/components/inventory/stock-dialogs';
import { cn } from '@/lib/utils';
import type { InventoryBatch, InventoryItem, InventoryTransaction } from '@/types';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

// An item is "low stock" below its own reorder level, or below this default
// when it has none. The page passes the default to the backend
// (GET /inventory/alerts/low-stock), and the backend decides which items are
// low, so there is a single definition of "low stock" in the system.
const LOW_STOCK_THRESHOLD = DEFAULT_REORDER_LEVEL;
const MAX_ALERT_CARDS = 4;
const EXPIRY_WINDOW_DAYS = 30;
const MAX_EXPIRY_ROWS = 5;

// "2026-11" -> "November 2026".
function monthLabel(month: string) {
  return format(parseISO(`${month}-01`), 'MMMM yyyy');
}

// "2026-01" moved by -1 -> "2025-12".
function shiftMonth(month: string, by: number) {
  const [year, m] = month.split('-').map(Number);
  const d = new Date(year, m - 1 + by, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

// One accent primary action; the rest are outline buttons with a coloured icon.
const ACTION_BUTTON = 'h-10 gap-2 rounded-lg px-4 text-sm font-semibold shadow-sm transition-colors';
const SECONDARY_BUTTON = cn(
  ACTION_BUTTON,
  'border-border-brand bg-surface text-text-primary hover:bg-bg-subtle'
);

const ALERT_TONES = {
  out: {
    label: 'Out of stock',
    card: 'border-red-500/30 bg-red-500/10',
    bar: 'bg-red-500',
    chip: 'border-red-500/30 bg-red-500/15 text-negative',
    value: 'text-negative',
  },
  low: {
    label: 'Low stock',
    card: 'border-amber-500/30 bg-amber-500/10',
    bar: 'bg-amber-500',
    chip: 'border-amber-500/30 bg-amber-500/15 text-accent',
    value: 'text-accent',
  },
} as const;

type MovementStyle = { label: string; Icon: LucideIcon; sign: string; pill: string };

// Labels match the action buttons: Issue = Stock Out, Restock = Stock In.
const MOVEMENT_STYLES: Record<string, MovementStyle> = {
  Issue: {
    label: 'Stock Out',
    Icon: ArrowUpCircle,
    sign: '-',
    pill: 'border-red-500/20 bg-red-500/10 text-negative',
  },
  Restock: {
    label: 'Stock In',
    Icon: ArrowDownCircle,
    sign: '+',
    pill: 'border-green-500/20 bg-green-500/10 text-positive',
  },
  Return: {
    label: 'Return',
    Icon: RotateCcw,
    sign: '+',
    pill: 'border-border-brand bg-bg-subtle text-text-primary',
  },
};

const FALLBACK_MOVEMENT: MovementStyle = {
  label: 'Other',
  Icon: Package,
  sign: '',
  pill: 'border-border-brand bg-bg-subtle text-text-secondary',
};

const getMovementStyle = (type: string): MovementStyle =>
  MOVEMENT_STYLES[type] ?? FALLBACK_MOVEMENT;

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

// The sidebar hides Stock from roles without inventory:read, but a URL typed
// by hand bypasses the sidebar, so the page checks for itself (as the Finance
// Ledger does). The inner check stops the page's requests from firing during
// the moment before ProtectedRoute's redirect happens.
export default function InventoryPage() {
  const { user } = useAuthStore();
  const canRead = hasPermission(user?.role as string, 'inventory:read');
  return (
    <ProtectedRoute requiredPermission="inventory:read">
      {canRead ? <StockPage /> : null}
    </ProtectedRoute>
  );
}

function StockPage() {
  const { user } = useAuthStore();
  // Every Stock page action (Add Item, Stock In, Stock Out, Return) needs
  // inventory:manage: Admin, Director, Finance Officer and Operations Lead.
  const canManage = hasPermission(user?.role as string, 'inventory:manage');

  const { data: items, isLoading: loadingItems, isError: itemsError } = useInventoryItems();
  // Each item's batches with their own price (migrations 020 and 021).
  const { data: batches } = useAllBatches();
  // The Movements card shows every movement in one month ("YYYY-MM").
  const thisMonth = todayISO().slice(0, 7);
  const [month, setMonth] = useState(thisMonth);
  const {
    data: transactions,
    isLoading: loadingTransactions,
    isError: transactionsError,
  } = useInventoryMonthTransactions(month);
  const {
    data: lowStock,
    isLoading: loadingLowStock,
    isError: lowStockError,
  } = useLowStockItems(LOW_STOCK_THRESHOLD);
  const {
    data: expiring,
    isLoading: loadingExpiring,
    isError: expiringError,
  } = useExpiringItems(EXPIRY_WINDOW_DAYS);

  // Which form is open. Each form saves and disables its own button while
  // saving, so the same movement cannot be submitted twice.
  const [addItemOpen, setAddItemOpen] = useState(false);
  const [movement, setMovement] = useState<{ kind: MovementKind; itemId?: number } | null>(null);
  const [editing, setEditing] = useState<InventoryItem | null>(null);
  const [reversing, setReversing] = useState<InventoryTransaction | null>(null);
  const hasItems = (items?.length ?? 0) > 0;

  // Programs: names for the movement list, and the Stock Out picker.
  const { data: programs } = useQuery({
    queryKey: ['programs'],
    queryFn: FinanceService.getPrograms,
  });
  // Stock goes out only to a program that is running (the API refuses the
  // rest). Returns pick from the programs that hold the item instead.
  const activePrograms = useMemo(
    () =>
      (programs ?? [])
        .filter((p) => isActiveProgram(p.status))
        .sort((a, b) => a.program_name.localeCompare(b.program_name)),
    [programs]
  );

  const [search, setSearch] = useState('');
  const [stockFilter, setStockFilter] = useState<'all' | 'low'>('all');

  // ---- derived data -------------------------------------------------------

  const lowStockIds = useMemo(() => new Set((lowStock ?? []).map((i) => i.id)), [lowStock]);

  const alertCards = (lowStock ?? []).slice(0, MAX_ALERT_CARDS);
  const hiddenAlerts = (lowStock?.length ?? 0) - alertCards.length;

  const visibleItems = useMemo(() => {
    const term = search.trim().toLowerCase();
    return [...(items ?? [])]
      .filter((i) => (stockFilter === 'low' ? lowStockIds.has(i.id) : true))
      .filter((i) => i.item_name.toLowerCase().includes(term))
      .sort((a, b) => a.item_name.localeCompare(b.item_name));
  }, [items, search, stockFilter, lowStockIds]);

  // All items A-Z for the form pickers (the table's search filter does not apply there).
  const sortedItems = useMemo(
    () => [...(items ?? [])].sort((a, b) => a.item_name.localeCompare(b.item_name)),
    [items]
  );

  // Batches per item, in the order Stock Out uses them.
  const batchesByItem = useMemo(() => {
    const map = new Map<number, InventoryBatch[]>();
    for (const b of batches ?? []) {
      const list = map.get(b.item_id) ?? [];
      list.push(b);
      map.set(b.item_id, list);
    }
    return map;
  }, [batches]);

  // An item's value: each batch at its own price. Falls back to stock x the
  // item's price when the batches are not loaded or do not add up.
  const itemValue = (item: InventoryItem) => {
    const list = batchesByItem.get(item.id);
    const inBatches = (list ?? []).reduce((sum, b) => sum + b.quantity_remaining, 0);
    if (list && list.length > 0 && inBatches === item.current_stock) {
      return list.reduce((sum, b) => sum + b.quantity_remaining * Number(b.unit_cost), 0);
    }
    return item.current_stock * Number(item.unit_cost);
  };

  const totalValue = (items ?? []).reduce((sum, i) => sum + itemValue(i), 0);

  const today = todayISO();
  const expiryRows = (expiring ?? [])
    .slice()
    .sort((a, b) => a.expire_date.localeCompare(b.expire_date))
    .slice(0, MAX_EXPIRY_ROWS);

  const visibleValue = visibleItems.reduce((sum, i) => sum + itemValue(i), 0);

  const unitCostById = useMemo(
    () => new Map((items ?? []).map((i) => [i.id, Number(i.unit_cost)])),
    [items]
  );

  // Name lookups built from the item and program lists this page already loads,
  // so the Recent Movements table can show names even when the API response
  // doesn't include the joined names.
  const itemNameById = useMemo(
    () => new Map((items ?? []).map((i) => [i.id, i.item_name] as const)),
    [items]
  );
  const programNameById = useMemo(
    () => new Map((programs ?? []).map((p) => [p.id, p.program_name] as const)),
    [programs]
  );

  // Newest first; the id breaks ties between movements on the same day.
  const movements = useMemo(
    () =>
      [...(transactions ?? [])]
        .sort(
          (a, b) =>
            b.transaction_date.localeCompare(a.transaction_date) || b.id - a.id
        ),
    [transactions]
  );

  // Amount = the cost saved on the movement. Older rows saved before costs were
  // recorded have 0, so those fall back to quantity x the item's current unit
  // cost and are shown in italics as an estimate.
  const getMovementAmount = (tx: InventoryTransaction) => {
    const saved = Number(tx.total_cost) || 0;
    if (saved > 0) return { value: saved, estimated: false };
    return { value: tx.quantity * (unitCostById.get(tx.item_id) ?? 0), estimated: true };
  };

  // Prefer the names the API sends with the movement, then fall back to the
  // lists loaded above, and only show an id as a last resort.
  const getItemName = (tx: InventoryTransaction) =>
    tx.inventory_items?.item_name ?? itemNameById.get(tx.item_id) ?? `Item #${tx.item_id}`;

  // The label depends on program_id, not on whether a name arrived: a Stock Out
  // is only a "Stock adjustment" when it really has no program.
  const getProgramLabel = (tx: InventoryTransaction) => {
    if (tx.rescue_case_id != null) {
      return `Rescue case: ${tx.rescue_case?.animal_type ?? 'unknown'}`;
    }
    if (tx.program_id == null) {
      if (tx.reverses_id != null) return '—';
      return tx.transaction_type === 'Issue' ? 'Stock adjustment' : '—';
    }
    return (
      tx.programs?.program_name ?? programNameById.get(tx.program_id) ?? `Program #${tx.program_id}`
    );
  };

  const hasEstimates = movements.some((tx) => {
    const { value, estimated } = getMovementAmount(tx);
    return estimated && value > 0;
  });

  const getStockStatus = (item: InventoryItem) => {
    if (item.current_stock <= 0)
      return { label: 'Out', badge: 'border-red-500/30 bg-red-500/10 text-negative' };
    if (lowStockIds.has(item.id))
      return { label: 'Low', badge: 'border-amber-500/30 bg-amber-500/10 text-accent' };
    return { label: '', badge: 'border-green-500/20 bg-green-500/5 text-positive' };
  };

  // ---- render -------------------------------------------------------------

  return (
    <div className="space-y-8 pb-12">
      {/* Header */}
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-center">
        <div>
          <h1 className="mb-2 text-3xl font-bold font-heading tracking-tight text-text-primary">
            Inventory
          </h1>
          <p className="text-sm text-text-secondary">
            Medical supplies and equipment: stock levels, movements and alerts.
          </p>
        </div>

        {canManage && (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              onClick={() => setMovement({ kind: 'in' })}
              disabled={!hasItems}
              title={hasItems ? undefined : 'Add an item first'}
              className={cn(ACTION_BUTTON, 'bg-accent text-white hover:bg-accent/90')}
            >
              <ArrowDownCircle className="h-4 w-4" /> Stock In
            </Button>
            <Button
              variant="outline"
              onClick={() => setMovement({ kind: 'out' })}
              disabled={!hasItems}
              className={SECONDARY_BUTTON}
            >
              <ArrowUpCircle className="h-4 w-4 text-negative" /> Stock Out
            </Button>
            <Button
              variant="outline"
              onClick={() => setMovement({ kind: 'return' })}
              disabled={!hasItems}
              className={SECONDARY_BUTTON}
            >
              <RotateCcw className="h-4 w-4 text-text-secondary" /> Return
            </Button>
            <span className="hidden h-8 w-px bg-border-brand sm:block" />
            <Button variant="outline" onClick={() => setAddItemOpen(true)} className={SECONDARY_BUTTON}>
              <Plus className="h-4 w-4 text-accent" /> Add Item
            </Button>
          </div>
        )}
      </div>

      {/* Summary */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {loadingItems ? (
          Array(4)
            .fill(0)
            .map((_, i) => (
              <Skeleton key={i} className="h-28 rounded-card border border-border-brand bg-bg-subtle" />
            ))
        ) : (
          <>
            <KPICard title="Items" value={items?.length ?? 0} />
            <KPICard title="Stock value" value={formatLKR(totalValue)} />
            <KPICard title="Low stock" value={lowStockError ? '—' : (lowStock?.length ?? 0)} />
            <KPICard
              title={`Expiring in ${EXPIRY_WINDOW_DAYS} days`}
              value={expiringError ? '—' : (expiring?.length ?? 0)}
            />
          </>
        )}
      </div>

      {/* Low stock alerts */}
      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-accent" />
            <h2 className="text-sm font-semibold font-heading text-text-primary">Low Stock Alerts</h2>
            {(lowStock?.length ?? 0) > 0 && (
              <Badge
                variant="outline"
                className="rounded-full border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] text-accent"
              >
                {lowStock?.length}
              </Badge>
            )}
          </div>
          <p className="text-xs text-text-muted">
            Items below their reorder level ({LOW_STOCK_THRESHOLD} units unless set on the item)
            {hiddenAlerts > 0 &&
              ` · showing the ${alertCards.length} lowest, ${hiddenAlerts} more in the list below`}
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {loadingLowStock || loadingItems ? (
            Array(4)
              .fill(0)
              .map((_, i) => (
                <Skeleton key={i} className="h-36 rounded-card border border-border-brand bg-bg-subtle" />
              ))
          ) : lowStockError ? (
            <div className="rounded-card border border-border-brand bg-surface p-5 text-xs text-text-muted shadow-card sm:col-span-2 lg:col-span-4">
              Couldn&apos;t load low-stock alerts right now.
            </div>
          ) : items && items.length === 0 ? (
            <div className="rounded-card border border-dashed border-border-brand bg-bg-subtle p-5 text-xs text-text-muted sm:col-span-2 lg:col-span-4">
              No inventory items yet. Use Add Item to get started.
            </div>
          ) : alertCards.length === 0 ? (
            <div className="flex items-center gap-4 rounded-card border border-green-500/30 bg-green-500/10 p-5 shadow-card sm:col-span-2 lg:col-span-4">
              <CheckCircle2 className="h-8 w-8 shrink-0 text-positive" />
              <div>
                <p className="text-sm font-semibold font-heading text-text-primary">
                  All items are well stocked
                </p>
                <p className="text-xs text-text-secondary">
                  Every item is at or above its reorder level.
                </p>
              </div>
            </div>
          ) : (
            alertCards.map((item) => {
              const tone = item.current_stock <= 0 ? ALERT_TONES.out : ALERT_TONES.low;
              return (
                <div
                  key={item.id}
                  className={cn(
                    'relative flex flex-col justify-between gap-4 overflow-hidden rounded-card border p-5 shadow-card md:p-6',
                    tone.card
                  )}
                >
                  <div className={cn('absolute left-0 top-0 h-full w-1', tone.bar)} />

                  <div className="flex items-start justify-between gap-2">
                    <span className="truncate text-xs font-semibold uppercase tracking-wider text-text-secondary">
                      {item.item_name}
                    </span>
                    <span
                      className={cn(
                        'shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide',
                        tone.chip
                      )}
                    >
                      {tone.label}
                    </span>
                  </div>

                  <div>
                    <div className={cn('text-2xl font-bold font-mono tracking-tight md:text-3xl', tone.value)}>
                      {item.current_stock}
                    </div>
                    <p className="mt-1 truncate text-xs text-text-secondary">
                      units left · reorder at {item.reorder_level}
                      {item.supplier_name ? ` · ${item.supplier_name}` : ''}
                    </p>
                  </div>

                  {canManage && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setMovement({ kind: 'in', itemId: item.id })}
                      className="h-8 w-fit gap-1.5 rounded-md border-border-brand bg-surface text-xs font-semibold text-text-primary hover:bg-bg-subtle"
                    >
                      <ArrowDownCircle className="h-3.5 w-3.5 text-positive" /> Restock
                    </Button>
                  )}
                </div>
              );
            })
          )}
        </div>
      </section>

      {/* Expiring soon */}
      <section className="rounded-card border border-border-brand bg-surface p-5 shadow-card">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <CalendarClock className="h-4 w-4 text-accent" />
            <h2 className="text-sm font-semibold font-heading text-text-primary">Expiring Soon</h2>
          </div>
          <p className="text-xs text-text-muted">
            Items with stock that expire within {EXPIRY_WINDOW_DAYS} days
            {(expiring?.length ?? 0) > expiryRows.length &&
              ` · showing the ${expiryRows.length} soonest of ${expiring?.length}`}
          </p>
        </div>
        {loadingExpiring ? (
          <Skeleton className="h-16 w-full bg-bg-subtle" />
        ) : expiringError ? (
          <p className="text-xs text-text-muted">Couldn&apos;t load expiry alerts right now.</p>
        ) : expiryRows.length === 0 ? (
          <p className="text-xs text-text-secondary">Nothing expires in the next {EXPIRY_WINDOW_DAYS} days.</p>
        ) : (
          <ul className="divide-y divide-border-brand">
            {expiryRows.map((item) => {
              const expired = item.expire_date < today;
              return (
                <li key={item.id} className="flex items-center justify-between gap-3 py-2 text-xs">
                  <span className="truncate font-semibold text-text-primary">{item.item_name}</span>
                  <span className="flex shrink-0 items-center gap-3">
                    <span className="font-mono text-text-secondary">{item.current_stock} units</span>
                    <span className={cn('font-mono', expired ? 'text-negative' : 'text-accent')}>
                      {expired ? 'Expired ' : ''}
                      {format(parseISO(item.expire_date), 'MMM dd, yyyy')}
                    </span>
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* Stock list & movements */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Detailed Stock List */}
        <Card className="rounded-card border border-border-brand bg-surface p-5 shadow-card">
          <CardHeader className="p-0 pb-4">
            <CardTitle className="text-base font-semibold font-heading text-text-primary">
              Detailed Stock List
            </CardTitle>
            <CardDescription className="mt-1 text-xs text-text-secondary">
              {visibleItems.length} {visibleItems.length === 1 ? 'item' : 'items'} · Total value{' '}
              {formatLKR(visibleValue)}
            </CardDescription>
          </CardHeader>

          <CardContent className="p-0">
            <div className="mb-4 flex flex-col gap-3 sm:flex-row">
              <div className="relative flex-1">
                <Search
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary"
                  size={16} 
                />
                <Input
                  placeholder="Search items..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="h-10 rounded-lg border-border-brand bg-bg-subtle pl-9 text-xs focus:border-accent"
                />
              </div>
              <div className="flex rounded-lg border border-border-brand bg-bg-subtle p-1">
                {(
                  [
                    ['all', 'All items'],
                    ['low', 'Low stock'],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    key={value}
                    onClick={() => setStockFilter(value)}
                    className={cn(
                      'rounded-md px-3 py-1 text-xs font-semibold transition-all',
                      stockFilter === value
                        ? 'bg-surface text-text-primary shadow-xs'
                        : 'text-text-secondary hover:text-text-primary'
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {itemsError ? (
              <p className="rounded-xl border border-border-brand py-8 text-center text-xs text-negative">
                Couldn&apos;t load the stock list. Refresh the page to try again.
              </p>
            ) : loadingItems ? (
              <div className="space-y-2">
                <Skeleton className="h-10 w-full bg-bg-subtle" />
                <Skeleton className="h-10 w-full bg-bg-subtle" />
                <Skeleton className="h-10 w-full bg-bg-subtle" />
              </div>
            ) : (
              <div className="overflow-hidden rounded-xl border border-border-brand">
                <Table>
                  <TableHeader className="bg-bg-subtle">
                    <TableRow className="border-border-brand hover:bg-transparent">
                      <TableHead className="font-heading text-xs text-text-secondary">Item Name</TableHead>
                      <TableHead className="font-heading text-xs text-text-secondary">Stock</TableHead>
                      <TableHead className="text-right font-heading text-xs text-text-secondary">
                        Unit Cost
                      </TableHead>
                      <TableHead className="text-right font-heading text-xs text-text-secondary">
                        Total Value
                      </TableHead>
                      {canManage && (
                        <TableHead className="w-10">
                          <span className="sr-only">Edit</span>
                        </TableHead>
                      )}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {visibleItems.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={canManage ? 5 : 4} className="py-8 text-center text-xs text-text-muted">
                          {items && items.length > 0
                            ? 'No items match your search or filter'
                            : 'No inventory items yet'}
                        </TableCell>
                      </TableRow>
                    ) : (
                      visibleItems.map((item) => {
                        const status = getStockStatus(item);
                        const itemBatches = batchesByItem.get(item.id) ?? [];
                        const prices = itemBatches.map((b) => Number(b.unit_cost));
                        const mixedPrices = prices.length > 1 && Math.min(...prices) !== Math.max(...prices);
                        return (
                          <Fragment key={item.id}>
                          <TableRow className="border-border-brand transition-colors hover:bg-bg-subtle/60">
                            <TableCell className="text-xs font-semibold text-text-primary">
                              {item.item_name}
                              {itemBatches.length === 1 && (
                                <p className="mt-0.5 font-mono text-[10px] font-normal text-text-muted">
                                  Batch {itemBatches[0].batch_number}
                                </p>
                              )}
                              {itemBatches.length > 1 && (
                                <p className="mt-0.5 text-[10px] font-normal text-text-muted">
                                  {itemBatches.length} batches
                                </p>
                              )}
                            </TableCell>
                            <TableCell>
                              <div className="flex items-center gap-2">
                                <Badge
                                  variant="outline"
                                  className={cn('rounded-full px-2 py-0.5 font-mono text-[10px]', status.badge)}
                                >
                                  {item.current_stock}
                                </Badge>
                                {status.label && (
                                  <span className="text-[9px] font-bold uppercase tracking-wide text-text-muted">
                                    {status.label}
                                  </span>
                                )}
                              </div>
                            </TableCell>
                            <TableCell className="text-right font-mono text-xs font-semibold text-text-primary">
                              {mixedPrices ? (
                                <span className="text-text-secondary">See batches</span>
                              ) : (
                                formatLKR(prices.length > 0 ? prices[0] : Number(item.unit_cost))
                              )}
                            </TableCell>
                            <TableCell className="text-right font-mono text-xs text-text-secondary">
                              {formatLKR(itemValue(item))}
                            </TableCell>
                            {canManage && (
                              <TableCell className="py-1 text-right">
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => setEditing(item)}
                                  title={`Edit ${item.item_name}`}
                                  aria-label={`Edit ${item.item_name}`}
                                  className="h-8 w-8 p-0 text-text-secondary hover:text-text-primary"
                                >
                                  <Pencil className="h-3.5 w-3.5" />
                                </Button>
                              </TableCell>
                            )}
                          </TableRow>
                          {/* One line per batch when there is more than one, in the
                              order Stock Out uses them. */}
                          {itemBatches.length > 1 &&
                            itemBatches.map((b, index) => (
                              <TableRow
                                key={`batch-${b.id}`}
                                className="border-border-brand bg-bg-subtle/40 hover:bg-bg-subtle/60"
                              >
                                <TableCell className="py-1.5 pl-6 text-[11px] text-text-secondary">
                                  <span className="font-mono text-text-primary">{b.batch_number}</span>
                                  {index === 0 && (
                                    <span className="ml-2 text-[9px] font-bold uppercase tracking-wide text-accent">
                                      used next
                                    </span>
                                  )}
                                  {b.expire_date && (
                                    <span className="block text-[10px] text-text-muted">expires {b.expire_date}</span>
                                  )}
                                </TableCell>
                                <TableCell className="py-1.5 font-mono text-[11px] text-text-secondary">
                                  {b.quantity_remaining} left
                                </TableCell>
                                <TableCell className="py-1.5 text-right font-mono text-[11px] text-text-secondary">
                                  {formatLKR(Number(b.unit_cost))}
                                </TableCell>
                                <TableCell className="py-1.5 text-right font-mono text-[11px] text-text-muted">
                                  {formatLKR(b.quantity_remaining * Number(b.unit_cost))}
                                </TableCell>
                                {canManage && <TableCell className="py-1.5" />}
                              </TableRow>
                            ))}
                          </Fragment>
                        );
                      })
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Movements, one month at a time */}
        <Card className="rounded-card border border-border-brand bg-surface p-5 shadow-card">
          <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3 space-y-0 p-0 pb-4">
            <div>
              <CardTitle className="text-base font-semibold font-heading text-text-primary">
                Movements
              </CardTitle>
              <CardDescription className="mt-1 text-xs text-text-secondary">
                Every stock movement in {monthLabel(month)}, newest first
                {!loadingTransactions && !transactionsError ? ` (${movements.length})` : ''}.
              </CardDescription>
            </div>
            <div className="flex items-center gap-1">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setMonth(shiftMonth(month, -1))}
                aria-label="Previous month"
                className="h-9 w-9 p-0 text-text-secondary hover:text-text-primary"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <input
                type="month"
                aria-label="Month"
                value={month}
                max={thisMonth}
                onChange={(e) => e.target.value && setMonth(e.target.value)}
                className="h-9 rounded-lg border border-border-brand bg-bg-subtle px-2 font-mono text-xs text-text-primary outline-none focus:border-accent dark:[color-scheme:dark]"
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setMonth(shiftMonth(month, 1))}
                disabled={month >= thisMonth}
                aria-label="Next month"
                className="h-9 w-9 p-0 text-text-secondary hover:text-text-primary"
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>

          <CardContent className="p-0">
            {loadingTransactions ? (
              <div className="space-y-2">
                <Skeleton className="h-12 w-full bg-bg-subtle" />
                <Skeleton className="h-12 w-full bg-bg-subtle" />
                <Skeleton className="h-12 w-full bg-bg-subtle" />
              </div>
            ) : transactionsError ? (
              <p className="py-8 text-center text-xs text-text-muted">
                Movement history isn&apos;t available for your account.
              </p>
            ) : (
              <>
                <div className="max-h-[520px] overflow-auto rounded-xl border border-border-brand">
                  <Table>
                    <TableHeader className="sticky top-0 z-10 bg-bg-subtle">
                      <TableRow className="border-border-brand hover:bg-transparent">
                        <TableHead className="font-heading text-xs text-text-secondary">Date</TableHead>
                        <TableHead className="font-heading text-xs text-text-secondary">Item</TableHead>
                        <TableHead className="font-heading text-xs text-text-secondary">Type</TableHead>
                        <TableHead className="text-right font-heading text-xs text-text-secondary">Qty</TableHead>
                        <TableHead className="text-right font-heading text-xs text-text-secondary">
                          Amount
                        </TableHead>
                        {canManage && (
                          <TableHead className="w-10">
                            <span className="sr-only">Reverse</span>
                          </TableHead>
                        )}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {movements.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={canManage ? 6 : 5} className="py-8 text-center text-xs text-text-muted">
                            No movements in {monthLabel(month)}
                          </TableCell>
                        </TableRow>
                      ) : (
                        movements.map((tx) => {
                          const style = getMovementStyle(tx.transaction_type);
                          const MovementIcon = style.Icon;
                          const { value, estimated } = getMovementAmount(tx);
                          const isOut = style.sign === '-';
                          const destination = getProgramLabel(tx);
                          return (
                            <TableRow
                              key={tx.id}
                              className="border-border-brand align-top transition-colors hover:bg-bg-subtle/60"
                            >
                              <TableCell className="whitespace-nowrap py-3 font-mono text-xs text-text-secondary">
                                {format(parseISO(tx.transaction_date), 'dd MMM yyyy')}
                              </TableCell>
                              <TableCell className="max-w-[200px] py-3">
                                <p className="truncate text-xs font-semibold text-text-primary" title={getItemName(tx)}>
                                  {getItemName(tx)}
                                </p>
                                {tx.batch_number && (
                                  <p className="mt-0.5 truncate font-mono text-[11px] text-text-secondary" title={`Batch ${tx.batch_number}`}>
                                    Batch {tx.batch_number}
                                  </p>
                                )}
                                {destination !== '—' && (
                                  <p className="mt-0.5 truncate text-[11px] text-text-secondary" title={destination}>
                                    {destination}
                                  </p>
                                )}
                                {tx.notes && (
                                  <p className="mt-0.5 truncate text-[11px] italic text-text-muted" title={tx.notes}>
                                    {tx.notes}
                                  </p>
                                )}
                              </TableCell>
                              <TableCell className="py-3">
                                <span
                                  className={cn(
                                    'inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] font-semibold',
                                    style.pill
                                  )}
                                >
                                  <MovementIcon size={12} /> {style.label}
                                </span>
                                {tx.reverses_id != null && (
                                  <p className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-text-muted">
                                    Reversal
                                  </p>
                                )}
                                {tx.reversed_by != null && (
                                  <p className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-text-muted">
                                    Reversed
                                  </p>
                                )}
                              </TableCell>
                              <TableCell
                                className={cn(
                                  'whitespace-nowrap py-3 text-right font-mono text-xs font-semibold',
                                  isOut ? 'text-negative' : 'text-positive'
                                )}
                              >
                                {style.sign}
                                {tx.quantity.toLocaleString()}
                              </TableCell>
                              <TableCell
                                title={estimated ? 'Estimated from the current unit cost' : undefined}
                                className={cn(
                                  'whitespace-nowrap py-3 text-right font-mono text-xs text-text-primary',
                                  estimated && 'italic text-text-secondary'
                                )}
                              >
                                {value > 0 ? formatLKR(value) : '—'}
                              </TableCell>
                              {canManage && (
                                <TableCell className="py-2 text-right">
                                  {tx.reverses_id == null && tx.reversed_by == null && (
                                    <Button
                                      type="button"
                                      variant="ghost"
                                      size="sm"
                                      onClick={() => setReversing(tx)}
                                      title="Reverse this movement"
                                      aria-label={`Reverse movement of ${getItemName(tx)}`}
                                      className="h-8 w-8 p-0 text-text-secondary hover:text-text-primary"
                                    >
                                      <Undo2 className="h-3.5 w-3.5" />
                                    </Button>
                                  )}
                                </TableCell>
                              )}
                            </TableRow>
                          );
                        })
                      )}
                    </TableBody>
                  </Table>
                </div>
                {hasEstimates && (
                  <p className="mt-3 text-[10px] text-text-muted">
                    Amounts in italics are estimates from the current unit cost, because the cost wasn&apos;t
                    recorded when that movement was made.
                  </p>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {canManage && (
        <>
          <AddItemDialog open={addItemOpen} onClose={() => setAddItemOpen(false)} />
          <MovementDialog
            kind={movement?.kind ?? null}
            presetItemId={movement?.itemId}
            items={sortedItems}
            programs={activePrograms}
            onClose={() => setMovement(null)}
          />
          <EditItemDialog item={editing} onClose={() => setEditing(null)} />
          <ReverseMovementDialog
            movement={reversing}
            itemName={reversing ? getItemName(reversing) : ''}
            onClose={() => setReversing(null)}
          />
        </>
      )}
    </div>
  );
}
