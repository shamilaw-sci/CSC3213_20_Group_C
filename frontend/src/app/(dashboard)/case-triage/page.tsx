// frontend/src/app/(dashboard)/case-triage/page.tsx
'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  DndContext, DragEndEvent, DragOverlay, DragStartEvent,
  useDraggable, useDroppable, PointerSensor, useSensor, useSensors,
} from '@dnd-kit/core';
import { RescueCasesService } from '@/services/rescue-cases.service';
import { useRescueBoardLive } from '@/hooks/useRescueBoardLive';
import { useAuthStore } from '@/store/useAuthStore';
import { hasPermission } from '@/lib/permissions';
import { toast } from 'sonner';
import { AssigneeOption, CaseOut } from '@/types';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn, getErrorMessage } from '@/lib/utils';
import { AlertTriangle, GripVertical, User, Inbox, RefreshCw, MoveRight, Info, Sparkles } from 'lucide-react';

const COLUMNS = ['Reported', 'In Treatment', 'Resolved'] as const;
type Status = (typeof COLUMNS)[number];

const STATUS_ACCENT: Record<Status, string> = {
  Reported: '#6B7280',
  'In Treatment': '#EF9F27',
  Resolved: '#16A34A',
};

// What each column means in practice. Column titles alone left new staff
// guessing whether "Reported" meant unseen or merely unresolved.
const STATUS_HINT: Record<Status, string> = {
  Reported: 'Awaiting a responder',
  'In Treatment': 'Being handled now',
  Resolved: 'Closed cases',
};

const STATUS_EMPTY: Record<Status, string> = {
  Reported: 'No new reports. Everything has been picked up.',
  'In Treatment': 'Nothing in progress right now.',
  Resolved: 'No cases resolved yet.',
};

// Same idea as STATUS_ACCENT, applied to the AI-assigned urgency badge —
// Critical/High reuse the same red/amber already used for outbreak zones
// and destructive actions elsewhere, so the color language stays consistent
// rather than introducing a third palette.
const URGENCY_ACCENT: Record<CaseOut['urgency'], { bg: string; text: string }> = {
  Critical: { bg: '#DC2626', text: '#FFFFFF' },
  High: { bg: '#EF9F27', text: '#FFFFFF' },
  Medium: { bg: 'transparent', text: '#6B7280' },
  Low: { bg: 'transparent', text: '#9CA3AF' },
};

const URGENCY_ORDER: Record<CaseOut['urgency'], number> = {
  Critical: 0, High: 1, Medium: 2, Low: 3,
};

// A default urgency is unknown, not Medium — the case behind it may be severe.
// It sorts above every genuine Medium so it is seen and reassessed, but below
// Critical/High, which a classifier actually judged to be urgent.
const DEFAULT_URGENCY_RANK = 1.5;

function sortRank(c: CaseOut): number {
  if (c.urgency_source && c.urgency_source !== 'ai') return DEFAULT_URGENCY_RANK;
  return URGENCY_ORDER[c.urgency] ?? 4;
}

// Only the two urgencies that demand attention get a stripe, so the signal
// stays meaningful — striping all four would just be decoration.
const URGENCY_STRIPE: Partial<Record<CaseOut['urgency'], string>> = {
  Critical: '#DC2626',
  High: '#EF9F27',
};

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const mins = Math.round((Date.now() - then) / 60000);
  if (!Number.isFinite(mins)) return '';
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

// "Nimal Perera" -> "NP"; an email (no profile name) -> its first two letters.
function initialsOf(nameOrEmail: string): string {
  const words = nameOrEmail.trim().split(/\s+/);
  return (words.length > 1 ? words[0][0] + words[1][0] : nameOrEmail.slice(0, 2)).toUpperCase();
}

function UrgencyBadge({ urgency }: { urgency: CaseOut['urgency'] }) {
  const accent = URGENCY_ACCENT[urgency] || URGENCY_ACCENT.Medium;
  const outlined = accent.bg === 'transparent';
  return (
    <span
      style={{
        backgroundColor: accent.bg,
        color: accent.text,
        borderColor: outlined ? 'currentColor' : 'transparent',
      }}
      className={`inline-flex items-center text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded shrink-0 ${outlined ? 'border' : ''}`}
    >
      {urgency}
    </span>
  );
}

// A default urgency must never read as if the classifier weighed the case, so
// these replace the stored reason with a plain statement of what happened.
const DEFAULT_URGENCY_LABEL: Record<string, string> = {
  default_no_description: 'Default urgency — no description to classify',
  default_classifier_error: 'Default urgency — classification unavailable',
  default_invalid_label: 'Default urgency — classifier gave an invalid result',
};

