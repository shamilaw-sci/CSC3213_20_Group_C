'use client';

import { useState } from 'react';
import { AlertTriangle, BarChart3, Table2 } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { FinanceReport, OutstandingSide } from '@/types';
import { buildCsv, downloadCsv } from '@/lib/csv';
import { monthLabel, periodLabel } from '@/lib/finance-periods';
import { formatLKR } from '@/lib/formatters';
import { cn } from '@/lib/utils';
import { Delta, Money, ReportSection, td, th } from './ReportSection';

interface SectionProps {
  report: FinanceReport;
}

function exportName(report: FinanceReport, section: string) {
  return `finance_${section}_${report.period.start}_${report.period.end}.csv`;
}

// --------------------------------------------------------------------------
// Income & Expenditure
// --------------------------------------------------------------------------

export function IncomeExpenditure({ report }: SectionProps) {
  const { current, previous, change } = report.summary;
  const prevLabel = periodLabel({ start: report.period.previous_start, end: report.period.previous_end });
  const surplus = current.net >= 0;

  const exportCsv = () =>
    downloadCsv(
      exportName(report, 'income_expenditure'),
      buildCsv(
        ['Line', `This period (${report.period.start} to ${report.period.end})`, `Previous period (${report.period.previous_start} to ${report.period.previous_end})`],
        [
          ['Income', current.income, previous.income],
          ['Income received', current.income_received, previous.income_received],
          ['Income pending', current.income_pending, previous.income_pending],
          ['Expenditure', current.expense, previous.expense],
          ['Expenditure paid', current.expense_paid, previous.expense_paid],
          ['Expenditure unpaid', current.expense_unpaid, previous.expense_unpaid],
          ['Surplus / (deficit)', current.net, previous.net],
        ],
      ),
    );

  const tiles = [
    {
      label: 'Income',
      value: current.income,
      split: [['Received', current.income_received], ['Pending', current.income_pending]] as const,
      delta: <Delta pct={change.income_pct} upIsGood label={prevLabel} />,
    },
    {
      label: 'Expenditure',
      value: current.expense,
      split: [['Paid', current.expense_paid], ['Unpaid', current.expense_unpaid]] as const,
      delta: <Delta pct={change.expense_pct} upIsGood={false} label={prevLabel} />,
    },
  ];

  return (
    <ReportSection
      title="Income & Expenditure"
      description="Totals include pending income and unpaid expenses; the split beneath each shows how much has actually moved."
      onExport={exportCsv}
    >
      <div className="grid gap-4 md:grid-cols-3">
        {tiles.map((t) => (
          <div key={t.label} className="rounded-lg border border-border-brand bg-bg-subtle p-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-text-secondary">{t.label}</p>
            <p className="mt-1 text-2xl font-bold font-mono text-text-primary">{formatLKR(t.value)}</p>
            <div className="mt-1">{t.delta}</div>
            <dl className="mt-3 grid grid-cols-2 gap-2 border-t border-border-brand pt-3 text-xs">
              {t.split.map(([name, value]) => (
                <div key={name}>
                  <dt className="text-text-muted">{name}</dt>
                  <dd className="font-mono tabular-nums text-text-primary">{formatLKR(value)}</dd>
                </div>
              ))}
            </dl>
          </div>
        ))}

        <div
          className={cn(
            'rounded-lg border p-4',
            surplus ? 'border-border-brand bg-bg-subtle' : 'border-red-500/30 bg-red-500/5',
          )}
        >
          <p className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
            {surplus ? 'Surplus' : 'Deficit'}
          </p>
          <p className={cn('mt-1 text-2xl font-bold font-mono', surplus ? 'text-text-primary' : 'text-negative')}>
            {formatLKR(current.net)}
          </p>
          <p className="mt-1 text-xs text-text-secondary">
            {change.net_difference === 0 ? (
              <>Same as {prevLabel}</>
            ) : (
              <>
                <span className={cn('font-semibold', change.net_difference > 0 ? 'text-positive' : 'text-negative')}>
                  {change.net_difference > 0 ? '+' : '−'}{formatLKR(Math.abs(change.net_difference))}
                </span>{' '}
                vs {prevLabel}
              </>
            )}
          </p>
          <p className="mt-3 border-t border-border-brand pt-3 text-xs text-text-muted">
            {prevLabel}: <span className="font-mono text-text-secondary">{formatLKR(previous.net)}</span>
          </p>
        </div>
      </div>
    </ReportSection>
  );
}

