'use client';

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FinanceService } from '@/services/finance.service';
import { Transaction } from '@/types';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { TrendingUp, TrendingDown, Loader2, Lock, ShieldAlert } from 'lucide-react';
import { useAuthStore } from '@/store/useAuthStore';
import { hasPermission } from '@/lib/permissions';

interface NewTransactionModalProps {
  open: boolean;
  onClose: () => void;
}

const EMPTY_FORM = {
  transaction_date: new Date().toISOString().split('T')[0],
  amount: '',
  transaction_type: '' as 'Income' | 'Expense' | '',
  status: '' as 'Cash' | 'Receivable' | '',
  program_id: null as number | null,
  is_restricted: false,
};

export function NewTransactionModal({ open, onClose }: NewTransactionModalProps) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  // Set when the backend rejects an overspend with 409. Holding it separately
  // from `error` is what lets the override affordance appear only after a real
  // shortfall, rather than inviting an override before one exists.
  const [shortfall, setShortfall] = useState<string | null>(null);

  const { user } = useAuthStore();
  const canOverride = hasPermission(user?.role as string, 'finance:restricted:override');

  const { data: programs } = useQuery({
    queryKey: ['programs'],
    queryFn: FinanceService.getPrograms,
  });

  // Live balance for the chosen program, so an expense shows what is left
  // before it is submitted rather than only after a rejection.
  const { data: balance } = useQuery({
    queryKey: ['restrictedBalance', form.program_id],
    queryFn: () => FinanceService.getRestrictedBalance(form.program_id as number),
    enabled: form.program_id !== null,
    retry: false,
  });

  const { mutate: createTransaction, isPending } = useMutation({
    mutationFn: (overrideRestricted: boolean) =>
      FinanceService.createTransaction(
        {
          transaction_date: form.transaction_date,
          amount: parseFloat(form.amount),
          transaction_type: form.transaction_type as 'Income' | 'Expense',
          status: form.status as 'Cash' | 'Receivable',
          program_id: form.program_id,
          is_restricted: form.is_restricted,
        } as Omit<Transaction, 'id'>,
        overrideRestricted,
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['financeSummary'] });
      queryClient.invalidateQueries({ queryKey: ['restrictedBalance'] });
      queryClient.invalidateQueries({ queryKey: ['program-financials'] });
      handleClose();
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail;
      if (err?.response?.status === 409) {
        setShortfall(detail);
        setError(null);
        return;
      }
      setShortfall(null);
      setError(detail || 'Failed to record transaction. Please try again.');
    },
  });

  const handleClose = () => {
    setForm(EMPTY_FORM);
    setError(null);
    setShortfall(null);
    onClose();
  };

  const handleSubmit = (overrideRestricted = false) => {
    setError(null);
    if (!overrideRestricted) setShortfall(null);

    if (!form.transaction_date || !form.amount || !form.transaction_type || !form.status) {
      setError('All fields except Program are required.');
      return;
    }

    const amount = parseFloat(form.amount);
    if (isNaN(amount) || amount <= 0) {
      setError('Amount must be a positive number.');
      return;
    }

    // Mirrors the backend validator so the user is told immediately rather
    // than by a 422 round trip. The backend remains the enforcement point.
    if (form.is_restricted && form.program_id === null) {
      setError('Restricted income must be assigned to a program.');
      return;
    }

    createTransaction(overrideRestricted);
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleClose()}>
      <DialogContent className="bg-surface border border-border-brand text-text-primary sm:max-w-md rounded-card shadow-card p-6">
        <DialogHeader className="p-0 pb-4">
          <DialogTitle className="text-lg font-bold font-heading text-text-primary">Record Transaction</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Transaction Type Toggle */}
          <div className="space-y-1.5">
            <Label className="text-text-secondary text-xs uppercase tracking-wider font-semibold">Type</Label>
            <div className="grid grid-cols-2 gap-2">
              {(['Income', 'Expense'] as const).map((type) => (
                <button
                  key={type}
                  onClick={() =>
                    setForm((f) => ({
                      ...f,
                      transaction_type: type,
                      // Only income can be earmarked; an expense draws down
                      // restricted funds via its program, not via a flag.
                      is_restricted: type === 'Income' ? f.is_restricted : false,
                    }))
                  }
                  className={`flex items-center justify-center gap-2 py-2 rounded-lg border text-xs font-semibold transition-all ${
                    form.transaction_type === type
                      ? type === 'Income'
                        ? 'bg-green-500/10 border-green-500/30 text-positive shadow-[0_0_8px_rgba(34,197,94,0.15)]'
                        : 'bg-red-500/10 border-red-500/30 text-negative shadow-[0_0_8px_rgba(239,68,68,0.15)]'
                      : 'border-border-brand text-text-secondary hover:border-accent/40 bg-bg-subtle'
                  }`}
                >
                  {type === 'Income' ? (
                    <TrendingUp className="h-4 w-4" />
                  ) : (
                    <TrendingDown className="h-4 w-4" />
                  )}
                  {type}
                </button>
              ))}
            </div>
          </div>

          {/* Amount */}
          <div className="space-y-1.5">
            <Label className="text-text-secondary text-xs uppercase tracking-wider font-semibold">Amount (LKR)</Label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted text-xs">Rs.</span>
              <Input
                type="number"
                min="0"
                step="0.01"
                placeholder="0.00"
                value={form.amount}
                onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))}
                className="pl-9 bg-bg-subtle border border-border-brand text-text-primary placeholder:text-text-muted focus:border-accent text-xs rounded-lg h-10"
              />
            </div>
          </div>

          {/* Date */}
          <div className="space-y-1.5">
            <Label className="text-text-secondary text-xs uppercase tracking-wider font-semibold">Date</Label>
            <Input
              type="date"
              value={form.transaction_date}
              onChange={(e) => setForm((f) => ({ ...f, transaction_date: e.target.value }))}
              className="bg-bg-subtle border border-border-brand text-text-primary focus:border-accent text-xs rounded-lg h-10"
            />
          </div>

          {/* Status */}
          <div className="space-y-1.5">
            <Label className="text-text-secondary text-xs uppercase tracking-wider font-semibold">Status</Label>
            <Select
              value={form.status}
              onValueChange={(v) => setForm((f) => ({ ...f, status: v as 'Cash' | 'Receivable' }))}
            >
              <SelectTrigger className="bg-bg-subtle border border-border-brand text-text-primary focus:border-accent text-xs rounded-lg h-10">
                <SelectValue placeholder="Select status" />
              </SelectTrigger>
              <SelectContent className="bg-surface border border-border-brand text-text-primary rounded-lg">
                <SelectItem value="Cash" className="text-text-primary focus:bg-bg-subtle focus:text-accent">Cash</SelectItem>
                <SelectItem value="Receivable" className="text-text-primary focus:bg-bg-subtle focus:text-accent">Receivable</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Program (optional) */}
          <div className="space-y-1.5">
            <Label className="text-text-secondary text-xs uppercase tracking-wider font-semibold">
              Program <span className="text-text-muted normal-case font-normal">(optional)</span>
            </Label>
            <Select
              value={form.program_id?.toString() ?? 'none'}
              onValueChange={(v) =>
                setForm((f) => {
                  const program_id = v === null || v === 'none' ? null : parseInt(v);
                  // Clearing the program clears the earmark with it, so the
                  // form can never submit a restricted row with no program.
                  return { ...f, program_id, is_restricted: program_id === null ? false : f.is_restricted };
                })
              }
            >
              <SelectTrigger className="bg-bg-subtle border border-border-brand text-text-primary focus:border-accent text-xs rounded-lg h-10">
                {/* Base UI's Select.Value renders the raw VALUE, not the
                    selected item's label — unlike Radix. Without this function
                    child the trigger showed the bare program id ("1"), so an
                    officer booking a program-linked expense could not see
                    which program they had picked. The Status select above
                    only looks correct because its value and label are the
                    same string. */}
                <SelectValue placeholder="No program">
                  {(value) =>
                    value == null || value === 'none'
                      ? 'No program'
                      : programs?.find((p) => p.id.toString() === value)?.program_name ?? value
                  }
                </SelectValue>
              </SelectTrigger>
              <SelectContent className="bg-surface border border-border-brand text-text-primary rounded-lg">
                <SelectItem value="none" className="text-text-muted focus:bg-bg-subtle">No program</SelectItem>
                {programs?.map((p) => (
                  <SelectItem key={p.id} value={p.id.toString()} className="text-text-primary focus:bg-bg-subtle focus:text-accent">
                    {p.program_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Restrict to program — income only */}
          {form.transaction_type === 'Income' && (
            <div className="space-y-1.5">
              <button
                type="button"
                onClick={() => setForm((f) => ({ ...f, is_restricted: !f.is_restricted }))}
                disabled={form.program_id === null}
                className={`w-full flex items-start gap-3 rounded-lg border px-3 py-2.5 text-left transition-all disabled:opacity-50 disabled:cursor-not-allowed ${
                  form.is_restricted
                    ? 'bg-accent/10 border-accent/40'
                    : 'bg-bg-subtle border-border-brand hover:border-accent/40'
                }`}
              >
                <span
                  className={`mt-0.5 flex h-4 w-8 shrink-0 items-center rounded-full transition-colors ${
                    form.is_restricted ? 'bg-accent justify-end' : 'bg-border-brand justify-start'
                  }`}
                >
                  <span className="h-3 w-3 rounded-full bg-white mx-0.5" />
                </span>
                <span className="min-w-0">
                  <span className="flex items-center gap-1.5 text-xs font-semibold text-text-primary">
                    <Lock size={12} className={form.is_restricted ? 'text-accent' : 'text-text-muted'} />
                    Restrict to program
                  </span>
                  <span className="block text-[10px] text-text-secondary mt-0.5 leading-relaxed">
                    {form.program_id === null
                      ? 'Select a program above to earmark this donation.'
                      : 'The donor earmarked this money for this program. It cannot be spent elsewhere.'}
                  </span>
                </span>
              </button>
            </div>
          )}

          {/* Restricted position — shown for expenses so the officer sees the
              ceiling before submitting, not only after a rejection. */}
          {form.transaction_type === 'Expense' && form.program_id !== null && balance && balance.raised > 0 && (
            <div className="rounded-lg border border-border-brand bg-bg-subtle px-3 py-2.5">
              <p className="text-[10px] font-bold uppercase tracking-wider text-text-secondary flex items-center gap-1.5">
                <Lock size={11} className="text-accent" /> Restricted funds
              </p>
              <div className="mt-1.5 grid grid-cols-3 gap-2 text-xs">
                <div>
                  <p className="text-[10px] text-text-muted">Raised</p>
                  <p className="font-semibold text-text-primary">Rs. {balance.raised.toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-[10px] text-text-muted">Spent</p>
                  <p className="font-semibold text-text-primary">Rs. {balance.spent.toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-[10px] text-text-muted">Remaining</p>
                  <p className={`font-semibold ${balance.remaining < 0 ? 'text-negative' : 'text-positive'}`}>
                    Rs. {balance.remaining.toLocaleString()}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Shortfall — the backend refused this expense */}
          {shortfall && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2.5 space-y-2">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-amber-500">
                <ShieldAlert size={13} /> Exceeds restricted funds
              </p>
              <p className="text-[11px] text-text-secondary leading-relaxed">{shortfall}</p>
              {canOverride ? (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={isPending}
                  onClick={() => handleSubmit(true)}
                  className="h-8 w-full border-amber-500/40 text-amber-500 hover:bg-amber-500/10 text-[11px]"
                >
                  {isPending ? (
                    <><Loader2 className="mr-2 h-3 w-3 animate-spin" /> Authorizing...</>
                  ) : (
                    'Authorize overspend anyway'
                  )}
                </Button>
              ) : (
                <p className="text-[10px] text-text-muted italic">
                  You are not authorized to override this. Reduce the amount or ask an
                  administrator.
                </p>
              )}
            </div>
          )}

          {/* Error */}
          {error && (
            <p className="text-negative text-xs bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
        </div>

        <DialogFooter className="gap-2 pt-4">
          <Button
            variant="outline"
            onClick={handleClose}
            className="border-border-brand text-text-primary hover:bg-bg-subtle text-xs rounded-lg h-10"
          >
            Cancel
          </Button>
          <Button
            onClick={() => handleSubmit()}
            disabled={isPending}
            className="bg-accent hover:bg-accent/80 text-white font-semibold text-xs rounded-lg h-10 min-w-[120px] shadow-sm"
          >
            {isPending ? (
              <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Saving...</>
            ) : (
              'Record transaction'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}