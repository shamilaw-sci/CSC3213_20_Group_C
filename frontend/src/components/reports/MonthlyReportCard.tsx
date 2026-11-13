'use client';

import { useState } from 'react';
import { FileDown, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ReportsService } from '@/services/reports.service';
import { getErrorMessage } from '@/lib/utils';

const MONTH = new Intl.DateTimeFormat('en-LK', { month: 'long', year: 'numeric' });
// How far back the picker goes; older months can still be asked for by URL.
const MONTHS_OFFERED = 24;

function lastMonths(): { year: number; month: number; label: string }[] {
  const now = new Date();
  return Array.from({ length: MONTHS_OFFERED }, (_, i) => {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    return {
      year: d.getFullYear(),
      month: d.getMonth() + 1,
      label: MONTH.format(d) + (i === 0 ? ' (to date)' : ''),
    };
  });
}

// A failed blob request carries its JSON error as a Blob, which
// getErrorMessage can't read; turn it back into the API's message.
async function blobError(err: unknown): Promise<string> {
  const data = (err as { response?: { data?: unknown } })?.response?.data;
  if (data instanceof Blob) {
    try {
      const detail = JSON.parse(await data.text())?.detail;
      if (typeof detail === 'string') return detail;
    } catch { /* not JSON */ }
  }
  return getErrorMessage(err) || "Couldn't create the report. Please try again.";
}

/**
 * Download the monthly management report: rescue, finance, people and stock
 * for one month, as a PDF. Admin and Director (reports:monthly).
 */
export function MonthlyReportCard() {
  const months = lastMonths();
  // Default to last month: the current one is still changing.
  const [choice, setChoice] = useState(`${months[1].year}-${months[1].month}`);
  const [busy, setBusy] = useState(false);

  const download = async () => {
    const [year, month] = choice.split('-').map(Number);
    setBusy(true);
    try {
      await ReportsService.downloadMonthly(year, month);
    } catch (err) {
      toast.error(await blobError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="bg-surface border-border-brand">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Monthly report</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-text-secondary">
          One month across the organisation as a PDF: rescue outcomes and costs, income and spending,
          donations, staff and payroll, and stock.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={choice}
            onChange={(e) => setChoice(e.target.value)}
            aria-label="Report month"
            className="rounded-md border border-border-brand bg-surface px-2 py-2 text-sm text-text-primary outline-none focus:border-accent"
          >
            {months.map((m) => (
              <option key={`${m.year}-${m.month}`} value={`${m.year}-${m.month}`}>{m.label}</option>
            ))}
          </select>
          <Button onClick={download} disabled={busy} className="gap-1.5 bg-accent text-white hover:bg-accent/90">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />}
            {busy ? 'Preparing…' : 'Download PDF'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
