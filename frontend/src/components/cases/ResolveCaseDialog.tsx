'use client';

import { useState } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { CASE_OUTCOMES, type CaseOutcome } from '@/types';

// What each outcome means, so staff pick the same one for the same thing and
// the counts mean something.
export const OUTCOME_HINT: Record<CaseOutcome, string> = {
  Released: 'Treated and returned to where it was found',
  Rehomed: 'Adopted or placed with a new owner or foster',
  Transferred: 'Handed to a vet, hospital or another shelter',
  Died: 'Died or was put down',
  'Not found': 'Could not be located at the reported place',
};

const field =
  'w-full rounded-md border border-border-brand bg-surface px-2 py-2 text-sm text-text-primary outline-none focus:border-accent';

/**
 * Asked for on every move into Resolved, however it is made (drag or the
 * status menu). Cancelling leaves the case where it was.
 */
export function ResolveCaseDialog({ animalType, onConfirm, onClose, title, description, confirmLabel, busy }: {
  animalType: string;
  onConfirm: (outcome: CaseOutcome, note: string) => void;
  onClose: () => void;
  // Overrides for reuse, e.g. recording the outcome of an older case.
  title?: string;
  description?: string;
  confirmLabel?: string;
  busy?: boolean;
}) {
  const [outcome, setOutcome] = useState<CaseOutcome | null>(null);
  const [note, setNote] = useState('');

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-surface border-border-brand sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title ?? `Resolve ${animalType} case`}</DialogTitle>
          <DialogDescription>{description ?? 'What happened to the animal? This goes on the case timeline.'}</DialogDescription>
        </DialogHeader>

        <div role="radiogroup" aria-label="Outcome" className="space-y-1.5">
          {CASE_OUTCOMES.map((o) => (
            <button
              key={o}
              type="button"
              role="radio"
              aria-checked={outcome === o}
              onClick={() => setOutcome(o)}
              className={cn(
                'w-full rounded-md border px-3 py-2 text-left transition-colors',
                outcome === o
                  ? 'border-accent bg-accent/10'
                  : 'border-border-brand hover:border-accent/50',
              )}
            >
              <p className="text-sm font-semibold text-text-primary">{o}</p>
              <p className="text-[11px] text-text-secondary">{OUTCOME_HINT[o]}</p>
            </button>
          ))}
        </div>

        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
          maxLength={2000}
          placeholder="Details (optional), e.g. who adopted, which vet"
          aria-label="Outcome details"
          className={field}
        />

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            onClick={() => outcome && onConfirm(outcome, note.trim())}
            disabled={!outcome || busy}
            className="gap-1.5 bg-accent text-white hover:bg-accent/90"
          >
            <CheckCircle2 className="h-4 w-4" /> {confirmLabel ?? 'Resolve case'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
