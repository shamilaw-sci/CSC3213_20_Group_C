'use client';

// Stock page forms (Add Item, Stock In, Stock Out, Return), built on the
// app's themed Dialog instead of SweetAlert HTML strings. That keeps them in
// the light/dark theme, lets labels point at their inputs, and means names
// typed by users are rendered by React instead of pasted into HTML.

import { useState } from 'react';
import { toast } from 'sonner';

import {
  useCreateInventoryItem,
  useCreateInventoryTransaction,
  useItemOutstanding,
} from '@/hooks/useInventory';
import { getApiErrorMessage, MAX_QUANTITY, parseQuantity, todayISO } from '@/lib/inventory';
import { cn } from '@/lib/utils';
import type { InventoryItem } from '@/types';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

export type MovementKind = 'in' | 'out' | 'return';

type ProgramOption = { id: number; program_name: string };

export const FIELD_CLASS =
  'h-10 w-full rounded-lg border border-border-brand bg-bg-subtle px-3 text-sm text-text-primary outline-none transition-colors focus:border-accent disabled:opacity-60 dark:[color-scheme:dark]';
export const LABEL_CLASS =
  'mb-1 block text-[11px] font-bold uppercase tracking-wide text-text-secondary';
const HELP_CLASS = 'mt-1 text-[11px] text-text-muted';

function FormError({ message }: { message: string }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-xs text-negative"
    >
      {message}
    </div>
  );
}

function DialogShell({
  open,
  onClose,
  title,
  description,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="border border-border-brand bg-surface text-text-primary sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-lg font-semibold text-text-primary">{title}</DialogTitle>
          <DialogDescription className="text-xs text-text-secondary">{description}</DialogDescription>
        </DialogHeader>
        {children}
      </DialogContent>
    </Dialog>
  );
}

function FormButtons({
  onCancel,
  saving,
  label,
}: {
  onCancel: () => void;
  saving: boolean;
  label: string;
}) {
  return (
    <DialogFooter className="border-border-brand bg-bg-subtle/60">
      <Button
        type="button"
        variant="outline"
        onClick={onCancel}
        disabled={saving}
        className="border-border-brand bg-surface text-text-primary hover:bg-bg-subtle"
      >
        Cancel
      </Button>
      <Button type="submit" disabled={saving} className="bg-accent text-white hover:bg-accent/90">
        {saving ? 'Saving...' : label}
      </Button>
    </DialogFooter>
  );
}

// ---------------------------------------------------------------------------
// Add Item
// ---------------------------------------------------------------------------

export function AddItemDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <DialogShell
      open={open}
      onClose={onClose}
      title="Add Inventory Item"
      description="This registers the item with 0 stock. Add its stock afterwards with Stock In."
    >
      {/* Remounted on each open, so the fields start empty every time. */}
      {open && <AddItemForm onClose={onClose} />}
    </DialogShell>
  );
}

function AddItemForm({ onClose }: { onClose: () => void }) {
  const createItem = useCreateInventoryItem();
  const [name, setName] = useState('');
  const [cost, setCost] = useState('');
  const [supplier, setSupplier] = useState('');
  const [expire, setExpire] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!name.trim() || !cost.trim()) {
      setError('Item name and unit cost are required.');
      return;
    }
    const costVal = Number(cost);
    if (!Number.isFinite(costVal) || costVal <= 0) {
      setError('Unit cost must be more than 0.');
      return;
    }

    createItem.mutate(
      {
        item_name: name.trim(),
        // Always 0: stock is only added with Stock In.
        current_stock: 0,
        unit_cost: costVal,
        supplier_name: supplier.trim() || undefined,
        expire_date: expire || undefined,
      },
      {
        onSuccess: () => {
          toast.success('Inventory item added.');
          onClose();
        },
        onError: (err: unknown) => setError(getApiErrorMessage(err, 'Failed to add the item.')),
      }
    );
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <FormError message={error} />
      <div>
        <label htmlFor="inv-add-name" className={LABEL_CLASS}>
          Item name
        </label>
        <input
          id="inv-add-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={255}
          placeholder="e.g. Rabies Vaccine Vials"
          className={FIELD_CLASS}
        />
      </div>
      <div>
        <div>
          <label htmlFor="inv-add-cost" className={LABEL_CLASS}>
            Unit cost (LKR)
          </label>
          <input
            id="inv-add-cost"
            type="number"
            min={0.01}
            step={0.01}
            inputMode="decimal"
            value={cost}
            onChange={(e) => setCost(e.target.value)}
            placeholder="1500"
            className={cn(FIELD_CLASS, 'font-mono')}
          />
        </div>
      </div>
      <div>
        <label htmlFor="inv-add-supplier" className={LABEL_CLASS}>
          Supplier (optional)
        </label>
        <input
          id="inv-add-supplier"
          value={supplier}
          onChange={(e) => setSupplier(e.target.value)}
          maxLength={255}
          placeholder="e.g. ABC Pharma"
          className={FIELD_CLASS}
        />
      </div>
      <div>
        <label htmlFor="inv-add-expire" className={LABEL_CLASS}>
          Expiry date (optional)
        </label>
        <input
          id="inv-add-expire"
          type="date"
          value={expire}
          onChange={(e) => setExpire(e.target.value)}
          className={cn(FIELD_CLASS, 'font-mono')}
        />
      </div>
      <FormButtons onCancel={onClose} saving={createItem.isPending} label="Add Item" />
    </form>
  );
}

