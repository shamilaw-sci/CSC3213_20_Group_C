// frontend/src/app/(dashboard)/volunteers/shifts/page.tsx
'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  VolunteersService, type Shift, type Volunteer, type Assignment,
} from '@/services/volunteers.service';
import { FinanceService } from '@/services/finance.service';
import type { Program } from '@/types';
import { useAuthStore } from '@/store/useAuthStore';
import { hasPermission } from '@/lib/permissions';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { KPICard } from '@/components/shared/kpi-card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
// No DialogTrigger: this is Base UI, not Radix, so there is no `asChild`, and
// the existing modals in components/finance drive `open` from the parent
// instead. Following that rather than inventing a second pattern.
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import {
  Loader2, Plus, MapPin, Users, Clock, AlertTriangle, Trash2,
} from 'lucide-react';
import { cn, getErrorMessage } from '@/lib/utils';
import { todayISO } from '@/lib/inventory';

/** Days until a shift, from today. Negative means it is in the past. */
function daysUntil(shiftDate: string): number {
  const [y, m, d] = shiftDate.split('-').map(Number);
  const target = new Date(y, m - 1, d);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}

function formatDate(shiftDate: string): string {
  const [y, m, d] = shiftDate.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-GB', {
    weekday: 'short', day: 'numeric', month: 'short',
  });
}

/**
 * "6 assigned: 4 accepted, 1 declined, 1 awaiting response".
 *
 * This line is the main operational point of the whole feature, so it is
 * rendered as prose rather than as three numbers a coordinator has to
 * interpret. The urgency treatment keys off the shift date: an unanswered
 * assignment three weeks out is normal, the same one tomorrow is a problem.
 */
function ConfirmationLine({ shift }: { shift: Shift }) {
  const c = shift.confirmation;
  const days = daysUntil(shift.shift_date);
  const short = c.accepted < c.needed;
  const urgent = short && days <= 3 && days >= 0;

  if (c.assigned === 0) {
    return (
      <span className={cn('text-sm', days <= 3 && days >= 0 ? 'text-red-600 font-medium' : 'text-text-muted')}>
        Nobody assigned yet — {c.needed} needed
      </span>
    );
  }

  return (
    <div className="space-y-0.5">
      <span className="text-sm text-text-secondary">
        <strong className="text-text-primary">{c.assigned} assigned:</strong>{' '}
        {c.accepted} accepted
        {c.declined > 0 && `, ${c.declined} declined`}
        {c.awaiting > 0 && `, ${c.awaiting} awaiting response`}
      </span>
      {(urgent || (c.awaiting > 0 && days <= 3 && days >= 0)) && (
        <div className="flex items-center gap-1 text-xs font-medium text-red-600">
          <AlertTriangle className="w-3 h-3" />
          {days === 0 ? 'Today' : days === 1 ? 'Tomorrow' : `In ${days} days`}
          {short && ` — ${c.needed - c.accepted} short of ${c.needed}`}
          {!short && c.awaiting > 0 && ` — ${c.awaiting} still unanswered`}
        </div>
      )}
    </div>
  );
}

/** Active programmes are the only ones a new shift can be for. */
function isActiveProgram(p: Program): boolean {
  return (p.status || '').trim().toLowerCase() === 'active';
}

/**
 * Assign several volunteers to one shift. One request per volunteer rather
 * than a bulk endpoint, so each still gets its own audit entry and its own
 * notification email, exactly as a single assignment does.
 */
async function assignMany(shiftId: string, volunteerIds: string[]) {
  const results = await Promise.allSettled(
    volunteerIds.map((id) => VolunteersService.assign({ volunteer_id: id, shift_id: shiftId }))
  );
  const failed = results.filter((r): r is PromiseRejectedResult => r.status === 'rejected');
  // The API warns (but still assigns) when a shift goes over the number needed.
  const warnings = results
    .filter((r): r is PromiseFulfilledResult<Assignment> => r.status === 'fulfilled')
    .map((r) => r.value.warning)
    .filter((w): w is string => !!w);
  return {
    assigned: results.length - failed.length,
    failed: failed.length,
    firstError: failed[0]?.reason as unknown,
    warning: warnings[warnings.length - 1],
  };
}

function toggleIn(set: Set<string>, id: string): Set<string> {
  const next = new Set(set);
  if (next.has(id)) next.delete(id); else next.add(id);
  return next;
}

/**
 * Checklist of approved volunteers. Volunteers already on the shift are shown
 * ticked and locked, so the coordinator sees the whole approved list in one
 * place rather than only the people who are left.
 */
