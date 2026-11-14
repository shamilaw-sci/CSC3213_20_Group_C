'use client';

// Stock page forms (Add Item, Edit Item, Stock In, Stock Out, Return,
// Reverse), built on the
// app's themed Dialog instead of SweetAlert HTML strings. That keeps them in
// the light/dark theme, lets labels point at their inputs, and means names
// typed by users are rendered by React instead of pasted into HTML.

import { useState } from 'react';
import { toast } from 'sonner';

import {
  useCreateInventoryItem,
  useCreateInventoryTransaction,
  useItemBatches,
  useItemOutstanding,
  useReverseInventoryTransaction,
  useUpdateInventoryBatch,
  useUpdateInventoryItem,
} from '@/hooks/useInventory';
import { formatLKR } from '@/lib/formatters';
import {
  DEFAULT_REORDER_LEVEL,
  getApiErrorMessage,
  MAX_QUANTITY,
  parseQuantity,
  todayISO,
} from '@/lib/inventory';
import { cn } from '@/lib/utils';
import type {
  InventoryBatch,
  InventoryBatchUpdate,
  InventoryItem,
  InventoryItemUpdate,
  InventoryTransaction,
} from '@/types';
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
  wide = false,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description: string;
  children: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent
        className={cn(
          // Never taller than the screen: the form scrolls inside the dialog.
          'max-h-[calc(100dvh-2rem)] overflow-y-auto border border-border-brand bg-surface text-text-primary',
          wide ? 'sm:max-w-xl' : 'sm:max-w-md'
        )}
      >
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
      description="This registers the item with 0 stock. Add its stock, and each batch's expiry date, with Stock In."
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
  const [reorder, setReorder] = useState('');
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
    const reorderVal = parseReorderLevel(reorder);
    if (reorderVal === 'invalid') {
      setError(`Reorder level must be a whole number from 0 to ${MAX_QUANTITY.toLocaleString()}.`);
      return;
    }

    createItem.mutate(
      {
        item_name: name.trim(),
        // Always 0: stock is only added with Stock In.
        current_stock: 0,
        unit_cost: costVal,
        supplier_name: supplier.trim() || undefined,
        ...(reorderVal !== null ? { reorder_level: reorderVal } : {}),
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
      <ReorderLevelField id="inv-add-reorder" value={reorder} onChange={setReorder} />
      <FormButtons onCancel={onClose} saving={createItem.isPending} label="Add Item" />
    </form>
  );
}

/** '' = not set (null); a whole number 0..MAX_QUANTITY; anything else 'invalid'. */
function parseReorderLevel(raw: string): number | null | 'invalid' {
  const text = raw.trim();
  if (!text) return null;
  const value = Number(text);
  if (!Number.isInteger(value) || value < 0 || value > MAX_QUANTITY) return 'invalid';
  return value;
}

