// frontend/src/app/(dashboard)/case-triage/page.tsx
'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  DndContext, DragEndEvent, DragOverlay, DragStartEvent,
  useDraggable, useDroppable, PointerSensor, useSensor, useSensors,
} from '@dnd-kit/core';
import { RescueCasesService } from '@/services/rescue-cases.service';
import { UsersService, StaffUser } from '@/services/users.service';
import { useAuthStore } from '@/store/useAuthStore';
import { hasPermission } from '@/lib/permissions';
import { toast } from 'sonner';
import { CaseOut } from '@/types';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { AlertTriangle, GripVertical, User } from 'lucide-react';

// "Assigned" used to be a fourth drag-target column, but who's handling a
// case and what stage it's at are different things — conflating them let a
// card sit in "Reported" with an assignee already attached, or get dragged
// into "Assigned" with nobody actually assigned. Assignment is now a
// persistent property shown on every card (see CaseCard) regardless of
// stage; claiming a case moves it straight to In Treatment.
const COLUMNS = ['Reported', 'In Treatment', 'Resolved'] as const;

// Color language per stage so the board is scannable at a glance —
// gray (untouched) -> amber (active work) -> green (done). Reuses hex
// values already present elsewhere in the app (--color-accent,
// --color-positive) rather than introducing a new palette.
const STATUS_ACCENT: Record<(typeof COLUMNS)[number], string> = {
  Reported: '#6B7280',
  'In Treatment': '#EF9F27',
  Resolved: '#16A34A',
};