function VolunteerChecklist({
  volunteers, selected, onToggle, lockedIds, emptyText,
}: {
  volunteers: Volunteer[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  lockedIds?: Set<string>;
  emptyText: string;
}) {
  const [filter, setFilter] = useState('');

  if (volunteers.length === 0) {
    return <p className="text-xs text-text-muted">{emptyText}</p>;
  }

  const needle = filter.trim().toLowerCase();
  const shown = volunteers.filter((v) =>
    `${v.full_name} ${v.email}`.toLowerCase().includes(needle)
  );

  return (
    <div className="space-y-2">
      {volunteers.length > 6 && (
        <Input
          placeholder="Search volunteers..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      )}
      <ul className="max-h-56 overflow-y-auto rounded-lg border border-border-brand/60 divide-y divide-border-brand/40">
        {shown.map((v) => {
          const locked = lockedIds?.has(v.id) ?? false;
          return (
            <li key={v.id}>
              <label
                className={cn(
                  'flex items-center gap-2.5 px-3 py-2 text-sm',
                  locked ? 'opacity-60 cursor-default' : 'cursor-pointer hover:bg-bg-subtle'
                )}
              >
                <input
                  type="checkbox"
                  checked={locked || selected.has(v.id)}
                  disabled={locked}
                  onChange={() => onToggle(v.id)}
                  className="accent-[var(--color-accent)]"
                />
                <span className="flex-1 min-w-0">
                  <span className="block truncate text-text-primary">{v.full_name}</span>
                  <span className="block truncate text-xs text-text-muted">{v.email}</span>
                </span>
                {locked && <span className="text-[11px] text-text-muted">Assigned</span>}
              </label>
            </li>
          );
        })}
        {shown.length === 0 && (
          <li className="px-3 py-2 text-xs text-text-muted">No volunteers match.</li>
        )}
      </ul>
    </div>
  );
}

const EMPTY_FORM = {
  title: '', description: '', location: '',
  shift_date: '', start_time: '09:00', end_time: '13:00',
  volunteers_needed: 1,
};

function NewShiftDialog({
  volunteers, onCreated,
}: { volunteers: Volunteer[]; onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Same query key as the Programs page, so the list is shared and cached.
  const { data: programs = [], isLoading: programsLoading } = useQuery({
    queryKey: ['programs'],
    queryFn: FinanceService.getPrograms,
    enabled: open,
  });
  const activePrograms = programs.filter(isActiveProgram);

  const create = useMutation({
    mutationFn: async () => {
      // Link the shift to its programme by id, so renaming the programme
      // later does not lose its volunteers.
      const program = activePrograms.find((p) => p.program_name === form.title);
      const shift = await VolunteersService.createShift({
        ...form,
        description: form.description || undefined,
        location: form.location || undefined,
        program_id: program?.id,
      });
      // Assigning at creation is optional. The shift exists either way, and
      // anyone left out can still be added later through Manage.
      if (selected.size === 0) {
        return { assigned: 0, failed: 0, firstError: undefined, warning: undefined, shiftWarning: shift.warning };
      }
      return { ...(await assignMany(shift.id, [...selected])), shiftWarning: shift.warning };
    },
    onSuccess: ({ assigned, failed, firstError, warning, shiftWarning }) => {
      if (shiftWarning) toast.warning(shiftWarning);
      if (warning) toast.warning(warning);
      if (failed > 0) {
        toast.warning(
          `Shift created, but ${failed} volunteer${failed === 1 ? '' : 's'} could not be assigned` +
          (firstError ? ` (${getErrorMessage(firstError)})` : '') +
          '. You can add them through Manage.'
        );
      } else if (assigned > 0) {
        toast.success(`Shift created and ${assigned} volunteer${assigned === 1 ? '' : 's'} assigned.`);
      } else {
        toast.success('Shift created.');
      }
      setOpen(false);
      setForm(EMPTY_FORM);
      setSelected(new Set());
      onCreated();
    },
    onError: (err) => toast.error(getErrorMessage(err) || "Couldn't create the shift."),
  });

  const valid = form.title.trim() && form.shift_date && form.shift_date >= todayISO()
    && form.end_time > form.start_time;

  return (
    <>
      <Button className="gap-1.5" onClick={() => setOpen(true)}>
        <Plus className="w-4 h-4" /> New shift
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent>
        <DialogHeader><DialogTitle>New shift</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <label className="text-xs text-text-secondary">Programme</label>
            {/* The shift's title is the programme's name, and the shift is
                also linked to the programme by id when it is saved. The value
                is the name itself, so Base UI's Select.Value (which renders the
                raw value, not the label) still shows the right text. */}
            <Select
              value={form.title || null}
              onValueChange={(v) => { if (typeof v === 'string') setForm({ ...form, title: v }); }}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder={
                  programsLoading ? 'Loading programmes...'
                  : activePrograms.length ? 'Select an active programme'
                  : 'No active programmes'
                } />
              </SelectTrigger>
              <SelectContent>
                {activePrograms.map((p) => (
                  <SelectItem key={p.id} value={p.program_name}>{p.program_name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Input
            placeholder="Location (optional)"
            value={form.location}
            onChange={(e) => setForm({ ...form, location: e.target.value })}
          />
          <textarea
            placeholder="Anything volunteers should know (optional)"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            rows={2}
            className="w-full rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          />
          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1">
              <label className="text-xs text-text-secondary">Date</label>
              <Input type="date" value={form.shift_date} min={todayISO()}
                onChange={(e) => setForm({ ...form, shift_date: e.target.value })} />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-text-secondary">From</label>
              <Input type="time" value={form.start_time}
                onChange={(e) => setForm({ ...form, start_time: e.target.value })} />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-text-secondary">To</label>
              <Input type="time" value={form.end_time}
                onChange={(e) => setForm({ ...form, end_time: e.target.value })} />
            </div>
          </div>
          {form.start_time && form.end_time && form.end_time <= form.start_time && (
            <p className="text-xs text-red-600">A shift must end after it starts.</p>
          )}
          {form.shift_date && form.shift_date < todayISO() && (
            <p className="text-xs text-red-600">A shift can&apos;t be in the past.</p>
          )}
          <div className="space-y-1">
            <label className="text-xs text-text-secondary">Volunteers needed</label>
            <Input type="number" min={1} max={200} value={form.volunteers_needed}
              onChange={(e) => setForm({ ...form, volunteers_needed: Number(e.target.value) })} />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-text-secondary">
              Assign volunteers{' '}
              <span className="text-text-muted">
                (optional{selected.size ? ` · ${selected.size} selected` : ''})
              </span>
            </label>
            <VolunteerChecklist
              volunteers={volunteers}
              selected={selected}
              onToggle={(id) => setSelected((s) => toggleIn(s, id))}
              emptyText="No approved volunteers yet. You can assign people later through Manage."
            />
          </div>
          <Button
            className="w-full"
            disabled={!valid || create.isPending}
            onClick={() => create.mutate()}
          >
            {create.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Create shift'}
          </Button>
        </div>
      </DialogContent>
      </Dialog>
    </>
  );
}

function AssignPanel({
  shift, volunteers, canAssign,
}: { shift: Shift; volunteers: Volunteer[]; canAssign: boolean }) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const { data: assignments = [] } = useQuery({
    queryKey: ['volunteer-assignments', shift.id],
    queryFn: () => VolunteersService.listAssignments({ shift_id: shift.id }),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['volunteer-assignments', shift.id] });
    queryClient.invalidateQueries({ queryKey: ['volunteer-shifts'] });
  };

  const assign = useMutation({
    mutationFn: (volunteerIds: string[]) => assignMany(shift.id, volunteerIds),
    onSuccess: ({ assigned, failed, firstError, warning }) => {
      if (warning) toast.warning(warning);
      if (failed > 0) {
        toast.error(
          `${failed} could not be assigned` +
          (firstError ? `: ${getErrorMessage(firstError)}` : '.') +
          (assigned ? ` ${assigned} assigned.` : '')
        );
      } else {
        toast.success(
          `${assigned} volunteer${assigned === 1 ? '' : 's'} assigned — notification sent if email is configured.`
        );
      }
      setSelected(new Set());
      refresh();
    },
    onError: (err) => toast.error(getErrorMessage(err) || "Couldn't assign those volunteers."),
  });

  const unassign = useMutation({
    mutationFn: (id: string) => VolunteersService.unassign(id),
    onSuccess: () => { toast.success('Assignment removed. They are emailed if email is configured.'); refresh(); },
    onError: (err) => toast.error(getErrorMessage(err) || "Couldn't remove that assignment."),
  });

  const byId = new Map(volunteers.map((v) => [v.id, v]));
  const assignedIds = new Set(assignments.map((a) => a.volunteer_id));

  const badge = (a: Assignment) =>
    a.response === 'accepted' ? <Badge className="bg-emerald-600 text-white">Accepted</Badge>
    : a.response === 'declined' ? <Badge variant="outline">Declined</Badge>
    : <Badge variant="outline" className="text-amber-600 border-amber-600/40 gap-1">
        <Clock className="w-3 h-3" /> Awaiting
      </Badge>;

  return (
    <div className="space-y-3 pt-3 border-t border-border-brand/50">
      {assignments.length > 0 ? (
        <ul className="space-y-1.5">
          {assignments.map((a) => (
            <li key={a.id} className="flex items-center gap-2 text-sm">
              <span className="flex-1 truncate">
                {byId.get(a.volunteer_id)?.full_name ?? 'Unknown volunteer'}
              </span>
              {a.decline_reason && (
                <span className="text-xs text-text-muted italic truncate max-w-[180px]">
                  “{a.decline_reason}”
                </span>
              )}
              {badge(a)}
              {canAssign && (
                <Button
                  size="sm" variant="ghost"
                  aria-label="Remove assignment"
                  disabled={unassign.isPending}
                  onClick={() => unassign.mutate(a.id)}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-text-muted">Nobody is assigned to this shift yet.</p>
      )}

      {canAssign && !shift.is_cancelled && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-text-secondary uppercase tracking-wide">
            Approved volunteers
          </p>
          <VolunteerChecklist
            volunteers={volunteers}
            selected={selected}
            onToggle={(id) => setSelected((s) => toggleIn(s, id))}
            lockedIds={assignedIds}
            emptyText="No approved volunteers yet. Approve applications first."
          />
          <Button
            disabled={selected.size === 0 || assign.isPending}
            onClick={() => assign.mutate([...selected])}
          >
            {assign.isPending
              ? <Loader2 className="w-4 h-4 animate-spin" />
              : `Assign selected${selected.size ? ` (${selected.size})` : ''}`}
          </Button>
        </div>
      )}
    </div>
  );
}

export default function VolunteerShiftsPage() {
  const { user } = useAuthStore();
  const canAssign = hasPermission(user?.role || '', 'volunteers:assign');
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState<string | null>(null);
  const [includePast, setIncludePast] = useState(false);

  const { data: shifts = [], isLoading } = useQuery({
    queryKey: ['volunteer-shifts', includePast],
    queryFn: () => VolunteersService.listShifts(includePast),
  });

  // Only approved volunteers can be assigned; the API rejects the rest, so
  // offering them in the picker would just produce a 400.
  const { data: volunteers = [] } = useQuery({
    queryKey: ['volunteers', 'approved'],
    queryFn: () => VolunteersService.list('approved'),
    enabled: canAssign,
  });

  const cancel = useMutation({
    mutationFn: (id: string) => VolunteersService.updateShift(id, { is_cancelled: true }),
    onSuccess: () => {
      toast.success('Shift cancelled. Its volunteers are emailed if email is configured.');
      queryClient.invalidateQueries({ queryKey: ['volunteer-shifts'] });
    },
    onError: (err) => toast.error(getErrorMessage(err) || "Couldn't cancel the shift."),
  });

  const active = shifts.filter((s) => !s.is_cancelled);
  const upcoming = active.filter((s) => daysUntil(s.shift_date) >= 0);
  const understaffed = upcoming.filter((s) => s.confirmation.accepted < s.confirmation.needed).length;
  const accepted = upcoming.reduce((n, s) => n + s.confirmation.accepted, 0);
  const needed = upcoming.reduce((n, s) => n + s.confirmation.needed, 0);
  const awaiting = upcoming.reduce((n, s) => n + s.confirmation.awaiting, 0);
  const kpi = (v: number | string) => (isLoading ? '—' : v);

  return (
    <div className="space-y-8 pb-12">
      {/* Header, in the finance pages' shape */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold font-heading tracking-tight mb-2 text-text-primary">Shifts</h1>
          <p className="text-text-secondary text-sm">
            Create and manage volunteer shifts, assign volunteers, and track shift schedules across all programs.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            className="border-border-brand text-text-primary"
            onClick={() => setIncludePast(!includePast)}
          >
            {includePast ? 'Upcoming only' : 'Include past'}
          </Button>
          {canAssign && (
            <NewShiftDialog
              volunteers={volunteers}
              onCreated={() => queryClient.invalidateQueries({ queryKey: ['volunteer-shifts'] })}
            />
          )}
        </div>
      </div>

      {/* KPI strip. Counts cover upcoming, non-cancelled shifts only, so
          "Include past" changes the list below but not these numbers. */}
      <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        <KPICard title="Upcoming Shifts" value={kpi(upcoming.length)} />
        <KPICard
          title="Understaffed"
          value={kpi(understaffed)}
          className={understaffed > 0 ? 'border-red-500/40 dark:border-red-500/40' : undefined}
        />
        <KPICard title="Volunteers Confirmed" value={kpi(`${accepted}/${needed}`)} />
        <KPICard title="Awaiting Response" value={kpi(awaiting)} />
      </div>

      <Card className="bg-surface border border-border-brand rounded-card shadow-card p-5">
        <CardHeader className="p-0 pb-4">
          <CardTitle className="text-base font-semibold font-heading text-text-primary">
            {includePast ? 'All Shifts' : 'Upcoming Shifts'}
          </CardTitle>
          <CardDescription className="text-text-secondary text-xs mt-1">
            Who is coming, who has answered, and who still needs chasing.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => <Skeleton key={i} className="h-20 w-full bg-bg-subtle" />)}
            </div>
          ) : shifts.length === 0 ? (
            <p className="py-12 text-center text-sm text-text-muted">
              No {includePast ? '' : 'upcoming '}shifts.
            </p>
          ) : (
            <div className="space-y-3">
              {shifts.map((shift) => {
                const c = shift.confirmation;
                const pct = c.needed ? Math.min(100, Math.round((c.accepted / c.needed) * 100)) : 0;
                const [, m, d] = shift.shift_date.split('-').map(Number);
                const month = new Date(2000, m - 1, 1).toLocaleDateString('en-GB', { month: 'short' });
                return (
                  <div
                    key={shift.id}
                    className={cn(
                      'rounded-lg border border-border-brand bg-bg-subtle/40 p-4 space-y-3 transition-colors hover:border-accent/40',
                      shift.is_cancelled && 'opacity-60'
                    )}
                  >
                    <div className="flex flex-col sm:flex-row sm:items-start gap-4">
                      {/* Date block */}
                      <div className="flex sm:flex-col items-center justify-center gap-1.5 sm:gap-0 sm:w-14 shrink-0 self-start rounded-lg border border-border-brand bg-surface px-3 py-1.5 sm:py-2">
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-accent">{month}</span>
                        <span className="text-xl font-bold font-mono text-text-primary leading-none sm:mt-0.5">{d}</span>
                      </div>

                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h2 className="font-semibold font-heading text-text-primary">{shift.title}</h2>
                          {shift.is_cancelled && <Badge variant="outline">Cancelled</Badge>}
                        </div>
                        <div className="flex flex-wrap items-center gap-x-4 gap-y-0.5 text-xs text-text-secondary">
                          <span className="flex items-center gap-1">
                            <Clock className="w-3.5 h-3.5" />
                            {formatDate(shift.shift_date)} · {shift.start_time.slice(0, 5)}–{shift.end_time.slice(0, 5)}
                          </span>
                          {shift.location && (
                            <span className="flex items-center gap-1">
                              <MapPin className="w-3.5 h-3.5" /> {shift.location}
                            </span>
                          )}
                        </div>
                        <div className="pt-1"><ConfirmationLine shift={shift} /></div>
                      </div>

                      <div className="flex sm:flex-col items-center sm:items-end justify-between gap-3 shrink-0 sm:w-44">
                        <div className="w-28 sm:w-full space-y-1">
                          <div className="flex items-center justify-between text-xs">
                            <span className="flex items-center gap-1 text-text-secondary">
                              <Users className="w-3.5 h-3.5" /> Confirmed
                            </span>
                            <span className="font-mono font-semibold text-text-primary">{c.accepted}/{c.needed}</span>
                          </div>
                          <div className="h-1.5 w-full rounded-full bg-border-brand/60 overflow-hidden">
                            <div
                              className={cn('h-full rounded-full', pct >= 100 ? 'bg-emerald-500' : 'bg-accent')}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <Button
                            size="sm" variant="outline"
                            className="border-border-brand"
                            onClick={() => setExpanded(expanded === shift.id ? null : shift.id)}
                          >
                            {expanded === shift.id ? 'Hide' : 'Manage'}
                          </Button>
                          {canAssign && !shift.is_cancelled && (
                            <Button
                              size="sm" variant="ghost"
                              className="text-text-secondary hover:text-red-500"
                              disabled={cancel.isPending}
                              onClick={() => cancel.mutate(shift.id)}
                            >
                              Cancel
                            </Button>
                          )}
                        </div>
                      </div>
                    </div>

                    {expanded === shift.id && (
                      <AssignPanel shift={shift} volunteers={volunteers} canAssign={canAssign} />
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
