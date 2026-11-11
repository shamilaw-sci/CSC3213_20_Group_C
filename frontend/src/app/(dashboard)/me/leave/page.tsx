'use client';

import { CalendarPlus } from 'lucide-react';
import ProtectedRoute from '@/components/layout/protected-route';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { BalanceCards, LeaveForm, StatusBadge, dateRange, fmtDays } from '@/components/leave/LeaveForm';
import { useCancelLeave, useMyLeave } from '@/hooks/useLeave';
import { toISODate } from '@/lib/finance-periods';

export default function MyLeavePage() {
  return (
    <ProtectedRoute requiredPermission="hr:attendance:self">
      <MyLeave />
    </ProtectedRoute>
  );
}

function MyLeave() {
  const { data, isLoading, error } = useMyLeave();
  const { mutate: cancel, isPending: isCancelling, variables: cancellingId } = useCancelLeave();
  const today = toISODate(new Date());

  return (
    <div className="space-y-6 pb-12">
      <div>
        <h1 className="text-3xl font-bold font-heading tracking-tight mb-2 text-text-primary">My Leave</h1>
        <p className="text-text-secondary text-sm">Your balances for {data?.year ?? new Date().getFullYear()}, and leave you have asked for.</p>
      </div>

      {error ? (
        <p className="rounded-lg border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-500">
          {/* Only a 404 means no linked record; anything else used to say so too. */}
          {(error as { response?: { status?: number } }).response?.status === 404
            ? "Your account isn't linked to an employee record yet. Ask HR to link it."
            : 'Could not load your leave. Refresh to try again.'}
        </p>
      ) : isLoading || !data ? (
        <Skeleton className="h-28 w-full bg-bg-subtle" />
      ) : (
        <>
          <BalanceCards balances={data.balances} />
          {!data.date_joined && (
            <p className="text-xs text-text-muted">
              HR hasn&apos;t recorded your join date yet; your annual and casual leave are set up once they do.
            </p>
          )}

          <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            <Card className="bg-surface border border-border-brand rounded-card shadow-card h-fit">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base font-semibold font-heading text-text-primary">
                  <CalendarPlus className="h-4 w-4 text-accent" /> Request leave
                </CardTitle>
              </CardHeader>
              <CardContent>
                <LeaveForm />
              </CardContent>
            </Card>

            <Card className="bg-surface border border-border-brand rounded-card shadow-card">
              <CardHeader>
                <CardTitle className="text-base font-semibold font-heading text-text-primary">My requests</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                {data.requests.length === 0 ? (
                  <p className="px-6 pb-6 text-sm text-text-muted">No leave requested yet.</p>
                ) : (
                  <table className="w-full text-left text-sm">
                    <thead className="bg-bg-subtle/60 text-[11px] uppercase tracking-wider text-text-secondary">
                      <tr>
                        <th className="px-4 py-2.5 font-semibold">Dates</th>
                        <th className="px-4 py-2.5 font-semibold">Type</th>
                        <th className="px-4 py-2.5 text-right font-semibold">Days</th>
                        <th className="px-4 py-2.5 font-semibold">Status</th>
                        <th className="px-4 py-2.5"><span className="sr-only">Actions</span></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border-brand">
                      {data.requests.map((r) => {
                        const cancellable = r.status === 'Pending' || (r.status === 'Approved' && r.start_date > today);
                        return (
                          <tr key={r.id}>
                            <td className="px-4 py-2.5 text-text-primary">{dateRange(r)}</td>
                            <td className="px-4 py-2.5 text-text-secondary">{r.leave_types?.name}</td>
                            <td className="px-4 py-2.5 text-right font-mono tabular-nums text-text-primary">{fmtDays(Number(r.days))}</td>
                            <td className="px-4 py-2.5">
                              <StatusBadge status={r.status} />
                              {r.decision_note && <p className="mt-1 text-xs text-text-muted">{r.decision_note}</p>}
                            </td>
                            <td className="px-4 py-2.5 text-right">
                              {cancellable && (
                                <Button variant="ghost" size="sm" disabled={isCancelling && cancellingId === r.id}
                                  onClick={() => cancel(r.id)} className="h-7 px-2 text-xs text-text-secondary hover:text-negative">
                                  Cancel
                                </Button>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