// --------------------------------------------------------------------------
// Monthly trend
// --------------------------------------------------------------------------

const SERIES = [
  { key: 'income', label: 'Income', color: 'var(--color-series-1)' },
  { key: 'expense', label: 'Expenditure', color: 'var(--color-series-2)' },
] as const;

function compactLKR(value: number) {
  return `Rs ${new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(value)}`;
}

type MonthRow = FinanceReport['monthly'][number];

function TrendTooltip({ active, payload }: { active?: boolean; payload?: { payload: MonthRow }[] }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="rounded-lg border border-border-brand bg-surface px-3 py-2 text-xs shadow-card">
      <p className="mb-1.5 font-semibold text-text-primary">{monthLabel(row.month)}</p>
      {SERIES.map((s) => (
        <p key={s.key} className="flex items-center gap-2 text-text-secondary">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: s.color }} />
          {s.label}
          <span className="ml-auto pl-4 font-mono tabular-nums text-text-primary">{formatLKR(row[s.key])}</span>
        </p>
      ))}
      <p className="mt-1.5 flex border-t border-border-brand pt-1.5 text-text-secondary">
        Net
        <span className={cn('ml-auto pl-4 font-mono tabular-nums', row.net < 0 ? 'text-negative' : 'text-text-primary')}>
          {formatLKR(row.net)}
        </span>
      </p>
    </div>
  );
}