function ReorderLevelField({
  id,
  value,
  onChange,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label htmlFor={id} className={LABEL_CLASS}>
        Reorder level (optional)
      </label>
      <input
        id={id}
        type="number"
        min={0}
        max={MAX_QUANTITY}
        step={1}
        inputMode="numeric"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={String(DEFAULT_REORDER_LEVEL)}
        className={cn(FIELD_CLASS, 'font-mono')}
      />
      <p className={HELP_CLASS}>
        Shown as low stock below this many units. Leave empty for the default ({DEFAULT_REORDER_LEVEL}).
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Edit Item
// ---------------------------------------------------------------------------

export function EditItemDialog({ item, onClose }: { item: InventoryItem | null; onClose: () => void }) {
  return (
    <DialogShell
      open={item !== null}
      onClose={onClose}
      title="Edit Item"
      description="Correct the name, supplier or reorder level, or a batch's number, expiry date or unit price. Stock changes only through Stock In, Stock Out and Return."
      wide
    >
      {item && <EditItemForm key={item.id} item={item} onClose={onClose} />}
    </DialogShell>
  );
}

function EditItemForm({ item, onClose }: { item: InventoryItem; onClose: () => void }) {
  const updateItem = useUpdateInventoryItem();
  const [name, setName] = useState(item.item_name);
  const [supplier, setSupplier] = useState(item.supplier_name ?? '');
  const [reorder, setReorder] = useState(item.reorder_level == null ? '' : String(item.reorder_level));
  const [error, setError] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!name.trim()) {
      setError('Item name is required.');
      return;
    }
    const reorderVal = parseReorderLevel(reorder);
    if (reorderVal === 'invalid') {
      setError(`Reorder level must be a whole number from 0 to ${MAX_QUANTITY.toLocaleString()}.`);
      return;
    }

    // Only what changed is sent, so the audit log shows just that.
    const changes: InventoryItemUpdate = {};
    if (name.trim() !== item.item_name) changes.item_name = name.trim();
    if ((supplier.trim() || null) !== (item.supplier_name ?? null)) changes.supplier_name = supplier.trim() || null;
    if (reorderVal !== (item.reorder_level ?? null)) changes.reorder_level = reorderVal;
    if (Object.keys(changes).length === 0) {
      onClose();
      return;
    }

    updateItem.mutate(
      { id: item.id, changes },
      {
        onSuccess: () => {
          toast.success('Item updated.');
          onClose();
        },
        onError: (err: unknown) => setError(getApiErrorMessage(err, 'Failed to update the item.')),
      }
    );
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {/* Only this part scrolls, so the buttons stay in place. The negative
          margin matches the dialog's padding, so nothing is cut off. */}
      <div className="-mx-4 max-h-[60vh] space-y-4 overflow-y-auto px-4">
        <FormError message={error} />
        <BatchList itemId={item.id} />
        <div>
          <label htmlFor="inv-edit-name" className={LABEL_CLASS}>
            Item name
          </label>
          <input
            id="inv-edit-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={255}
            className={FIELD_CLASS}
          />
        </div>
        <div>
          <label htmlFor="inv-edit-supplier" className={LABEL_CLASS}>
            Supplier (optional)
          </label>
          <input
            id="inv-edit-supplier"
            value={supplier}
            onChange={(e) => setSupplier(e.target.value)}
            maxLength={255}
            className={FIELD_CLASS}
          />
        </div>
        <ReorderLevelField id="inv-edit-reorder" value={reorder} onChange={setReorder} />
      </div>
      <FormButtons onCancel={onClose} saving={updateItem.isPending} label="Save Changes" />
    </form>
  );
}

// ---------------------------------------------------------------------------
// Batches (shown in Edit Item)
// ---------------------------------------------------------------------------

// The item's batches with stock left, in the order Stock Out uses them
// (soonest expiry first). The item's expiry date is the first one here.
function BatchList({ itemId }: { itemId: number }) {
  const { data: batches, isLoading, isError } = useItemBatches(itemId);
  const [editingId, setEditingId] = useState<number | null>(null);

  return (
    <div>
      <p className={LABEL_CLASS}>Batches in stock</p>
      {isLoading ? (
        <div className="h-14 animate-pulse rounded-lg border border-border-brand bg-bg-subtle" />
      ) : isError ? (
        <p className="text-xs text-negative">Could not load the batches.</p>
      ) : !batches || batches.length === 0 ? (
        <p className="text-xs text-text-muted">No stock on hand.</p>
      ) : (
        <ul className="divide-y divide-border-brand rounded-lg border border-border-brand">
          {batches.map((batch, index) =>
            editingId === batch.id ? (
              <BatchEditRow key={batch.id} batch={batch} onDone={() => setEditingId(null)} />
            ) : (
              <li key={batch.id} className="flex items-center gap-3 px-3 py-2 text-xs">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-mono font-semibold text-text-primary">
                    {batch.batch_number}
                    {index === 0 && batches.length > 1 && (
                      <span className="ml-2 font-sans text-[10px] font-medium uppercase text-accent">used next</span>
                    )}
                  </p>
                  <p className="text-text-secondary">
                    {batch.quantity_remaining.toLocaleString()} of {batch.quantity_received.toLocaleString()} left
                    {' · '}
                    {formatLKR(Number(batch.unit_cost))} each
                    {' · '}expires {batch.expire_date ?? 'not set'}
                    {batch.received_date ? ` · received ${batch.received_date}` : ''}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setEditingId(batch.id)}
                  className="rounded-md px-2 py-1 font-semibold text-accent hover:bg-bg-subtle"
                >
                  Edit
                </button>
              </li>
            )
          )}
        </ul>
      )}
    </div>
  );
}

