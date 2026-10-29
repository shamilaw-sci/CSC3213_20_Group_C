'use client';

import { useState } from 'react';
import { AlertTriangle, Download, Moon, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
  useDeleteHoliday, useHolidayImportPreview, useHolidays, useImportHolidays, useSaveHoliday,
} from '@/hooks/useWorkCalendar';
import { Holiday, HolidayInput } from '@/types';
import { cn } from '@/lib/utils';

const input =
  'h-9 rounded-md border border-border-brand bg-surface px-2 text-sm text-text-primary outline-none focus:border-accent';

const DAY = new Intl.DateTimeFormat('en-LK', { weekday: 'short', day: 'numeric', month: 'short' });
const MONTH = new Intl.DateTimeFormat('en-LK', { month: 'long' });

// Parse as a local calendar date: new Date('2026-11-24') would be UTC
// midnight, which renders as the 24th only by luck of the timezone.
function localDate(iso: string) {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(y, m - 1, d);
}

function Tag({ children, tone }: { children: React.ReactNode; tone: 'muted' | 'accent' | 'sky' }) {
  return (
    <span
      className={cn(
        'rounded px-1.5 py-0.5 text-[10px] font-semibold',
        tone === 'muted' && 'bg-bg-subtle text-text-secondary',
        tone === 'accent' && 'bg-accent/10 text-accent',
        tone === 'sky' && 'bg-sky-500/10 text-sky-600',
      )}
    >
      {children}
    </span>
  );
}

function toInput(h: Holiday): HolidayInput {
  return {
    holiday_date: h.holiday_date.slice(0, 10),
    name: h.name,
    is_public: h.is_public,
    is_bank: h.is_bank,
    is_mercantile: h.is_mercantile,
    is_day_off: h.is_day_off,
    source: h.source,
  };
}

// --------------------------------------------------------------------------
// Import from the gazette file
// --------------------------------------------------------------------------

