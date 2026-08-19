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

const COLUMNS = ['Reported', 'Assigned', 'In Treatment', 'Resolved'] as const;

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

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...(canManage ? listeners : {})}
      {...(canManage ? attributes : {})}
      className={`bg-surface border border-border-brand rounded-lg p-3 mb-3 space-y-2 ${
        canManage ? 'cursor-grab active:cursor-grabbing' : ''
      } ${isDragging ? 'opacity-50 shadow-lg' : ''}`}
    >
      {c.photo_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={c.photo_url} alt={c.animal_type} className="w-full h-28 object-cover rounded-md" />
      )}
      <p className="text-xs font-semibold text-text-primary">{c.animal_type}</p>
      {c.description && <p className="text-xs text-text-secondary line-clamp-2">{c.description}</p>}
      <p className="text-[10px] text-text-muted font-mono">
        {new Date(c.reported_at).toLocaleDateString()}
      </p>

      {canManage && c.status === 'Reported' && !c.assigned_to && (
        <button
          onClick={(e) => { e.stopPropagation(); onAssignToMe(c.id); }}
          className="text-[10px] text-[#EF9F27] hover:underline font-semibold"
        >
          Assign to me
        </button>
      )}

      {canAssign && staffList && staffList.length > 0 && (
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
    </div>
  );
}

function Column({ status, cases, canManage, canAssign, staffList, onAssignToMe, onAssignTo }: {
  status: string;
  cases: CaseOut[];
  canManage: boolean;
  canAssign: boolean;
  staffList?: StaffUser[];
  onAssignToMe: (id: string) => void;
  onAssignTo: (caseId: string, staffId: string) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: status });

  return (
    <div
      ref={setNodeRef}
      className={`flex-1 min-w-[260px] bg-bg-subtle border border-border-brand rounded-xl p-3 transition-colors ${
        isOver ? 'bg-[#EF9F27]/10 border-[#EF9F27]/40' : ''
      }`}
    >
      <div className="flex items-center justify-between mb-3 px-1">
        <h2 className="text-xs font-bold uppercase tracking-wider text-text-secondary">{status}</h2>
        <span className="text-[10px] font-mono text-text-muted">{cases.length}</span>
      </div>
      <div className="min-h-[100px]">
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
    enabled: canAssign,
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

    statusMutation.mutate({ id: caseId, new_status: newStatus });
  }

  function handleAssignToMe(caseId: string) {
    if (!user?.id) return;
    statusMutation.mutate({ id: caseId, new_status: 'Assigned', assigned_to: user.id });
  }

  function handleAssignTo(caseId: string, staffId: string) {
    const currentCase = data?.find((c) => c.id === caseId);
    if (!currentCase) return;
    const newStatus = currentCase.status === 'Reported' ? 'Assigned' : currentCase.status;
    statusMutation.mutate({ id: caseId, new_status: newStatus, assigned_to: staffId });
  }

  const activeCase = data?.find((c) => c.id === activeId);

  return (
    <div className="p-6">
      <div className="mb-4">
        <h1 className="text-xl font-semibold">Rescue Case Triage</h1>
        <p className="text-text-secondary text-sm mt-1">
          {canManage ? 'Drag cases between columns to update their status.' : 'View-only — you do not have permission to manage cases.'}
        </p>
      </div>

      {isLoading && <p>Loading cases...</p>}
      {error && <p>Failed to load cases.</p>}

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
              <div className="bg-surface border border-[#EF9F27] rounded-lg p-3 shadow-xl w-64">
                <p className="text-xs font-semibold">{activeCase.animal_type}</p>
              </div>
            ) : null}
          </DragOverlay>
        </DndContext>
      )}
    </div>
  );
}