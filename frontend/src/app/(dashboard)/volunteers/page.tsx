// frontend/src/app/(dashboard)/volunteers/page.tsx
'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  VolunteersService, volunteerLinkFor, SKILLS, AVAILABILITY,
  type Volunteer, type VolunteerStatus,
} from '@/services/volunteers.service';
import { useAuthStore } from '@/store/useAuthStore';
import ProtectedRoute from '@/components/layout/protected-route';
import { hasPermission } from '@/lib/permissions';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { KPICard } from '@/components/shared/kpi-card';
import { Badge } from '@/components/ui/badge';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { toast } from 'sonner';
import { Copy, Check, X, Link2, AlertTriangle, RotateCcw, Loader2 } from 'lucide-react';
import { cn, getErrorMessage } from '@/lib/utils';

const LABEL = Object.fromEntries(
  [...SKILLS, ...AVAILABILITY].map((o) => [o.value, o.label])
) as Record<string, string>;

const STATUS_TABS: { value: VolunteerStatus; label: string; description: string }[] = [
  { value: 'pending', label: 'Pending', description: 'New applications waiting for a decision.' },
  { value: 'approved', label: 'Approved', description: 'Active volunteers who can be assigned to shifts.' },
  { value: 'rejected', label: 'Rejected', description: 'Applications that were turned down. They may apply again.' },
  { value: 'inactive', label: 'Inactive', description: 'Volunteers who have been deactivated. Reactivating gives them a new personal link.' },
];

// Actions that need a second click (V10). Approve stays one click.
type ConfirmKind = 'rejected' | 'inactive' | 'reactivate' | 'reset';

const CONFIRM: Record<ConfirmKind, { title: string; body: string; button: string }> = {
  rejected: {
    title: 'Reject this application?',
    body: 'They will not be able to take shifts. They can apply again later.',
    button: 'Reject',
  },
  inactive: {
    title: 'Deactivate this volunteer?',
    body: 'Their personal link stops working, and they are taken off shifts from today on and off anything they have not answered yet. Past shifts stay on record.',
    button: 'Deactivate',
  },
  reactivate: {
    title: 'Reactivate this volunteer?',
    body: 'They become an approved volunteer again with a new personal link. The welcome email with the new link is sent if email is configured.',
    button: 'Reactivate',
  },
  reset: {
    title: 'Reset this personal link?',
    body: 'The old link stops working at once. The new link is emailed to them if email is configured, and you can copy it here.',
    button: 'Reset link',
  },
};

function relativeDays(iso?: string | null): string {
  if (!iso) return 'Never shared';
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return 'Link shared today';
  if (days === 1) return 'Link shared yesterday';
  return `Link shared ${days} days ago`;
}

// The sidebar hides this page from roles without volunteers:read, but a URL typed by
// hand bypasses the sidebar, so the page checks for itself.
export default function VolunteersRosterPage() {
  return (
    <ProtectedRoute requiredPermission="volunteers:read">
      <VolunteersRosterContent />
    </ProtectedRoute>
  );
}