function CaseCard({ c, canManage, canAssign, staffList, onAssignToMe, onAssignTo }: {
  c: CaseOut;
  canManage: boolean;
  canAssign: boolean;
  staffList?: StaffUser[];
  onAssignToMe: (id: string) => void;
  onAssignTo: (caseId: string, staffId: string) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: c.id,
    disabled: !canManage,
  });

  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`, zIndex: 50 }
    : undefined;

  const assignee = staffList?.find((s) => s.id === c.assigned_to);

  return (
    <Card
      ref={setNodeRef}
      style={style}
      {...(canManage ? listeners : {})}
      {...(canManage ? attributes : {})}
      className={`group/case relative bg-surface border border-border-brand rounded-card shadow-card p-3 mb-3 gap-2 transition-all ${
        canManage ? 'cursor-grab active:cursor-grabbing hover:shadow-md hover:border-accent/40' : ''
      } ${isDragging ? 'opacity-50 shadow-lg' : ''}`}
    >
      {canManage && (
        <GripVertical
          className="absolute top-2 right-2 h-3.5 w-3.5 text-text-muted opacity-0 group-hover/case:opacity-100 transition-opacity"
          aria-hidden="true"
        />
      )}

      {c.photo_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={c.photo_url} alt={c.animal_type} className="w-full h-28 object-cover rounded-md" />
      )}
      <p className="text-xs font-semibold text-text-primary pr-4">{c.animal_type}</p>
      {c.description && <p className="text-xs text-text-secondary line-clamp-2">{c.description}</p>}
      <p className="text-[10px] text-text-muted font-mono">
        {new Date(c.reported_at).toLocaleDateString()}
      </p>

      {c.assigned_to && (
        <p className="text-[10px] text-text-secondary flex items-center gap-1">
          <User className="h-3 w-3 shrink-0" />
          <span className="truncate">{assignee ? assignee.email : 'Assigned'}</span>
        </p>
      )}

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

      {canAssign && c.status !== 'Resolved' && staffList && staffList.length > 0 && (
        <div onPointerDown={(e) => e.stopPropagation()}>
          <Select
            onValueChange={(val) => {
              if (typeof val === 'string') onAssignTo(c.id, val);
            }}
          >
            <SelectTrigger className="h-7 text-[10px]">
              <SelectValue placeholder={c.assigned_to ? 'Reassign staff' : 'Assign staff'} />
            </SelectTrigger>
            <SelectContent>
              {staffList.map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  {s.email} {s.roles?.role_name ? `(${s.roles.role_name})` : ''}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
    </Card>
  );
}

function Column({ status, cases, canManage, canAssign, staffList, onAssignToMe, onAssignTo }: {
  status: (typeof COLUMNS)[number];
  cases: CaseOut[];
  canManage: boolean;
  canAssign: boolean;
  staffList?: StaffUser[];
  onAssignToMe: (id: string) => void;
  onAssignTo: (caseId: string, staffId: string) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: status });
  const accent = STATUS_ACCENT[status];

  return (
    <div
      ref={setNodeRef}
      style={{ borderTopColor: accent, maxHeight: 'calc(100vh - 280px)' }}
      className={`flex-1 min-w-[260px] flex flex-col bg-bg-subtle border border-t-4 border-border-brand rounded-card p-3 transition-colors ${
        isOver ? 'bg-accent/10 border-accent/40' : ''
      }`}
    >
      <div className="flex items-center justify-between mb-3 px-1 shrink-0">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: accent }} />
          <h2 className="text-xs font-bold uppercase tracking-wider text-text-secondary">{status}</h2>
        </div>
        <span className="text-[10px] font-mono font-semibold" style={{ color: accent }}>{cases.length}</span>
      </div>
      <div className="min-h-[100px] flex-1 overflow-y-auto pr-1">
        {cases.map((c) => (
          <CaseCard
            key={c.id}
            c={c}
            canManage={canManage}
            canAssign={canAssign}
            staffList={staffList}
            onAssignToMe={onAssignToMe}
            onAssignTo={onAssignTo}
          />
        ))}
      </div>
    </div>
  );
}

function BoardSkeleton() {
  return (
    <div className="flex gap-4 overflow-x-auto pb-4">
      {COLUMNS.map((status) => (
        <div key={status} className="flex-1 min-w-[260px] bg-bg-subtle border border-border-brand rounded-card p-3 space-y-3">
          <Skeleton className="h-4 w-20 bg-surface" />
          <Skeleton className="h-24 w-full bg-surface" />
          <Skeleton className="h-24 w-full bg-surface" />
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

  const { data, isLoading, error } = useQuery({
    queryKey: ['rescueCases', 'list'],
    queryFn: () => RescueCasesService.listCases(),
  });

  // Fetched unconditionally (not gated on canAssign) so any board viewer can
  // see who a case is assigned to — the assignment dropdown itself still
  // stays permission-gated below.
  const { data: staffList } = useQuery({
    queryKey: ['users', 'list'],
    queryFn: () => UsersService.listUsers(),
    select: (users) => users.filter((u) => ['Staff', 'Admin'].includes(u.roles?.role_name || '')),
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, new_status, assigned_to }: { id: string; new_status: string; assigned_to?: string }) =>
      RescueCasesService.updateCaseStatus(id, { new_status, assigned_to }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rescueCases', 'list'] });
      toast.success('Case updated');
    },
    onError: () => toast.error("Couldn't update the case. Please try again."),
  });

  function handleDragStart(event: DragStartEvent) {
    setActiveId(event.active.id as string);
  }

  function handleDragEnd(event: DragEndEvent) {
    setActiveId(null);
    const { active, over } = event;
    if (!over) return;

    const caseId = active.id as string;
    const newStatus = over.id as string;
    const currentCase = data?.find((c) => c.id === caseId);
    if (!currentCase || currentCase.status === newStatus) return;

    // Reported is the only stage a case can be unclaimed in. Dragging a case
    // forward without an existing assignee claims it for whoever dragged it,
    // same as clicking "Assign to me" — dragging into Reported needs nothing
    // extra, the backend releases the claim on its own.
    const assigned_to = newStatus !== 'Reported' && !currentCase.assigned_to
      ? user?.id
      : undefined;

    statusMutation.mutate({ id: caseId, new_status: newStatus, assigned_to });
  }

  // Claiming an unassigned case also starts it — a fresh Reported case moves
  // straight to In Treatment. Claiming a case that's already past Reported
  // just attaches the assignee without disturbing its current stage.
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

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold font-heading tracking-tight mb-2 text-text-primary">
          Rescue Case Triage
        </h1>
        <p className="text-text-secondary text-sm">
          {canManage ? 'Drag cases between columns to update their status.' : 'View-only — you do not have permission to manage cases.'}
        </p>
      </div>

      {isLoading && <BoardSkeleton />}

      {error && (
        <div className="flex items-center gap-2 text-sm text-rose-500 bg-rose-500/10 p-4 rounded-lg border border-rose-500/20">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          Failed to load cases. Please try again.
        </div>
      )}

      {data && (
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
              />
            ))}
          </div>
          <DragOverlay>
            {activeCase ? (
              <Card className="bg-surface border border-accent rounded-card shadow-xl p-3 w-64">
                <p className="text-xs font-semibold">{activeCase.animal_type}</p>
              </Card>
            ) : null}
          </DragOverlay>
        </DndContext>
      )}
    </div>
  );
}