function UrgencyReason({ source, reason }: {
  source: CaseOut['urgency_source'];
  reason: CaseOut['urgency_reason'];
}) {
  const [expanded, setExpanded] = useState(false);

  // Legacy cases: nothing is known about how they were classified.
  if (!source) return null;

  if (source !== 'ai') {
    return (
      <p className="flex items-center gap-1 text-[10px] text-text-muted italic">
        <Info className="h-3 w-3 shrink-0" aria-hidden="true" />
        {DEFAULT_URGENCY_LABEL[source] ?? 'Default urgency — classification unavailable'}
      </p>
    );
  }

  if (!reason) return null;

  // Collapsed to one line so cards stay the same height in a full column;
  // the button stops pointer events so expanding never starts a drag.
  return (
    <button
      type="button"
      onPointerDown={(e) => e.stopPropagation()}
      onClick={(e) => { e.stopPropagation(); setExpanded((v) => !v); }}
      aria-expanded={expanded}
      title={expanded ? undefined : reason}
      className="flex items-start gap-1 text-left text-[10px] text-text-secondary leading-snug hover:text-text-primary"
    >
      <Sparkles className="h-3 w-3 shrink-0 mt-px text-accent" aria-hidden="true" />
      <span className="sr-only">AI urgency reason: </span>
      <span className={expanded ? undefined : 'line-clamp-1'}>{reason}</span>
    </button>
  );
}