function VolunteersRosterContent() {
  const { user } = useAuthStore();
  const canApprove = hasPermission(user?.role || '', 'volunteers:approve');
  const canAssign = hasPermission(user?.role || '', 'volunteers:assign');
  // Sharing a link is contact, not a vetting or scheduling decision, so either
  // permission grants it. Mirrors require_any_permission on the endpoint —
  // hiding the button for one of the two roles would strand them.
  const canShareLink = canApprove || canAssign;

  const [tab, setTab] = useState<VolunteerStatus>('pending');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<{ v: Volunteer; kind: ConfirmKind } | null>(null);
  const queryClient = useQueryClient();

  // One fetch of every status rather than one per tab, so the summary cards
  // and tab counts come from the same rows the table shows. Invalidating
  // ['volunteers'] after a review still refreshes it.
  const { data: allVolunteers = [], isLoading } = useQuery({
    queryKey: ['volunteers', 'all'],
    queryFn: () => VolunteersService.list(),
  });
  const volunteers = allVolunteers.filter((v) => v.status === tab);
  const counts = STATUS_TABS.reduce(
    (acc, s) => ({ ...acc, [s.value]: allVolunteers.filter((v) => v.status === s.value).length }),
    {} as Record<VolunteerStatus, number>
  );
  const neverContacted = allVolunteers.filter(
    (v) => v.status === 'approved' && !v.link_shared_at
  ).length;

  const review = useMutation({
    mutationFn: ({ id, status }: { id: string; status: 'approved' | 'rejected' | 'inactive' }) =>
      VolunteersService.review(id, { status }),
    onSuccess: (_, v) => {
      toast.success(
        v.status === 'approved'
          ? 'Approved — welcome email sent if email is configured.'
          : v.status === 'rejected' ? 'Application rejected.' : 'Volunteer deactivated.'
      );
      setConfirm(null);
      queryClient.invalidateQueries({ queryKey: ['volunteers'] });
    },
    onError: (err) => toast.error(getErrorMessage(err) || "Couldn't update this volunteer."),
  });

  const resetLink = useMutation({
    mutationFn: (id: string) => VolunteersService.resetLink(id),
    onSuccess: () => {
      toast.success('New link made — emailed to them if email is configured.');
      setConfirm(null);
      queryClient.invalidateQueries({ queryKey: ['volunteers'] });
    },
    onError: (err) => toast.error(getErrorMessage(err) || "Couldn't reset the link."),
  });

  function runConfirmed() {
    if (!confirm) return;
    const { v, kind } = confirm;
    if (kind === 'reset') resetLink.mutate(v.id);
    else review.mutate({ id: v.id, status: kind === 'reactivate' ? 'approved' : kind });
  }
  const confirmBusy = review.isPending || resetLink.isPending;

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
    <div className="space-y-8 pb-12">
      {/* Header, in the finance pages' shape */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold font-heading tracking-tight mb-2 text-text-primary">
            Volunteer Applications
          </h1>
          <p className="text-text-secondary text-sm">
            Review and manage volunteer applications across all programs.
          </p>
        </div>
      </div>

      {/* KPI strip */}
      <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        <KPICard title="Awaiting Review" value={isLoading ? '—' : counts.pending} />
        <KPICard title="Approved Volunteers" value={isLoading ? '—' : counts.approved} />
        <KPICard title="Never Contacted" value={isLoading ? '—' : neverContacted} />
        <KPICard title="Total Applications" value={isLoading ? '—' : allVolunteers.length} />
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as VolunteerStatus)}>
        {/* Larger than the default tab size: these are the page's primary
            navigation, and the default h-8 was easy to miss and to mis-tap.
            The group-data-horizontal height has to be overridden with the
            same variant, or tailwind-merge keeps the original h-8. */}
        <TabsList className="w-full sm:w-fit p-1 group-data-horizontal/tabs:h-12 bg-bg-subtle border border-border-brand overflow-x-auto">
          {STATUS_TABS.map((s) => (
            <TabsTrigger
              key={s.value}
              value={s.value}
              className="px-4 sm:px-5 text-sm sm:text-base font-semibold gap-2 data-active:bg-surface data-active:text-text-primary"
            >
              {s.label}
              <span
                className={cn(
                  'min-w-6 rounded-full px-1.5 py-0.5 text-xs font-mono',
                  tab === s.value ? 'bg-accent/15 text-accent' : 'bg-surface/70 text-text-secondary'
                )}
              >
                {isLoading ? '·' : counts[s.value]}
              </span>
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <Card className="bg-surface border border-border-brand rounded-card shadow-card overflow-hidden">
        <CardHeader className="px-5 pt-5 pb-0">
          <CardTitle className="text-base font-semibold font-heading text-text-primary">
            {STATUS_TABS.find((s) => s.value === tab)?.label} Applications
          </CardTitle>
          <CardDescription className="text-text-secondary text-xs mt-1">
            {STATUS_TABS.find((s) => s.value === tab)?.description}
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0 pt-4">
          {isLoading ? (
            <div className="space-y-3 p-5">
              {[1, 2, 3].map((i) => <Skeleton key={i} className="h-10 w-full bg-bg-subtle" />)}
            </div>
          ) : volunteers.length === 0 ? (
            <p className="py-12 text-center text-sm text-text-muted">
              No {tab} volunteers.
            </p>
          ) : (
            <Table>
              <TableHeader className="bg-bg-subtle/60 [&_th]:text-[11px] [&_th]:uppercase [&_th]:tracking-wider [&_th]:font-semibold [&_th]:text-text-secondary [&_th:first-child]:pl-5 [&_th:last-child]:pr-5">
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Contact</TableHead>
                  <TableHead>Can help with</TableHead>
                  <TableHead>Available</TableHead>
                  {tab === 'approved' && <TableHead>Personal link</TableHead>}
                  <TableHead className="text-right whitespace-nowrap">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody className="[&_td:first-child]:pl-5 [&_td:last-child]:pr-5">
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
                            {canApprove && (
                              <button
                                type="button"
                                onClick={() => setConfirm({ v, kind: 'reset' })}
                                className="text-[11px] text-text-secondary hover:text-accent flex items-center gap-1"
                              >
                                <RotateCcw className="w-3 h-3" /> Reset link
                              </button>
                            )}
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
                              onClick={() => setConfirm({ v, kind: 'rejected' })}
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
                            onClick={() => setConfirm({ v, kind: 'inactive' })}
                          >
                            Deactivate
                          </Button>
                        )}
                        {tab === 'inactive' && canApprove && (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={review.isPending}
                            onClick={() => setConfirm({ v, kind: 'reactivate' })}
                          >
                            Reactivate
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

      <Dialog open={!!confirm} onOpenChange={(open) => { if (!open && !confirmBusy) setConfirm(null); }}>
        <DialogContent>
          {confirm && (
            <>
              <DialogHeader>
                <DialogTitle>{CONFIRM[confirm.kind].title}</DialogTitle>
                <DialogDescription>
                  <strong className="text-text-primary">{confirm.v.full_name}</strong> — {CONFIRM[confirm.kind].body}
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={() => setConfirm(null)} disabled={confirmBusy}>
                  Cancel
                </Button>
                <Button
                  onClick={runConfirmed}
                  disabled={confirmBusy}
                  className={confirm.kind === 'reactivate' ? undefined : 'bg-red-600 hover:bg-red-600/90 text-white'}
                >
                  {confirmBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : CONFIRM[confirm.kind].button}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
