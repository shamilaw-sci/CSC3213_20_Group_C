'use client';

import { useState } from 'react';
import { useAuthStore } from '@/store/useAuthStore';
import { hasPermission } from '@/lib/permissions';
import { getApiErrorMessage, parseQuantity, todayISO } from '@/lib/inventory';
import { cn } from '@/lib/utils';
import ProtectedRoute from '@/components/layout/protected-route';
import { FIELD_CLASS, LABEL_CLASS } from '@/components/inventory/stock-dialogs';
import { useInventoryItems, useCreateInventoryTransaction, useItemOutstanding } from '@/hooks/useInventory';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

// The sidebar only shows this page to inventory:issue holders, but a typed URL
// bypasses the sidebar, so the page checks for itself. The inner check stops
// the item and program requests firing before ProtectedRoute redirects.
export default function ReturnInventoryPage() {
  const { user } = useAuthStore();
  const canWrite = hasPermission(user?.role as string, 'inventory:issue');
  return (
    <ProtectedRoute requiredPermission="inventory:issue">
      {canWrite ? <ReturnForm /> : null}
    </ProtectedRoute>
  );
}

function ReturnForm() {
  const { data: items } = useInventoryItems();
  const { mutate: createTransaction, isPending } = useCreateInventoryTransaction();
  const today = todayISO();

  const [itemId, setItemId] = useState('');
  const [programId, setProgramId] = useState('');
  const [quantity, setQuantity] = useState('');
  const [transactionDate, setTransactionDate] = useState(today);
  const [notes, setNotes] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const sortedItems = [...(items ?? [])].sort((a, b) => a.item_name.localeCompare(b.item_name));

  // A return must come from the program the stock was issued to, and cannot
  // be more than that program still holds. Only those programs are offered.
  const { data: outstanding, isLoading: loadingOutstanding } = useItemOutstanding(
    itemId ? Number(itemId) : undefined
  );
  const holders = (outstanding ?? []).filter((o) => o.outstanding > 0);
  const held = holders.find((o) => o.program_id === Number(programId))?.outstanding ?? 0;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    if (!itemId || !programId || !quantity || !transactionDate) {
      setError('Choose an item and the program it is returned from, and enter a quantity and date.');
      return;
    }
    if (transactionDate > today) {
      setError('Date cannot be in the future.');
      return;
    }
    const parsed = parseQuantity(quantity);
    if ('error' in parsed) {
      setError(parsed.error);
      return;
    }
    const qty = parsed.value;
    if (qty > held) {
      setError(`That program holds only ${held} of this item (issued minus already returned).`);
      return;
    }

    createTransaction(
      {
        item_id: Number(itemId),
        program_id: Number(programId),
        quantity: qty,
        transaction_type: 'Return',
        transaction_date: transactionDate,
        notes: notes.trim() || null,
      },
      {
        onSuccess: () => {
          setSuccess('Items returned to stock.');
          setItemId('');
          setProgramId('');
          setQuantity('');
          setNotes('');
          setTransactionDate(todayISO());
        },
        onError: (err: unknown) => setError(getApiErrorMessage(err, 'Failed to return items.')),
      }
    );
  };

  const programPlaceholder = !itemId
    ? 'Choose an item first'
    : loadingOutstanding
      ? 'Loading...'
      : holders.length === 0
        ? 'No program holds this item'
        : 'Select a program';

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="mb-2 text-3xl font-bold font-heading tracking-tight text-text-primary">
          Return Inventory
        </h1>
        <p className="text-sm text-text-secondary">
          Record unused stock coming back from the program it was issued to.
        </p>
      </div>

      <Card className="rounded-card border border-border-brand bg-surface p-5 shadow-card">
        <CardHeader className="p-0 pb-4">
          <CardTitle className="text-base font-semibold font-heading text-text-primary">New Return</CardTitle>
          <CardDescription className="mt-1 text-xs text-text-secondary">
            Only programs that still hold the chosen item are listed.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div role="alert" className="rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-sm text-negative">
                {error}
              </div>
            )}
            {success && (
              <div role="status" className="rounded-lg border border-green-500/20 bg-green-500/10 p-3 text-sm text-positive">
                {success}
              </div>
            )}

            <div>
              <label htmlFor="return-item" className={LABEL_CLASS}>Item to return</label>
              <select
                id="return-item"
                value={itemId}
                onChange={(e) => {
                  setItemId(e.target.value);
                  setProgramId('');
                }}
                className={FIELD_CLASS}
              >
                <option value="">Select an item</option>
                {sortedItems.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.item_name} ({i.current_stock} in stock)
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="return-program" className={LABEL_CLASS}>Returned from program</label>
              <select
                id="return-program"
                value={programId}
                onChange={(e) => setProgramId(e.target.value)}
                disabled={!itemId || loadingOutstanding || holders.length === 0}
                className={FIELD_CLASS}
              >
                <option value="">{programPlaceholder}</option>
                {holders.map((h) => (
                  <option key={h.program_id} value={h.program_id}>
                    {h.program_name ?? `Program #${h.program_id}`} (holds {h.outstanding})
                  </option>
                ))}
              </select>
              {itemId && !loadingOutstanding && holders.length === 0 && (
                <p className="mt-1 text-[11px] text-text-muted">
                  Nothing of this item is out with a program, so there is nothing to return.
                </p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="return-qty" className={LABEL_CLASS}>Quantity</label>
                <input
                  id="return-qty"
                  type="number"
                  min={1}
                  max={programId ? held : undefined}
                  step={1}
                  inputMode="numeric"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  placeholder="0"
                  className={cn(FIELD_CLASS, 'font-mono')}
                />
              </div>
              <div>
                <label htmlFor="return-date" className={LABEL_CLASS}>Date</label>
                <input
                  id="return-date"
                  type="date"
                  max={today}
                  value={transactionDate}
                  onChange={(e) => setTransactionDate(e.target.value)}
                  className={cn(FIELD_CLASS, 'font-mono')}
                />
              </div>
            </div>

            <div>
              <label htmlFor="return-notes" className={LABEL_CLASS}>Notes (optional)</label>
              <textarea
                id="return-notes"
                rows={2}
                maxLength={500}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="e.g. Unopened vials after the camp"
                className={cn(FIELD_CLASS, 'h-auto py-2')}
              />
            </div>

            <Button type="submit" disabled={isPending} className="h-10 w-full bg-accent font-semibold text-white hover:bg-accent/90">
              {isPending ? 'Saving...' : 'Confirm Return'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
