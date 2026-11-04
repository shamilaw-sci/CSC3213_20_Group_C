'use client';

import { useState, useMemo } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { FinanceService } from '@/services/finance.service';
import { Transaction } from '@/types';
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableHeader, 
  TableRow 
} from '@/components/ui/table';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  TrendingDown,
  TrendingUp,
  Pencil,
  Ban,
  MoreHorizontal,
  Layers,
  ArrowRight
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { format } from 'date-fns';
import { EditTransactionModal } from '@/components/finance/EditTransactionModal';
import { VoidTransactionDialog } from '@/components/finance/VoidTransactionDialog';
import { AUTO_POSTED_HINT, isAutoPosted } from '@/lib/finance-source';
import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell
} from 'recharts';
import { KPICard } from '@/components/shared/kpi-card';
import { useAuthStore } from '@/store/useAuthStore';
import { hasPermission } from '@/lib/permissions';

const formatLKR = (amount: number) => {
  return new Intl.NumberFormat('en-LK', {
    style: 'currency',
    currency: 'LKR',
    minimumFractionDigits: 0,
  }).format(amount);
};

// The Overview is the dashboard; the Ledger is the full record. This table
// only shows the latest entries and links there for the rest.
const RECENT_LIMIT = 10;

export default function FinancePage() {
  const { user } = useAuthStore();
  // Same permission as the Ledger's nav entry and page guard.
  const canOpenLedger = hasPermission(user?.role as string, 'finance:read');
  const [editingTransaction, setEditingTransaction] = useState<Transaction | null>(null);
  const [voidingTransaction, setVoidingTransaction] = useState<Transaction | null>(null);
  const [range, setRange] = useState<'12m' | '30d' | '7d'>('30d');
  const [statusFilter, setStatusFilter] = useState<'All' | 'Income' | 'Expense'>('All');

  const { data: transactions, isLoading } = useQuery({
    queryKey: ['transactions'],
    queryFn: () => FinanceService.getTransactions()
  });

  const { data: summary } = useQuery({
    queryKey: ['financeSummary'],
    queryFn: FinanceService.getSummary
  });

  const { data: aging } = useQuery({
    queryKey: ['financeAging'],
    queryFn: FinanceService.getAging
  });


  // Bucket real transactions into a time series for the trend chart —
  // this used to be Math.random(), which meant the chart lied on every render.
  const chartData = useMemo(() => {
    if (!transactions) return [];
    const now = new Date();

    if (range === '12m') {
      const months = Array.from({ length: 12 }, (_, i) => {
        const d = new Date(now.getFullYear(), now.getMonth() - (11 - i), 1);
        return { key: `${d.getFullYear()}-${d.getMonth()}`, name: d.toLocaleDateString('en-US', { month: 'short' }), income: 0, expense: 0 };
      });
      const byKey = new Map(months.map((m) => [m.key, m]));
      transactions.forEach((tx) => {
        if (tx.status === 'Voided') return;
        const d = new Date(tx.transaction_date);
        const bucket = byKey.get(`${d.getFullYear()}-${d.getMonth()}`);
        if (!bucket) return;
        if (tx.transaction_type === 'Income') bucket.income += tx.amount;
        else bucket.expense += tx.amount;
      });
      return months;
    }

    const days = range === '7d' ? 7 : 30;
    const daily = Array.from({ length: days }, (_, i) => {
      const d = new Date(now);
      d.setDate(now.getDate() - (days - 1 - i));
      return { key: d.toISOString().slice(0, 10), name: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }), income: 0, expense: 0 };
    });
    const byKey = new Map(daily.map((d) => [d.key, d]));
    transactions.forEach((tx) => {
      if (tx.status === 'Voided') return;
      const bucket = byKey.get(tx.transaction_date.slice(0, 10));
      if (!bucket) return;
      if (tx.transaction_type === 'Income') bucket.income += tx.amount;
      else bucket.expense += tx.amount;
    });
    return daily;
  }, [transactions, range]);

  // Non-voided expense totals per program, largest first. Expenses with no
  // program are overhead and show as "General Operations". Both the donut
  // and the Top Expense Programs list read from this, so they cannot
  // disagree.
  //
  // This used to read programs[].total_cost, but /finance/programs responds
  // with a schema that has no such field, so FastAPI stripped it and the
  // donut was permanently empty.
  const expenseByProgram = useMemo(() => {
    if (!transactions) return [];
    const byProgram = new Map<string, number>();
    transactions.forEach((tx) => {
      if (tx.transaction_type !== 'Expense' || tx.status === 'Voided') return;
      const name = tx.programs?.program_name || 'General Operations';
      byProgram.set(name, (byProgram.get(name) || 0) + Number(tx.amount));
    });
    return Array.from(byProgram.entries()).sort((a, b) => b[1] - a[1]);
  }, [transactions]);

  // Top four programs plus "Other", so every slice gets its own colour from
  // the five in COLORS.
  const programData = useMemo(() => {
    const total = expenseByProgram.reduce((sum, [, value]) => sum + value, 0);
    if (total === 0) return [];
    const top = expenseByProgram.slice(0, 4).map(([name, value]) => ({ name, value }));
    const rest = expenseByProgram.slice(4).reduce((sum, [, value]) => sum + value, 0);
    if (rest > 0) top.push({ name: 'Other', value: rest });
    return top.map((slice) => ({ ...slice, share: Math.round((slice.value / total) * 100) }));
  }, [expenseByProgram]);

  // Month-over-month deltas for the KPI trend pills, computed from the same
  // transaction log rather than hardcoded percentages.
  const monthlyTrends = useMemo(() => {
    if (!transactions) return { expenseTrend: undefined, receivablesTrend: undefined };
    const now = new Date();
    const thisKey = `${now.getFullYear()}-${now.getMonth()}`;
    const prevDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const prevKey = `${prevDate.getFullYear()}-${prevDate.getMonth()}`;

    let thisExpense = 0, prevExpense = 0, thisReceivable = 0, prevReceivable = 0;
    transactions.forEach((tx) => {
      if (tx.status === 'Voided') return;
      const d = new Date(tx.transaction_date);
      const key = `${d.getFullYear()}-${d.getMonth()}`;
      if (key !== thisKey && key !== prevKey) return;
      if (tx.transaction_type === 'Expense') {
        if (key === thisKey) thisExpense += tx.amount; else prevExpense += tx.amount;
      }
      if (tx.status === 'Receivable') {
        if (key === thisKey) thisReceivable += tx.amount; else prevReceivable += tx.amount;
      }
    });

    const pctChange = (curr: number, prev: number) => (prev === 0 ? null : Math.round(((curr - prev) / prev) * 1000) / 10);
    const expensePct = pctChange(thisExpense, prevExpense);
    const receivablePct = pctChange(thisReceivable, prevReceivable);

    return {
      // Spending and money still owed to us are both better when they fall.
      expenseTrend: expensePct === null ? undefined : { value: expensePct, upIsGood: false },
      receivablesTrend: receivablePct === null ? undefined : { value: receivablePct, upIsGood: false },
    };
  }, [transactions]);

  // Real program breakdowns replacing the hardcoded "Top Expense Categories"
  // and "Revenue by Region" lists — Transaction has no category/region field,
  // so those cards were rendering data with no backing source at all.
  const topExpensePrograms = useMemo(() => {
    const sorted = expenseByProgram.slice(0, 4);
    const max = sorted[0]?.[1] || 1;
    return sorted.map(([category, value]) => ({ category, value, percentage: Math.round((value / max) * 100) }));
  }, [expenseByProgram]);

  const incomeByProgram = useMemo(() => {
    if (!transactions) return [];
    const byProgram = new Map<string, number>();
    transactions.forEach((tx) => {
      if (tx.transaction_type !== 'Income' || tx.status === 'Voided') return;
      const name = tx.programs?.program_name || 'General Operations';
      byProgram.set(name, (byProgram.get(name) || 0) + tx.amount);
    });
    const sorted = Array.from(byProgram.entries()).sort((a, b) => b[1] - a[1]).slice(0, 4);
    const max = sorted[0]?.[1] || 1;
    return sorted.map(([program, value]) => ({ program, value, percentage: Math.round((value / max) * 100) }));
  }, [transactions]);

  const filteredTransactions = useMemo(() => {
    if (!transactions) return [];
    const matching = statusFilter === 'All'
      ? transactions
      : transactions.filter((tx) => tx.transaction_type === statusFilter);
    return matching.slice(0, RECENT_LIMIT);
  }, [transactions, statusFilter]);

  const COLORS = ['#EF9F27', '#16A34A', '#2563EB', '#D97706', '#DC2626'];

  return (
    <div className="space-y-8 pb-12">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold font-heading tracking-tight mb-2 text-text-primary">
            Financial Management
          </h1>
          <p className="text-text-secondary text-sm">
            Track income, expenses, and manage receivables across all programs.
          </p>
        </div>
      </div>

      {/* KPI Strip */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <KPICard
          title="Cash Liquidity"
          value={formatLKR(summary?.cash_available || 0)}
          description="current balance"
        />
        <KPICard
          title="Total Receivables"
          value={formatLKR(summary?.receivables || 0)}
          trend={monthlyTrends.receivablesTrend}
          description="vs last month"
        />
        <KPICard
          title="Monthly Burn"
          value={formatLKR(summary?.monthly_expenses || 0)}
          trend={monthlyTrends.expenseTrend}
          description="vs last month"
        />
      </div>

      {/* Primary Trend Chart + Side Panel */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Trend Area Chart */}
        <Card className="lg:col-span-2 bg-surface border border-border-brand rounded-card shadow-card p-5">
          <CardHeader className="flex flex-row items-center justify-between p-0 pb-6">
            <div>
              <CardTitle className="text-base font-semibold font-heading text-text-primary">
                Revenue Analytics
              </CardTitle>
              <CardDescription className="text-text-secondary text-xs mt-1">
                Overview of {range === '12m' ? 'the last 12 months' : range === '7d' ? 'the last 7 days' : 'the last 30 days'} cash flows
              </CardDescription>
            </div>
            
            {/* Range Toggle */}
            <div className="flex bg-bg-subtle p-1 rounded-lg border border-border-brand">
              <button 
                onClick={() => setRange('12m')}
                className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${
                  range === '12m' 
                    ? 'bg-surface text-text-primary shadow-xs' 
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                12 Months
              </button>
              <button 
                onClick={() => setRange('30d')}
                className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${
                  range === '30d' 
                    ? 'bg-surface text-text-primary shadow-xs' 
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                30 Days
              </button>
              <button 
                onClick={() => setRange('7d')}
                className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${
                  range === '7d' 
                    ? 'bg-surface text-text-primary shadow-xs' 
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                7 Days
              </button>
            </div>
          </CardHeader>
          <CardContent className="h-[300px] p-0">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="colorInc" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#16A34A" stopOpacity={0.2}/>
                    <stop offset="95%" stopColor="#16A34A" stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="colorExp" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#DC2626" stopOpacity={0.2}/>
                    <stop offset="95%" stopColor="#DC2626" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" opacity={0.3} vertical={false} />
                <XAxis
                  dataKey="name"
                  stroke="var(--color-text-secondary)"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  interval={range === '30d' ? 4 : 0}
                />
                <YAxis 
                  stroke="var(--color-text-secondary)" 
                  fontSize={11} 
                  tickLine={false} 
                  axisLine={false} 
                  tickFormatter={(value) => `Rs.${value/1000}k`}
                />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: 'var(--color-surface)', 
                    border: '1px solid var(--color-border)', 
                    borderRadius: '8px',
                    fontFamily: 'var(--font-mono)' 
                  }}
                  itemStyle={{ color: 'var(--color-text-primary)' }}
                />
                <Area type="monotone" dataKey="income" stroke="#16A34A" strokeWidth={2} fillOpacity={1} fill="url(#colorInc)" />
                <Area type="monotone" dataKey="expense" stroke="#DC2626" strokeWidth={2} fillOpacity={1} fill="url(#colorExp)" />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Side Panel: Receivables Aging */}
        <Card className="bg-surface border border-border-brand rounded-card shadow-card p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
                Outstanding Receivables
              </span>
              <span className={`w-2.5 h-2.5 rounded-full ${(aging?.['61+'] || 0) > 0 ? 'bg-red-500 animate-pulse' : 'bg-green-500'}`} />
            </div>

            <div className="mt-4">
              <div className="text-3xl font-bold font-mono text-text-primary">
                {formatLKR(summary?.receivables || 0)}
              </div>
              <span className="text-xs text-text-secondary">
                Owed across all programs
              </span>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2 mt-6 pt-6 border-t border-border-brand text-center">
            <div>
              <div className="text-sm font-semibold font-mono text-text-primary">{formatLKR(aging?.['0-30'] || 0)}</div>
              <span className="text-[9px] text-text-secondary uppercase">0-30 Days</span>
            </div>
            <div>
              <div className="text-sm font-semibold font-mono text-text-primary">{formatLKR(aging?.['31-60'] || 0)}</div>
              <span className="text-[9px] text-text-secondary uppercase">31-60 Days</span>
            </div>
            <div>
              <div className={`text-sm font-semibold font-mono ${(aging?.['61+'] || 0) > 0 ? 'text-negative' : 'text-text-primary'}`}>{formatLKR(aging?.['61+'] || 0)}</div>
              <span className="text-[9px] text-text-secondary uppercase">61+ Days</span>
            </div>
          </div>
        </Card>
      </div>

      {/* Program split and ranked lists. The donut spans the full row at
          md, where only two columns fit, so neither list is left alone. */}
      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
        {/* Allocations Donut Chart */}
        <Card className="bg-surface border border-border-brand rounded-card shadow-card p-5 md:col-span-2 xl:col-span-1">
          <CardHeader className="flex flex-row items-center justify-between p-0 pb-4">
            <div>
              <CardTitle className="text-base font-semibold font-heading text-text-primary">
                Program Allocations Split
              </CardTitle>
              <CardDescription className="text-text-secondary text-xs mt-0.5">
                Share of total spending by program
              </CardDescription>
            </div>
            <button className="text-text-secondary hover:text-text-primary">
              <MoreHorizontal className="w-5 h-5" />
            </button>
          </CardHeader>
          <CardContent className="h-[200px] flex items-center justify-center p-0">
            {programData.length === 0 ? (
              <p className="text-xs text-text-muted">No program spend recorded yet</p>
            ) : (
              <>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={programData}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={80}
                      paddingAngle={5}
                      dataKey="value"
                    >
                      {programData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value) => formatLKR(Number(value))} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex flex-col gap-1.5 ml-4 shrink-0 text-left max-w-[150px] overflow-hidden">
                  {programData.map((entry, index) => (
                    <div key={entry.name} className="flex items-center gap-2 text-[10px] text-text-secondary">
                      <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: COLORS[index % COLORS.length] }} />
                      <span className="truncate">{entry.name}</span>
                      <span className="ml-auto pl-1 font-mono text-text-primary">{entry.share}%</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Top Expense Programs */}
        <Card className="bg-surface border border-border-brand rounded-card shadow-card p-5">
          <CardHeader className="flex flex-row items-center justify-between p-0 pb-4">
            <CardTitle className="text-base font-semibold font-heading text-text-primary">
              Top Expense Programs
            </CardTitle>
            <button className="text-text-secondary hover:text-text-primary">
              <MoreHorizontal className="w-5 h-5" />
            </button>
          </CardHeader>
          <CardContent className="p-0 space-y-4">
            {topExpensePrograms.length === 0 ? (
              <p className="text-xs text-text-muted py-2">No expense transactions recorded yet</p>
            ) : (
              topExpensePrograms.map((item) => (
                <div key={item.category} className="relative py-2">
                  <div className="flex items-center justify-between text-xs font-semibold relative z-10">
                    <span className="text-text-primary">{item.category}</span>
                    <span className="font-mono text-text-primary">{formatLKR(item.value)}</span>
                  </div>
                  <div
                    className="absolute bottom-0 left-0 h-1 bg-red-500/10 rounded-full transition-all"
                    style={{ width: `${item.percentage}%` }}
                  />
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* Income by Program */}
        <Card className="bg-surface border border-border-brand rounded-card shadow-card p-5">
          <CardHeader className="flex flex-row items-center justify-between p-0 pb-4">
            <div>
              <CardTitle className="text-base font-semibold font-heading text-text-primary">
                Income by Program
              </CardTitle>
              <CardDescription className="text-text-secondary text-xs mt-0.5">
                Funding distribution across active programs
              </CardDescription>
            </div>
            <button className="text-text-secondary hover:text-text-primary">
              <MoreHorizontal className="w-5 h-5" />
            </button>
          </CardHeader>
          <CardContent className="p-0 space-y-4">
            {incomeByProgram.length === 0 ? (
              <p className="text-xs text-text-muted py-2">No income transactions recorded yet</p>
            ) : (
              incomeByProgram.map((entry) => (
                <div key={entry.program} className="relative py-2">
                  <div className="flex items-center justify-between text-xs font-semibold relative z-10">
                    <div className="flex items-center gap-2">
                      <Layers className="w-3.5 h-3.5 text-[#EF9F27]" />
                      <span className="text-text-primary">{entry.program}</span>
                    </div>
                    <span className="font-mono text-text-primary">{formatLKR(entry.value)}</span>
                  </div>
                  <div
                    className="absolute bottom-0 left-0 h-1 bg-amber-500/10 rounded-full transition-all"
                    style={{ width: `${entry.percentage}%` }}
                  />
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent Transactions Data Table */}
      <Card className="bg-surface border border-border-brand rounded-card shadow-card p-5">
        <CardHeader className="flex flex-row items-center justify-between p-0 pb-4">
          <div>
            <CardTitle className="text-base font-semibold font-heading text-text-primary">
              Recent Transactions
            </CardTitle>
            <CardDescription className="text-text-secondary text-xs mt-0.5">
              The latest {RECENT_LIMIT} entries.
              {canOpenLedger && ' The full record, with filters and a running balance, is in the Ledger.'}
            </CardDescription>
          </div>
          <div className="flex items-center gap-3">
          {canOpenLedger && (
            <Link
              href="/finance/ledger"
              className="flex items-center gap-1 text-xs font-semibold text-accent hover:underline"
            >
              View all in Ledger <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          )}
          <div className="flex bg-bg-subtle p-1 rounded-lg border border-border-brand">
            {(['All', 'Income', 'Expense'] as const).map((opt) => (
              <button
                key={opt}
                onClick={() => setStatusFilter(opt)}
                className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${
                  statusFilter === opt
                    ? 'bg-surface text-text-primary shadow-xs'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                {opt}
              </button>
            ))}
          </div>
          </div>
        </CardHeader>
        <CardContent className="p-0 pt-4">
          {isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-12 w-full bg-bg-subtle" />
              <Skeleton className="h-12 w-full bg-bg-subtle" />
            </div>
          ) : (
            <div className="rounded-xl border border-border-brand overflow-hidden">
              <Table>
                <TableHeader className="bg-bg-subtle">
                  <TableRow className="hover:bg-transparent border-border-brand">
                    <TableHead className="text-text-secondary font-heading text-xs">Date</TableHead>
                    <TableHead className="text-text-secondary font-heading text-xs">Program</TableHead>
                    <TableHead className="text-text-secondary font-heading text-xs">Type</TableHead>
                    <TableHead className="text-text-secondary font-heading text-xs text-right">Amount</TableHead>
                    <TableHead className="text-text-secondary font-heading text-xs">Status</TableHead>
                    <TableHead className="text-text-secondary font-heading text-xs">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredTransactions.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} className="text-center py-8 text-text-muted">
                        {transactions?.length === 0 ? 'No transactions recorded' : `No ${statusFilter.toLowerCase()} transactions`}
                      </TableCell>
                    </TableRow>
                  ) : (
                    filteredTransactions.map((tx) => (
                      <TableRow 
                        key={tx.id} 
                        className={`border-border-brand hover:bg-[#14161C]/40 transition-colors ${tx.status === 'Voided' ? 'opacity-50' : ''}`}
                      >
                        <TableCell className="font-semibold text-xs">
                          <div className="text-text-primary">{format(new Date(tx.transaction_date), 'MMM dd, yyyy')}</div>
                          <div className="text-[10px] text-text-muted mt-0.5">ID: {tx.id}</div>
                        </TableCell>
                        <TableCell className="text-text-secondary text-xs font-medium">
                          {tx.programs?.program_name || 'General Operations'}
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-1.5 uppercase text-[9px] font-bold tracking-wider">
                            {tx.transaction_type === 'Income' ? (
                              <><TrendingUp className="text-positive h-3 w-3" /> Income</>
                            ) : (
                              <><TrendingDown className="text-negative h-3 w-3" /> Expense</>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className={`text-right font-mono font-bold text-xs ${tx.transaction_type === 'Income' ? 'text-positive' : 'text-text-primary'}`}>
                          {tx.transaction_type === 'Income' ? '+' : '-'}{formatLKR(tx.amount)}
                        </TableCell>
                        <TableCell>
                          {tx.status === 'Voided' ? (
                            <Badge variant="outline" className="text-text-muted border-border-brand bg-bg-subtle rounded-full px-2 py-0.5 text-[10px]">Voided</Badge>
                          ) : tx.status === 'Receivable' ? (
                            <Badge variant="outline" className="text-accent border-accent/20 bg-accent/5 rounded-full px-2 py-0.5 text-[10px]">Receivable</Badge>
                          ) : (
                            <Badge variant="outline" className="text-positive border-green-500/20 bg-green-500/5 rounded-full px-2 py-0.5 text-[10px]">Settled</Badge>
                          )}
                        </TableCell>
                        <TableCell>
                          {tx.status !== 'Voided' && (
                            <div className="flex items-center gap-2">
                              {isAutoPosted(tx) ? (
                                // A span, not a disabled button: disabled buttons show no tooltip.
                                <span
                                  title={AUTO_POSTED_HINT}
                                  aria-label={`Transaction ${tx.id} cannot be edited. ${AUTO_POSTED_HINT}`}
                                  className="inline-flex h-7 w-7 items-center justify-center text-text-muted"
                                >
                                  <Pencil className="h-3.5 w-3.5 opacity-30" />
                                </span>
                              ) : (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => setEditingTransaction(tx)}
                                  className="h-7 w-7 p-0 text-text-secondary hover:text-text-primary hover:bg-bg-subtle"
                                >
                                  <Pencil className="h-3.5 w-3.5" />
                                </Button>
                              )}
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setVoidingTransaction(tx)}
                                className="h-7 w-7 p-0 text-text-secondary hover:text-negative hover:bg-red-500/10"
                              >
                                <Ban className="h-3.5 w-3.5" />
                              </Button>
                            </div>
                          )}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
      
      {/* Transaction Modals */}
      
      <EditTransactionModal
        transaction={editingTransaction}
        onClose={() => setEditingTransaction(null)}
      />

      <VoidTransactionDialog
        transaction={voidingTransaction}
        onClose={() => setVoidingTransaction(null)}
      />
    </div>
  );
}
