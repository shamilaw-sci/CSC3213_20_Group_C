'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { format, parseISO } from 'date-fns';
import Swal from 'sweetalert2';
import { toast } from 'sonner';
import {
  AlertTriangle,
  ArrowDownCircle,
  ArrowUpCircle,
  CheckCircle2,
  Package,
  Plus,
  RotateCcw,
  Search,
  type LucideIcon,
} from 'lucide-react';

import {
  useInventoryItems,
  useInventoryTransactions,
  useCreateInventoryTransaction,
  useCreateInventoryItem,
  useLowStockItems,
} from '@/hooks/useInventory';
import { FinanceService } from '@/services/finance.service';
import { useAuthStore } from '@/store/useAuthStore';
import { useThemeStore } from '@/store/useThemeStore';
import { hasPermission } from '@/lib/permissions';
import { formatLKR } from '@/lib/formatters';
import { cn } from '@/lib/utils';
import type { InventoryItem, InventoryTransaction } from '@/types';
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

// Items with fewer units than this count as "low stock". The page passes it to
// the backend (GET /inventory/alerts/low-stock), and the backend decides which
// items are low, so there is a single definition of "low stock" in the system.
const LOW_STOCK_THRESHOLD = 10;
const MAX_ALERT_CARDS = 4;
const MAX_MOVEMENTS = 10;

const ACTION_BUTTON =
  'h-11 gap-2 rounded-lg px-5 text-sm font-semibold text-white shadow-sm transition-colors';

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
    pill: 'border-blue-500/20 bg-blue-500/10 text-blue-600',
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
// Dialog helpers (SweetAlert forms)
// ---------------------------------------------------------------------------

// Item and program names are typed by users and end up inside HTML strings,
// so they are escaped before being put in <option> tags.
const escapeHtml = (value: string) =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

function getSwalTheme() {
  const isDark = useThemeStore.getState().theme === 'dark';
  const muted = isDark ? '#9CA3AF' : '#6B7280';
  const inputStyle = `width: 100%; margin-top: 4px; box-sizing: border-box; font-size: 12px; height: 38px; background: ${
    isDark ? '#14161C' : '#FFFFFF'
  }; color: ${isDark ? '#F9FAFB' : '#111318'}; border: 1px solid ${
    isDark ? '#232730' : '#E5E7EB'
  }; border-radius: 8px; padding: 0 10px;`;

  return {
    background: isDark ? '#0F1520' : '#FFFFFF',
    color: isDark ? '#F9FAFB' : '#111318',
    cancelButtonColor: isDark ? '#232730' : '#E5E7EB',
    inputStyle,
    textareaStyle: `${inputStyle} height: 70px; padding: 8px 10px; font-family: inherit;`,
    labelStyle: `display: block; font-size: 10px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; color: ${muted};`,
    helpStyle: `margin-top: 4px; font-size: 11px; color: ${muted};`,
  };
}

type SwalTheme = ReturnType<typeof getSwalTheme>;

const swalField = (t: SwalTheme, label: string, control: string, help?: string) =>
  `<div><label style="${t.labelStyle}">${label}</label>${control}${
    help ? `<p style="${t.helpStyle}">${help}</p>` : ''
  }</div>`;

const swalForm = (fields: string[]) =>
  `<div style="display: flex; flex-direction: column; gap: 12px; text-align: left; font-family: sans-serif;">${fields.join(
    ''
  )}</div>`;

const buildItemOptions = (items: InventoryItem[], selectedId?: number) =>
  items
    .map(
      (item) =>
        `<option value="${item.id}"${item.id === selectedId ? ' selected' : ''}>${escapeHtml(
          item.item_name
        )} (Current: ${item.current_stock})</option>`
    )
    .join('');