function CaseCard({ c, canManage, canAssign, staffList, onAssignToMe, onAssignTo, onMove }: {
  c: CaseOut;
  canManage: boolean;
  canAssign: boolean;
  staffList?: AssigneeOption[];
  onAssignToMe: (id: string) => void;
  onAssignTo: (caseId: string, staffId: string) => void;
  onMove: (caseId: string, status: Status) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: c.id,
    disabled: !canManage,
  });

  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`, zIndex: 50 }
    : undefined;

  const assignee = c.assignee;
  const assigneeLabel = assignee ? assignee.display_name || assignee.email.split('@')[0] : 'Assigned';
  const stripe = URGENCY_STRIPE[c.urgency];

  return (
    <Card
      ref={setNodeRef}
      style={style}
      {...(canManage ? listeners : {})}
      {...(canManage ? attributes : {})}
      className={cn(
        'group/case relative overflow-hidden bg-surface border border-border-brand rounded-card shadow-card p-3.5 pl-4 mb-3 gap-2.5 transition-all duration-200',
        canManage && 'cursor-grab active:cursor-grabbing hover:shadow-lg hover:-translate-y-0.5 hover:border-accent/50',
        isDragging && 'opacity-40'
      )}
    >
      {/* A colour stripe down the edge makes urgency readable while scanning
          a full column, without having to land on each badge in turn. */}
      {stripe && (
        <span
          aria-hidden="true"
          className="absolute left-0 top-0 bottom-0 w-1"
          style={{ backgroundColor: stripe }}
        />
      )}

      {canManage && (
        <GripVertical
          className="absolute top-2.5 right-2 h-3.5 w-3.5 text-text-muted opacity-0 group-hover/case:opacity-100 transition-opacity"
          aria-hidden="true"
        />
      )}

      {c.photo_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={c.photo_url}
          alt={`Reported ${c.animal_type}`}
          className="w-full h-32 object-cover rounded-md bg-bg-subtle"
        />
      )}

      <div className="flex items-start justify-between gap-2 pr-4">
        <p className="text-sm font-semibold text-text-primary leading-tight">{c.animal_type}</p>
        <UrgencyBadge urgency={c.urgency} />
      </div>

      <UrgencyReason source={c.urgency_source} reason={c.urgency_reason} />

      {c.description && (
        <p className="text-xs text-text-secondary leading-relaxed line-clamp-2">{c.description}</p>
      )}

      <div className="flex items-center justify-between gap-2 pt-0.5">
        <span className="text-[10px] text-text-muted">{relativeTime(c.reported_at)}</span>

        {c.assigned_to ? (
          <span
            className="flex items-center gap-1.5 min-w-0"
            title={assignee ? assignee.email : 'Assigned'}
          >
            <span className="h-5 w-5 rounded-full bg-accent/15 text-accent text-[9px] font-bold flex items-center justify-center shrink-0">
              {assignee ? initialsOf(assignee.display_name || assignee.email) : <User className="h-3 w-3" />}
            </span>
            <span className="text-[10px] text-text-secondary truncate max-w-[90px]">
              {assigneeLabel}
            </span>
          </span>
        ) : (
          c.status !== 'Resolved' && (
            <span className="text-[10px] text-text-muted italic">Unassigned</span>
          )
        )}
      </div>

      {canManage && !c.assigned_to && c.status !== 'Resolved' && (
        <Button
          variant="link"
          size="xs"
          onClick={(e) => { e.stopPropagation(); onAssignToMe(c.id); }}
          className="h-auto justify-start p-0 text-[10px] text-accent font-semibold"
        >
          Assign to me
        </Button>
      )}

      {/* Dragging is the fast path, but it is unusable with a keyboard or a
          screen reader and awkward on a phone. These selects give every
          action a plain, reachable equivalent. */}
      {canManage && (
        <div onPointerDown={(e) => e.stopPropagation()} className="space-y-1.5">
          {canAssign && c.status !== 'Resolved' && staffList && staffList.length > 0 && (
            <Select
              onValueChange={(val) => {
                if (typeof val === 'string') onAssignTo(c.id, val);
              }}
            >
              <SelectTrigger className="h-7 text-[10px]" aria-label={`Assign ${c.animal_type} case to staff`}>
                <SelectValue placeholder={c.assigned_to ? 'Reassign staff' : 'Assign staff'} />
              </SelectTrigger>
              <SelectContent>
                {staffList.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.display_name || s.email} ({s.role_name})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}

          <Select
            value={c.status}
            onValueChange={(val) => {
              if (typeof val === 'string' && val !== c.status) onMove(c.id, val as Status);
            }}
          >
            <SelectTrigger className="h-7 text-[10px]" aria-label={`Move ${c.animal_type} case to another status`}>
              <MoveRight className="h-3 w-3 text-text-muted shrink-0" aria-hidden="true" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {COLUMNS.map((s) => (
                <SelectItem key={s} value={s}>{s}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
    </Card>
  );
}

function Column({ status, cases, canManage, canAssign, staffList, onAssignToMe, onAssignTo, onMove }: {
  status: Status;
  cases: CaseOut[];
  canManage: boolean;
  canAssign: boolean;
  staffList?: AssigneeOption[];
  onAssignToMe: (id: string) => void;
  onAssignTo: (caseId: string, staffId: string) => void;
  onMove: (caseId: string, status: Status) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: status });
  const accent = STATUS_ACCENT[status];

  // Critical/High cases float to the top of every column so the most
  // urgent work is always the first thing a staff member sees, without
  // needing a separate filter or sort control.
  const sortedCases = [...cases].sort((a, b) => sortRank(a) - sortRank(b));

  return (
    <div
      ref={setNodeRef}
      style={{ borderTopColor: accent, maxHeight: 'calc(100vh - 300px)' }}
      // The board is recessed and the cards sit on top of it. bg-subtle and
      // surface are the same colour in dark mode, so the column falls back to
      // the page background there to keep the cards legible as cards.
      className={cn(
        'flex-1 min-w-[280px] flex flex-col bg-bg-subtle dark:bg-bg-brand border border-t-4 border-border-brand rounded-card p-3 transition-all duration-200',
        isOver && 'ring-2 ring-accent ring-offset-2 ring-offset-bg-brand border-accent/50'
      )}
    >
      <div className="flex items-start justify-between gap-2 mb-3 px-1 shrink-0">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: accent }} />
            <h2 className="text-xs font-bold uppercase tracking-wider text-text-primary">{status}</h2>
          </div>
          <p className="text-[10px] text-text-muted mt-0.5 ml-4">{STATUS_HINT[status]}</p>
        </div>
        <span
          className="text-[11px] font-mono font-bold px-2 py-0.5 rounded-full bg-surface border border-border-brand shrink-0"
          style={{ color: accent }}
        >
          {cases.length}
        </span>
      </div>

      <div className="min-h-[120px] flex-1 overflow-y-auto pr-1">
        {sortedCases.length === 0 ? (
          // An empty column used to render as blank space, which reads as a
          // loading failure rather than as good news.
          <div className="h-full min-h-[120px] flex flex-col items-center justify-center text-center gap-2 border border-dashed border-border-brand rounded-lg p-4">
            <Inbox className="h-5 w-5 text-text-muted" aria-hidden="true" />
            <p className="text-[11px] text-text-muted leading-relaxed">{STATUS_EMPTY[status]}</p>
          </div>
        ) : (
          sortedCases.map((c) => (
            <CaseCard
              key={c.id}
              c={c}
              canManage={canManage}
              canAssign={canAssign}
              staffList={staffList}
              onAssignToMe={onAssignToMe}
              onAssignTo={onAssignTo}
              onMove={onMove}
            />
          ))
        )}
      </div>
    </div>
  );
}

function StatChip({ label, value, tone }: { label: string; value: number; tone?: 'critical' | 'warn' }) {
  return (
    <div
      className={cn(
        'rounded-card border border-border-brand bg-surface px-4 py-2.5 shadow-card min-w-[104px]',
        tone === 'critical' && value > 0 && 'border-red-500/40 bg-red-500/5',
        tone === 'warn' && value > 0 && 'border-accent/40 bg-accent/5'
      )}
    >
      <p
        className={cn(
          'text-xl font-bold font-heading leading-none',
          tone === 'critical' && value > 0 && 'text-red-500',
          tone === 'warn' && value > 0 && 'text-accent'
        )}
      >
        {value}
      </p>
      <p className="text-[10px] uppercase tracking-wider text-text-secondary mt-1">{label}</p>
    </div>
  );
}

function BoardSkeleton() {
  return (
    <div className="flex gap-4 overflow-x-auto pb-4">
      {COLUMNS.map((status) => (
        <div key={status} className="flex-1 min-w-[280px] bg-bg-subtle dark:bg-bg-brand border border-border-brand rounded-card p-3 space-y-3">
          <Skeleton className="h-4 w-24 bg-surface" />
          <Skeleton className="h-28 w-full bg-surface" />
          <Skeleton className="h-28 w-full bg-surface" />
        </div>
      ))}
    </div>
  );
}

export default function CaseTriagePage() {
  const { user } = useAuthStore();
  const canManage = hasPermission(user?.role || '', 'rescue:manage');
  const canAssign = hasPermission(user?.role || '', 'rescue:assign');
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(null);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['rescueCases', 'list'],
    queryFn: () => RescueCasesService.listCases(),
    // Fallback for when the live channel is down. Pings normally keep the
    // board current; this bounds how stale it can get without them.
    refetchInterval: 45_000,
    // 'always', not true: the global 60 s staleTime outlasts the polling
    // interval, so with plain true a focus refetch would never fire.
    refetchOnWindowFocus: 'always',
  });

  // Only for the assign dropdown. Cards name their assignee from the case
  // itself, so viewers without rescue:assign never fetch a staff list — the
  // endpoint would refuse them anyway. Who is eligible is decided server-side.
  const { data: staffList } = useQuery({
    // Outside the ['rescueCases'] prefix on purpose: useRescueBoardLive
    // invalidates that whole prefix on every case ping, and the staff list
    // does not change when a case does.
    queryKey: ['assignees'],
    queryFn: () => RescueCasesService.listAssignees(),
    enabled: canAssign,
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, new_status, assigned_to }: { id: string; new_status: string; assigned_to?: string }) =>
      RescueCasesService.updateCaseStatus(id, { new_status, assigned_to }),

    // Move the card immediately and roll back if the server refuses. Waiting
    // for a round trip made every drag look like it had failed and snapped
    // back, which is the single most confusing thing about the board.
    onMutate: async ({ id, new_status, assigned_to }) => {
      await queryClient.cancelQueries({ queryKey: ['rescueCases', 'list'] });
      const previous = queryClient.getQueryData<CaseOut[]>(['rescueCases', 'list']);

      queryClient.setQueryData<CaseOut[]>(['rescueCases', 'list'], (old) =>
        old?.map((c) =>
          c.id === id
            ? { ...c, status: new_status as CaseOut['status'], assigned_to: assigned_to ?? c.assigned_to }
            : c
        )
      );

      return { previous };
    },
    onError: (err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(['rescueCases', 'list'], context.previous);
      }
      toast.error(getErrorMessage(err) || "Couldn't update the case. Please try again.");
    },
    onSuccess: () => toast.success('Case updated'),
    onSettled: () => {
      // This refetch already covers any ping held during the mutation —
      // including the one the server sent for this very change.
      live.discardPending();
      return queryClient.invalidateQueries({ queryKey: ['rescueCases', 'list'] });
    },
  });

  const live = useRescueBoardLive(activeId !== null || statusMutation.isPending);

  function handleDragStart(event: DragStartEvent) {
    setActiveId(event.active.id as string);
  }

  function moveCase(caseId: string, newStatus: Status) {
    const currentCase = data?.find((c) => c.id === caseId);
    if (!currentCase || currentCase.status === newStatus) return;

    const assigned_to = newStatus !== 'Reported' && !currentCase.assigned_to
      ? user?.id
      : undefined;

    statusMutation.mutate({ id: caseId, new_status: newStatus, assigned_to });
  }

  function handleDragEnd(event: DragEndEvent) {
    setActiveId(null);
    const { active, over } = event;
    if (!over) return;
    moveCase(active.id as string, over.id as Status);
  }

  function handleAssignToMe(caseId: string) {
    if (!user?.id) return;
    const currentCase = data?.find((c) => c.id === caseId);
    if (!currentCase) return;
    const newStatus = currentCase.status === 'Reported' ? 'In Treatment' : currentCase.status;
    statusMutation.mutate({ id: caseId, new_status: newStatus, assigned_to: user.id });
  }

  function handleAssignTo(caseId: string, staffId: string) {
    const currentCase = data?.find((c) => c.id === caseId);
    if (!currentCase) return;
    const newStatus = currentCase.status === 'Reported' ? 'In Treatment' : currentCase.status;
    statusMutation.mutate({ id: caseId, new_status: newStatus, assigned_to: staffId });
  }

  const activeCase = data?.find((c) => c.id === activeId);

  const criticalOpen = data?.filter(
    (c) => c.status !== 'Resolved' && (c.urgency === 'Critical' || c.urgency === 'High')
  ).length ?? 0;
  const unassignedOpen = data?.filter((c) => c.status !== 'Resolved' && !c.assigned_to).length ?? 0;
  const openTotal = data?.filter((c) => c.status !== 'Resolved').length ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold font-heading tracking-tight mb-2 text-text-primary">
            Rescue Case Triage
          </h1>
          <p className="text-text-secondary text-sm">
            {canManage
              ? 'Drag a case between columns, or use the menu on each card to move it.'
              : 'View-only — you do not have permission to manage cases.'}
          </p>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={() => refetch()}
          disabled={isFetching}
          className="gap-2 shrink-0"
        >
          <RefreshCw className={cn('h-3.5 w-3.5', isFetching && 'animate-spin')} aria-hidden="true" />
          Refresh
        </Button>
      </div>

      {/* The board answers "where is everything"; these answer "what needs me
          first", which is the question someone actually opens this page with. */}
      {data && data.length > 0 && (
        <div className="flex flex-wrap gap-3">
          <StatChip label="Open cases" value={openTotal} />
          <StatChip label="Urgent open" value={criticalOpen} tone="critical" />
          <StatChip label="Unassigned" value={unassignedOpen} tone="warn" />
        </div>
      )}

      {isLoading && <BoardSkeleton />}

      {error && (
        <div className="flex flex-wrap items-center gap-3 text-sm text-rose-500 bg-rose-500/10 p-4 rounded-lg border border-rose-500/20">
          <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="flex-1 min-w-[200px]">
            {getErrorMessage(error) || 'Failed to load cases.'}
          </span>
          <Button variant="outline" size="sm" onClick={() => refetch()} className="gap-2">
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            Retry
          </Button>
        </div>
      )}

      {data && data.length === 0 && (
        <div className="flex flex-col items-center justify-center text-center gap-3 py-20 border border-dashed border-border-brand rounded-card">
          <Inbox className="h-8 w-8 text-text-muted" aria-hidden="true" />
          <div>
            <p className="text-sm font-semibold text-text-primary">No rescue cases yet</p>
            <p className="text-xs text-text-secondary mt-1">
              Cases reported from the public form will appear here for triage.
            </p>
          </div>
        </div>
      )}

      {data && data.length > 0 && (
        <DndContext sensors={sensors} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
          <div className="flex gap-4 overflow-x-auto pb-4">
            {COLUMNS.map((status) => (
              <Column
                key={status}
                status={status}
                cases={data.filter((c) => c.status === status)}
                canManage={canManage}
                canAssign={canAssign}
                staffList={staffList}
                onAssignToMe={handleAssignToMe}
                onAssignTo={handleAssignTo}
                onMove={moveCase}
              />
            ))}
          </div>

          <DragOverlay>
            {activeCase ? (
              // Carry enough of the card that you can still tell what you are
              // holding mid-drag, tilted slightly so it reads as lifted.
              <Card className="bg-surface border border-accent rounded-card shadow-2xl p-3.5 w-72 gap-2 rotate-2 cursor-grabbing">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-semibold text-text-primary">{activeCase.animal_type}</p>
                  <UrgencyBadge urgency={activeCase.urgency} />
                </div>
                {activeCase.description && (
                  <p className="text-xs text-text-secondary line-clamp-2">{activeCase.description}</p>
                )}
              </Card>
            ) : null}
          </DragOverlay>
        </DndContext>
      )}
    </div>
  );
}
