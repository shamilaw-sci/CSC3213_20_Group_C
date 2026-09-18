// frontend/src/app/(dashboard)/volunteers/shifts/page.tsx
'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  VolunteersService, type Shift, type Volunteer, type Assignment,
} from '@/services/volunteers.service';
import { useAuthStore } from '@/store/useAuthStore';
import { hasPermission } from '@/lib/permissions';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
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
  Loader2, Plus, MapPin, Users, Check, X, Clock, AlertTriangle, Trash2,
} from 'lucide-react';
import { cn, getErrorMessage } from '@/lib/utils';

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

function NewShiftDialog({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    title: '', description: '', location: '',
    shift_date: '', start_time: '09:00', end_time: '13:00',
    volunteers_needed: 1,
  });

  const create = useMutation({
    mutationFn: () => VolunteersService.createShift({
      ...form,
      description: form.description || undefined,
      location: form.location || undefined,
    }),
    onSuccess: () => {
      toast.success('Shift created.');
      setOpen(false);
      setForm({
        title: '', description: '', location: '',
        shift_date: '', start_time: '09:00', end_time: '13:00', volunteers_needed: 1,
      });
      onCreated();
    },
    onError: (err) => toast.error(getErrorMessage(err) || "Couldn't create the shift."),
  });

  const valid = form.title.trim() && form.shift_date && form.end_time > form.start_time;

  return (
    <>
      <Button className="gap-1.5" onClick={() => setOpen(true)}>
        <Plus className="w-4 h-4" /> New shift
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent>
        <DialogHeader><DialogTitle>New shift</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <Input
            placeholder="Title — e.g. Saturday sterilization clinic"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
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
              <Input type="date" value={form.shift_date}
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
          <div className="space-y-1">
            <label className="text-xs text-text-secondary">Volunteers needed</label>
            <Input type="number" min={1} max={200} value={form.volunteers_needed}
              onChange={(e) => setForm({ ...form, volunteers_needed: Number(e.target.value) })} />
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

function AssignPanel({ shift, volunteers }: { shift: Shift; volunteers: Volunteer[] }) {
  const queryClient = useQueryClient();
  const [picked, setPicked] = useState('');

  const { data: assignments = [] } = useQuery({
    queryKey: ['volunteer-assignments', shift.id],
    queryFn: () => VolunteersService.listAssignments({ shift_id: shift.id }),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['volunteer-assignments', shift.id] });
    queryClient.invalidateQueries({ queryKey: ['volunteer-shifts'] });
  };

  const assign = useMutation({
    mutationFn: (volunteerId: string) =>
      VolunteersService.assign({ volunteer_id: volunteerId, shift_id: shift.id }),
    onSuccess: () => { toast.success('Assigned — notification sent if email is configured.'); setPicked(''); refresh(); },
    onError: (err) => toast.error(getErrorMessage(err) || "Couldn't assign that volunteer."),
  });

  const unassign = useMutation({
    mutationFn: (id: string) => VolunteersService.unassign(id),
    onSuccess: () => { toast.success('Assignment removed.'); refresh(); },
    onError: (err) => toast.error(getErrorMessage(err) || "Couldn't remove that assignment."),
  });

  const byId = new Map(volunteers.map((v) => [v.id, v]));
  const assignedIds = new Set(assignments.map((a) => a.volunteer_id));
  const available = volunteers.filter((v) => !assignedIds.has(v.id));

  const badge = (a: Assignment) =>
    a.response === 'accepted' ? <Badge className="bg-emerald-600 text-white">Accepted</Badge>
    : a.response === 'declined' ? <Badge variant="outline">Declined</Badge>
    : <Badge variant="outline" className="text-amber-600 border-amber-600/40 gap-1">
        <Clock className="w-3 h-3" /> Awaiting
      </Badge>;

  return (
    <div className="space-y-3 pt-3 border-t border-border-brand/50">
      {assignments.length > 0 && (
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
              <Button
                size="sm" variant="ghost"
                aria-label="Remove assignment"
                disabled={unassign.isPending}
                onClick={() => unassign.mutate(a.id)}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      )}

      {!shift.is_cancelled && (
        <div className="flex gap-2">
          <Select value={picked} onValueChange={(v) => { if (typeof v === 'string') setPicked(v); }}>
            <SelectTrigger className="flex-1">
              <SelectValue placeholder={
                available.length ? 'Add a volunteer...' : 'Everyone approved is already assigned'
              } />
            </SelectTrigger>
            <SelectContent>
              {available.map((v) => (
                <SelectItem key={v.id} value={v.id}>{v.full_name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            disabled={!picked || assign.isPending}
            onClick={() => assign.mutate(picked)}
          >
            {assign.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Assign'}
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
      toast.success('Shift cancelled.');
      queryClient.invalidateQueries({ queryKey: ['volunteer-shifts'] });
    },
    onError: (err) => toast.error(getErrorMessage(err) || "Couldn't cancel the shift."),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold font-heading text-text-primary">Shifts</h1>
          <p className="text-sm text-text-secondary mt-1">
            Who is coming, who has answered, and who still needs chasing.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setIncludePast(!includePast)}>
            {includePast ? 'Upcoming only' : 'Include past'}
          </Button>
          {canAssign && (
            <NewShiftDialog
              onCreated={() => queryClient.invalidateQueries({ queryKey: ['volunteer-shifts'] })}
            />
          )}
        </div>
      </div>

      {isLoading ? (
        <div className="py-12 flex justify-center">
          <Loader2 className="w-5 h-5 animate-spin text-text-muted" />
        </div>
      ) : shifts.length === 0 ? (
        <Card><CardContent className="py-12 text-center text-sm text-text-secondary">
          No {includePast ? '' : 'upcoming '}shifts.
        </CardContent></Card>
      ) : (
        <div className="space-y-3">
          {shifts.map((shift) => (
            <Card key={shift.id} className={cn(shift.is_cancelled && 'opacity-60')}>
              <CardContent className="pt-5 space-y-3">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h2 className="font-semibold text-text-primary">{shift.title}</h2>
                      {shift.is_cancelled && <Badge variant="outline">Cancelled</Badge>}
                    </div>
                    <p className="text-sm text-text-secondary mt-0.5">
                      {formatDate(shift.shift_date)} · {shift.start_time.slice(0, 5)}–{shift.end_time.slice(0, 5)}
                    </p>
                    {shift.location && (
                      <p className="text-sm text-text-muted flex items-center gap-1 mt-0.5">
                        <MapPin className="w-3.5 h-3.5" /> {shift.location}
                      </p>
                    )}
                    <div className="mt-2"><ConfirmationLine shift={shift} /></div>
                  </div>

                  <div className="flex flex-col items-end gap-2 shrink-0">
                    <div className="flex items-center gap-1 text-sm text-text-secondary">
                      <Users className="w-4 h-4" />
                      {shift.confirmation.accepted}/{shift.confirmation.needed}
                    </div>
                    <div className="flex gap-2">
                      <Button
                        size="sm" variant="outline"
                        onClick={() => setExpanded(expanded === shift.id ? null : shift.id)}
                      >
                        {expanded === shift.id ? 'Hide' : 'Manage'}
                      </Button>
                      {canAssign && !shift.is_cancelled && (
                        <Button
                          size="sm" variant="ghost"
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
                  <AssignPanel shift={shift} volunteers={volunteers} />
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
