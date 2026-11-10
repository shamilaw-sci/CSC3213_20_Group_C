// frontend/src/app/my-assignments/[token]/page.tsx
'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { VolunteersService, type MyAssignment } from '@/services/volunteers.service';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import {
  Loader2, CalendarDays, MapPin, PawPrint, FolderOpen, Check, X, HeartHandshake,
} from 'lucide-react';
import { cn, getErrorMessage } from '@/lib/utils';

const TYPE_ICON = {
  shift: CalendarDays,
  rescue_case: PawPrint,
  program: FolderOpen,
} as const;

function formatWhen(a: MyAssignment): string | null {
  if (!a.shift_date) return null;
  // Parsed as a plain date, deliberately not through a timezone-aware path.
  // The backend stores wall-clock date/time because a clinic at 9am is at 9am
  // regardless of the reader's device timezone; converting here would shift it.
  const [y, m, d] = a.shift_date.split('-').map(Number);
  const date = new Date(y, m - 1, d).toLocaleDateString('en-GB', {
    weekday: 'long', day: 'numeric', month: 'long',
  });
  if (!a.start_time) return date;
  const hhmm = (t: string) => t.slice(0, 5);
  return a.end_time
    ? `${date}, ${hhmm(a.start_time)}–${hhmm(a.end_time)}`
    : `${date}, ${hhmm(a.start_time)}`;
}

/** A shift whose day has gone. It can no longer be answered (the API refuses). */
function isPast(a: MyAssignment): boolean {
  if (!a.shift_date) return false;
  const now = new Date();
  const today = new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
  return a.shift_date < today;
}