function BatchEditRow({ batch, onDone }: { batch: InventoryBatch; onDone: () => void }) {
  const updateBatch = useUpdateInventoryBatch();
  const [number, setNumber] = useState(batch.batch_number);
  const [expire, setExpire] = useState(batch.expire_date ?? '');
  const [price, setPrice] = useState(String(batch.unit_cost));
  const [error, setError] = useState('');

  const save = () => {
    setError('');
    if (!number.trim()) {
      setError('Batch number is required.');
      return;
    }
    const priceValue = Number(price);
    if (!price.trim() || !Number.isFinite(priceValue) || priceValue <= 0) {
      setError('Unit price must be more than 0.');
      return;
    }
    const changes: InventoryBatchUpdate = {};
    if (number.trim() !== batch.batch_number) changes.batch_number = number.trim();
    if ((expire || null) !== (batch.expire_date ?? null)) changes.expire_date = expire || null;
    if (priceValue !== Number(batch.unit_cost)) changes.unit_cost = priceValue;
    if (Object.keys(changes).length === 0) {
      onDone();
      return;
    }
    updateBatch.mutate(
      { id: batch.id, changes },
      {
        onSuccess: () => {
          toast.success('Batch updated.');
          onDone();
        },
        onError: (err: unknown) => setError(getApiErrorMessage(err, 'Failed to update the batch.')),
      }
    );
  };

  return (
    <li
      className="space-y-2 bg-bg-subtle/60 px-3 py-3 text-xs"
      // Enter saves this batch instead of submitting the item form around it.
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          save();
        }
      }}
    >
      <FormError message={error} />
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <div>
          <label htmlFor={`inv-batch-no-${batch.id}`} className={LABEL_CLASS}>
            Batch number
          </label>
          <input
            id={`inv-batch-no-${batch.id}`}
            value={number}
            onChange={(e) => setNumber(e.target.value)}
            maxLength={100}
            className={cn(FIELD_CLASS, 'font-mono')}
          />
        </div>
        <div>
          <label htmlFor={`inv-batch-exp-${batch.id}`} className={LABEL_CLASS}>
            Expiry date
          </label>
          <input
            id={`inv-batch-exp-${batch.id}`}
            type="date"
            value={expire}
            onChange={(e) => setExpire(e.target.value)}
            className={cn(FIELD_CLASS, 'font-mono')}
          />
        </div>
        <div>
          <label htmlFor={`inv-batch-cost-${batch.id}`} className={LABEL_CLASS}>
            Unit price (LKR)
          </label>
          <input
            id={`inv-batch-cost-${batch.id}`}
            type="number"
            min={0.01}
            step="0.01"
            inputMode="decimal"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            className={cn(FIELD_CLASS, 'font-mono')}
          />
        </div>
      </div>
      <p className={HELP_CLASS}>
        The price changes what later Stock Outs from this batch cost. The expense already in Finance stays
        the same. To correct that, reverse the Stock In and record it again.
      </p>
      <div className="flex justify-end gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={onDone}
          disabled={updateBatch.isPending}
          className="h-8 border-border-brand bg-surface text-text-primary hover:bg-bg-subtle"
        >
          Cancel
        </Button>
        <Button
          type="button"
          onClick={save}
          disabled={updateBatch.isPending}
          className="h-8 bg-accent text-white hover:bg-accent/90"
        >
          {updateBatch.isPending ? 'Saving...' : 'Save Batch'}
        </Button>
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Reverse a movement
// ---------------------------------------------------------------------------

