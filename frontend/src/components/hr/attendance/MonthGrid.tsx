'use client';

import { useMemo, useState } from 'react';
import { AlertTriangle, ChevronLeft, ChevronRight, FileSpreadsheet, Info, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useAttendanceMonth } from '@/hooks/useHR';
import { buildCsv, downloadCsv } from '@/lib/csv';
import { cn } from '@/lib/utils';
import { AttentionItem, DayCell, MonthRow } from '@/types';
import { DayDetailDialog } from './DayDetailDialog';
import { LEGEND, TONE_CLASS, hhmm, localDate, lookOf } from './dayStatus';

const MONTH = new Intl.DateTimeFormat('en-LK', { month: 'long', year: 'numeric' });
const SHORT = new Intl.DateTimeFormat('en-LK', { weekday: 'short', day: 'numeric', month: 'short' });
const WEEKDAY_LETTER = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

const KIND_LABEL: Record<AttentionItem['kinds'][number], string> = {
  absent: 'Absent',
  missing_clock_out: 'Missing clock-out',
  late: 'Late',
  left_early: 'Left early',
  worked_off_day: 'Worked a day off',
};

export function MonthGrid({ canEdit }: { canEdit: boolean }) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [search, setSearch] = useState('');
  const [attentionOnly, setAttentionOnly] = useState(false);
  const [open, setOpen] = useState<{ row: MonthRow; cell: DayCell } | null>(null);
  const { data, isLoading, isFetching, error } = useAttendanceMonth(year, month);

  const step = (delta: number) => {
    const d = new Date(year, month - 1 + delta, 1);
    setYear(d.getFullYear());
    setMonth(d.getMonth() + 1);
  };

  const needsAttention = useMemo(
    () => new Set((data?.attention ?? []).filter((a) => !a.info).map((a) => a.employee_id)),
    [data],
  );

  const rows = (data?.employees ?? []).filter((r) =>
    r.employee_name.toLowerCase().includes(search.trim().toLowerCase()) && (!attentionOnly || needsAttention.has(r.employee_id)),
  );

  const openCell = (employeeId: number, date: string) => {
    const row = data?.employees.find((r) => r.employee_id === employeeId);
    const cell = row?.cells.find((c) => c.date === date);
    if (row && cell) setOpen({ row, cell });
  };

  const exportCsv = () => {
    if (!data) return;
    downloadCsv(
      `attendance_${data.year}-${String(data.month).padStart(2, '0')}.csv`,
      buildCsv(
        ['Employee', 'Date', 'Status', 'Clock in', 'Clock out', 'Late (min)', 'Left early (min)', 'Worked (min)', 'Leave', 'Note'],
        data.employees.flatMap((r) =>
          r.cells.map((c) => [
            r.employee_name, c.date, lookOf(c).label, c.clock_in ? hhmm(c.clock_in) : '', c.clock_out ? hhmm(c.clock_out) : '',
            c.late_minutes || '', c.left_early_minutes || '', c.worked_minutes || '', c.leave?.type_name ?? '', c.reason,
          ]),
        ),
      ),
    );
  };

  const problems = (data?.attention ?? []).filter((a) => !a.info);
  const info = (data?.attention ?? []).filter((a) => a.info);

  return (
    <div className="space-y-4">
      {/* Controls: one row, above what they filter. */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1">
          <Button variant="outline" size="sm" onClick={() => step(-1)} aria-label="Previous month" className="h-9 w-9 border-border-brand p-0">
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="min-w-[150px] text-center text-sm font-semibold text-text-primary">{MONTH.format(new Date(year, month - 1, 1))}</span>
          <Button variant="outline" size="sm" onClick={() => step(1)} aria-label="Next month" className="h-9 w-9 border-border-brand p-0">
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        <div className="relative min-w-[180px] flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-text-muted" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Find an employee" aria-label="Find an employee"
            className="h-9 w-full rounded-md border border-border-brand bg-surface pl-8 pr-2 text-sm text-text-primary outline-none focus:border-accent" />
        </div>
        <label className="flex h-9 cursor-pointer items-center gap-1.5 rounded-md border border-border-brand px-2 text-xs text-text-secondary">
          <input type="checkbox" checked={attentionOnly} onChange={(e) => setAttentionOnly(e.target.checked)} className="accent-[var(--color-accent)]" />
          Needs attention only
        </label>
        <Button variant="outline" onClick={exportCsv} disabled={!data} className="gap-2 border-border-brand">
          <FileSpreadsheet className="h-4 w-4" /> CSV
        </Button>
      </div>

      {/* Legend: letters and colours together. */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-secondary">
        {LEGEND.map((l) => (
          <span key={l.code} className="flex items-center gap-1.5">
            <span className={cn('inline-flex min-w-6 justify-center rounded px-1 py-0.5 text-[10px] font-bold', TONE_CLASS[l.tone])}>{l.code}</span>
            {l.label}
          </span>
        ))}
        <span className="flex items-center gap-1.5"><span className="inline-block h-4 w-6 rounded bg-bg-subtle" />Weekend / day off</span>
      </div>

      {canEdit && data?.payroll_frozen_through && (
        <p className="rounded-lg border border-border-brand bg-bg-subtle px-4 py-2.5 text-xs text-text-secondary">
          {data.payroll_frozen_through >= data.days[data.days.length - 1].date
            ? `Payroll for ${MONTH.format(new Date(year, month - 1, 1))} is approved, so this month's attendance is read-only.`
            : `Payroll for ${MONTH.format(new Date(year, month - 1, 1))} was approved on ${SHORT.format(localDate(data.payroll_frozen_through))}, so attendance up to that day is read-only.`}
        </p>
      )}

      {error && !data ? (
        <p className="rounded-lg border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-500">Failed to load attendance for this month.</p>
      ) : isLoading || !data ? (
        <Skeleton className="h-64 w-full bg-bg-subtle" />
      ) : (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
          <Card className="bg-surface border border-border-brand rounded-card shadow-card overflow-hidden">
            <CardContent className={cn('p-0 transition-opacity', isFetching && 'opacity-60')}>
              {rows.length === 0 ? (
                <p className="py-12 text-center text-sm text-text-muted">
                  {attentionOnly ? 'Nothing needs attention this month.' : 'No employees match.'}
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="border-separate border-spacing-0 text-xs">
                    <thead>
                      <tr>
                        <th className="sticky left-0 z-10 min-w-[160px] border-b border-border-brand bg-surface px-3 py-2 text-left font-semibold text-text-secondary">
                          Employee
                        </th>
                        {data.days.map((d) => {
                          const off = d.weekday >= 6 || d.holidays.length > 0;
                          return (
                            <th key={d.date} title={d.holidays.join(', ') || undefined}
                              className={cn('border-b border-border-brand px-0.5 py-1 text-center font-medium',
                                off ? 'bg-bg-subtle text-text-muted' : 'text-text-secondary',
                                d.date === data.today && 'text-accent')}>
                              <div className="text-[10px]">{WEEKDAY_LETTER[d.weekday - 1]}</div>
                              <div className={cn(d.holidays.length && 'underline decoration-dotted')}>{Number(d.date.slice(8))}</div>
                            </th>
                          );
                        })}
                        <th className="border-b border-border-brand px-2 text-center font-semibold text-text-secondary" title="Present">P</th>
                        <th className="border-b border-border-brand px-2 text-center font-semibold text-text-secondary" title="Absent">A</th>
                        <th className="border-b border-border-brand px-2 text-center font-semibold text-text-secondary" title="Late">L</th>
                        <th className="border-b border-border-brand px-2 text-center font-semibold text-text-secondary" title="Leave days">LV</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => (
                        <tr key={r.employee_id} className="group">
                          <td className="sticky left-0 z-10 whitespace-nowrap border-b border-border-brand bg-surface px-3 py-1.5 font-medium text-text-primary group-hover:bg-bg-subtle">
                            {r.employee_name}
                            {r.status && r.status !== 'Active' && <span className="ml-1 text-[10px] text-text-muted">({r.status})</span>}
                          </td>
                          {r.cells.map((c, i) => {
                            const look = lookOf(c);
                            const day = data.days[i];
                            const off = day.weekday >= 6 || day.holidays.length > 0;
                            return (
                              <td key={c.date} className={cn('border-b border-border-brand p-0.5 text-center', off && 'bg-bg-subtle/60')}>
                                <button
                                  type="button"
                                  onClick={() => setOpen({ row: r, cell: c })}
                                  title={`${SHORT.format(localDate(c.date))}: ${look.label}`}
                                  aria-label={`${r.employee_name}, ${SHORT.format(localDate(c.date))}: ${look.label}`}
                                  className={cn('flex h-7 w-7 items-center justify-center rounded text-[10px] font-bold transition-shadow hover:ring-2 hover:ring-accent/50',
                                    TONE_CLASS[look.tone])}
                                >
                                  {look.code}
                                </button>
                              </td>
                            );
                          })}
                          <td className="border-b border-border-brand px-2 text-center font-mono tabular-nums text-text-primary">{r.totals.present}</td>
                          <td className={cn('border-b border-border-brand px-2 text-center font-mono tabular-nums', r.totals.absent ? 'text-rose-600' : 'text-text-muted')}>{r.totals.absent}</td>
                          <td className={cn('border-b border-border-brand px-2 text-center font-mono tabular-nums', r.totals.late ? 'text-amber-600' : 'text-text-muted')}>{r.totals.late}</td>
                          <td className="border-b border-border-brand px-2 text-center font-mono tabular-nums text-text-primary">{r.totals.leave_days}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Needs attention: problems oldest first, then information. */}
          <Card className="bg-surface border border-border-brand rounded-card shadow-card h-fit">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm font-semibold font-heading text-text-primary">
                <AlertTriangle className="h-4 w-4 text-amber-600" /> Needs attention
                <span className="ml-auto rounded-full bg-bg-subtle px-2 py-0.5 text-xs font-normal text-text-secondary">{problems.length}</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="max-h-[520px] space-y-1 overflow-y-auto px-3 pb-3">
              {problems.length === 0 && <p className="px-2 py-4 text-sm text-text-muted">Nothing to follow up this month.</p>}
              {[...problems, ...info].map((a) => (
                <button key={`${a.employee_id}-${a.date}`} type="button" onClick={() => openCell(a.employee_id, a.date)}
                  className="flex w-full flex-col items-start gap-0.5 rounded-md px-2 py-1.5 text-left hover:bg-bg-subtle">
                  <span className="flex w-full items-center gap-2 text-xs">
                    {a.info ? <Info className="h-3.5 w-3.5 shrink-0 text-violet-600" /> : <span className="h-2 w-2 shrink-0 rounded-full bg-rose-500" />}
                    <span className="font-medium text-text-primary">{a.employee_name}</span>
                    <span className="ml-auto font-mono text-text-muted">{SHORT.format(localDate(a.date))}</span>
                  </span>
                  <span className="pl-4 text-[11px] text-text-secondary">
                    {a.kinds.map((k) => KIND_LABEL[k]).join(', ')}{a.leave_pending ? ' · leave awaiting a decision' : ''}
                  </span>
                </button>
              ))}
            </CardContent>
          </Card>
        </div>
      )}

      {open && (
        <DayDetailDialog
          key={`${open.row.employee_id}-${open.cell.date}`}
          cell={open.cell}
          employeeId={open.row.employee_id}
          employeeName={open.row.employee_name}
          canEdit={canEdit}
          isOwn={data?.my_employee_id === open.row.employee_id}
          payrollApproved={!!data?.payroll_frozen_through && open.cell.date <= data.payroll_frozen_through}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  );
}