// ---------------------------------------------------------------------------
// Stock In / Stock Out / Return
// ---------------------------------------------------------------------------

const MOVEMENT_TEXT: Record<MovementKind, { title: string; description: string; button: string }> = {
  in: {
    title: 'Stock In',
    description: 'New stock arriving. Unit cost, supplier and expiry belong to the item.',
    button: 'Record Stock In',
  },
  out: {
    title: 'Stock Out',
    description:
      'Stock issued to a program. With no program it is a stock adjustment (for example a breakage or count correction) and needs a reason.',
    button: 'Record Stock Out',
  },
  return: {
    title: 'Stock Return',
    description:
      'Unused stock coming back from the program it was issued to. Stock that was never issued is added with Stock In.',
    button: 'Record Return',
  },
};

export function MovementDialog({
  kind,
  presetItemId,
  items,
  programs,
  onClose,
}: {
  kind: MovementKind | null;
  presetItemId?: number;
  items: InventoryItem[];
  programs: ProgramOption[];
  onClose: () => void;
}) {
  const text = MOVEMENT_TEXT[kind ?? 'in'];
  return (
    <DialogShell open={kind !== null} onClose={onClose} title={text.title} description={text.description}>
      {kind && (
        <MovementForm
          key={kind}
          kind={kind}
          presetItemId={presetItemId}
          items={items}
          programs={programs}
          buttonLabel={text.button}
          onClose={onClose}
        />
      )}
    </DialogShell>
  );
}

