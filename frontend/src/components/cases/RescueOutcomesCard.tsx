'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { RescueCasesService } from '@/services/rescue-cases.service';
import { formatLKR } from '@/lib/formatters';
import { getErrorMessage } from '@/lib/utils';
import { OUTCOME_HINT } from './ResolveCaseDialog';

const MONTH = new Intl.DateTimeFormat('en-LK', { month: 'long', year: 'numeric' });

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border-brand bg-bg-subtle px-3 py-2">
      <p className="text-lg font-bold font-heading leading-none text-text-primary">{value}</p>
      <p className="mt-1 text-[10px] uppercase tracking-wider text-text-secondary">{label}</p>
    </div>
  );
}

/**
 * Cases resolved in a month, by outcome, with what their supplies cost.
 * Shown to rescue:read holders; the dashboard decides where.
 */
export function RescueOutcomesCard() {
  const now = new Date();
  const [period, setPeriod] = useState({ year: now.getFullYear(), month: now.getMonth() + 1 });
  const isCurrent = period.year === now.getFullYear() && period.month === now.getMonth() + 1;

  const { data, isLoading, error } = useQuery({
    queryKey: ['rescueCases', 'report', period.year, period.month],
    queryFn: () => RescueCasesService.getReport(period.year, period.month),
  });

  const step = (delta: number) =>
    setPeriod(({ year, month }) => {
      const d = new Date(year, month - 1 + delta, 1);
      return { year: d.getFullYear(), month: d.getMonth() + 1 };
    });

  const most = Math.max(1, ...(data?.by_outcome.map((o) => o.cases) ?? [0]));

  return (
    <Card className="bg-surface border-border-brand">
      <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-3">
        <CardTitle className="text-base">Rescue outcomes</CardTitle>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => step(-1)} aria-label="Previous month">
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="min-w-[8.5rem] text-center text-xs font-semibold text-text-secondary">
            {MONTH.format(new Date(period.year, period.month - 1, 1))}
          </span>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => step(1)} disabled={isCurrent}
            aria-label="Next month">
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : error || !data ? (
          <p className="text-sm text-negative">{getErrorMessage(error) || 'Could not load the report.'}</p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat label="Resolved" value={String(data.resolved)} />
              <Stat label="Supplies cost" value={formatLKR(data.supplies_cost)} />
              <Stat label="Avg per case" value={data.average_cost == null ? '—' : formatLKR(data.average_cost)} />
              <Stat label="Open now" value={String(data.open_cases)} />
            </div>

            {data.resolved === 0 ? (
              <p className="text-xs text-text-muted">No cases were resolved this month.</p>
            ) : (
              <table className="w-full text-xs">
                <caption className="sr-only">Cases resolved by outcome, with supplies cost</caption>
                <thead className="sr-only">
                  <tr><th>Outcome</th><th>Cases</th><th>Supplies cost</th></tr>
                </thead>
                <tbody>
                  {data.by_outcome.map((o) => (
                    <tr key={o.outcome} title={`${o.outcome}: ${o.cases} case${o.cases === 1 ? '' : 's'}, supplies ${formatLKR(o.supplies_cost)}. ${OUTCOME_HINT[o.outcome]}`}
                      className="group">
                      <td className="w-24 py-1 pr-2 text-text-secondary">{o.outcome}</td>
                      <td className="py-1">
                        <div className="h-2.5 rounded-r-[4px] bg-accent transition-opacity group-hover:opacity-80"
                          style={{ width: `${(o.cases / most) * 100}%`, minWidth: o.cases ? 4 : 0 }} />
                      </td>
                      <td className="w-8 py-1 pl-2 text-right font-mono font-semibold text-text-primary">{o.cases}</td>
                      <td className="w-28 py-1 pl-2 text-right font-mono text-text-muted">{formatLKR(o.supplies_cost)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <p className="text-[10px] text-text-muted">
              A case counts in the month it was resolved, with all its supplies.
              {data.unrecorded_outcomes > 0 &&
                ` ${data.unrecorded_outcomes} older resolved case${data.unrecorded_outcomes === 1 ? ' has' : 's have'} no outcome recorded.`}
              {' '}<Link href="/case-triage" className="text-accent hover:underline">Open the board</Link>
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
