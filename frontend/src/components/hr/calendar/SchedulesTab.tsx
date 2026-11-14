'use client';

import { useState } from 'react';
import { CalendarClock, Moon, Pencil, Plus, Star, Trash2, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
  useAssignSchedule, useDeleteAssignment, useDeleteSchedule, useMakeDefaultSchedule,
  useSaveSchedule, useScheduleAssignments, useSchedules,
} from '@/hooks/useWorkCalendar';
import { ScheduleAssignmentRow, ScheduleDay, WorkSchedule, WorkScheduleInput } from '@/types';
import { TrackingDialog, longDate } from '@/components/hr/attendance/TrackingDialog';
import { toISODate } from '@/lib/finance-periods';
import { cn } from '@/lib/utils';

export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const input =
  'h-9 rounded-md border border-border-brand bg-surface px-2 text-sm text-text-primary outline-none focus:border-accent';

export const hhmm = (t: string) => t.slice(0, 5);

function overnight(d: Pick<ScheduleDay, 'start_time' | 'end_time'>) {
  return hhmm(d.end_time) < hhmm(d.start_time);
}

// The week at a glance: hours on working days, "Off" on the rest.
export function WeekStrip({ days }: { days: ScheduleDay[] }) {
  return (
    <div className="grid grid-cols-7 gap-1 text-center text-[11px]">
      {WEEKDAYS.map((label, i) => {
        const d = days.find((x) => x.weekday === i + 1);
        return (
          <div
            key={label}
            className={cn(
              'rounded-md border px-1 py-1.5',
              d ? 'border-accent/30 bg-accent/10 text-text-primary' : 'border-border-brand bg-bg-subtle text-text-muted',
            )}
          >
            <div className="font-semibold">{label}</div>
            {d ? (
              <div className="font-mono leading-tight">
                {hhmm(d.start_time)}
                <br />
                {hhmm(d.end_time)}
                {overnight(d) && <Moon className="mx-auto mt-0.5 h-3 w-3" aria-label="Overnight" />}
              </div>
            ) : (
              <div className="leading-tight">Off</div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// --------------------------------------------------------------------------
// Schedule editor
// --------------------------------------------------------------------------

const DEFAULT_DAY = { start_time: '08:30', end_time: '17:00', break_minutes: 60 };

function ScheduleEditor({ schedule, onClose }: { schedule: WorkSchedule | 'new'; onClose: () => void }) {
  const existing = schedule === 'new' ? null : schedule;
  const [name, setName] = useState(existing?.name ?? '');
  const [grace, setGrace] = useState(existing?.grace_minutes ?? 15);
  const [observes, setObserves] = useState(existing?.observes_holidays ?? true);
  const [days, setDays] = useState<Record<number, ScheduleDay | null>>(() =>
    Object.fromEntries(
      [1, 2, 3, 4, 5, 6, 7].map((w) => {
        const d = existing?.days.find((x) => x.weekday === w);
        return [w, d ? { ...d, start_time: hhmm(d.start_time), end_time: hhmm(d.end_time) } : null];
      }),
    ),
  );
  const { mutate: save, isPending } = useSaveSchedule();

  const setDay = (w: number, patch: Partial<ScheduleDay> | null) =>
    setDays((all) => ({ ...all, [w]: patch === null ? null : { ...(all[w] ?? { weekday: w, ...DEFAULT_DAY }), ...patch } }));

  const working = Object.values(days).filter((d): d is ScheduleDay => !!d);
  const invalid = !name.trim() || working.some((d) => d.start_time === d.end_time);

  const submit = () => {
    const body: WorkScheduleInput = { name: name.trim(), grace_minutes: grace, observes_holidays: observes, days: working };
    save({ id: existing?.id, body }, { onSuccess: onClose });
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-surface border-border-brand sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{existing ? `Edit ${existing.name}` : 'New schedule'}</DialogTitle>
          <DialogDescription>
            Times are Sri Lanka time. An end time earlier than the start is an overnight shift.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
            <label className="space-y-1 text-xs font-medium text-text-secondary">
              Name
              <input value={name} onChange={(e) => setName(e.target.value)} className={cn(input, 'w-full')} placeholder="e.g. Rescue rota" />
            </label>
            <label className="space-y-1 text-xs font-medium text-text-secondary">
              Grace before late (min)
              <input type="number" min={0} max={120} value={grace} onChange={(e) => setGrace(Number(e.target.value))} className={cn(input, 'w-full sm:w-32')} />
            </label>
          </div>

          <label className="flex items-start gap-2 text-sm text-text-primary">
            <input type="checkbox" checked={observes} onChange={(e) => setObserves(e.target.checked)} className="mt-1 accent-[var(--color-accent)]" />
            <span>
              Takes holidays off
              <span className="block text-xs text-text-secondary">
                Untick for staff who work through Poya days and other holidays, such as the rescue rota.
              </span>
            </span>
          </label>

          <table className="w-full text-sm">
            <thead className="text-[11px] uppercase tracking-wider text-text-secondary">
              <tr>
                <th className="py-1 text-left font-semibold">Day</th>
                <th className="py-1 text-left font-semibold">Start</th>
                <th className="py-1 text-left font-semibold">End</th>
                <th className="py-1 text-left font-semibold">Break (min)</th>
              </tr>
            </thead>
            <tbody>
              {[1, 2, 3, 4, 5, 6, 7].map((w) => {
                const d = days[w];
                return (
                  <tr key={w} className="border-t border-border-brand">
                    <td className="py-1.5 pr-2">
                      <label className="flex items-center gap-2 text-text-primary">
                        <input type="checkbox" checked={!!d} onChange={(e) => setDay(w, e.target.checked ? {} : null)} className="accent-[var(--color-accent)]" />
                        {WEEKDAYS[w - 1]}
                      </label>
                    </td>
                    {d ? (
                      <>
                        <td className="py-1.5 pr-2">
                          <input type="time" value={d.start_time} onChange={(e) => setDay(w, { start_time: e.target.value })} className={input} aria-label={`${WEEKDAYS[w - 1]} start`} />
                        </td>
                        <td className="py-1.5 pr-2">
                          <input type="time" value={d.end_time} onChange={(e) => setDay(w, { end_time: e.target.value })} className={input} aria-label={`${WEEKDAYS[w - 1]} end`} />
                          {overnight(d) && <span className="ml-1 text-[10px] text-text-muted">next day</span>}
                        </td>
                        <td className="py-1.5">
                          <input type="number" min={0} max={600} value={d.break_minutes} onChange={(e) => setDay(w, { break_minutes: Number(e.target.value) })} className={cn(input, 'w-20')} aria-label={`${WEEKDAYS[w - 1]} break`} />
                        </td>
                      </>
                    ) : (
                      <td colSpan={3} className="py-1.5 text-xs text-text-muted">Day off</td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
          {existing && (
            <p className="text-xs text-text-muted">
              Changing the hours changes how every day on this schedule is judged, past days included, until a month is closed.
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isPending}>Cancel</Button>
          <Button onClick={submit} disabled={invalid || isPending} className="bg-accent text-white hover:bg-accent/90">
            {isPending ? 'Saving…' : 'Save schedule'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --------------------------------------------------------------------------
// Assigning a schedule to an employee
// --------------------------------------------------------------------------

function AssignDialog({ row, schedules, onClose, canEdit }: {
  row: ScheduleAssignmentRow; schedules: WorkSchedule[]; onClose: () => void; canEdit: boolean;
}) {
  const [scheduleId, setScheduleId] = useState(row.current_schedule_id ?? schedules[0]?.id);
  const [from, setFrom] = useState(toISODate(new Date()));
  const { mutate: assign, isPending } = useAssignSchedule();
  const { mutate: remove, isPending: isRemoving } = useDeleteAssignment();

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-surface border-border-brand">
        <DialogHeader>
          <DialogTitle>{row.employee_name}</DialogTitle>
          <DialogDescription>
            Follows <span className="font-semibold text-text-primary">{row.current_schedule_name ?? 'no schedule'}</span> today
            {row.follows_default && ' (the default)'}.
          </DialogDescription>
        </DialogHeader>

        {canEdit && (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="space-y-1 text-xs font-medium text-text-secondary">
              Schedule
              <select value={scheduleId} onChange={(e) => setScheduleId(Number(e.target.value))} className={cn(input, 'w-full')}>
                {schedules.map((s) => <option key={s.id} value={s.id}>{s.name}{s.is_default ? ' (default)' : ''}</option>)}
              </select>
            </label>
            <label className="space-y-1 text-xs font-medium text-text-secondary">
              From
              <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className={cn(input, 'w-full font-mono')} />
            </label>
            <p className="text-xs text-text-muted sm:col-span-2">
              Days before this date keep the schedule they had, so earlier attendance is not re-judged.
            </p>
          </div>
        )}

        {row.history.length > 0 && (
          <div>
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-text-secondary">History</p>
            <ul className="divide-y divide-border-brand rounded-md border border-border-brand text-sm">
              {row.history.map((a) => (
                <li key={a.id} className="flex items-center gap-3 px-3 py-2">
                  <span className="font-mono text-xs text-text-secondary">from {a.effective_from}</span>
                  <span className="flex-1 text-text-primary">{a.schedule_name}</span>
                  {canEdit && (
                    <Button variant="ghost" size="sm" disabled={isRemoving} onClick={() => remove(a.id)}
                      aria-label={`Remove assignment from ${a.effective_from}`} className="h-7 w-7 p-0 text-text-secondary hover:text-negative">
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Close</Button>
          {canEdit && (
            <Button
              onClick={() => scheduleId && assign({ employeeId: row.employee_id, scheduleId, effectiveFrom: from }, { onSuccess: onClose })}
              disabled={!scheduleId || !from || isPending}
              className="bg-accent text-white hover:bg-accent/90"
            >
              {isPending ? 'Saving…' : 'Assign'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --------------------------------------------------------------------------
// Tab
// --------------------------------------------------------------------------

export function SchedulesTab({ canEdit }: { canEdit: boolean }) {
  const { data: schedules, isLoading } = useSchedules();
  const { data: assignments, isLoading: loadingAssignments } = useScheduleAssignments();
  const { mutate: makeDefault, isPending: isDefaulting } = useMakeDefaultSchedule();
  const { mutate: remove, isPending: isDeleting } = useDeleteSchedule();
  const [editing, setEditing] = useState<WorkSchedule | 'new' | null>(null);
  const [assigning, setAssigning] = useState<ScheduleAssignmentRow | null>(null);
  const [tracking, setTracking] = useState<ScheduleAssignmentRow | null>(null);
  const orgDate = assignments?.find((a) => !a.tracking_overridden)?.tracked_from ?? null;

  const countFor = (id: number) => assignments?.filter((a) => a.current_schedule_id === id).length ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-text-secondary">
          Each schedule is a weekly pattern. Employees follow the default unless assigned another from a given date.
        </p>
        {canEdit && (
          <Button onClick={() => setEditing('new')} className="gap-2 bg-accent text-white hover:bg-accent/90">
            <Plus className="h-4 w-4" /> New schedule
          </Button>
        )}
      </div>

      {isLoading ? (
        <Skeleton className="h-48 w-full bg-bg-subtle" />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {schedules?.map((s) => (
            <Card key={s.id} className="bg-surface border border-border-brand rounded-card shadow-card">
              <CardHeader className="flex flex-row items-start justify-between gap-3 pb-3">
                <div>
                  <CardTitle className="flex flex-wrap items-center gap-2 text-base font-semibold font-heading text-text-primary">
                    {s.name}
                    {s.is_default && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-semibold text-accent">
                        <Star className="h-3 w-3" /> Default
                      </span>
                    )}
                    {!s.observes_holidays && (
                      <span className="rounded-full bg-sky-500/10 px-2 py-0.5 text-[10px] font-semibold text-sky-600">Works holidays</span>
                    )}
                  </CardTitle>
                  <CardDescription className="mt-1 flex items-center gap-3 text-xs">
                    <span>{s.grace_minutes} min grace</span>
                    <span className="inline-flex items-center gap-1"><Users className="h-3 w-3" /> {countFor(s.id)} today</span>
                  </CardDescription>
                </div>
                {canEdit && (
                  <div className="flex gap-1">
                    {!s.is_default && (
                      <Button variant="ghost" size="sm" disabled={isDefaulting} onClick={() => makeDefault(s.id)} className="h-8 px-2 text-xs text-text-secondary">
                        Make default
                      </Button>
                    )}
                    <Button variant="ghost" size="sm" onClick={() => setEditing(s)} aria-label={`Edit ${s.name}`} className="h-8 w-8 p-0 text-text-secondary">
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    {!s.is_default && (
                      <Button variant="ghost" size="sm" disabled={isDeleting} onClick={() => remove(s.id)} aria-label={`Delete ${s.name}`} className="h-8 w-8 p-0 text-text-secondary hover:text-negative">
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                )}
              </CardHeader>
              <CardContent>
                <WeekStrip days={s.days} />
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Card className="bg-surface border border-border-brand rounded-card shadow-card">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base font-semibold font-heading text-text-primary">
            <CalendarClock className="h-4 w-4 text-text-muted" /> Who follows which schedule
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loadingAssignments ? (
            <Skeleton className="m-4 h-24 bg-bg-subtle" />
          ) : (
            <table className="w-full text-left text-sm">
              <thead className="bg-bg-subtle/60 text-[11px] uppercase tracking-wider text-text-secondary">
                <tr>
                  <th className="px-4 py-2.5 font-semibold">Employee</th>
                  <th className="px-4 py-2.5 font-semibold">Schedule today</th>
                  <th className="px-4 py-2.5 font-semibold">Attendance tracked from</th>
                  <th className="px-4 py-2.5"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-brand">
                {assignments?.map((r) => (
                  <tr key={r.employee_id}>
                    <td className="px-4 py-2.5 text-text-primary">
                      {r.employee_name}
                      {r.status && r.status !== 'Active' && <span className="ml-2 text-xs text-text-muted">({r.status})</span>}
                    </td>
                    <td className="px-4 py-2.5 text-text-secondary">
                      {r.current_schedule_name ?? '—'}
                      {r.follows_default && <span className="ml-1 text-xs text-text-muted">(default)</span>}
                    </td>
                    <td className="px-4 py-2.5 text-text-secondary">
                      {canEdit ? (
                        <button type="button" onClick={() => setTracking(r)} className="text-left hover:text-accent hover:underline"
                          aria-label={`Change when attendance is tracked from for ${r.employee_name}`}>
                          {longDate(r.tracked_from)}
                        </button>
                      ) : longDate(r.tracked_from)}
                      <span className="ml-1 text-xs text-text-muted">{r.tracking_overridden ? '(own date)' : '(organisation)'}</span>
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <Button variant="ghost" size="sm" onClick={() => setAssigning(r)} className="h-7 px-2 text-xs text-accent">
                        {canEdit ? 'Change' : 'History'}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {editing && <ScheduleEditor schedule={editing} onClose={() => setEditing(null)} />}
      {assigning && schedules && (
        <AssignDialog row={assigning} schedules={schedules} canEdit={canEdit} onClose={() => setAssigning(null)} />
      )}
      {tracking && (
        <TrackingDialog
          current={tracking.tracked_from}
          employee={{ id: tracking.employee_id, name: tracking.employee_name, overridden: tracking.tracking_overridden }}
          orgDate={orgDate}
          onClose={() => setTracking(null)}
        />
      )}
    </div>
  );
}
