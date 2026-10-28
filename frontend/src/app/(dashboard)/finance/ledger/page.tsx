'use client';

import { useState } from 'react';
import { useAuthStore } from '@/store/useAuthStore';
import { useTransactions } from '@/hooks/useFinance';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { PlusCircle } from 'lucide-react';
import { formatLKR } from '@/lib/formatters';
import { hasPermission } from '@/lib/permissions';
import { NewTransactionModal } from '@/components/finance/NewTransactionModal';

export default function LedgerPage() {
  const { user } = useAuthStore();
  const canWrite = hasPermission(user?.role as string, 'finance:write');

  const { data: transactions, isLoading } = useTransactions();

  // Entries go through the same modal as the Overview page. This page used to
  // carry its own form, which had no restricted-funds toggle, no override
  // path, and always posted today's date.
  const [showNewModal, setShowNewModal] = useState(false);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold font-heading text-text-primary">General Ledger</h1>
        {canWrite && (
          <Button
            onClick={() => setShowNewModal(true)}
            className="bg-accent text-bg-brand hover:bg-accent/90 flex items-center gap-2"
          >
            <PlusCircle className="h-4 w-4" /> New Entry
          </Button>
        )}
      </div>

      <Card className="bg-surface border-border-brand">
        <CardHeader>
          <CardTitle>Recent Transactions</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-4">
              {[1, 2, 3, 4].map(i => <Skeleton key={i} className="w-full h-12" />)}
            </div>
          ) : transactions && transactions.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-text-secondary uppercase bg-bg-subtle/50">
                  <tr>
                    <th className="px-4 py-3">Date</th>
                    <th className="px-4 py-3">Type</th>
                    <th className="px-4 py-3">Amount</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Program</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-brand">
                  {transactions.map(t => (
                    <tr key={t.id} className="hover:bg-bg-subtle/50 transition-colors">
                      <td className="px-4 py-3 text-text-secondary">{t.transaction_date}</td>
                      <td className="px-4 py-3">
                        <span className={t.transaction_type === 'Income' ? 'text-emerald-500' : 'text-rose-500'}>
                          {t.transaction_type}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-medium">{formatLKR(Number(t.amount))}</td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                          t.status === 'Cash' ? 'bg-emerald-500/10 text-emerald-500' :
                          t.status === 'Voided' ? 'bg-rose-500/10 text-rose-500' :
                          'bg-amber-500/10 text-amber-500'
                        }`}>
                          {t.status === 'Receivable' ? (t.transaction_type === 'Income' ? 'Receivable' : 'Payable') : t.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-text-secondary">
                        {t.programs?.program_name || '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-8 text-text-secondary">No transactions found.</div>
          )}
        </CardContent>
      </Card>

      <NewTransactionModal open={showNewModal} onClose={() => setShowNewModal(false)} />
    </div>
  );
}