function ImportDialog({ year, onClose }: { year: number; onClose: () => void }) {
  const { data, isLoading, error } = useHolidayImportPreview(year, true);
  const { mutate: run, isPending } = useImportHolidays();
  const detail = (error as { response?: { data?: { detail?: string } } } | null)?.response?.data?.detail;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-surface border-border-brand sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Import {year} holidays from the gazette</DialogTitle>
          <DialogDescription>
            From the official file for {year}. Holidays already on the calendar, including ones you have edited, are left as
            they are.
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <Skeleton className="h-32 w-full bg-bg-subtle" />
        ) : error ? (
          <p className="rounded-md border border-rose-500/20 bg-rose-500/10 p-3 text-sm text-rose-500">
            {detail ?? 'Could not read the holiday file.'}
          </p>
        ) : data && (
          <div className="space-y-3 text-sm">
            <p className="text-text-secondary">
              <span className="font-semibold text-text-primary">{data.new_count}</span> to add,{' '}
              {data.existing_count} already on the calendar. Days off follow VFF policy: mercantile holidays and every Poya day.
            </p>
            {data.warnings.length > 0 && (
              <ul className="space-y-1 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-text-secondary">
                {data.warnings.map((w) => (
                  <li key={w} className="flex gap-2"><AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-600" /> {w}</li>
                ))}
              </ul>
            )}
            <ul className="max-h-64 divide-y divide-border-brand overflow-y-auto rounded-md border border-border-brand">
              {data.rows.map((r) => (
                <li key={`${r.holiday_date}-${r.name}`} className="flex items-center gap-2 px-3 py-1.5 text-xs">
                  <span className="w-24 shrink-0 font-mono text-text-secondary">{DAY.format(localDate(r.holiday_date))}</span>
                  <span className="flex-1 text-text-primary">{r.name}</span>
                  {r.is_day_off ? <Tag tone="accent">Day off</Tag> : <Tag tone="muted">Working</Tag>}
                </li>
              ))}
            </ul>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isPending}>Cancel</Button>
          <Button
            onClick={() => run(year, { onSuccess: onClose })}
            disabled={!data || data.new_count === 0 || isPending}
            className="bg-accent text-white hover:bg-accent/90"
          >
            {isPending ? 'Importing…' : data?.new_count === 0 ? 'Nothing to add' : `Add ${data?.new_count ?? ''} holidays`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --------------------------------------------------------------------------
// Add a holiday by hand (gazette amendments, short-notice declarations)
// --------------------------------------------------------------------------

function AddHolidayDialog({ year, onClose }: { year: number; onClose: () => void }) {
  const [form, setForm] = useState<HolidayInput>({
    holiday_date: `${year}-01-01`, name: '', is_public: true, is_bank: false, is_mercantile: false,
    is_day_off: true, source: '',
  });
  const { mutate: save, isPending } = useSaveHoliday();
  const set = (patch: Partial<HolidayInput>) => setForm((f) => ({ ...f, ...patch }));

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-surface border-border-brand">
        <DialogHeader>
          <DialogTitle>Add a holiday</DialogTitle>
          <DialogDescription>For gazette amendments and holidays declared at short notice.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-[auto_1fr]">
          <label className="space-y-1 text-xs font-medium text-text-secondary">
            Date
            <input type="date" value={form.holiday_date} onChange={(e) => set({ holiday_date: e.target.value })} className={cn(input, 'w-full font-mono')} />
          </label>
          <label className="space-y-1 text-xs font-medium text-text-secondary">
            Name
            <input value={form.name} onChange={(e) => set({ name: e.target.value })} className={cn(input, 'w-full')} placeholder="e.g. Special Government Holiday" />
          </label>
          <label className="space-y-1 text-xs font-medium text-text-secondary sm:col-span-2">
            Source
            <input value={form.source ?? ''} onChange={(e) => set({ source: e.target.value })} className={cn(input, 'w-full')} placeholder="e.g. Gazette Extraordinary No. … or circular reference" />
          </label>
          <div className="flex flex-wrap gap-4 text-sm text-text-primary sm:col-span-2">
            {([['is_public', 'Public'], ['is_bank', 'Bank'], ['is_mercantile', 'Mercantile'], ['is_day_off', 'Day off at VFF']] as const).map(([key, label]) => (
              <label key={key} className="flex items-center gap-1.5">
                <input type="checkbox" checked={form[key]} onChange={(e) => set({ [key]: e.target.checked })} className="accent-[var(--color-accent)]" />
                {label}
              </label>
            ))}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isPending}>Cancel</Button>
          <Button onClick={() => save({ body: form }, { onSuccess: onClose })} disabled={!form.name.trim() || !form.holiday_date || isPending}
            className="bg-accent text-white hover:bg-accent/90">
            {isPending ? 'Saving…' : 'Add holiday'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --------------------------------------------------------------------------
// Tab
// --------------------------------------------------------------------------

export function HolidaysTab({ canEdit }: { canEdit: boolean }) {
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const [importing, setImporting] = useState(false);
  const [adding, setAdding] = useState(false);
  const { data: holidays, isLoading } = useHolidays(year);
  const { mutate: save } = useSaveHoliday();
  const { mutate: remove } = useDeleteHoliday();

  const daysOff = holidays?.filter((h) => h.is_day_off).length ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <select value={year} onChange={(e) => setYear(Number(e.target.value))} aria-label="Year" className={input}>
            {[thisYear - 1, thisYear, thisYear + 1].map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          {holidays && (
            <span className="text-sm text-text-secondary">
              {holidays.length} holidays, <span className="font-semibold text-text-primary">{daysOff}</span> days off
            </span>
          )}
        </div>
        {canEdit && (
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setAdding(true)} className="gap-2 border-border-brand">
              <Plus className="h-4 w-4" /> Add holiday
            </Button>
            <Button onClick={() => setImporting(true)} className="gap-2 bg-accent text-white hover:bg-accent/90">
              <Download className="h-4 w-4" /> Import from gazette
            </Button>
          </div>
        )}
      </div>

      <Card className="bg-surface border border-border-brand rounded-card shadow-card">
        <CardContent className="p-0">
          {isLoading ? (
            <Skeleton className="m-4 h-40 bg-bg-subtle" />
          ) : !holidays?.length ? (
            <div className="py-12 text-center text-sm text-text-muted">
              No holidays for {year} yet.{canEdit && ' Use Import from gazette to load the official list.'}
            </div>
          ) : (
            <table className="w-full text-left text-sm">
              <thead className="bg-bg-subtle/60 text-[11px] uppercase tracking-wider text-text-secondary">
                <tr>
                  <th className="px-4 py-2.5 font-semibold">Date</th>
                  <th className="px-4 py-2.5 font-semibold">Holiday</th>
                  <th className="px-4 py-2.5 font-semibold">Category</th>
                  <th className="px-4 py-2.5 font-semibold">At VFF</th>
                  {canEdit && <th className="px-4 py-2.5"><span className="sr-only">Actions</span></th>}
                </tr>
              </thead>
              <tbody>
                {holidays.map((h, i) => {
                  const d = localDate(h.holiday_date);
                  const month = MONTH.format(d);
                  // A month heading above the first holiday of each month.
                  const header = i === 0 || month !== MONTH.format(localDate(holidays[i - 1].holiday_date));
                  return [
                    header && (
                      <tr key={`m-${month}`} className="bg-bg-subtle/40">
                        <td colSpan={canEdit ? 5 : 4} className="px-4 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-muted">{month}</td>
                      </tr>
                    ),
                    <tr key={h.id} className="border-t border-border-brand">
                      <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs text-text-secondary">{DAY.format(d)}</td>
                      <td className="px-4 py-2.5 text-text-primary" title={h.source ?? undefined}>
                        <span className="inline-flex items-center gap-1.5">
                          {h.is_poya && <Moon className="h-3.5 w-3.5 text-sky-600" aria-label="Poya day" />}
                          {h.name}
                        </span>
                      </td>
                      <td className="px-4 py-2.5">
                        <span className="flex flex-wrap gap-1">
                          {h.is_poya && <Tag tone="sky">Poya</Tag>}
                          {h.is_mercantile && <Tag tone="accent">Mercantile</Tag>}
                          {h.is_public && <Tag tone="muted">Public</Tag>}
                          {h.is_bank && <Tag tone="muted">Bank</Tag>}
                        </span>
                      </td>
                      <td className="px-4 py-2.5">
                        {canEdit ? (
                          <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-text-primary">
                            <input
                              type="checkbox"
                              checked={h.is_day_off}
                              onChange={(e) => save({ id: h.id, body: { ...toInput(h), is_day_off: e.target.checked } })}
                              className="accent-[var(--color-accent)]"
                            />
                            {h.is_day_off ? 'Day off' : 'Working day'}
                          </label>
                        ) : (
                          <span className="text-xs text-text-secondary">{h.is_day_off ? 'Day off' : 'Working day'}</span>
                        )}
                      </td>
                      {canEdit && (
                        <td className="px-4 py-2.5 text-right">
                          <Button variant="ghost" size="sm" onClick={() => remove(h.id)} aria-label={`Remove ${h.name}`}
                            className="h-7 w-7 p-0 text-text-secondary hover:text-negative">
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </td>
                      )}
                    </tr>,
                  ];
                })}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <p className="text-xs text-text-muted">
        Poya dates come from the government gazette, not a formula; they follow the lunar calendar. Hover a holiday to see
        its source. VFF days off are mercantile holidays and every Poya day; other public holidays are working days unless
        changed here.
      </p>

      {importing && <ImportDialog year={year} onClose={() => setImporting(false)} />}
      {adding && <AddHolidayDialog year={year} onClose={() => setAdding(false)} />}
    </div>
  );
}
