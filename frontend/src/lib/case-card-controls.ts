// Which controls a triage card shows, decided in one place.
//
// The card used to nest the assign dropdown inside its `canManage` block, so
// a viewer holding rescue:assign without rescue:manage (HR Officer, Director)
// never saw it — the two permissions are separate on the backend and must be
// separate here. Kept out of the component so it can be tested on plain node.
//
//   rescue:manage  drag, "Assign to me", the status select
//   rescue:assign  the assign dropdown (handing a case to someone else)

import type { AssigneeOption, CaseOut } from '@/types';

export interface CardControls {
  draggable: boolean;
  showAssignToMe: boolean;
  showStatusSelect: boolean;
  /** Null when the dropdown is hidden; otherwise its options, in order. */
  assignOptions: { value: string; label: string }[] | null;
}

export function cardControls(
  c: Pick<CaseOut, 'status' | 'assigned_to'>,
  canManage: boolean,
  canAssign: boolean,
  assignees: AssigneeOption[] | undefined,
): CardControls {
  const open = c.status !== 'Resolved';
  return {
    draggable: canManage,
    showAssignToMe: canManage && open && !c.assigned_to,
    showStatusSelect: canManage,
    // Eligibility was decided by GET /rescue_cases/assignees; no client-side
    // role filter on top of it.
    assignOptions:
      canAssign && open && assignees && assignees.length > 0
        ? assignees.map((a) => ({ value: a.id, label: `${a.display_name || a.email} (${a.role_name})` }))
        : null,
  };
}
