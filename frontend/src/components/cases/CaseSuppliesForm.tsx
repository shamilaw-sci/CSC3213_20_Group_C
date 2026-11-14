'use client';

import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { useCreateInventoryTransaction, useInventoryItems } from '@/hooks/useInventory';
import { formatLKR } from '@/lib/formatters';
import { getApiErrorMessage, parseQuantity, todayISO } from '@/lib/inventory';

const field =
  'w-full rounded-md border border-border-brand bg-surface px-2 py-2 text-sm text-text-primary outline-none focus:border-accent';

/**
 * Supplies used on an open case: a Stock Out against the case, costed from
 * the batches it takes, like an issue to a program. There are no returns
 * from a case; a mistake is undone with Reverse on the Stock page.
 */
export function CaseSuppliesForm({ caseId, onRecorded }: { caseId: string; onRecorded: () => void }) {
  const queryClient = useQueryClient();
  const { data: items } = useInventoryItems();
  const { mutate: issue, isPending } = useCreateInventoryTransaction();
  const today = todayISO();

  const [itemId, setItemId] = useState('');
  const [quantity, setQuantity] = useState('');
  const [date, setDate] = useState(today);
  const [notes, setNotes] = useState('');
  const [error, setError] = useState('');

  const inStock = [...(items ?? [])]
    .filter((i) => i.current_stock > 0)
    .sort((a, b) => a.item_name.localeCompare(b.item_name));
  const selected = inStock.find((i) => i.id === Number(itemId));

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!itemId || !quantity || !date) {
      setError('Choose an item and enter a quantity and date.');
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
    if (selected && parsed.value > selected.current_stock) {
      setError(`Insufficient stock: only ${selected.current_stock} available.`);
      return;
    }
    issue(
      {
        item_id: Number(itemId),
        program_id: null,
        rescue_case_id: caseId,
        quantity: parsed.value,
        transaction_type: 'Issue',
        transaction_date: date,
        notes: notes.trim() || null,
      },
      {
        onSuccess: () => {
          setItemId('');
          setQuantity('');
          setNotes('');
          setDate(todayISO());
          queryClient.invalidateQueries({ queryKey: ['rescueCases', 'timeline', caseId] });
          onRecorded();
        },
        onError: (err: unknown) => setError(getApiErrorMessage(err, "Couldn't record the supplies.")),
      },
    );
  };

  return (
    <form onSubmit={submit} className="space-y-2">
      <div className="grid grid-cols-[1fr_5rem] gap-2">
        <select value={itemId} onChange={(e) => setItemId(e.target.value)} aria-label="Item" className={field}>
          <option value="">Item…</option>
          {inStock.map((i) => (
            <option key={i.id} value={i.id}>{i.item_name} ({i.current_stock} in stock)</option>
          ))}
        </select>
        <input
          type="number" min={1} step={1} inputMode="numeric" value={quantity}
          onChange={(e) => setQuantity(e.target.value)} placeholder="Qty" aria-label="Quantity" className={field}
        />
      </div>
      <div className="grid grid-cols-[9rem_1fr] gap-2">
        <input type="date" value={date} max={today} onChange={(e) => setDate(e.target.value)}
          aria-label="Date used" className={field} />
        <input value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500}
          placeholder="Note (optional), e.g. dose" aria-label="Supplies note" className={field} />
      </div>
      {error && <p className="text-xs text-negative">{error}</p>}
      <div className="flex items-center justify-between gap-2">
        <p className="text-[10px] text-text-muted">
          {selected
            ? `About ${formatLKR((Number(quantity) || 0) * Number(selected.unit_cost))}; the saved cost uses the batches taken.`
            : 'Taken out of stock and charged to this case.'}
        </p>
        <Button type="submit" size="sm" disabled={isPending}
          className="shrink-0 bg-accent text-white hover:bg-accent/90">
          {isPending ? 'Recording…' : 'Record supplies'}
        </Button>
      </div>
    </form>
  );
}
