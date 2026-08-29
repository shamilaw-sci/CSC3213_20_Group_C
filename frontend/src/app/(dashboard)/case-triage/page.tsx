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

const COLUMNS = ['Reported', 'In Treatment', 'Resolved'] as const;

const STATUS_ACCENT: Record<(typeof COLUMNS)[number], string> = {
  Reported: '#6B7280',
  'In Treatment': '#EF9F27',
  Resolved: '#16A34A',
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
      className={`inline-flex items-center text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${outlined ? 'border' : ''}`}
    >
      {urgency}
    </span>
  );
}

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

      <div className="flex items-center justify-between gap-2 pr-4">
        <p className="text-xs font-semibold text-text-primary">{c.animal_type}</p>
        <UrgencyBadge urgency={c.urgency} />
      </div>

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

  // Critical/High cases float to the top of every column so the most
  // urgent work is always the first thing a staff member sees, without
  // needing a separate filter or sort control.
  const sortedCases = [...cases].sort(
    (a, b) => (URGENCY_ORDER[a.urgency] ?? 4) - (URGENCY_ORDER[b.urgency] ?? 4)
  );

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
        {sortedCases.map((c) => (
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

    const assigned_to = newStatus !== 'Reported' && !currentCase.assigned_to
      ? user?.id
      : undefined;

    statusMutation.mutate({ id: caseId, new_status: newStatus, assigned_to });
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