const buildProgramOptions = (programs?: { id: number; program_name: string }[]) =>
  (programs ?? [])
    .map((p) => `<option value="${p.id}">${escapeHtml(p.program_name)}</option>`)
    .join('');

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function InventoryPage() {
  const { user } = useAuthStore();
  const canIssue = hasPermission(user?.role as string, 'inventory:issue');

  const { data: items, isLoading: loadingItems } = useInventoryItems();
  const {
    data: transactions,
    isLoading: loadingTransactions,
    isError: transactionsError,
  } = useInventoryTransactions();
  const {
    data: lowStock,
    isLoading: loadingLowStock,
    isError: lowStockError,
  } = useLowStockItems(LOW_STOCK_THRESHOLD);

  const createItem = useCreateInventoryItem();
  const createTransaction = useCreateInventoryTransaction();

  // Programs for the Stock Out / Return dialogs
  const { data: programs } = useQuery({
    queryKey: ['programs'],
    queryFn: FinanceService.getPrograms,
  });

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

  const visibleValue = useMemo(
    () => visibleItems.reduce((sum, i) => sum + i.current_stock * Number(i.unit_cost), 0),
    [visibleItems]
  );

  const unitCostById = useMemo(
    () => new Map((items ?? []).map((i) => [i.id, Number(i.unit_cost)])),
    [items]
  );

  // Newest first; the id breaks ties between movements on the same day.
  const movements = useMemo(
    () =>
      [...(transactions ?? [])]
        .sort(
          (a, b) =>
            b.transaction_date.localeCompare(a.transaction_date) || b.id - a.id
        )
        .slice(0, MAX_MOVEMENTS),
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

  // ---- dialogs ------------------------------------------------------------

  const handleAddItem = () => {
    const t = getSwalTheme();

    Swal.fire({
      title: 'Add Inventory Item',
      html: swalForm([
        swalField(
          t,
          'Item name',
          `<input id="swal-iname" style="${t.inputStyle}" placeholder="e.g. Rabies Vaccine Vials">`
        ),
        swalField(
          t,
          'Initial stock',
          `<input id="swal-istock" type="number" min="0" style="${t.inputStyle}" placeholder="100">`
        ),
        swalField(
          t,
          'Unit cost (LKR)',
          `<input id="swal-icost" type="number" min="0" step="0.01" style="${t.inputStyle}" placeholder="1500">`
        ),
        swalField(
          t,
          'Supplier (optional)',
          `<input id="swal-isupplier" style="${t.inputStyle}" placeholder="e.g. ABC Pharma">`
        ),
        swalField(
          t,
          'Expire date (optional)',
          `<input id="swal-iexpire" type="date" style="${t.inputStyle}">`
        ),
      ]),
      background: t.background,
      color: t.color,
      showCancelButton: true,
      confirmButtonText: 'Add Item',
      confirmButtonColor: '#EF9F27',
      cancelButtonText: 'Cancel',
      cancelButtonColor: t.cancelButtonColor,
      preConfirm: () => {
        const name = (document.getElementById('swal-iname') as HTMLInputElement).value.trim();
        const stock = (document.getElementById('swal-istock') as HTMLInputElement).value.trim();
        const cost = (document.getElementById('swal-icost') as HTMLInputElement).value.trim();
        const supplier = (document.getElementById('swal-isupplier') as HTMLInputElement).value.trim();
        const expire = (document.getElementById('swal-iexpire') as HTMLInputElement).value;

        if (!name || !stock || !cost) {
          Swal.showValidationMessage('Item name, stock, and unit cost are required');
          return false;
        }

        const stockVal = parseInt(stock);
        const costVal = parseFloat(cost);

        if (isNaN(stockVal) || stockVal < 0) {
          Swal.showValidationMessage('Stock must be a non-negative integer');
          return false;
        }
        if (isNaN(costVal) || costVal <= 0) {
          Swal.showValidationMessage('Unit cost must be a positive number');
          return false;
        }

        return {
          item_name: name,
          current_stock: stockVal,
          unit_cost: costVal,
          supplier_name: supplier || undefined,
          expire_date: expire || undefined,
        };
      },
    }).then((result) => {
      if (result.isConfirmed && result.value) {
        createItem.mutate(result.value, {
          onSuccess: () => toast.success('Inventory item added successfully!'),
          onError: (err: any) =>
            toast.error(err?.response?.data?.detail || 'Failed to add inventory item'),
        });
      }
    });
  };

  // STOCK IN: new inventory entering the organization (transaction_type
  // 'Restock', never tied to a program). Supplier, unit cost and expiry belong
  // to the item and are set once in Add Item. An optional item id pre-selects
  // that item, which is how the "Restock" button on a low-stock box works.
  const handleStockIn = (presetItemId?: number) => {
    if (!items || items.length === 0) {
      toast.error('Add an inventory item first before stocking in');
      return;
    }

    const t = getSwalTheme();
    const today = format(new Date(), 'yyyy-MM-dd');

    Swal.fire({
      title: 'Stock In',
      html: swalForm([
        swalField(
          t,
          'Inventory item',
          `<select id="swal-in-item" style="${t.inputStyle}">${buildItemOptions(items, presetItemId)}</select>`
        ),
        swalField(
          t,
          'Quantity',
          `<input id="swal-in-qty" type="number" min="1" style="${t.inputStyle}" placeholder="50">`
        ),
        swalField(
          t,
          'Date',
          `<input id="swal-in-date" type="date" style="${t.inputStyle}" value="${today}">`
        ),
        swalField(
          t,
          'Notes (optional)',
          `<textarea id="swal-in-notes" style="${t.textareaStyle}" placeholder="Any additional detail..."></textarea>`
        ),
      ]),
      background: t.background,
      color: t.color,
      showCancelButton: true,
      confirmButtonText: 'Stock In',
      confirmButtonColor: '#059669',
      cancelButtonText: 'Cancel',
      cancelButtonColor: t.cancelButtonColor,
      preConfirm: () => {
        const itemIdStr = (document.getElementById('swal-in-item') as HTMLSelectElement).value;
        const qtyStr = (document.getElementById('swal-in-qty') as HTMLInputElement).value.trim();
        const dateStr = (document.getElementById('swal-in-date') as HTMLInputElement).value;
        const notes = (document.getElementById('swal-in-notes') as HTMLTextAreaElement).value.trim();

        if (!itemIdStr || !qtyStr || !dateStr) {
          Swal.showValidationMessage('Item, quantity, and date are required');
          return false;
        }

        const qtyVal = parseInt(qtyStr);
        if (isNaN(qtyVal) || qtyVal <= 0) {
          Swal.showValidationMessage('Quantity must be a positive number');
          return false;
        }

        return {
          item_id: parseInt(itemIdStr),
          quantity: qtyVal,
          transaction_type: 'Restock' as const,
          transaction_date: dateStr,
          program_id: null,
          notes: notes || undefined,
        };
      },
    }).then((result) => {
      if (result.isConfirmed && result.value) {
        createTransaction.mutate(result.value, {
          onSuccess: () => toast.success('Stock In recorded successfully!'),
          onError: (err: any) =>
            toast.error(err?.response?.data?.detail || 'Failed to record Stock In'),
        });
      }
    });
  };

  // STOCK OUT: inventory issued for veterinary work (transaction_type 'Issue').
  // program_id is how Cost-per-Animal knows which program used the stock.
  const handleStockOut = () => {
    if (!items || items.length === 0) {
      toast.error('No inventory items available to issue');
      return;
    }

    const t = getSwalTheme();
    const today = format(new Date(), 'yyyy-MM-dd');

    Swal.fire({
      title: 'Stock Out',
      html: swalForm([
        swalField(
          t,
          'Inventory item',
          `<select id="swal-out-item" style="${t.inputStyle}">${buildItemOptions(items)}</select>`
        ),
        swalField(
          t,
          'Quantity',
          `<input id="swal-out-qty" type="number" min="1" style="${t.inputStyle}" placeholder="10">`
        ),
        swalField(
          t,
          'Program (optional)',
          `<select id="swal-out-program" style="${t.inputStyle}"><option value="none">Stock Adjustment (No Program)</option>${buildProgramOptions(
            programs
          )}</select>`
        ),
        swalField(
          t,
          'Date',
          `<input id="swal-out-date" type="date" style="${t.inputStyle}" value="${today}">`
        ),
      ]),
      background: t.background,
      color: t.color,
      showCancelButton: true,
      confirmButtonText: 'Stock Out',
      confirmButtonColor: '#E11D48',
      cancelButtonText: 'Cancel',
      cancelButtonColor: t.cancelButtonColor,
      preConfirm: () => {
        const itemIdStr = (document.getElementById('swal-out-item') as HTMLSelectElement).value;
        const qtyStr = (document.getElementById('swal-out-qty') as HTMLInputElement).value.trim();
        const progIdStr = (document.getElementById('swal-out-program') as HTMLSelectElement).value;
        const dateStr = (document.getElementById('swal-out-date') as HTMLInputElement).value;

        if (!itemIdStr || !qtyStr || !dateStr) {
          Swal.showValidationMessage('Item, quantity, and date are required');
          return false;
        }

        const qtyVal = parseInt(qtyStr);
        if (isNaN(qtyVal) || qtyVal <= 0) {
          Swal.showValidationMessage('Quantity must be a positive number');
          return false;
        }

        return {
          item_id: parseInt(itemIdStr),
          quantity: qtyVal,
          transaction_type: 'Issue' as const,
          transaction_date: dateStr,
          program_id: progIdStr === 'none' ? null : parseInt(progIdStr),
        };
      },
    }).then((result) => {
      if (result.isConfirmed && result.value) {
        createTransaction.mutate(result.value, {
          onSuccess: () => toast.success('Stock Out recorded successfully!'),
          // The backend sends the exact reason (e.g. "Insufficient stock").
          onError: (err: any) =>
            toast.error(err?.response?.data?.detail || 'Failed to record Stock Out'),
        });
      }
    });
  };

  // STOCK RETURN: unused inventory coming back (transaction_type 'Return').
  // The program is optional: choose the program the stock was issued to, or
  // leave it as general stock.
  const handleStockReturn = () => {
    if (!items || items.length === 0) {
      toast.error('No inventory items available to return');
      return;
    }

    const t = getSwalTheme();
    const today = format(new Date(), 'yyyy-MM-dd');

    Swal.fire({
      title: 'Stock Return',
      html: swalForm([
        swalField(
          t,
          'Inventory item',
          `<select id="swal-ret-item" style="${t.inputStyle}">${buildItemOptions(items)}</select>`
        ),
        swalField(
          t,
          'Quantity',
          `<input id="swal-ret-qty" type="number" min="1" style="${t.inputStyle}" placeholder="10">`
        ),
        swalField(
          t,
          'Returned from program (optional)',
          `<select id="swal-ret-program" style="${t.inputStyle}"><option value="none">General stock (no program)</option>${buildProgramOptions(
            programs
          )}</select>`,
          'Pick the program this stock was issued to.'
        ),
        swalField(
          t,
          'Date',
          `<input id="swal-ret-date" type="date" style="${t.inputStyle}" value="${today}">`
        ),
      ]),
      background: t.background,
      color: t.color,
      showCancelButton: true,
      confirmButtonText: 'Return Stock',
      confirmButtonColor: '#2563EB',
      cancelButtonText: 'Cancel',
      cancelButtonColor: t.cancelButtonColor,
      preConfirm: () => {
        const itemIdStr = (document.getElementById('swal-ret-item') as HTMLSelectElement).value;
        const qtyStr = (document.getElementById('swal-ret-qty') as HTMLInputElement).value.trim();
        const progIdStr = (document.getElementById('swal-ret-program') as HTMLSelectElement).value;
        const dateStr = (document.getElementById('swal-ret-date') as HTMLInputElement).value;

        if (!itemIdStr || !qtyStr || !dateStr) {
          Swal.showValidationMessage('Item, quantity, and date are required');
          return false;
        }

        const qtyVal = parseInt(qtyStr);
        if (isNaN(qtyVal) || qtyVal <= 0) {
          Swal.showValidationMessage('Quantity must be a positive number');
          return false;
        }

        return {
          item_id: parseInt(itemIdStr),
          quantity: qtyVal,
          transaction_type: 'Return' as const,
          transaction_date: dateStr,
          program_id: progIdStr === 'none' ? null : parseInt(progIdStr),
        };
      },
    }).then((result) => {
      if (result.isConfirmed && result.value) {
        createTransaction.mutate(result.value, {
          onSuccess: () => toast.success('Stock Return recorded successfully!'),
          onError: (err: any) =>
            toast.error(err?.response?.data?.detail || 'Failed to record Stock Return'),
        });
      }
    });
  };

  // ---- render -------------------------------------------------------------

  return (
    <div className="space-y-8 pb-12">
      {/* Header */}
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-center">
        <div>
          <h1 className="mb-2 text-3xl font-bold font-heading tracking-tight text-text-primary">
            Inventory System
          </h1>
          <p className="text-sm text-text-secondary">
            Manage medical supplies, equipment, and resource allocations.
          </p>
        </div>

        {canIssue && (
          <div className="flex flex-wrap items-center gap-3">
            <Button
              onClick={handleAddItem}
              className={cn(ACTION_BUTTON, 'bg-[#EF9F27] hover:bg-[#D97706]')}
            >
              <Plus className="h-4 w-4" /> Add Item
            </Button>
            <span className="hidden h-8 w-px bg-border-brand sm:block" />
            <Button
              onClick={() => handleStockIn()}
              className={cn(ACTION_BUTTON, 'bg-emerald-600 hover:bg-emerald-700')}
            >
              <ArrowDownCircle className="h-4 w-4" /> Stock In
            </Button>
            <Button
              onClick={handleStockOut}
              className={cn(ACTION_BUTTON, 'bg-rose-600 hover:bg-rose-700')}
            >
              <ArrowUpCircle className="h-4 w-4" /> Stock Out
            </Button>
            <Button
              onClick={handleStockReturn}
              className={cn(ACTION_BUTTON, 'bg-blue-600 hover:bg-blue-700')}
            >
              <RotateCcw className="h-4 w-4" /> Stock Return
            </Button>
          </div>
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
            Items with fewer than {LOW_STOCK_THRESHOLD} units
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
                  Every item has at least {LOW_STOCK_THRESHOLD} units on hand.
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
                      units left{item.supplier_name ? ` · ${item.supplier_name}` : ''}
                    </p>
                  </div>

                  {canIssue && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => handleStockIn(item.id)}
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

      {/* Stock list & movements */}
      <div className="grid gap-8 lg:grid-cols-5">
        {/* Detailed Stock List */}
        <Card className="rounded-card border border-border-brand bg-surface p-5 shadow-card lg:col-span-3">
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

            {loadingItems ? (
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
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {visibleItems.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={4} className="py-8 text-center text-xs text-text-muted">
                          {items && items.length > 0
                            ? 'No items match your search or filter'
                            : 'No inventory items yet'}
                        </TableCell>
                      </TableRow>
                    ) : (
                      visibleItems.map((item) => {
                        const status = getStockStatus(item);
                        return (
                          <TableRow
                            key={item.id}
                            className="border-border-brand transition-colors hover:bg-bg-subtle/60"
                          >
                            <TableCell className="text-xs font-semibold text-text-primary">
                              {item.item_name}
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
                              {formatLKR(Number(item.unit_cost))}
                            </TableCell>
                            <TableCell className="text-right font-mono text-xs text-text-secondary">
                              {formatLKR(item.current_stock * Number(item.unit_cost))}
                            </TableCell>
                          </TableRow>
                        );
                      })
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent Movements */}
        <Card className="rounded-card border border-border-brand bg-surface p-5 shadow-card lg:col-span-2">
          <CardHeader className="p-0 pb-4">
            <CardTitle className="text-base font-semibold font-heading text-text-primary">
              Recent Movements
            </CardTitle>
            <CardDescription className="mt-1 text-xs text-text-secondary">
              Last {MAX_MOVEMENTS} stock movements.
            </CardDescription>
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
                <div className="overflow-x-auto rounded-xl border border-border-brand">
                  <Table>
                    <TableHeader className="bg-bg-subtle">
                      <TableRow className="border-border-brand hover:bg-transparent">
                        <TableHead className="font-heading text-xs text-text-secondary">Date</TableHead>
                        <TableHead className="font-heading text-xs text-text-secondary">Type</TableHead>
                        <TableHead className="text-right font-heading text-xs text-text-secondary">
                          Amount
                        </TableHead>
                        <TableHead className="font-heading text-xs text-text-secondary">Program</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {movements.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={4} className="py-8 text-center text-xs italic text-text-muted">
                            No recent movements
                          </TableCell>
                        </TableRow>
                      ) : (
                        movements.map((tx) => {
                          const style = getMovementStyle(tx.transaction_type);
                          const MovementIcon = style.Icon;
                          const { value, estimated } = getMovementAmount(tx);
                          return (
                            <TableRow
                              key={tx.id}
                              className="border-border-brand transition-colors hover:bg-bg-subtle/60"
                            >
                              <TableCell className="whitespace-nowrap text-xs text-text-secondary">
                                {format(parseISO(tx.transaction_date), 'MMM dd, yyyy')}
                              </TableCell>
                              <TableCell>
                                <div className="flex flex-col items-start gap-1">
                                  <span
                                    className={cn(
                                      'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide',
                                      style.pill
                                    )}
                                  >
                                    <MovementIcon size={12} /> {style.label}
                                  </span>
                                  <span className="max-w-[130px] truncate text-[10px] text-text-muted">
                                    {tx.inventory_items?.item_name ?? `Item #${tx.item_id}`}
                                  </span>
                                </div>
                              </TableCell>
                              <TableCell className="text-right">
                                <p
                                  title={estimated ? 'Estimated from the current unit cost' : undefined}
                                  className={cn(
                                    'font-mono text-xs font-bold',
                                    style.sign === '-' ? 'text-negative' : 'text-positive',
                                    estimated && 'italic'
                                  )}
                                >
                                  {value > 0 ? `${style.sign}${formatLKR(value)}` : '—'}
                                </p>
                                <p className="font-mono text-[10px] text-text-muted">{tx.quantity} units</p>
                              </TableCell>
                              <TableCell className="text-xs text-text-secondary">
                                {tx.programs?.program_name ??
                                  (tx.transaction_type === 'Issue' ? 'Stock adjustment' : '—')}
                              </TableCell>
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
    </div>
  );
}
