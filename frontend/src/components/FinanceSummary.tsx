'use client';

import { useState } from 'react';
import { useMonthlySummary } from '@/hooks/useFinance';
import { Card } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { formatLKR } from '@/lib/formatters';
import { AlertTriangle } from 'lucide-react';

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

export default function FinanceSummary() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);

  const { data: summary, isLoading, error } = useMonthlySummary(year, month);

  const years = [now.getFullYear(), now.getFullYear() - 1, now.getFullYear() - 2];
  const isEmpty = !!summary && summary.income === 0 && summary.expense === 0;

  return (
    <div className="mb-8">
      <div className="flex items-center gap-3 mb-4">
        <Select
          value={String(month)}
          onValueChange={(val) => { if (typeof val === 'string') setMonth(Number(val)); }}
        >
          <SelectTrigger className="w-[150px]">
            <SelectValue placeholder="Month" />
          </SelectTrigger>
          <SelectContent>
            {MONTHS.map((label, i) => (
              <SelectItem key={label} value={String(i + 1)}>{label}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={String(year)}
          onValueChange={(val) => { if (typeof val === 'string') setYear(Number(val)); }}
        >
          <SelectTrigger className="w-[100px]">
            <SelectValue placeholder="Year" />
          </SelectTrigger>
          <SelectContent>
            {years.map((y) => (
              <SelectItem key={y} value={String(y)}>{y}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Skeleton className="h-28 w-full bg-bg-subtle" />
          <Skeleton className="h-28 w-full bg-bg-subtle" />
          <Skeleton className="h-28 w-full bg-bg-subtle" />
        </div>
      )}

      {!!error && (
        <div className="flex items-center gap-2 text-sm text-rose-500 bg-rose-500/10 p-4 rounded-lg border border-rose-500/20">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          Failed to load financial summary. Please try again.
        </div>
      )}

      {isEmpty && (
        <p className="text-sm text-text-muted py-8 text-center border border-dashed border-border-brand rounded-card">
          No transactions recorded for {MONTHS[month - 1]} {year}.
        </p>
      )}

      {!!summary && !isEmpty && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Card className="bg-surface border border-border-brand rounded-card shadow-card p-6 border-l-4 border-l-positive">
            <h3 className="text-text-secondary text-sm font-bold uppercase tracking-wider">Total Income</h3>
            <p className="text-3xl font-black text-text-primary mt-2">
              {formatLKR(summary.income)}
            </p>
          </Card>

          <Card className="bg-surface border border-border-brand rounded-card shadow-card p-6 border-l-4 border-l-negative">
            <h3 className="text-text-secondary text-sm font-bold uppercase tracking-wider">Total Expenses</h3>
            <p className="text-3xl font-black text-text-primary mt-2">
              {formatLKR(summary.expense)}
            </p>
          </Card>

          <Card className="bg-surface border border-border-brand rounded-card shadow-card p-6 border-l-4 border-l-accent">
            <h3 className="text-text-secondary text-sm font-bold uppercase tracking-wider">Net Balance</h3>
            <p className={`text-3xl font-black mt-2 ${summary.balance >= 0 ? 'text-positive' : 'text-negative'}`}>
              {formatLKR(summary.balance)}
            </p>
          </Card>
        </div>
      )}
    </div>
  );
}
