'use client';

// The program's listing on the public /clinics page: what people in the area
// are told so they can bring their animals. Off until someone with
// programs:manage publishes it; it drops off the public page by itself once
// the program is completed or cancelled.

import { useState } from 'react';
import Link from 'next/link';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Globe, EyeOff, Loader2, Pencil, ExternalLink, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';

import { ProgramService, type ProgramStage } from '@/services/program.service';
import { PROGRAM_TYPES, type ProgramDetail, type ProgramType } from '@/types';
import { cn, getErrorMessage } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';

const LABEL_CLASS = 'text-xs font-semibold text-text-secondary';
const TEXTAREA_CLASS =
  'flex w-full rounded-md border border-border-brand bg-transparent px-3 py-2 text-sm placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent';

export function PublicListingCard({
  program, stage, canManage,
}: { program: ProgramDetail; stage: ProgramStage; canManage: boolean }) {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();

  const listable = stage === 'Upcoming' || stage === 'Active';
  const live = !!program.is_public && listable;

  const save = useMutation({
    mutationFn: (data: Parameters<typeof ProgramService.updatePublicListing>[1]) =>
      ProgramService.updatePublicListing(program.id, data),
    onSuccess: (updated) => {
      toast.success(updated.is_public ? 'Listing is live on the public site.' : 'Taken off the public site.');
      setOpen(false);
      queryClient.invalidateQueries({ queryKey: ['program', program.id] });
      queryClient.invalidateQueries({ queryKey: ['public-programs'] });
    },
    onError: (err) => toast.error(getErrorMessage(err) || 'Could not save the public listing.'),
  });

  const takeDown = () => save.mutate({
    is_public: false,
    program_type: program.program_type ?? null,
    public_venue: program.public_venue ?? '',
    public_schedule: program.public_schedule ?? '',
    public_notes: program.public_notes ?? '',
  });

  return (
    <Card className="bg-surface border border-border-brand rounded-card">
      <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
        <div className="space-y-1">
          <CardTitle className="text-base flex items-center gap-2">
            <Globe size={16} className="text-accent" /> Public listing
          </CardTitle>
          <p className="text-xs text-text-secondary">
            {live
              ? 'Shown on the public Clinics page so people nearby can bring their animals.'
              : listable
                ? 'Not on the public site. Publish it so people in the area know it is coming.'
                : `Not shown: the program is ${stage.toLowerCase()}.`}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {live ? (
            <Badge variant="outline" className="text-xs border-positive/40 text-positive bg-positive/10">Live</Badge>
          ) : (
            <Badge variant="outline" className="text-xs text-text-secondary">Not public</Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {(program.program_type || program.public_venue || program.public_schedule || program.public_notes) && (
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3 text-sm">
            <ListingField label="Type" value={program.program_type} />
            <ListingField label="Venue" value={program.public_venue} />
            <ListingField label="Days & hours" value={program.public_schedule} />
            <ListingField label="Good to know" value={program.public_notes} className="sm:col-span-2" />
          </dl>
        )}

        <div className="flex flex-wrap gap-2">
          {canManage && listable && (
            <Button
              size="sm"
              className={cn(!live && 'bg-accent text-white hover:bg-accent/90')}
              variant={live ? 'outline' : 'default'}
              onClick={() => setOpen(true)}
            >
              {live ? <><Pencil className="h-3.5 w-3.5 mr-1.5" /> Edit listing</> : <><Globe className="h-3.5 w-3.5 mr-1.5" /> Publish</>}
            </Button>
          )}
          {canManage && program.is_public && (
            <Button size="sm" variant="outline" onClick={takeDown} disabled={save.isPending}>
              {save.isPending && !open
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <><EyeOff className="h-3.5 w-3.5 mr-1.5" /> Take down</>}
            </Button>
          )}
          {live && (
            <Link
              href="/clinics" target="_blank" rel="noopener"
              className="inline-flex items-center h-8 px-3 text-xs font-medium text-accent hover:underline"
            >
              View public page <ExternalLink className="h-3.5 w-3.5 ml-1.5" />
            </Link>
          )}
        </div>
      </CardContent>

      {open && (
        <PublicListingDialog
          program={program}
          stage={stage}
          live={live}
          pending={save.isPending}
          onClose={() => setOpen(false)}
          onSave={(data) => save.mutate({ ...data, is_public: true })}
        />
      )}
    </Card>
  );
}

function ListingField({ label, value, className }: { label: string; value?: string | null; className?: string }) {
  return (
    <div className={className}>
      <dt className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">{label}</dt>
      <dd className={cn('mt-0.5 whitespace-pre-line', value ? 'text-text-primary' : 'text-text-muted')}>
        {value || '—'}
      </dd>
    </div>
  );
}

function PublicListingDialog({
  program, stage, live, pending, onClose, onSave,
}: {
  program: ProgramDetail;
  stage: ProgramStage;
  live: boolean;
  pending: boolean;
  onClose: () => void;
  onSave: (data: { program_type: ProgramType | null; public_venue: string; public_schedule: string; public_notes: string }) => void;
}) {
  const [type, setType] = useState<ProgramType | ''>(program.program_type ?? guessType(program.program_name));
  const [venue, setVenue] = useState(program.public_venue ?? '');
  const [schedule, setSchedule] = useState(program.public_schedule ?? '');
  const [notes, setNotes] = useState(program.public_notes ?? '');

  // The API refuses these with a 422; saying so up front saves a round trip.
  // An Active program is on now, so its listing needs no start date.
  const missing = [
    !program.location && 'a location',
    stage === 'Upcoming' && !program.start_date && 'a start date',
  ].filter(Boolean) as string[];
  const canSave = !!type && missing.length === 0 && !pending;

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{live ? 'Edit public listing' : 'Publish on the public site'}</DialogTitle>
          <DialogDescription>
            Anyone can see this on the Clinics page. The area ({program.location || 'not set'})
            {stage === 'Upcoming' ? ' and start date come' : ' comes'} from the program itself.
          </DialogDescription>
        </DialogHeader>

        {missing.length > 0 && (
          <p className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-600 dark:text-amber-400">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            Before publishing, set {missing.join(' and ')} on this program.
          </p>
        )}

        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className={LABEL_CLASS} htmlFor="listing-type">What is it?</label>
            <Select value={type} onValueChange={(v) => setType(v as ProgramType)}>
              <SelectTrigger id="listing-type"><SelectValue placeholder="Choose a type" /></SelectTrigger>
              <SelectContent>
                {PROGRAM_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <label className={LABEL_CLASS} htmlFor="listing-venue">Venue (optional)</label>
            <Input
              id="listing-venue" value={venue} maxLength={200}
              onChange={(e) => setVenue(e.target.value)}
              placeholder="e.g. Peradeniya Community Hall"
            />
          </div>
          <div className="space-y-1.5">
            <label className={LABEL_CLASS} htmlFor="listing-schedule">Days & hours (optional)</label>
            <Input
              id="listing-schedule" value={schedule} maxLength={200}
              onChange={(e) => setSchedule(e.target.value)}
              placeholder="e.g. Sat 22 – Mon 24 Nov, 8am – 1pm"
            />
          </div>
          <div className="space-y-1.5">
            <label className={LABEL_CLASS} htmlFor="listing-notes">Good to know (optional)</label>
            <textarea
              id="listing-notes" rows={3} value={notes} maxLength={1000}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Free of charge. Please don't feed your dog after 10pm the night before."
              className={TEXTAREA_CLASS}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={pending}>Cancel</Button>
          <Button
            className="bg-accent text-white hover:bg-accent/90"
            disabled={!canSave}
            onClick={() => onSave({
              program_type: type || null, public_venue: venue, public_schedule: schedule, public_notes: notes,
            })}
          >
            {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : live ? 'Save' : 'Publish'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** A starting point from the program's name; staff can change it. */
function guessType(name: string): ProgramType | '' {
  const n = name.toLowerCase();
  if (/steril|neuter|spay|abc/.test(n)) return 'Sterilization';
  if (/vaccin|rabies/.test(n)) return 'Vaccination';
  if (/clinic/.test(n)) return 'Free Clinic';
  if (/aware|education|school/.test(n)) return 'Awareness';
  return '';
}
