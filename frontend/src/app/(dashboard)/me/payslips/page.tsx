'use client';

import { useState } from 'react';
import { FileDown, Loader2, ReceiptText } from 'lucide-react';
import { toast } from 'sonner';
import ProtectedRoute from '@/components/layout/protected-route';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useMyPayslips } from '@/hooks/useHR';
import { HRService } from '@/services/hr.service';
import { formatLKR } from '@/lib/formatters';
import { saveBlob } from '@/lib/download';
import { MyPayslip } from '@/types';

const MONTH = new Intl.DateTimeFormat('en-LK', { month: 'long', year: 'numeric' });

export default function MyPayslipsPage() {
  return (
    <ProtectedRoute requiredPermission="hr:attendance:self">
      <MyPayslips />
    </ProtectedRoute>
  );
}

function MyPayslips() {
  const { data, isLoading, error } = useMyPayslips();
  const [downloading, setDownloading] = useState<number | null>(null);
  const notLinked = (error as { response?: { status?: number } } | null)?.response?.status === 404;

  const download = async (p: MyPayslip) => {
    setDownloading(p.run_id);
    try {
      const blob = await HRService.getMyPayslip(p.run_id);
      saveBlob(blob, `payslip_${p.payroll_year}-${String(p.payroll_month).padStart(2, '0')}.pdf`);
    } catch {
      toast.error('Could not download the payslip');
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div className="space-y-6 pb-12">
      <div>
        <h1 className="text-3xl font-bold font-heading tracking-tight mb-2 text-text-primary">My Payslips</h1>
        <p className="text-text-secondary text-sm">A payslip appears here once that month&apos;s payroll is approved.</p>
      </div>

      <Card className="bg-surface border border-border-brand rounded-card shadow-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base font-semibold font-heading text-text-primary">
            <ReceiptText className="h-4 w-4 text-accent" /> Payslips
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <Skeleton className="m-4 h-24 bg-bg-subtle" />
          ) : error ? (
            <p className="px-6 pb-6 text-sm text-text-muted">
              {notLinked
                ? "Your account isn't linked to an employee record yet. Ask HR to link it."
                : 'Could not load your payslips. Refresh to try again.'}
            </p>
          ) : !data?.length ? (
            <p className="px-6 pb-6 text-sm text-text-muted">No payslips yet.</p>
          ) : (
            <table className="w-full text-left text-sm">
              <thead className="bg-bg-subtle/60 text-[11px] uppercase tracking-wider text-text-secondary">
                <tr>
                  <th className="px-4 py-2.5 font-semibold">Month</th>
                  <th className="px-4 py-2.5 text-right font-semibold">Gross</th>
                  <th className="px-4 py-2.5 text-right font-semibold">Net pay</th>
                  <th className="px-4 py-2.5"><span className="sr-only">Download</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-brand">
                {data.map((p) => (
                  <tr key={p.run_id}>
                    <td className="px-4 py-2.5 text-text-primary">{MONTH.format(new Date(p.payroll_year, p.payroll_month - 1, 1))}</td>
                    <td className="px-4 py-2.5 text-right font-mono tabular-nums text-text-secondary">
                      {p.gross === null ? '—' : formatLKR(p.gross)}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono font-semibold tabular-nums text-text-primary">{formatLKR(p.net_payable)}</td>
                    <td className="px-4 py-2.5 text-right">
                      <Button variant="ghost" size="sm" disabled={downloading === p.run_id} onClick={() => download(p)}
                        className="h-7 gap-1.5 px-2 text-xs text-text-secondary hover:text-text-primary">
                        {downloading === p.run_id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileDown className="h-3.5 w-3.5" />}
                        PDF
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
