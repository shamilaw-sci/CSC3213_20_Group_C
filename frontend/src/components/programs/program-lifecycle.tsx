'use client';

// The three program lifecycle pages (Upcoming / Active / Completed) share this
// one component. Each stage decides its own KPIs, card face and card action;
// clicking anywhere else on a card opens the full details at /programs/[id].

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  CalendarClock, PlayCircle, CheckCircle2, Plus, Loader2, Search, Dog, MapPin, Pencil,
} from 'lucide-react';
import { toast } from 'sonner';

import { ProgramService, type ProgramStage, type ProgramSummary } from '@/services/program.service';
import { useAuthStore } from '@/store/useAuthStore';
import { hasPermission } from '@/lib/permissions';
import { formatLKR } from '@/lib/formatters';
import { cn, getErrorMessage } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Card } from '@/components/ui/card';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { KPICard } from '@/components/shared/kpi-card';
import ProtectedRoute from '@/components/layout/protected-route';

// ---------------------------------------------------------------------------
// Shared helpers (also used by the details page)
// ---------------------------------------------------------------------------

export const STAGE_PATH: Record<ProgramStage, string> = {
  Upcoming: '/programs/upcoming',
  Active: '/programs/active',
  Completed: '/programs/completed',
};

export const STAGE_BADGE: Record<ProgramStage, string> = {
  Upcoming: 'bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/30',
  Active: 'bg-green-500/10 text-positive border-green-500/30',
  Completed: 'bg-bg-subtle text-text-secondary border-border-brand',
};

export function asStage(status?: string | null): ProgramStage {
  const s = (status || '').trim().toLowerCase();
  if (s === 'upcoming') return 'Upcoming';
  if (s === 'completed') return 'Completed';
  return 'Active';
}

/** "7 Nov 2026" from a wall-clock YYYY-MM-DD, without a timezone shift. */
export function formatDay(day?: string | null): string {
  if (!day) return '—';
  const [y, m, d] = day.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-GB', {
    day: 'numeric', month: 'short', year: 'numeric',
  });
}

function toDate(day: string): Date {
  const [y, m, d] = day.split('-').map(Number);
  return new Date(y, m - 1, d);
}

/** Whole days from `from` to `to` (or today). */
export function daysBetween(from: string, to?: string | null): number {
  const end = to ? toDate(to) : new Date();
  end.setHours(0, 0, 0, 0);
  return Math.round((end.getTime() - toDate(from).getTime()) / 86_400_000);
}

// ---------------------------------------------------------------------------
// Start / complete, with a confirm step
// ---------------------------------------------------------------------------

const TRANSITION = {
  Upcoming: {
    label: 'Start Program',
    icon: PlayCircle,
    title: 'Start this program?',
    body: 'It moves to Active Programs and its start date is set to today (unless it already started earlier). This cannot be undone.',
    done: 'Program started — it is now under Active Programs.',
    run: (id: number) => ProgramService.start(id),
  },
  Active: {
    label: 'Mark as Completed',
    icon: CheckCircle2,
    title: 'Mark this program as completed?',
    body: 'Its end date is set to today and it moves to Completed Programs. Its team can no longer change. This cannot be undone.',
    done: 'Program completed — it is now under Completed Programs.',
    run: (id: number, animals: number) => ProgramService.complete(id, animals),
  },
} as const;