function MovementForm({
  kind,
  presetItemId,
  items,
  programs,
  buttonLabel,
  onClose,
}: {
  kind: MovementKind;
  presetItemId?: number;
  items: InventoryItem[];
  programs: ProgramOption[];
  buttonLabel: string;
  onClose: () => void;
}) {
  const createTransaction = useCreateInventoryTransaction();
  const today = todayISO();

  const [itemId, setItemId] = useState(presetItemId ? String(presetItemId) : '');
  const [programId, setProgramId] = useState('');
  const [quantity, setQuantity] = useState('');
  const [date, setDate] = useState(today);
  const [notes, setNotes] = useState('');
  const [error, setError] = useState('');

  const selectedItem = items.find((i) => i.id === Number(itemId));

  // Returns: only programs that still hold some of the chosen item.
  const { data: outstanding, isLoading: loadingOutstanding } = useItemOutstanding(
    kind === 'return' && itemId ? Number(itemId) : undefined
  );
  const holders = (outstanding ?? []).filter((o) => o.outstanding > 0);
  const heldBySelected = holders.find((o) => o.program_id === Number(programId))?.outstanding ?? 0;

  const isAdjustment = kind === 'out' && !programId;
  const notesLabel = isAdjustment ? 'Reason (required)' : 'Notes (optional)';

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!itemId || !date) {
      setError('Choose an item and a date.');
      return;
    }
    if (date > today) {
      setError('Date cannot be in the future.');
      return;
    }
    const parsed = parseQuantity(quantity);
    if ('error' in parsed) {
      setError(parsed.error);
      return;
    }
    const qty = parsed.value;

    if (kind === 'out') {
      if (selectedItem && qty > selectedItem.current_stock) {
        setError(`Insufficient stock: only ${selectedItem.current_stock} available.`);
        return;
      }
      if (isAdjustment && !notes.trim()) {
        setError('A stock adjustment needs a reason in the notes.');
        return;
      }
    }
    if (kind === 'return') {
      if (!programId) {
        setError('Choose the program this stock is returned from.');
        return;
      }
      if (qty > heldBySelected) {
        setError(`That program holds only ${heldBySelected} of this item.`);
        return;
      }
    }

    createTransaction.mutate(
      {
        item_id: Number(itemId),
        quantity: qty,
        transaction_type: kind === 'in' ? 'Restock' : kind === 'out' ? 'Issue' : 'Return',
        transaction_date: date,
        program_id: kind === 'in' || !programId ? null : Number(programId),
        notes: notes.trim() || null,
      },
      {
        onSuccess: () => {
          toast.success(`${MOVEMENT_TEXT[kind].title} recorded.`);
          onClose();
        },
        onError: (err: unknown) =>
          setError(getApiErrorMessage(err, `Failed to record ${MOVEMENT_TEXT[kind].title}.`)),
      }
    );
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <FormError message={error} />

      <div>
        <label htmlFor="inv-mv-item" className={LABEL_CLASS}>
          Inventory item
        </label>
        <select
          id="inv-mv-item"
          value={itemId}
          onChange={(e) => {
            setItemId(e.target.value);
            setProgramId('');
          }}
          className={FIELD_CLASS}
        >
          <option value="">Select an item</option>
          {items.map((i) => (
            <option key={i.id} value={i.id}>
              {i.item_name} ({i.current_stock} in stock)
            </option>
          ))}
        </select>
      </div>

      {kind === 'out' && (
        <div>
          <label htmlFor="inv-mv-program" className={LABEL_CLASS}>
            Program
          </label>
          <select
            id="inv-mv-program"
            value={programId}
            onChange={(e) => setProgramId(e.target.value)}
            className={FIELD_CLASS}
          >
            <option value="">Stock adjustment (no program)</option>
            {programs.map((p) => (
              <option key={p.id} value={p.id}>
                {p.program_name}
              </option>
            ))}
          </select>
        </div>
      )}

      {kind === 'return' && (
        <div>
          <label htmlFor="inv-mv-program" className={LABEL_CLASS}>
            Returned from program
          </label>
          <select
            id="inv-mv-program"
            value={programId}
            onChange={(e) => setProgramId(e.target.value)}
            disabled={!itemId || loadingOutstanding || holders.length === 0}
            className={FIELD_CLASS}
          >
            <option value="">
              {!itemId
                ? 'Choose an item first'
                : loadingOutstanding
                  ? 'Loading...'
                  : holders.length === 0
                    ? 'No program holds this item'
                    : 'Select a program'}
            </option>
            {holders.map((h) => (
              <option key={h.program_id} value={h.program_id}>
                {h.program_name ?? `Program #${h.program_id}`} (holds {h.outstanding})
              </option>
            ))}
          </select>
          {itemId && !loadingOutstanding && holders.length === 0 && (
            <p className={HELP_CLASS}>
              Nothing of this item is out with a program, so there is nothing to return.
            </p>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="inv-mv-qty" className={LABEL_CLASS}>
            Quantity
          </label>
          <input
            id="inv-mv-qty"
            type="number"
            min={1}
            max={
              kind === 'out'
                ? selectedItem?.current_stock
                : kind === 'return' && programId
                  ? heldBySelected
                  : MAX_QUANTITY
            }
            step={1}
            inputMode="numeric"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            placeholder="0"
            className={cn(FIELD_CLASS, 'font-mono')}
          />
        </div>
        <div>
          <label htmlFor="inv-mv-date" className={LABEL_CLASS}>
            Date
          </label>
          <input
            id="inv-mv-date"
            type="date"
            max={today}
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className={cn(FIELD_CLASS, 'font-mono')}
          />
        </div>
      </div>

      <div>
        <label htmlFor="inv-mv-notes" className={LABEL_CLASS}>
          {notesLabel}
        </label>
        <textarea
          id="inv-mv-notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          maxLength={500}
          rows={3}
          placeholder={isAdjustment ? 'e.g. 2 vials broken in transit' : 'Any additional detail...'}
          className={cn(FIELD_CLASS, 'h-auto py-2')}
        />
      </div>

      <FormButtons onCancel={onClose} saving={createTransaction.isPending} label={buttonLabel} />
    </form>
  );
}
