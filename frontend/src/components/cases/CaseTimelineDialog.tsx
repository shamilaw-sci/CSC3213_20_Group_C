'use client';

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Loader2, MessageSquare, MoveRight, Siren, UserRound } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { RescueCasesService } from '@/services/rescue-cases.service';
import { getErrorMessage } from '@/lib/utils';
import type { CaseAssignee, CaseEvent, CaseOut } from '@/types';

const WHEN = new Intl.DateTimeFormat('en-LK', {
  day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit',
});

const field =
  'w-full rounded-md border border-border-brand bg-surface px-2 py-2 text-sm text-text-primary outline-none focus:border-accent';

const nameOf = (p?: CaseAssignee | null) => (p ? p.display_name || p.email : null);

const ICON = {
  reported: Siren,
  note: MessageSquare,
  status: MoveRight,
  assign: UserRound,
  outcome: CheckCircle2,
} as const;

function headline(e: CaseEvent): string {
  switch (e.event_type) {
    case 'reported':
      return e.author ? `Reported by ${nameOf(e.author)}` : 'Reported by the public';
    case 'note':
      return nameOf(e.author) ?? 'Note';
    case 'status':
      return `Moved from ${e.from_status} to ${e.to_status}`;
    case 'assign':
      return e.assignee ? `Assigned to ${nameOf(e.assignee)}` : 'Released, now unassigned';
    case 'outcome':
      return `Outcome: ${e.outcome}`;
  }
}

function EventRow({ e }: { e: CaseEvent }) {
  const Icon = ICON[e.event_type];
  const by = e.event_type !== 'reported' && e.event_type !== 'note' ? nameOf(e.author) : null;
  return (
    <li className="relative flex gap-3 pb-4 last:pb-0">
      <span className="relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border-brand bg-surface">
        <Icon className="h-3 w-3 text-accent" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-semibold text-text-primary">{headline(e)}</p>
        {e.body && (
          <p className="mt-0.5 whitespace-pre-wrap break-words text-xs text-text-secondary">{e.body}</p>
        )}
        <p className="mt-0.5 text-[10px] text-text-muted">
          {WHEN.format(new Date(e.created_at))}{by ? ` · by ${by}` : ''}
        </p>
      </div>
    </li>
  );
}

/**
 * Everything that has happened on a case, oldest first, with a note box for
 * staff who work cases. Notes are append-only: a mistake is corrected with a
 * follow-up note.
 */
export function CaseTimelineDialog({ c, canManage, onClose }: {
  c: CaseOut;
  canManage: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState('');

  // Under the ['rescueCases'] prefix on purpose: the live board ping
  // invalidates it, so an open timeline follows moves made elsewhere.
  const queryKey = ['rescueCases', 'timeline', c.id];
  const { data, isLoading, error } = useQuery({
    queryKey,
    queryFn: () => RescueCasesService.getTimeline(c.id),
  });

  const addNote = useMutation({
    mutationFn: (body: string) => RescueCasesService.addNote(c.id, body),
    onSuccess: () => {
      setNote('');
      return queryClient.invalidateQueries({ queryKey });
    },
    onError: (err) => toast.error(getErrorMessage(err) || "Couldn't add the note."),
  });

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-surface border-border-brand sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{c.animal_type} case</DialogTitle>
          <DialogDescription>
            {c.status}
            {c.outcome ? ` · ${c.outcome}` : ''}
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[50vh] overflow-y-auto pr-1">
          {isLoading ? (
            <p className="flex items-center gap-2 text-sm text-text-secondary">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading the timeline…
            </p>
          ) : error || !data ? (
            <p className="text-sm text-negative">{getErrorMessage(error) || 'Could not load the timeline.'}</p>
          ) : (
            // The line behind the icons joins the entries into one history.
            <ol className="relative before:absolute before:left-3 before:top-3 before:bottom-3 before:w-px before:bg-border-brand">
              {data.map((e) => <EventRow key={`${e.event_type}-${e.id}`} e={e} />)}
            </ol>
          )}
        </div>

        {canManage && (
          <form
            className="space-y-2 border-t border-border-brand pt-3"
            onSubmit={(ev) => {
              ev.preventDefault();
              if (note.trim()) addNote.mutate(note.trim());
            }}
          >
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              maxLength={2000}
              placeholder="Add a note, e.g. vet visit, medication given, moved to foster"
              aria-label="New note"
              className={field}
            />
            <div className="flex items-center justify-between gap-2">
              <p className="text-[10px] text-text-muted">Notes can&apos;t be edited later. Add a follow-up to correct one.</p>
              <Button
                type="submit"
                size="sm"
                disabled={!note.trim() || addNote.isPending}
                className="shrink-0 bg-accent text-white hover:bg-accent/90"
              >
                {addNote.isPending ? 'Adding…' : 'Add note'}
              </Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
