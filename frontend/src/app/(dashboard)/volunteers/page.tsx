// frontend/src/app/(dashboard)/volunteers/page.tsx
'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  VolunteersService, volunteerLinkFor, SKILLS, AVAILABILITY,
  type Volunteer, type VolunteerStatus,
} from '@/services/volunteers.service';
import { useAuthStore } from '@/store/useAuthStore';
import { hasPermission } from '@/lib/permissions';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { toast } from 'sonner';
import { Loader2, Copy, Check, X, Link2, AlertTriangle } from 'lucide-react';
import { cn, getErrorMessage } from '@/lib/utils';

const LABEL = Object.fromEntries(
  [...SKILLS, ...AVAILABILITY].map((o) => [o.value, o.label])
) as Record<string, string>;

function relativeDays(iso?: string | null): string {
  if (!iso) return 'Never shared';
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return 'Link shared today';
  if (days === 1) return 'Link shared yesterday';
  return `Link shared ${days} days ago`;
}

export default function VolunteersRosterPage() {
  const { user } = useAuthStore();
  const canApprove = hasPermission(user?.role || '', 'volunteers:approve');
  const canAssign = hasPermission(user?.role || '', 'volunteers:assign');
  // Sharing a link is contact, not a vetting or scheduling decision, so either
  // permission grants it. Mirrors require_any_permission on the endpoint —
  // hiding the button for one of the two roles would strand them.
  const canShareLink = canApprove || canAssign;

  const [tab, setTab] = useState<VolunteerStatus>('pending');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data: volunteers = [], isLoading } = useQuery({
    queryKey: ['volunteers', tab],
    queryFn: () => VolunteersService.list(tab),
  });

  const review = useMutation({
    mutationFn: ({ id, status }: { id: string; status: 'approved' | 'rejected' | 'inactive' }) =>
      VolunteersService.review(id, { status }),
    onSuccess: (_, v) => {
      toast.success(
        v.status === 'approved'
          ? 'Approved — welcome email sent if email is configured.'
          : v.status === 'rejected' ? 'Application rejected.' : 'Volunteer deactivated.'
      );
      queryClient.invalidateQueries({ queryKey: ['volunteers'] });
    },
    onError: (err) => toast.error(getErrorMessage(err) || "Couldn't update this volunteer."),
  });

  const markShared = useMutation({
    mutationFn: (id: string) => VolunteersService.markLinkShared(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['volunteers'] }),
    // Deliberately quiet on failure: the copy itself already succeeded, so the
    // coordinator has what they need. Only the bookkeeping failed.
    onError: () => toast.warning('Link copied, but we could not record that.'),
  });

  async function copyLink(v: Volunteer) {
    const link = volunteerLinkFor(v.access_token);
    try {
      await navigator.clipboard.writeText(link);
    } catch {
      toast.error('Could not copy — your browser blocked clipboard access.');
      return;
    }
    setCopiedId(v.id);
    setTimeout(() => setCopiedId(null), 2000);
    toast.success(`Link copied — send it to ${v.full_name.split(' ')[0]}.`);
    markShared.mutate(v.id);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold font-heading text-text-primary">Volunteers</h1>
        <p className="text-sm text-text-secondary mt-1">
          Review applications and manage the approved roster.
        </p>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as VolunteerStatus)}>
        <TabsList>
          <TabsTrigger value="pending">Pending</TabsTrigger>
          <TabsTrigger value="approved">Approved</TabsTrigger>
          <TabsTrigger value="rejected">Rejected</TabsTrigger>
          <TabsTrigger value="inactive">Inactive</TabsTrigger>
        </TabsList>
      </Tabs>

      <Card>
        <CardContent className="pt-6">
          {isLoading ? (
            <div className="py-12 flex justify-center">
              <Loader2 className="w-5 h-5 animate-spin text-text-muted" />
            </div>
          ) : volunteers.length === 0 ? (
            <p className="py-12 text-center text-sm text-text-secondary">
              No {tab} volunteers.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Contact</TableHead>
                  <TableHead>Can help with</TableHead>
                  <TableHead>Available</TableHead>
                  {tab === 'approved' && <TableHead>Personal link</TableHead>}
                  <TableHead className="text-right whitespace-nowrap">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {volunteers.map((v) => (
                  <TableRow key={v.id}>
                    <TableCell className="font-medium align-top">{v.full_name}</TableCell>
                    <TableCell className="text-sm text-text-secondary align-top">
                      <div className="break-all max-w-[190px]">{v.email}</div>
                      {v.phone && <div className="text-text-muted">{v.phone}</div>}
                    </TableCell>
                    {/* The width constraint lives on the inner div, not the
                        cell. With table-layout:auto a browser sizes columns by
                        content and treats max-width on a <td> as a suggestion,
                        so constraining the cell alone does not stop the column
                        growing — which is what pushed Actions off the edge. */}
                    <TableCell className="align-top">
                      <div className="flex flex-wrap gap-1 max-w-[200px]">
                        {v.skills.map((s) => (
                          <Badge key={s} variant="outline" className="text-[10px]">
                            {LABEL[s] ?? s}
                          </Badge>
                        ))}
                        {v.skills_other && (
                          <span className="text-xs text-text-muted">{v.skills_other}</span>
                        )}
                      </div>
                    </TableCell>
                    {/* Badges rather than a comma-joined string: a volunteer can
                        pick all five options, and as one line that cell forced
                        the table wider than its container and pushed the Actions
                        column off the edge. A fixed max width makes it wrap. */}
                    <TableCell className="align-top">
                      {v.availability.length === 0 ? (
                        <span className="text-xs text-text-muted">—</span>
                      ) : (
                        <div className="flex flex-wrap gap-1 max-w-[170px]">
                          {v.availability.map((a) => (
                            <Badge key={a} variant="outline" className="text-[10px]">
                              {LABEL[a] ?? a}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </TableCell>

                    {tab === 'approved' && (
                      <TableCell>
                        {canShareLink ? (
                          <div className="space-y-1">
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => copyLink(v)}
                              className="gap-1.5"
                            >
                              {copiedId === v.id
                                ? <Check className="w-3.5 h-3.5 text-emerald-600" />
                                : <Copy className="w-3.5 h-3.5" />}
                              {copiedId === v.id ? 'Copied' : 'Copy link'}
                            </Button>
                            {/* Surfaced rather than buried: email on the free
                                tier often lands in spam, so "never shared" is
                                the signal that nobody has actually reached this
                                person yet. */}
                            <div
                              className={cn(
                                'text-[11px] flex items-center gap-1',
                                v.link_shared_at ? 'text-text-muted' : 'text-amber-600'
                              )}
                            >
                              {v.link_shared_at
                                ? <Link2 className="w-3 h-3" />
                                : <AlertTriangle className="w-3 h-3" />}
                              {relativeDays(v.link_shared_at)}
                            </div>
                          </div>
                        ) : (
                          <span className="text-xs text-text-muted">—</span>
                        )}
                      </TableCell>
                    )}

                    <TableCell className="text-right align-top whitespace-nowrap">
                      <div className="flex gap-2 justify-end">
                        {tab === 'pending' && canApprove && (
                          <>
                            <Button
                              size="sm"
                              disabled={review.isPending}
                              onClick={() => review.mutate({ id: v.id, status: 'approved' })}
                              className="bg-emerald-600 hover:bg-emerald-600/90 text-white gap-1"
                            >
                              <Check className="w-3.5 h-3.5" /> Approve
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={review.isPending}
                              onClick={() => review.mutate({ id: v.id, status: 'rejected' })}
                              className="gap-1"
                            >
                              <X className="w-3.5 h-3.5" /> Reject
                            </Button>
                          </>
                        )}
                        {tab === 'approved' && canApprove && (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={review.isPending}
                            onClick={() => review.mutate({ id: v.id, status: 'inactive' })}
                          >
                            Deactivate
                          </Button>
                        )}
                        {!canApprove && tab !== 'approved' && (
                          <span className="text-xs text-text-muted">View only</span>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