export default function MyAssignmentsPage() {
  const params = useParams<{ token: string }>();
  const token = params?.token ?? '';
  const queryClient = useQueryClient();
  const [decliningId, setDecliningId] = useState<string | null>(null);
  const [reason, setReason] = useState('');

  const { data, isLoading, isError } = useQuery({
    queryKey: ['my-assignments', token],
    queryFn: () => VolunteersService.getMyAssignments(token),
    enabled: Boolean(token),
    // An invalid link will never become valid by retrying, and each retry is
    // another request carrying the token.
    retry: false,
  });

  const respond = useMutation({
    mutationFn: ({ id, response, decline_reason }: {
      id: string; response: 'accepted' | 'declined'; decline_reason?: string;
    }) => VolunteersService.respond(token, id, { response, decline_reason }),
    onSuccess: (_, variables) => {
      toast.success(
        variables.response === 'accepted'
          ? "Thank you — we'll see you there!"
          : "Thanks for letting us know."
      );
      setDecliningId(null);
      setReason('');
      queryClient.invalidateQueries({ queryKey: ['my-assignments', token] });
    },
    onError: (err) => toast.error(getErrorMessage(err) || "Couldn't save your response."),
  });

  if (isLoading) {
    return (
      <div className="min-h-screen bg-bg-subtle flex items-center justify-center">
        <Loader2 className="w-6 h-6 text-[#EF9F27] animate-spin" />
      </div>
    );
  }

  // Every failure mode lands here with the same message — unknown token, not
  // yet approved, rejected, deactivated. The API deliberately returns an
  // identical 404 for all of them, and this page must not undo that by
  // inferring more than it was told. No stack trace, no raw error text.
  if (isError || !data) {
    return (
      <div className="min-h-screen bg-bg-subtle flex items-center justify-center px-4">
        <Card className="bg-surface border-border-brand/50 rounded-2xl shadow-card max-w-md w-full">
          <CardContent className="pt-8 pb-8 flex flex-col items-center gap-3 text-center">
            <HeartHandshake className="w-10 h-10 text-text-muted" />
            <h1 className="text-lg font-bold font-heading text-text-primary">
              This link is not valid
            </h1>
            <p className="text-sm text-text-secondary leading-relaxed max-w-sm">
              It may have been mistyped, or it may no longer be active. Please
              check the message we sent you, or get in touch and we will send a
              fresh one.
            </p>
            <a
              href="mailto:vetsforfuturesl@gmail.com"
              className="text-sm text-[#EF9F27] hover:underline mt-1"
            >
              vetsforfuturesl@gmail.com
            </a>
          </CardContent>
        </Card>
      </div>
    );
  }

  const awaiting = data.assignments.filter(
    (a) => a.response === 'pending' && !a.is_cancelled && !isPast(a)
  ).length;

  return (
    <div className="min-h-screen bg-bg-subtle text-text-primary">
      <header className="bg-[#0B0D12] px-4 py-10">
        <div className="max-w-2xl mx-auto text-center space-y-2">
          <HeartHandshake className="w-9 h-9 text-[#EF9F27] mx-auto" />
          <h1 className="text-2xl md:text-3xl font-bold font-heading text-white">
            Hello, {data.volunteer_name}
          </h1>
          <p className="text-sm text-white/80">
            {awaiting > 0
              ? `${awaiting} thing${awaiting === 1 ? '' : 's'} need${awaiting === 1 ? 's' : ''} your answer`
              : 'You are all caught up — thank you!'}
          </p>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-8 space-y-4">
        {data.assignments.length === 0 && (
          <Card className="bg-surface border-border-brand/50 rounded-2xl">
            <CardContent className="py-10 text-center text-sm text-text-secondary">
              Nothing has been assigned to you yet. We will be in touch when
              something comes up.
            </CardContent>
          </Card>
        )}

        {data.assignments.map((a) => {
          const Icon = TYPE_ICON[a.assignment_type];
          const when = formatWhen(a);
          return (
            <Card
              key={a.id}
              className={cn(
                'bg-surface border-border-brand/50 rounded-2xl shadow-card',
                a.is_cancelled && 'opacity-60'
              )}
            >
              <CardContent className="pt-5 space-y-3">
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 shrink-0 w-9 h-9 rounded-full bg-[#EF9F27]/10 flex items-center justify-center">
                    <Icon className="w-4 h-4 text-[#EF9F27]" />
                  </span>
                  <div className="flex-1 min-w-0">
                    <h2 className="font-semibold text-text-primary leading-snug">
                      {a.title}
                    </h2>
                    {when && (
                      <p className="text-sm text-text-secondary mt-0.5">{when}</p>
                    )}
                    {a.location && (
                      <p className="text-sm text-text-secondary flex items-center gap-1 mt-0.5">
                        <MapPin className="w-3.5 h-3.5" /> {a.location}
                      </p>
                    )}
                    {a.description && (
                      <p className="text-sm text-text-muted mt-2 leading-relaxed">
                        {a.description}
                      </p>
                    )}
                  </div>
                  {a.is_cancelled ? (
                    <Badge variant="outline" className="shrink-0">Cancelled</Badge>
                  ) : a.response === 'accepted' ? (
                    <Badge className="bg-emerald-600 text-white shrink-0">Going</Badge>
                  ) : a.response === 'declined' ? (
                    <Badge variant="outline" className="shrink-0">Can&apos;t make it</Badge>
                  ) : isPast(a) ? (
                    <Badge variant="outline" className="shrink-0">Past</Badge>
                  ) : null}
                </div>

                {!a.is_cancelled && !isPast(a) && (
                  <>
                    {decliningId === a.id ? (
                      <div className="space-y-2 pt-1">
                        <textarea
                          value={reason}
                          onChange={(e) => setReason(e.target.value)}
                          placeholder="Anything you'd like us to know? (optional)"
                          rows={2}
                          maxLength={500}
                          className="w-full rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                        />
                        <div className="flex gap-2">
                          <Button
                            variant="outline"
                            className="flex-1"
                            onClick={() => { setDecliningId(null); setReason(''); }}
                          >
                            Back
                          </Button>
                          <Button
                            className="flex-1"
                            disabled={respond.isPending}
                            onClick={() => respond.mutate({
                              id: a.id,
                              response: 'declined',
                              decline_reason: reason.trim() || undefined,
                            })}
                          >
                            Confirm
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex gap-2 pt-1">
                        <Button
                          className={cn(
                            'flex-1',
                            a.response === 'accepted'
                              ? 'bg-emerald-600 hover:bg-emerald-600/90 text-white'
                              : 'bg-[#EF9F27] hover:bg-[#EF9F27]/90 text-white'
                          )}
                          disabled={respond.isPending}
                          onClick={() => respond.mutate({ id: a.id, response: 'accepted' })}
                        >
                          <Check className="w-4 h-4 mr-1.5" />
                          {a.response === 'accepted' ? "I'm going" : 'I can make it'}
                        </Button>
                        <Button
                          variant="outline"
                          className="flex-1"
                          disabled={respond.isPending}
                          onClick={() => setDecliningId(a.id)}
                        >
                          <X className="w-4 h-4 mr-1.5" />
                          Can&apos;t make it
                        </Button>
                      </div>
                    )}
                    {a.response !== 'pending' && (
                      // Responses can be changed at any time; saying so matters
                      // more than it looks, because plans change and a stale
                      // "declined" is worse for the rota than a late switch.
                      <p className="text-xs text-text-muted">
                        You can change your answer any time.
                        {a.decline_reason && ` You said: “${a.decline_reason}”`}
                      </p>
                    )}
                  </>
                )}
              </CardContent>
            </Card>
          );
        })}

        <p className="text-xs text-text-muted text-center pt-4 leading-relaxed">
          This page is personal to you — please don&apos;t forward the link.
        </p>
      </main>
    </div>
  );
}
