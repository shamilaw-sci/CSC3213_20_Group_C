'use client';

import { useState } from 'react';
import { ReportsService } from '@/services/reports.service';
import { toast } from 'sonner';
import { FileDown } from 'lucide-react';
import { Button } from '@/components/ui/button';

function getDefaultDateRange() {
  const now = new Date();
  const firstOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
  const toISO = (d: Date) => d.toISOString().split('T')[0];
  return { start: toISO(firstOfMonth), end: toISO(now) };
}

export function FinanceReportButton() {
  const defaults = getDefaultDateRange();
  const [startDate, setStartDate] = useState(defaults.start);
  const [endDate, setEndDate] = useState(defaults.end);
  const [isGenerating, setIsGenerating] = useState(false);

  const handleDownload = async () => {
    if (!startDate || !endDate) {
      toast.error('Please select both a start and end date');
      return;
    }
    if (startDate > endDate) {
      toast.error('Start date must be before end date');
      return;
    }

    setIsGenerating(true);
    try {
      await ReportsService.downloadFinanceSummary(startDate, endDate);
      toast.success('Report downloaded');
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to generate report');
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="flex items-center gap-2 bg-bg-subtle border border-border-brand rounded-lg px-2 py-1.5">
      <input
        type="date"
        value={startDate}
        onChange={(e) => setStartDate(e.target.value)}
        className="text-xs font-mono bg-transparent border border-border-brand rounded-md px-2 py-1 text-text-primary"
        aria-label="Report start date"
      />
      <span className="text-text-secondary text-xs">to</span>
      <input
        type="date"
        value={endDate}
        onChange={(e) => setEndDate(e.target.value)}
        className="text-xs font-mono bg-transparent border border-border-brand rounded-md px-2 py-1 text-text-primary"
        aria-label="Report end date"
      />
      <Button
        onClick={handleDownload}
        disabled={isGenerating}
        variant="outline"
        className="border-border-brand text-text-primary text-xs font-semibold flex items-center gap-1.5 rounded-md py-1.5 px-3"
      >
        <FileDown className="h-3.5 w-3.5" />
        {isGenerating ? 'Generating...' : 'Download Report'}
      </Button>
    </div>
  );
}