export function MonthlyTrend({ report }: SectionProps) {
  const months = report.monthly;
  // One month is one group of two bars: the Income & Expenditure tiles
  // already say that better, so a single-month period gets the table only.
  const chartable = months.length > 1;
  const [view, setView] = useState<'chart' | 'table'>('chart');
  const showChart = chartable && view === 'chart';

  const exportCsv = () =>
    downloadCsv(
      exportName(report, 'monthly'),
      buildCsv(['Month', 'Income', 'Expenditure', 'Net'], months.map((m) => [m.month, m.income, m.expense, m.net])),
    );

  const toggle = chartable && (
    <div className="flex rounded-md border border-border-brand p-0.5" role="group" aria-label="Trend view">
      {([['chart', BarChart3, 'Chart'], ['table', Table2, 'Table']] as const).map(([value, Icon, label]) => (
        <button
          key={value}
          type="button"
          onClick={() => setView(value)}
          aria-pressed={view === value}
          className={cn(
            'flex items-center gap-1 rounded px-2 py-1 text-xs',
            view === value ? 'bg-bg-subtle text-text-primary font-semibold' : 'text-text-secondary hover:text-text-primary',
          )}
        >
          <Icon className="h-3.5 w-3.5" /> {label}
        </button>
      ))}
    </div>
  );

  return (
    <ReportSection title="Monthly Trend" description="Income and expenditure per month in the period." onExport={exportCsv} actions={toggle}>
      {showChart ? (
        <>
          <div className="mb-3 flex items-center gap-4 text-xs text-text-secondary">
            {SERIES.map((s) => (
              <span key={s.key} className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: s.color }} />
                {s.label}
              </span>
            ))}
          </div>
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={months} barGap={2} barCategoryGap="20%" margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
                <CartesianGrid stroke="var(--color-border)" vertical={false} />
                <XAxis
                  dataKey="month"
                  tickFormatter={(m) => monthLabel(m, months.length > 12)}
                  stroke="var(--color-text-secondary)"
                  fontSize={11}
                  tickLine={false}
                  axisLine={{ stroke: 'var(--color-border)' }}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tickFormatter={compactLKR}
                  stroke="var(--color-text-secondary)"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  width={64}
                />
                <Tooltip content={<TrendTooltip />} cursor={{ fill: 'var(--color-bg-subtle)' }} />
                {SERIES.map((s) => (
                  <Bar key={s.key} dataKey={s.key} name={s.label} fill={s.color} maxBarSize={24} radius={[4, 4, 0, 0]} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-bg-subtle/50">
              <tr>
                <th className={th}>Month</th>
                <th className={cn(th, 'text-right')}>Income</th>
                <th className={cn(th, 'text-right')}>Expenditure</th>
                <th className={cn(th, 'text-right')}>Net</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-brand">
              {months.map((m) => (
                <tr key={m.month}>
                  <td className={cn(td, 'text-text-primary')}>{monthLabel(m.month)}</td>
                  <td className={cn(td, 'text-right')}><Money value={m.income} /></td>
                  <td className={cn(td, 'text-right')}><Money value={m.expense} /></td>
                  <td className={cn(td, 'text-right')}><Money value={m.net} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </ReportSection>
  );
}

// --------------------------------------------------------------------------
// Program breakdown
// --------------------------------------------------------------------------

export function ProgramBreakdown({ report }: SectionProps) {
  const { rows, totals } = report.programs;
  const maxExpense = Math.max(...rows.map((r) => r.expense), 0) || 1;

  const exportCsv = () =>
    downloadCsv(
      exportName(report, 'programs'),
      buildCsv(
        ['Program', 'Income', 'Expenditure', 'Net'],
        [...rows.map((r) => [r.program_name, r.income, r.expense, r.net]), ['Total', totals.income, totals.expense, totals.net]],
      ),
    );

  return (
    <ReportSection
      title="Program Breakdown"
      description="Income and expenditure per program in the period. General Operations is anything not charged to a program."
      onExport={rows.length ? exportCsv : undefined}
    >
      {rows.length === 0 ? (
        <p className="py-6 text-center text-sm text-text-muted">No transactions in this period.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-bg-subtle/50">
              <tr>
                <th className={th}>Program</th>
                <th className={cn(th, 'text-right')}>Income</th>
                <th className={cn(th, 'text-right')}>Expenditure</th>
                <th className={cn(th, 'hidden w-32 sm:table-cell')}>
                  <span className="sr-only">Share of expenditure</span>
                </th>
                <th className={cn(th, 'text-right')}>Net</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-brand">
              {rows.map((r) => (
                <tr key={r.program_id ?? 'general'}>
                  <td className={cn(td, 'text-text-primary font-medium')}>{r.program_name}</td>
                  <td className={cn(td, 'text-right')}><Money value={r.income} /></td>
                  <td className={cn(td, 'text-right')}><Money value={r.expense} /></td>
                  <td className={cn(td, 'hidden sm:table-cell')}>
                    {/* Expenditure relative to the largest program, so the
                        biggest spenders stand out without reading figures. */}
                    <div className="h-1.5 rounded-full bg-bg-subtle">
                      <div
                        className="h-1.5 rounded-full"
                        style={{ width: `${(r.expense / maxExpense) * 100}%`, backgroundColor: 'var(--color-series-2)' }}
                      />
                    </div>
                  </td>
                  <td className={cn(td, 'text-right')}><Money value={r.net} /></td>
                </tr>
              ))}
            </tbody>
            <tfoot className="border-t-2 border-border-brand">
              <tr>
                <td className={cn(td, 'font-semibold text-text-primary')}>Total</td>
                <td className={cn(td, 'text-right')}><Money value={totals.income} strong /></td>
                <td className={cn(td, 'text-right')}><Money value={totals.expense} strong /></td>
                <td className={cn(td, 'hidden sm:table-cell')} />
                <td className={cn(td, 'text-right')}><Money value={totals.net} strong /></td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </ReportSection>
  );
}

// --------------------------------------------------------------------------
// Restricted funds
// --------------------------------------------------------------------------

export function RestrictedFunds({ report }: SectionProps) {
  const { rows, totals } = report.restricted;
  const columns = [
    ['opening', 'Opening'],
    ['received', 'Received'],
    ['spent', 'Spent'],
    ['closing', 'Closing'],
    ['pledged', 'Pledged'],
  ] as const;

  const exportCsv = () =>
    downloadCsv(
      exportName(report, 'restricted_funds'),
      buildCsv(
        ['Program', ...columns.map(([, label]) => label)],
        [
          ...rows.map((r) => [r.program_name, ...columns.map(([key]) => r[key])]),
          ['Total', ...columns.map(([key]) => totals[key])],
        ],
      ),
    );

  return (
    <ReportSection
      title="Restricted Funds Statement"
      description="Donor-earmarked money per program. Closing is what remains spendable on that program, the same balance new expenses are checked against. Pledged is earmarked but not yet received."
      onExport={rows.length ? exportCsv : undefined}
    >
      {rows.length === 0 ? (
        <p className="py-6 text-center text-sm text-text-muted">No program holds restricted funds.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-bg-subtle/50">
              <tr>
                <th className={th}>Program</th>
                {columns.map(([key, label]) => (
                  <th key={key} className={cn(th, 'text-right')}>{label}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border-brand">
              {rows.map((r) => (
                <tr key={r.program_id}>
                  <td className={cn(td, 'text-text-primary font-medium')}>
                    {r.program_name}
                    {r.closing < 0 && (
                      <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2 py-0.5 text-[10px] font-semibold text-negative">
                        <AlertTriangle className="h-3 w-3" /> Overdrawn
                      </span>
                    )}
                  </td>
                  {columns.map(([key]) => (
                    <td key={key} className={cn(td, 'text-right')}>
                      <Money value={r[key]} strong={key === 'closing'} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
            <tfoot className="border-t-2 border-border-brand">
              <tr>
                <td className={cn(td, 'font-semibold text-text-primary')}>Total</td>
                {columns.map(([key]) => (
                  <td key={key} className={cn(td, 'text-right')}><Money value={totals[key]} strong /></td>
                ))}
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </ReportSection>
  );
}

// --------------------------------------------------------------------------
// Outstanding
// --------------------------------------------------------------------------

const BUCKETS = ['0-30', '31-60', '61-90', '90+'] as const;

function OutstandingCard({ title, side }: { title: string; side: OutstandingSide }) {
  return (
    <div className="rounded-lg border border-border-brand bg-bg-subtle p-4">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
          {title} <span className="font-normal normal-case text-text-muted">({side.count})</span>
        </p>
        <p className="text-lg font-bold font-mono text-text-primary">{formatLKR(side.total)}</p>
      </div>

      <dl className="mt-3 grid grid-cols-4 gap-2">
        {BUCKETS.map((b) => (
          <div key={b} className="rounded-md border border-border-brand bg-surface px-2 py-1.5">
            <dt className={cn('text-[10px]', b === '90+' && side.buckets[b] > 0 ? 'font-semibold text-negative' : 'text-text-muted')}>
              {b} days
            </dt>
            <dd className="font-mono text-xs tabular-nums text-text-primary">{compactLKR(side.buckets[b])}</dd>
          </div>
        ))}
      </dl>

      {side.items.length > 0 && (
        <>
          <p className="mt-4 text-[10px] font-semibold uppercase tracking-wider text-text-muted">Oldest</p>
          <ul className="mt-1 divide-y divide-border-brand text-xs">
            {side.items.slice(0, 5).map((i) => (
              <li key={i.id} className="flex items-center gap-3 py-1.5">
                <span className="w-16 shrink-0 font-mono text-text-secondary">{i.days}d</span>
                <span className="min-w-0 flex-1 truncate text-text-primary">{i.program_name}</span>
                <span className="font-mono tabular-nums text-text-primary">{formatLKR(i.amount)}</span>
              </li>
            ))}
          </ul>
          {side.items.length > 5 && (
            <p className="mt-1 text-[10px] text-text-muted">+{side.items.length - 5} more in the CSV</p>
          )}
        </>
      )}
    </div>
  );
}

export function Outstanding({ report }: SectionProps) {
  const { as_of, receivables, payables } = report.outstanding;

  const exportCsv = () =>
    downloadCsv(
      exportName(report, 'outstanding'),
      buildCsv(
        ['Kind', 'Date', 'Program', 'Amount', 'Days outstanding'],
        [
          ...receivables.items.map((i) => ['Receivable', i.transaction_date, i.program_name, i.amount, i.days]),
          ...payables.items.map((i) => ['Payable', i.transaction_date, i.program_name, i.amount, i.days]),
        ],
      ),
    );

  return (
    <ReportSection
      title="Outstanding"
      description={
        <>
          Items still open today and dated on or before {report.period.end}, aged as at {as_of}. The ledger doesn&apos;t
          record when an item was settled, so this is today&apos;s position, not a historical one.
        </>
      }
      onExport={receivables.count + payables.count ? exportCsv : undefined}
    >
      <div className="grid gap-4 md:grid-cols-2">
        <OutstandingCard title="Receivables" side={receivables} />
        <OutstandingCard title="Payables" side={payables} />
      </div>
    </ReportSection>
  );
}