const REVERSE_EFFECT: Record<string, string> = {
  Restock:
    'The stock comes back out of its batch and the expense this Stock In posted to Finance is voided. If this was the latest Stock In, the item goes back to the price it had before.',
  Issue: 'The stock comes back into the store, and the program is no longer charged for it.',
  Return: 'The stock goes back out to the program, and the program is charged for it again.',
};

export function ReverseMovementDialog({
  movement,
  itemName,
  onClose,
}: {
  movement: InventoryTransaction | null;
  itemName: string;
  onClose: () => void;
}) {
  return (
    <DialogShell
      open={movement !== null}
      onClose={onClose}
      title="Reverse Movement"
      description="Records the opposite movement, dated today, at the same cost. The original stays in the history."
    >
      {movement && <ReverseForm key={movement.id} movement={movement} itemName={itemName} onClose={onClose} />}
    </DialogShell>
  );
}

function ReverseForm({
  movement,
  itemName,
  onClose,
}: {
  movement: InventoryTransaction;
  itemName: string;
  onClose: () => void;
}) {
  const reverse = useReverseInventoryTransaction();
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (reason.trim().length < 3) {
      setError('Give a reason for the reversal.');
      return;
    }
    reverse.mutate(
      { id: movement.id, reason: reason.trim() },
      {
        onSuccess: () => {
          toast.success('Movement reversed.');
          onClose();
        },
        onError: (err: unknown) => setError(getApiErrorMessage(err, 'Failed to reverse the movement.')),
      }
    );
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <FormError message={error} />
      <div className="rounded-lg border border-border-brand bg-bg-subtle p-3 text-xs text-text-secondary">
        <p className="font-semibold text-text-primary">
          {movement.quantity.toLocaleString()} x {itemName}, {movement.transaction_date}
          {Number(movement.total_cost) > 0 ? `, ${formatLKR(Number(movement.total_cost))}` : ''}
        </p>
        <p className="mt-1">
          {movement.rescue_case_id != null && movement.transaction_type === 'Issue'
            ? 'The stock comes back into the store, and the rescue case is no longer charged for it.'
            : REVERSE_EFFECT[movement.transaction_type] ?? ''}
        </p>
      </div>
      <div>
        <label htmlFor="inv-rev-reason" className={LABEL_CLASS}>
          Reason (required)
        </label>
        <textarea
          id="inv-rev-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          maxLength={300}
          rows={3}
          placeholder="e.g. Entered 50 instead of 5"
          className={cn(FIELD_CLASS, 'h-auto py-2')}
        />
      </div>
      <FormButtons onCancel={onClose} saving={reverse.isPending} label="Reverse" />
    </form>
  );
}

// ---------------------------------------------------------------------------
// Stock In / Stock Out / Return
// ---------------------------------------------------------------------------