/** The forward move for a program in `stage`. Renders nothing when Completed. */
export function TransitionButton({
  program, stage, size = 'sm', className, onDone,
}: {
  program: { id: number; program_name: string };
  stage: ProgramStage;
  size?: 'sm' | 'default';
  className?: string;
  onDone?: () => void;
}) {
  const [open, setOpen] = useState(false);
  // Completing asks for the final animal count. Kept as text so the field can
  // be empty; only a whole number of 0 or more enables the confirm button.
  const [animals, setAnimals] = useState('');
  const queryClient = useQueryClient();
  const config = stage === 'Completed' ? null : TRANSITION[stage];
  const needsCount = stage === 'Active';
  const countValid = /^\d+$/.test(animals.trim());

  const mutation = useMutation({
    mutationFn: () => config!.run(program.id, Number(animals.trim())),
    onSuccess: () => {
      toast.success(config!.done);
      setOpen(false);
      setAnimals('');
      queryClient.invalidateQueries({ queryKey: ['programs-stage'] });
      queryClient.invalidateQueries({ queryKey: ['programs'] });
      queryClient.invalidateQueries({ queryKey: ['program', program.id] });
      onDone?.();
    },
    onError: (err) => toast.error(getErrorMessage(err) || 'Could not change the program status.'),
  });

  if (!config) return null;
  const Icon = config.icon;

  // The wrapper stops clicks and key presses reaching the program card behind
  // it. React bubbles events from a portal through the component tree, so
  // without this a click anywhere in the confirm dialog (even its backdrop)
  // would also open the program's details.
  return (
    <span
      className="contents"
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
    >
      <Button
        size={size}
        className={cn('gap-1.5 bg-accent text-white hover:bg-accent/90 font-semibold', className)}
        onClick={() => setOpen(true)}
      >
        <Icon className="h-4 w-4" /> {config.label}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{config.title}</DialogTitle>
            <DialogDescription>
              <strong className="text-text-primary">{program.program_name}</strong> — {config.body}
            </DialogDescription>
          </DialogHeader>
          {needsCount && (
            <div className="space-y-1">
              <label htmlFor={`animals-${program.id}`} className="text-sm font-medium text-text-primary">
                How many animals were treated in this programme?
              </label>
              <Input
                id={`animals-${program.id}`}
                type="number"
                inputMode="numeric"
                min={0}
                step={1}
                value={animals}
                onChange={(e) => setAnimals(e.target.value)}
                placeholder="e.g. 120"
                autoFocus
              />
              {animals.trim() !== '' && !countValid && (
                <p className="text-xs text-negative">Enter a whole number, 0 or more.</p>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={mutation.isPending}>
              Cancel
            </Button>
            <Button
              className="bg-accent text-white hover:bg-accent/90"
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending || (needsCount && !countValid)}
            >
              {mutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : config.label}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Initialize Program (Upcoming page only)
// ---------------------------------------------------------------------------

function InitializeProgramDialog() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [location, setLocation] = useState('');
  const [startDate, setStartDate] = useState('');
  const queryClient = useQueryClient();

  const create = useMutation({
    mutationFn: () => ProgramService.create({
      program_name: name.trim(),
      location: location.trim(),
      start_date: startDate || undefined,
    }),
    onSuccess: () => {
      toast.success('Program initialized — it is listed under Upcoming Programs.');
      setOpen(false);
      setName('');
      setLocation('');
      setStartDate('');
      queryClient.invalidateQueries({ queryKey: ['programs-stage'] });
      queryClient.invalidateQueries({ queryKey: ['programs'] });
    },
    onError: (err) => toast.error(getErrorMessage(err) || 'Failed to initialize program'),
  });

  return (
    <>
      <Button onClick={() => setOpen(true)} className="bg-accent text-white hover:bg-accent/90 gap-2 font-semibold">
        <Plus className="h-4 w-4" /> Initialize Program
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Initialize Program</DialogTitle>
            <DialogDescription>
              New programs start as Upcoming. Start it from its card when it begins.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <label className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
                Program name
              </label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Kandy Sterilization Drive"
                maxLength={255}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
                Location
              </label>
              <Input
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="e.g. Peradeniya, Kandy"
                maxLength={200}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
                Start date <span className="normal-case font-normal text-text-muted">(optional)</span>
              </label>
              <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={create.isPending}>
              Cancel
            </Button>
            <Button
              className="bg-accent text-white hover:bg-accent/90"
              disabled={!name.trim() || !location.trim() || create.isPending}
              onClick={() => create.mutate()}
            >
              {create.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Initialize'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const PAGE: Record<ProgramStage, { title: string; description: string; empty: string }> = {
  Upcoming: {
    title: 'Upcoming Programs',
    description: 'Plan new programs, build their teams, and start them when they begin.',
    empty: 'No upcoming programs. Use Initialize Program to plan one.',
  },
  Active: {
    title: 'Active Programs',
    description: 'Track running programs: animals treated, costs, teams and volunteers.',
    empty: 'No active programs. Start one from Upcoming Programs.',
  },
  Completed: {
    title: 'Completed Programs',
    description: 'Finished programs with their final dates, costs and results.',
    empty: 'No completed programs yet.',
  },
};

function Kpis({ stage, programs, loading }: { stage: ProgramStage; programs: ProgramSummary[]; loading: boolean }) {
  const v = (x: string | number) => (loading ? '—' : x);
  const sum = (f: (p: ProgramSummary) => number) => programs.reduce((n, p) => n + f(p), 0);
  const animals = sum((p) => p.total_animals_treated || 0);
  const cost = sum((p) => p.total_cost || 0);

  if (stage === 'Upcoming') {
    const scheduled = programs.filter((p) => p.start_date).map((p) => p.start_date!).sort();
    const today = new Date().toISOString().slice(0, 10);
    const next = scheduled.find((d) => d >= today);
    return (
      <>
        <KPICard title="Upcoming Programs" value={v(programs.length)} />
        <KPICard title="Scheduled" value={v(`${scheduled.length}/${programs.length}`)} />
        <KPICard title="Team Members" value={v(sum((p) => p.team_count))} />
        <KPICard title="Next Start" value={v(next ? formatDay(next) : '—')} />
      </>
    );
  }
  if (stage === 'Active') {
    return (
      <>
        <KPICard title="Active Programs" value={v(programs.length)} />
        <KPICard title="Animals Treated" value={v(animals.toLocaleString())} />
        <KPICard title="Total Cost" value={v(formatLKR(cost))} />
        <KPICard title="Volunteers Engaged" value={v(sum((p) => p.volunteer_count))} />
      </>
    );
  }
  const profit = sum((p) => p.profit || 0);
  return (
    <>
      <KPICard title="Completed Programs" value={v(programs.length)} />
      <KPICard title="Animals Treated" value={v(animals.toLocaleString())} />
      <KPICard title="Total Cost" value={v(formatLKR(cost))} />
      <KPICard
        title="Net Profit"
        value={v(formatLKR(profit))}
        className={!loading && profit < 0 ? 'border-red-500/40 dark:border-red-500/40' : undefined}
      />
    </>
  );
}

/** A small location line with a map pin; muted when none is recorded. */
export function ProgramLocation({ location, className }: { location?: string | null; className?: string }) {
  return (
    <p className={cn('flex items-center gap-1.5 text-sm min-w-0', className)}>
      <MapPin className="h-4 w-4 shrink-0 text-accent" />
      {location
        ? <span className="truncate text-text-secondary">{location}</span>
        : <span className="italic text-text-muted">Location not set</span>}
    </p>
  );
}

/** Location with an Edit / Set button that opens a small dialog. */
export function EditableProgramLocation({
  program, canEdit,
}: { program: { id: number; location?: string | null }; canEdit: boolean }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState('');
  const queryClient = useQueryClient();

  const save = useMutation({
    mutationFn: () => ProgramService.updateLocation(program.id, value.trim()),
    onSuccess: () => {
      toast.success('Location saved.');
      setOpen(false);
      queryClient.invalidateQueries({ queryKey: ['program', program.id] });
      queryClient.invalidateQueries({ queryKey: ['programs-stage'] });
    },
    onError: (err) => toast.error(getErrorMessage(err) || 'Could not save the location.'),
  });

  return (
    <div className="flex items-center gap-2 min-w-0">
      <ProgramLocation location={program.location} />
      {canEdit && (
        <Button
          variant="ghost" size="sm"
          className="h-7 px-2 text-xs text-accent hover:text-accent gap-1"
          onClick={() => { setValue(program.location ?? ''); setOpen(true); }}
        >
          <Pencil className="h-3 w-3" /> {program.location ? 'Edit' : 'Set location'}
        </Button>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Program location</DialogTitle>
            <DialogDescription>Where this program takes place.</DialogDescription>
          </DialogHeader>
          <Input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="e.g. Peradeniya, Kandy"
            maxLength={200}
            autoFocus
            onKeyDown={(e) => { if (e.key === 'Enter' && value.trim()) save.mutate(); }}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={save.isPending}>
              Cancel
            </Button>
            <Button
              className="bg-accent text-white hover:bg-accent/90"
              disabled={!value.trim() || save.isPending}
              onClick={() => save.mutate()}
            >
              {save.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** Edit button + dialog for a completed program's animal count. */
export function EditAnimalsTreatedButton({
  program,
}: { program: { id: number; total_animals_treated?: number | null } }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState('');
  const queryClient = useQueryClient();
  const valid = /^\d+$/.test(value.trim());

  const save = useMutation({
    mutationFn: () => ProgramService.updateAnimalsTreated(program.id, Number(value.trim())),
    onSuccess: () => {
      toast.success('Animals treated saved.');
      setOpen(false);
      queryClient.invalidateQueries({ queryKey: ['program', program.id] });
      queryClient.invalidateQueries({ queryKey: ['programs-stage'] });
    },
    onError: (err) => toast.error(getErrorMessage(err) || 'Could not save the animal count.'),
  });

  return (
    <>
      <Button
        variant="ghost" size="sm"
        className="h-7 px-2 text-xs text-accent hover:text-accent gap-1"
        onClick={() => { setValue(String(program.total_animals_treated ?? '')); setOpen(true); }}
      >
        <Pencil className="h-3 w-3" /> Edit
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Animals treated</DialogTitle>
            <DialogDescription>How many animals were treated in this programme?</DialogDescription>
          </DialogHeader>
          <Input
            type="number" inputMode="numeric" min={0} step={1}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="e.g. 120"
            autoFocus
            onKeyDown={(e) => { if (e.key === 'Enter' && valid) save.mutate(); }}
          />
          {value.trim() !== '' && !valid && (
            <p className="text-xs text-negative">Enter a whole number, 0 or more.</p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={save.isPending}>
              Cancel
            </Button>
            <Button
              className="bg-accent text-white hover:bg-accent/90"
              disabled={!valid || save.isPending}
              onClick={() => save.mutate()}
            >
              {save.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

// Thin status-coloured strip down the card's left edge.
const STAGE_ACCENT: Record<ProgramStage, string> = {
  Upcoming: 'bg-sky-500',
  Active: 'bg-green-500',
  Completed: 'bg-slate-400 dark:bg-slate-500',
};

const STAGE_ICON: Record<ProgramStage, typeof CalendarClock> = {
  Upcoming: CalendarClock,
  Active: Dog,
  Completed: CheckCircle2,
};

export function ProgramLifecyclePage({ stage }: { stage: ProgramStage }) {
  const router = useRouter();
  const { user } = useAuthStore();
  const canManage = hasPermission(user?.role || '', 'programs:manage');
  const [search, setSearch] = useState('');
  const page = PAGE[stage];

  const { data: programs = [], isLoading, isError } = useQuery({
    queryKey: ['programs-stage', stage],
    queryFn: () => ProgramService.listByStage(stage),
  });

  const needle = search.trim().toLowerCase();
  const shown = programs.filter((p) =>
    `${p.program_name} ${p.location ?? ''}`.toLowerCase().includes(needle)
  );

  return (
    <ProtectedRoute requiredPermission="programs:read">
      <div className="space-y-8 pb-12">
        {/* Header, in the finance pages' shape */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold font-heading tracking-tight mb-2 text-text-primary">{page.title}</h1>
            <p className="text-text-secondary text-sm">{page.description}</p>
          </div>
          {stage === 'Upcoming' && canManage && <InitializeProgramDialog />}
        </div>

        <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
          <Kpis stage={stage} programs={programs} loading={isLoading} />
        </div>

        <div className="relative max-w-md">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name or location..."
            aria-label="Search programs"
            className="pl-9 h-10 bg-surface border-border-brand"
          />
        </div>

        {isError ? (
          <Card className="bg-surface border border-border-brand rounded-card shadow-card p-8 text-center text-sm text-negative">
            Could not load programs. Please refresh and try again.
          </Card>
        ) : isLoading ? (
          <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-36 w-full rounded-card bg-bg-subtle" />)}
          </div>
        ) : shown.length === 0 ? (
          <Card className="bg-surface border border-border-brand rounded-card shadow-card p-12 text-center text-sm text-text-muted">
            {search ? 'No programs match your search.' : page.empty}
          </Card>
        ) : (
          <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {shown.map((p) => {
              const Icon = STAGE_ICON[stage];
              return (
              <Card
                key={p.id}
                role="link"
                tabIndex={0}
                aria-label={`Open ${p.program_name}`}
                onClick={() => router.push(`/programs/${p.id}`)}
                onKeyDown={(e) => {
                  if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) {
                    e.preventDefault();
                    router.push(`/programs/${p.id}`);
                  }
                }}
                className="group relative overflow-hidden cursor-pointer bg-surface border border-border-brand rounded-card shadow-card p-5 pl-6 flex flex-col gap-4 transition-all hover:shadow-md hover:border-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
              >
                <span aria-hidden className={cn('absolute inset-y-0 left-0 w-1', STAGE_ACCENT[stage])} />

                <div className="flex items-start gap-3">
                  <div className="h-10 w-10 shrink-0 rounded-lg bg-accent/10 text-accent flex items-center justify-center">
                    <Icon className="h-5 w-5" />
                  </div>
                  <div className="min-w-0 flex-1 space-y-1">
                    <h2 className="font-semibold font-heading text-base text-text-primary truncate group-hover:text-accent transition-colors">
                      {p.program_name}
                    </h2>
                    <ProgramLocation location={p.location} />
                  </div>
                  <Badge variant="outline" className={cn('text-[10px] shrink-0', STAGE_BADGE[stage])}>{stage}</Badge>
                </div>

                <div className="mt-auto flex items-center justify-end gap-2 pt-3 border-t border-border-brand">
                  {canManage && stage !== 'Completed' ? (
                    <TransitionButton program={p} stage={stage} />
                  ) : (
                    <span className="text-[11px] font-semibold text-accent opacity-70 group-hover:opacity-100 transition-opacity">
                      View details →
                    </span>
                  )}
                </div>
              </Card>
              );
            })}
          </div>
        )}
      </div>
    </ProtectedRoute>
  );
}
