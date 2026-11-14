'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams, useRouter } from 'next/navigation';
import { ProgramService } from '@/services/program.service';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { ArrowLeft, Users, X, UserPlus, Lock, HeartHandshake, CalendarClock } from 'lucide-react';
import { SKILLS } from '@/services/volunteers.service';
import { FinanceService } from '@/services/finance.service';
import { useAuthStore } from '@/store/useAuthStore';
import { hasPermission } from '@/lib/permissions';
import { formatLKR } from '@/lib/formatters';
import { toast } from 'sonner';
import ProtectedRoute from '@/components/layout/protected-route';
import {
  CancelProgramButton, EditAnimalsTreatedButton, EditProgramDetailsButton, EditableProgramLocation, STAGE_BADGE, STAGE_PATH,
  TransitionButton, asStage, daysBetween, formatDay, moneyAccess,
} from '@/components/programs/program-lifecycle';
import { cn, getErrorMessage } from '@/lib/utils';

// The gate wraps the content rather than sitting inside it, so the content's
// requests never fire for a role that would only get 403s back.
export default function ProgramDetailsPage() {
  return (
    <ProtectedRoute requiredPermission="programs:read">
      <ProgramDetailsContent />
    </ProtectedRoute>
  );
}

function ProgramDetailsContent() {
  const params = useParams();
  const router = useRouter();
  const programId = Number(params.id);
  const queryClient = useQueryClient();

  const [selectedEmployeeId, setSelectedEmployeeId] = useState('');
  const [roleInput, setRoleInput] = useState('');

  const { data: program, isLoading: programLoading } = useQuery({
    queryKey: ['program', programId],
    queryFn: () => ProgramService.getProgram(programId),
  });

  const { data: team, isLoading: teamLoading } = useQuery({
    queryKey: ['program-team', programId],
    queryFn: () => ProgramService.getTeam(programId),
  });

  const { data: volunteers, isLoading: volunteersLoading } = useQuery({
    queryKey: ['program-volunteers', programId],
    queryFn: () => ProgramService.getVolunteers(programId),
    enabled: !Number.isNaN(programId),
  });

  // The restricted-balance endpoint is gated on finance:read, which Staff do
  // not hold. Guarding the query avoids a guaranteed 403 on every page load
  // for the role that most often opens this view.
  const { user } = useAuthStore();
  const canReadFinance = hasPermission(user?.role as string, 'finance:read');
  const canManage = hasPermission(user?.role as string, 'programs:manage');
  // Revenue and profit need finance:read; cost needs finance:read or
  // inventory:read. The API leaves out what the role may not see.
  const money = moneyAccess(user?.role as string);
  const stage = asStage(program?.status);
  // A completed or cancelled program's team is a record, not a roster: the
  // API refuses changes, so the controls are not offered.
  const teamEditable = canManage && (stage === 'Upcoming' || stage === 'Active');

  const { data: financials } = useQuery({
    queryKey: ['program-financials', programId],
    queryFn: () => ProgramService.getFinancials(programId),
    enabled: money.finances && !Number.isNaN(programId),
  });

  // Active employees to pick from. Comes from the programs API so an
  // Operations Lead (no HR access) can build a team.
  const { data: employees } = useQuery({
    queryKey: ['program-assignable-employees'],
    queryFn: ProgramService.getAssignableEmployees,
    enabled: teamEditable,
  });

  const { data: restricted } = useQuery({
    queryKey: ['restrictedBalance', programId],
    queryFn: () => FinanceService.getRestrictedBalance(programId),
    enabled: canReadFinance && !Number.isNaN(programId),
    retry: false,
  });

  const assignWorker = useMutation({
    mutationFn: () =>
      ProgramService.assignWorker(programId, {
        employee_id: Number(selectedEmployeeId),
        role_on_program: roleInput || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['program-team', programId] });
      toast.success('Worker assigned to program');
      setSelectedEmployeeId('');
      setRoleInput('');
    },
    onError: (err) => {
      toast.error(getErrorMessage(err) || 'Failed to assign worker');
    },
  });

  const removeWorker = useMutation({
    mutationFn: (assignmentId: number) => ProgramService.removeWorker(programId, assignmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['program-team', programId] });
      toast.success('Worker removed');
    },
    onError: () => {
      toast.error('Failed to remove worker');
    },
  });

  // Employees not already on the team, so the dropdown doesn't offer duplicates
  const availableEmployees = (employees || []).filter(
    (e) => !(team || []).some((t) => t.employee_id === e.id)
  );

  return (
    <>
      <div className="space-y-6 pb-12">
        <Button
          variant="ghost" size="sm"
          onClick={() => router.push(program ? STAGE_PATH[stage] : '/programs')}
          className="-ml-2 text-xs"
        >
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to {program ? `${stage} Programs` : 'Programs'}
        </Button>

        {programLoading ? (
          <Skeleton className="h-24 w-full rounded-xl" />
        ) : !program ? (
          <p className="text-text-secondary text-sm">Program not found.</p>
        ) : (
          <>
            {/* Basic Info */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-3 flex-wrap">
                  <h1 className="text-3xl font-bold font-heading tracking-tight text-text-primary">{program.program_name}</h1>
                  <Badge variant="outline" className={cn('text-xs w-fit', STAGE_BADGE[stage])}>{stage}</Badge>
                  {canManage && stage === 'Upcoming' && <EditProgramDetailsButton program={program} />}
                </div>
                <div className="mt-2">
                  <EditableProgramLocation program={program} canEdit={canManage} />
                </div>
                <p className="text-text-secondary text-sm mt-1">
                  {stage === 'Upcoming' && (program.start_date
                    ? `Start date ${formatDay(program.start_date)}`
                    : 'No start date planned yet')}
                  {stage === 'Active' && (program.start_date
                    ? `Started ${formatDay(program.start_date)} · running ${Math.max(0, daysBetween(program.start_date))} days`
                    : 'Start date not recorded')}
                  {stage === 'Completed' && (
                    <>
                      {program.start_date ? formatDay(program.start_date) : '—'} → {formatDay(program.end_date)}
                      {program.start_date && program.end_date &&
                        ` · ${daysBetween(program.start_date, program.end_date) + 1} days`}
                    </>
                  )}
                  {stage === 'Cancelled' && 'This program was cancelled before it started.'}
                </p>
              </div>
              {canManage && (stage === 'Upcoming' || stage === 'Active') && (
                <div className="flex flex-wrap gap-2">
                  <CancelProgramButton program={program} stage={stage} size="default" />
                  <TransitionButton program={program} stage={stage} size="default" />
                </div>
              )}
            </div>

            {/* Stats */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-5">
              <StatBox label="Start Date" value={formatDay(program.start_date)} />
              {stage === 'Completed' && <StatBox label="End Date" value={formatDay(program.end_date)} />}
              {/* The animal count is recorded when the program is marked as
                  completed, so it and cost per animal only mean something
                  then. Cost / animal is total cost / animals treated — the
                  same sum the program cards and list API use. */}
              {stage === 'Completed' && (
                <StatBox
                  label="Animals Treated"
                  value={(program.total_animals_treated ?? 0).toLocaleString()}
                  action={canManage ? <EditAnimalsTreatedButton program={program} /> : undefined}
                />
              )}
              {money.costs && <StatBox label="Total Cost" value={formatLKR(program.total_cost ?? 0)} />}
              {money.costs && stage === 'Completed' && (
                <StatBox
                  label="Cost / Animal"
                  value={program.total_animals_treated
                    ? formatLKR((program.total_cost ?? 0) / program.total_animals_treated)
                    : '—'}
                  hint={program.total_animals_treated
                    ? undefined
                    : 'Needs the number of animals treated (0 recorded).'}
                />
              )}
              <StatBox label="Workers Assigned" value={team?.length ?? 0} />
              {money.finances && (
                <>
                  <StatBox
                    label="Revenue"
                    value={financials ? formatLKR(financials.revenue) : '—'}
                  />
                  <StatBox
                    label="Profit"
                    value={financials ? formatLKR(financials.profit) : '—'}
                    valueClassName={financials && financials.profit < 0 ? 'text-red-500' : 'text-positive'}
                  />
                </>
              )}
            </div>

            {/* Restricted funds — only rendered when the program actually holds
                earmarked money, so unrestricted programs are not cluttered
                with three zeroes. */}
            {restricted && restricted.raised > 0 && (
              <Card className="bg-surface border border-border-brand rounded-card">
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Lock size={16} className="text-accent" /> Restricted Funds
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <StatBox
                      label="Raised"
                      value={formatLKR(restricted.raised)}
                    />
                    <StatBox
                      label="Spent"
                      value={formatLKR(restricted.spent)}
                    />
                    <StatBox
                      label="Remaining"
                      value={formatLKR(restricted.remaining)}
                      valueClassName={restricted.remaining < 0 ? 'text-red-500' : 'text-positive'}
                    />
                  </div>
                  <p className="text-[10px] text-text-secondary mt-3 leading-relaxed">
                    Donations earmarked for this program. Only received (Cash) donations
                    count as raised; outstanding pledges do not.
                    {restricted.remaining < 0 &&
                      ' This program is overdrawn — expenses exceed the funds raised for it.'}
                  </p>
                </CardContent>
              </Card>
            )}

            {/* Team Section */}
            <Card className="bg-surface border border-border-brand rounded-card">
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <Users size={18} className="text-accent" /> Program Team
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Add worker form */}
                {teamEditable && (
                <div className="flex flex-col sm:flex-row gap-2">
                  <select
                    className="flex-1 h-10 rounded-lg border border-border-brand bg-bg-subtle px-3 text-xs text-text-primary"
                    value={selectedEmployeeId}
                    onChange={(e) => setSelectedEmployeeId(e.target.value)}
                  >
                    <option value="">Select employee...</option>
                    {availableEmployees.map((e) => (
                      <option key={e.id} value={e.id}>
                        {e.first_name} {e.last_name}
                      </option>
                    ))}
                  </select>
                  <Input
                    placeholder="Role (e.g. Veterinarian)"
                    value={roleInput}
                    onChange={(e) => setRoleInput(e.target.value)}
                    className="sm:w-48 h-10 text-xs"
                  />
                  <Button
                    size="sm"
                    className="h-10 text-xs bg-accent hover:bg-accent/80 text-white"
                    disabled={!selectedEmployeeId || assignWorker.isPending}
                    onClick={() => assignWorker.mutate()}
                  >
                    <UserPlus className="mr-2 h-4 w-4" /> Add
                  </Button>
                </div>
                )}

                {/* Team list */}
                {teamLoading ? (
                  <Skeleton className="h-16 w-full rounded-lg" />
                ) : !team || team.length === 0 ? (
                  <p className="text-text-secondary text-xs py-4 text-center">No workers assigned yet.</p>
                ) : (
                  <div className="space-y-2">
                    {team.map((member) => (
                      <div
                        key={member.id}
                        className="flex items-center justify-between bg-bg-subtle border border-border-brand rounded-lg px-4 py-2.5"
                      >
                        <div>
                          <p className="text-sm text-text-primary font-medium">
                            {member.employee_profile?.first_name} {member.employee_profile?.last_name}
                          </p>
                          <p className="text-[10px] text-text-secondary uppercase tracking-wide">
                            {member.role_on_program || 'No role specified'}
                          </p>
                        </div>
                        {teamEditable && (
                          <Button
                            variant="ghost"
                            size="sm"
                            aria-label="Remove from team"
                            className="h-7 w-7 p-0 text-text-secondary hover:text-red-500"
                            onClick={() => removeWorker.mutate(member.id)}
                          >
                            <X size={14} />
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Volunteers — only those who accepted, through their personal
                link, a shift for this program (linked by program, or by title
                for older shifts) or a direct assignment to the program. Pending and declined answers and
                cancelled shifts are filtered out by the API. */}
            <Card className="bg-surface border border-border-brand rounded-card">
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <HeartHandshake size={18} className="text-accent" /> Volunteers
                  {volunteers && volunteers.length > 0 && (
                    <Badge variant="outline" className="text-[10px] ml-1">{volunteers.length}</Badge>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {volunteersLoading ? (
                  <Skeleton className="h-16 w-full rounded-lg" />
                ) : !volunteers || volunteers.length === 0 ? (
                  <p className="text-text-secondary text-xs py-4 text-center">
                    No volunteers have accepted shifts for this programme yet.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {volunteers.map((v) => (
                      <div
                        key={v.volunteer_id}
                        className="bg-bg-subtle border border-border-brand rounded-lg px-4 py-2.5 space-y-2"
                      >
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                          <p className="text-sm text-text-primary font-medium">{v.full_name}</p>
                          <div className="flex flex-wrap gap-1">
                            {v.skills.map((s) => (
                              <Badge key={s} variant="outline" className="text-[10px]">
                                {SKILL_LABEL[s] ?? s}
                              </Badge>
                            ))}
                            {v.skills_other && (
                              <span className="text-[10px] text-text-secondary">{v.skills_other}</span>
                            )}
                          </div>
                        </div>
                        <ul className="space-y-1">
                          {v.shifts.map((s) => (
                            <li key={s.shift_id} className="flex items-center gap-1.5 text-[11px] text-text-secondary">
                              <CalendarClock size={12} className="text-accent shrink-0" />
                              {formatShiftDate(s.shift_date)} · {s.start_time.slice(0, 5)}–{s.end_time.slice(0, 5)}
                              {s.location ? ` · ${s.location}` : ''}
                            </li>
                          ))}
                          {v.program_assignment && (
                            <li className="text-[11px] text-text-secondary">Assigned to the programme directly</li>
                          )}
                        </ul>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </>
  );
}

const SKILL_LABEL = Object.fromEntries(SKILLS.map((s) => [s.value, s.label])) as Record<string, string>;

/** "Sat 7 Nov" from a wall-clock YYYY-MM-DD, without a timezone shift. */
function formatShiftDate(shiftDate: string): string {
  const [y, m, d] = shiftDate.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-GB', {
    weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
  });
}

function StatBox({
  label,
  value,
  valueClassName,
  hint,
  action,
}: {
  label: string;
  value: string | number;
  valueClassName?: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="bg-surface border border-border-brand p-6 min-h-[120px] flex flex-col justify-center rounded-card">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-text-secondary font-bold uppercase tracking-wider">{label}</p>
        {action}
      </div>
      <p className={`text-2xl font-bold font-heading mt-1.5 ${valueClassName ?? 'text-text-primary'}`}>{value}</p>
      {hint && <p className="text-[11px] text-text-muted mt-1">{hint}</p>}
    </div>
  );
}