const MOVEMENT_TEXT: Record<MovementKind, { title: string; description: string; button: string }> = {
  in: {
    title: 'Stock In',
    description:
      'New stock arriving as a new batch. Its cost is posted to Finance as an expense. Enter the batch number and expiry date printed on it, if it has them.',
    button: 'Record Stock In',
  },
  out: {
    title: 'Stock Out',
    description:
      'Stock issued to an Active program, taken from the batch that expires first and costed at that batch\'s price. With no program it is a stock adjustment (for example a breakage or count correction) and needs a reason.',
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
    <DialogShell
      open={kind !== null}
      onClose={onClose}
      title={text.title}
      description={text.description}
      wide={kind === 'in'}
    >
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
  const [expiry, setExpiry] = useState('');
  const [batchNumber, setBatchNumber] = useState('');
  const [error, setError] = useState('');
  // Stock In only: the price paid per unit, prefilled with the item's stored
  // cost. A different price becomes the item's stored cost (last price paid).
  const [unitPrice, setUnitPrice] = useState(() => {
    const preset = items.find((i) => i.id === presetItemId);
    return kind === 'in' && preset ? String(preset.unit_cost) : '';
  });

  const selectedItem = items.find((i) => i.id === Number(itemId));
  const priceValue = Number(unitPrice);
  const priceChanged = !!selectedItem && unitPrice.trim() !== '' && priceValue !== selectedItem.unit_cost;
  const quantityValue = Number(quantity);
  const stockInTotal =
    Number.isInteger(quantityValue) && quantityValue > 0 && priceValue > 0 ? quantityValue * priceValue : null;

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

    if (kind === 'in' && (!unitPrice.trim() || !Number.isFinite(priceValue) || priceValue <= 0)) {
      setError('Unit price must be more than 0.');
      return;
    }
    if (kind === 'in' && expiry && expiry < date) {
      setError('This batch has already expired. Check the expiry date.');
      return;
    }

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
        ...(kind === 'in' ? { unit_cost: priceValue } : {}),
        ...(kind === 'in' && expiry ? { expire_date: expiry } : {}),
        ...(kind === 'in' && batchNumber.trim() ? { batch_number: batchNumber.trim() } : {}),
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
            if (kind === 'in') {
              const item = items.find((i) => i.id === Number(e.target.value));
              setUnitPrice(item ? String(item.unit_cost) : '');
            }
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
          <p className={HELP_CLASS}>Only Active programs are listed.</p>
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

      {kind === 'in' && (
        <div>
          <label htmlFor="inv-mv-price" className={LABEL_CLASS}>
            Unit price paid (LKR)
          </label>
          <input
            id="inv-mv-price"
            type="number"
            min={0.01}
            step="0.01"
            inputMode="decimal"
            value={unitPrice}
            onChange={(e) => setUnitPrice(e.target.value)}
            disabled={!selectedItem}
            placeholder={selectedItem ? undefined : 'Choose an item first'}
            className={cn(FIELD_CLASS, 'font-mono')}
          />
          <p className={HELP_CLASS}>
            {selectedItem && priceChanged
              ? `Was ${formatLKR(selectedItem.unit_cost)}. This price becomes the item's stored cost.`
              : "Prefilled with the item's stored cost. Change it if you paid a different price."}
            {stockInTotal !== null && ` Total ${formatLKR(stockInTotal)}, posted to Finance as an expense.`}
          </p>
        </div>
      )}

      {kind === 'in' && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor="inv-mv-batch" className={LABEL_CLASS}>
              Batch number (optional)
            </label>
            <input
              id="inv-mv-batch"
              value={batchNumber}
              onChange={(e) => setBatchNumber(e.target.value)}
              maxLength={100}
              placeholder="e.g. LOT-2026-114"
              className={cn(FIELD_CLASS, 'font-mono')}
            />
            <p className={HELP_CLASS}>Left empty, one is made from the date, like 20261110-57.</p>
          </div>
          <div>
            <label htmlFor="inv-mv-expiry" className={LABEL_CLASS}>
              Batch expiry date (optional)
            </label>
            <input
              id="inv-mv-expiry"
              type="date"
              min={date || undefined}
              value={expiry}
              onChange={(e) => setExpiry(e.target.value)}
              className={cn(FIELD_CLASS, 'font-mono')}
            />
            <p className={HELP_CLASS}>
              Stock Out uses the batch that expires first. The item shows the soonest expiry among the stock on hand.
            </p>
          </div>
        </div>
      )}

      <div>
        <label htmlFor="inv-mv-notes" className={LABEL_CLASS}>
          {notesLabel}
        </label>
        <textarea
          id="inv-mv-notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          maxLength={500}
          rows={kind === 'in' ? 2 : 3}
          placeholder={isAdjustment ? 'e.g. 2 vials broken in transit' : 'Any additional detail...'}
          className={cn(FIELD_CLASS, 'h-auto py-2')}
        />
      </div>

      <FormButtons onCancel={onClose} saving={createTransaction.isPending} label={buttonLabel} />
    </form>
  );
}
