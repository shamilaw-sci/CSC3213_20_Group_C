'use client';

// Void confirmation shared by the Ledger and the Overview.
//
// A Stock In expense gets two extra things. A warning that names the stock
// movement behind it, because voiding takes the money off the books but
// leaves the stock in Inventory (which has no reversal yet). And a required
// reason, which the API writes to the audit entry.

import { useState } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { useStockMovement, useVoidTransaction } from '@/hooks/useFinance';
import { describeTransaction, sourceOf } from '@/lib/finance-source';
import { formatDate, formatLKR } from '@/lib/formatters';
import { getApiErrorMessage } from '@/lib/inventory';
import { cn } from '@/lib/utils';
import type { Transaction } from '@/types';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';

type VoidableRow = Transaction & { description?: string; program_name?: string };

export function VoidTransactionDialog({
  transaction,
  onClose,
}: {
  transaction: VoidableRow | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={!!transaction} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-surface border-border-brand">
        {/* Remounted per row, so the reason starts empty every time. */}
        {transaction && <VoidForm key={transaction.id} transaction={transaction} onClose={onClose} />}
      </DialogContent>
    </Dialog>
  );
}

function VoidForm({ transaction, onClose }: { transaction: VoidableRow; onClose: () => void }) {
  const stockIn = sourceOf(transaction) === 'stock_in';
  const [reason, setReason] = useState('');
  const { mutate: voidTransaction, isPending } = useVoidTransaction();
  const missingReason = stockIn && !reason.trim();

  const submit = () => {
    if (missingReason) return;
    voidTransaction(
      { id: transaction.id, reason: reason.trim() || undefined },
      {
        onSuccess: () => {
          toast.success(`Transaction #${transaction.id} voided.`);
          onClose();
        },
        onError: (err: unknown) => toast.error(getApiErrorMessage(err, 'Failed to void the transaction')),
      },
    );
  };

  return (
    <>
      <DialogHeader>
        <DialogTitle>Void transaction #{transaction.id}?</DialogTitle>
        <DialogDescription>
          {transaction.transaction_type} of {formatLKR(transaction.amount)} on {transaction.transaction_date} (
          {describeTransaction(transaction)}). Voiding keeps it on the ledger as a reversal. Voided transactions
          can&apos;t be edited or restored.
        </DialogDescription>
      </DialogHeader>

      {stockIn && <StockInWarning transaction={transaction} />}

      <div>
        <label
          htmlFor="void-reason"
          className="mb-1 block text-[11px] font-bold uppercase tracking-wide text-text-secondary"
        >
          {stockIn ? 'Reason (required)' : 'Reason (optional)'}
        </label>
        <textarea
          id="void-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          maxLength={500}
          rows={2}
          placeholder={stockIn ? 'e.g. Stock In entered twice' : 'Why is this being voided?'}
          className={cn(
            'w-full rounded-md border border-border-brand bg-surface px-2 py-2 text-xs text-text-primary',
            'outline-none focus:border-accent',
          )}
        />
        <p className="mt-1 text-[11px] text-text-muted">Saved with the void in the audit log.</p>
      </div>

      <DialogFooter>
        <Button variant="outline" onClick={onClose} disabled={isPending}>Cancel</Button>
        <Button
          onClick={submit}
          disabled={isPending || missingReason}
          className="bg-negative text-white hover:bg-negative/90"
        >
          {isPending ? 'Voiding…' : 'Void transaction'}
        </Button>
      </DialogFooter>
    </>
  );
}

function StockInWarning({ transaction }: { transaction: VoidableRow }) {
  const { data: movement, isLoading } = useStockMovement(transaction.id);

  return (
    <div
      role="note"
      className="flex gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-text-primary"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" aria-hidden />
      <div className="space-y-1">
        <p>
          This takes the expense off the books, but the stock it paid for stays in Inventory. Correct the stock
          there as well:
        </p>
        {isLoading ? (
          <p className="flex items-center gap-1 text-text-secondary">
            <Loader2 className="h-3 w-3 animate-spin" /> Finding the Stock In…
          </p>
        ) : movement ? (
          <p className="font-semibold">
            {movement.item_name ?? 'Unknown item'} · {movement.quantity.toLocaleString()} units · Stock In on{' '}
            {formatDate(movement.transaction_date)} · {formatLKR(movement.total_cost)}
          </p>
        ) : (
          <p className="text-text-secondary">
            This expense isn&apos;t linked to its Stock In. Look in the Inventory history for a Stock In on{' '}
            {formatDate(transaction.transaction_date)} costing {formatLKR(transaction.amount)}.
          </p>
        )}
      </div>
    </div>
  );
}
