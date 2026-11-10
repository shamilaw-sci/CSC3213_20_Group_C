'use client';

import { useState } from 'react';
import { useAuthStore } from '@/store/useAuthStore';
import { hasPermission } from '@/lib/permissions';
import { formatLKR } from '@/lib/formatters';
import { getApiErrorMessage, isActiveProgram, parseQuantity, todayISO } from '@/lib/inventory';
import { cn } from '@/lib/utils';
import ProtectedRoute from '@/components/layout/protected-route';
import { FIELD_CLASS, LABEL_CLASS } from '@/components/inventory/stock-dialogs';
import { useInventoryItems, useCreateInventoryTransaction } from '@/hooks/useInventory';
import { usePrograms } from '@/hooks/useFinance';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

// The sidebar only shows this page to inventory:issue holders, but a typed URL
// bypasses the sidebar, so the page checks for itself. The inner check stops
// the item and program requests firing before ProtectedRoute redirects.
export default function IssueInventoryPage() {
  const { user } = useAuthStore();
  const canWrite = hasPermission(user?.role as string, 'inventory:issue');
  return (
    <ProtectedRoute requiredPermission="inventory:issue">
      {canWrite ? <IssueForm /> : null}
    </ProtectedRoute>
  );
}

function IssueForm() {
  const { data: items } = useInventoryItems();
  const { data: programs } = usePrograms();
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
  // Stock is only issued to a program that is running; the API refuses the
  // rest, so they are not offered.
  const activePrograms = (programs ?? [])
    .filter((p) => isActiveProgram(p.status))
    .sort((a, b) => a.program_name.localeCompare(b.program_name));
  const selectedItem = sortedItems.find((i) => i.id === Number(itemId));

  // Cost preview at the item's current unit cost (the server works out the
  // saved cost the same way).
  const previewQty = Number(quantity);
  const preview =
    selectedItem && Number.isInteger(previewQty) && previewQty > 0
      ? previewQty * Number(selectedItem.unit_cost)
      : null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    // Issues from this page always go to a program; stock adjustments with
    // no program are made on the Stock page.
    if (!itemId || !programId || !quantity || !transactionDate) {
      setError('Choose an item and a program, and enter a quantity and date.');
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
    if (selectedItem && qty > selectedItem.current_stock) {
      setError(`Insufficient stock: only ${selectedItem.current_stock} available.`);
      return;
    }

    createTransaction(
      {
        item_id: Number(itemId),
        program_id: Number(programId),
        quantity: qty,
        transaction_type: 'Issue',
        transaction_date: transactionDate,
        notes: notes.trim() || null,
      },
      {
        onSuccess: () => {
          setSuccess('Items issued.');
          setItemId('');
          setProgramId('');
          setQuantity('');
          setNotes('');
          setTransactionDate(todayISO());
        },
        onError: (err: unknown) => setError(getApiErrorMessage(err, 'Failed to issue items.')),
      }
    );
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="mb-2 text-3xl font-bold font-heading tracking-tight text-text-primary">
          Issue Inventory
        </h1>
        <p className="text-sm text-text-secondary">
          Record stock taken out for a program. The cost is charged to that program.
        </p>
      </div>

      <Card className="rounded-card border border-border-brand bg-surface p-5 shadow-card">
        <CardHeader className="p-0 pb-4">
          <CardTitle className="text-base font-semibold font-heading text-text-primary">New Issuance</CardTitle>
          <CardDescription className="mt-1 text-xs text-text-secondary">All fields except notes are required.</CardDescription>
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
              <label htmlFor="issue-item" className={LABEL_CLASS}>Item to issue</label>
              <select id="issue-item" value={itemId} onChange={(e) => setItemId(e.target.value)} className={FIELD_CLASS}>
                <option value="">Select an item</option>
                {sortedItems.map((i) => (
                  <option key={i.id} value={i.id} disabled={i.current_stock <= 0}>
                    {i.item_name} ({i.current_stock} in stock)
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="issue-program" className={LABEL_CLASS}>Program</label>
              <select id="issue-program" value={programId} onChange={(e) => setProgramId(e.target.value)} className={FIELD_CLASS}>
                <option value="">
                  {programs && activePrograms.length === 0 ? 'No Active programs' : 'Select a program'}
                </option>
                {activePrograms.map((p) => (
                  <option key={p.id} value={p.id}>{p.program_name}</option>
                ))}
              </select>
              <p className="mt-1 text-[11px] text-text-muted">Only Active programs are listed.</p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="issue-qty" className={LABEL_CLASS}>Quantity</label>
                <input
                  id="issue-qty"
                  type="number"
                  min={1}
                  max={selectedItem?.current_stock}
                  step={1}
                  inputMode="numeric"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  placeholder="0"
                  className={cn(FIELD_CLASS, 'font-mono')}
                />
              </div>
              <div>
                <label htmlFor="issue-date" className={LABEL_CLASS}>Date</label>
                <input
                  id="issue-date"
                  type="date"
                  max={today}
                  value={transactionDate}
                  onChange={(e) => setTransactionDate(e.target.value)}
                  className={cn(FIELD_CLASS, 'font-mono')}
                />
              </div>
            </div>

            <div>
              <label htmlFor="issue-notes" className={LABEL_CLASS}>Notes (optional)</label>
              <textarea
                id="issue-notes"
                rows={2}
                maxLength={500}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="e.g. Kandy sterilisation camp"
                className={cn(FIELD_CLASS, 'h-auto py-2')}
              />
            </div>

            {preview !== null && (
              <p className="text-xs text-text-secondary">
                Estimated cost to the program:{' '}
                <span className="font-mono font-semibold text-text-primary">{formatLKR(preview)}</span>
              </p>
            )}

            <Button type="submit" disabled={isPending} className="h-10 w-full bg-accent font-semibold text-white hover:bg-accent/90">
              {isPending ? 'Saving...' : 'Confirm Issuance'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
