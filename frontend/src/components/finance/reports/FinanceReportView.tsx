'use client';

import { useMemo, useState } from 'react';
import { AlertTriangle, FileDown, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useFinanceReport } from '@/hooks/useFinance';
import { ReportsService } from '@/services/reports.service';
import { Period, PeriodPreset, PRESETS, periodLabel, presetPeriod, toISODate } from '@/lib/finance-periods';
import { cn } from '@/lib/utils';
import { IncomeExpenditure, MonthlyTrend, Outstanding, ProgramBreakdown, RestrictedFunds } from './ReportSections';

const dateInput =
  'text-xs font-mono bg-surface border border-border-brand rounded-md px-2 py-1.5 text-text-primary focus:border-accent outline-none';

export function FinanceReportView() {
  const today = useMemo(() => new Date(), []);
  const [preset, setPreset] = useState<PeriodPreset>('this-fy');
  const [custom, setCustom] = useState<Period>(() => presetPeriod('this-month', today));

  const period = preset === 'custom' ? custom : presetPeriod(preset, today);
  const invalid = !period.start || !period.end || period.start > period.end;

  const { data: report, isLoading, isFetching, error } = useFinanceReport(period.start, period.end);
  const [downloading, setDownloading] = useState(false);

  const todayISO = toISODate(today);
  const inProgress = period.end > todayISO && period.start <= todayISO;

  const downloadPdf = async () => {
    setDownloading(true);
    try {
      await ReportsService.downloadFinanceSummary(period.start, period.end);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Failed to generate the PDF');
    } finally {
      setDownloading(false);
    }
  };

  // The report shown may briefly be the previous period's while the new one
  // loads (placeholderData), so the heading follows the data, not the picker.
  const shownLabel = report
    ? periodLabel({ start: report.period.start, end: report.period.end })
    : periodLabel(period);
  const prevLabel = report
    ? periodLabel({ start: report.period.previous_start, end: report.period.previous_end })
    : null;

  return (
    <div className="space-y-6 pb-12">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-3xl font-bold font-heading tracking-tight mb-2 text-text-primary">Financial Reports</h1>
          <p className="text-text-secondary text-sm">
            {shownLabel}
            {prevLabel && <span className="text-text-muted"> · compared with {prevLabel}</span>}
            {isFetching && !isLoading && <Loader2 className="ml-2 inline h-3.5 w-3.5 animate-spin text-text-muted" />}
          </p>
        </div>
        <Button
          onClick={downloadPdf}
          disabled={downloading || invalid}
          className="bg-accent text-white hover:bg-accent/90 font-semibold gap-2 self-start lg:self-auto"
        >
          {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />}
          {downloading ? 'Generating…' : 'Download PDF'}
        </Button>
      </div>

      {/* Period picker: one row, above everything it filters. */}
      <div className="flex flex-wrap items-center gap-2 rounded-card border border-border-brand bg-surface p-2 shadow-card">
        {[...PRESETS, { value: 'custom' as const, label: 'Custom' }].map((p) => (
          <button
            key={p.value}
            type="button"
            onClick={() => {
              // Starting a custom range from the period on screen is less
              // surprising than jumping back to some fixed default.
              if (p.value === 'custom' && preset !== 'custom') setCustom(period);
              setPreset(p.value);
            }}
            aria-pressed={preset === p.value}
            className={cn(
              'rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
              preset === p.value
                ? 'bg-accent/10 text-accent ring-1 ring-accent/40'
                : 'text-text-secondary hover:bg-bg-subtle hover:text-text-primary',
            )}
          >
            {p.label}
          </button>
        ))}

        {preset === 'custom' && (
          <div className="flex items-center gap-2 pl-1">
            <input
              type="date"
              value={custom.start}
              max={custom.end || undefined}
              onChange={(e) => setCustom((c) => ({ ...c, start: e.target.value }))}
              className={dateInput}
              aria-label="Report start date"
            />
            <span className="text-xs text-text-secondary">to</span>
            <input
              type="date"
              value={custom.end}
              min={custom.start || undefined}
              onChange={(e) => setCustom((c) => ({ ...c, end: e.target.value }))}
              className={dateInput}
              aria-label="Report end date"
            />
          </div>
        )}
      </div>

      {inProgress && !invalid && (
        <p className="flex items-start gap-2 text-xs text-text-secondary">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" />
          This period runs to {period.end}, so it is still in progress. Comparisons are against the whole of the
          previous period.
        </p>
      )}

      {invalid ? (
        <p className="rounded-card border border-dashed border-border-brand py-10 text-center text-sm text-text-muted">
          Choose a start date on or before the end date.
        </p>
      ) : error && !report ? (
        <div className="flex items-center gap-2 rounded-lg border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-500">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {(error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
            'Failed to load the report. Please try again.'}
        </div>
      ) : isLoading || !report ? (
        <div className="space-y-6">
          <Skeleton className="h-48 w-full bg-bg-subtle" />
          <Skeleton className="h-72 w-full bg-bg-subtle" />
          <Skeleton className="h-56 w-full bg-bg-subtle" />
        </div>
      ) : (
        <div className={cn('space-y-6 transition-opacity', isFetching && 'opacity-60')}>
          <IncomeExpenditure report={report} />
          <MonthlyTrend report={report} />
          <ProgramBreakdown report={report} />
          <RestrictedFunds report={report} />
          <Outstanding report={report} />
        </div>
      )}
    </div>
  );
}
