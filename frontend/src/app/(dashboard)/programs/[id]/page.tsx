'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams, useRouter } from 'next/navigation';
import { ProgramService } from '@/services/program.service';
import { HRService } from '@/services/hr.service';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { ArrowLeft, Users, TrendingUp, X, UserPlus, Lock } from 'lucide-react';
import { FinanceService } from '@/services/finance.service';
import { useAuthStore } from '@/store/useAuthStore';
import { hasPermission } from '@/lib/permissions';
import { toast } from 'sonner';
import ProtectedRoute from '@/components/layout/protected-route';

export default function ProgramDetailsPage() {
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

  const { data: costData } = useQuery({
    queryKey: ['program-cost-per-animal', programId],
    queryFn: () => ProgramService.getCostPerAnimal(programId),
    retry: false, // don't hammer the RPC if the program has no cost data yet
  });

  const { data: financials } = useQuery({
    queryKey: ['program-financials', programId],
    queryFn: () => ProgramService.getFinancials(programId),
  });

  const { data: employees } = useQuery({
    queryKey: ['employees'],
    queryFn: HRService.getEmployees,
  });

  // The restricted-balance endpoint is gated on finance:read, which Staff do
  // not hold. Guarding the query avoids a guaranteed 403 on every page load
  // for the role that most often opens this view.
  const { user } = useAuthStore();
  const canReadFinance = hasPermission(user?.role as string, 'finance:read');

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
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail || 'Failed to assign worker');
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
    <ProtectedRoute requiredPermission="programs:read">
      <div className="space-y-6 pb-12">
        <Button variant="ghost" size="sm" onClick={() => router.push('/programs')} className="-ml-2 text-xs">
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to Programs
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
                <h1 className="text-2xl font-bold font-heading text-text-primary">{program.program_name}</h1>
                <p className="text-text-secondary text-sm mt-1">
                  {program.start_date ? `Started ${program.start_date}` : 'No start date set'}
                  {program.end_date ? ` · Ends ${program.end_date}` : ''}
                </p>
              </div>
              <Badge variant="outline" className="text-xs w-fit">{program.status}</Badge>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-5">
              <StatBox label="Animals Treated" value={program.total_animals_treated} />
              <StatBox label="Total Cost" value={`Rs. ${(program.total_cost ?? 0).toLocaleString()}`} />
              <StatBox
                label="Cost / Animal"
                value={costData ? `Rs. ${costData.cost_per_animal.toLocaleString()}` : '—'}
              />
              <StatBox label="Workers Assigned" value={team?.length ?? 0} />
              <StatBox
                label="Revenue"
                value={financials ? `Rs. ${financials.revenue.toLocaleString()}` : '—'}
              />
              <StatBox
                label="Profit"
                value={financials ? `Rs. ${financials.profit.toLocaleString()}` : '—'}
                valueClassName={financials && financials.profit < 0 ? 'text-red-500' : 'text-positive'}
              />
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
                      value={`Rs. ${restricted.raised.toLocaleString()}`}
                    />
                    <StatBox
                      label="Spent"
                      value={`Rs. ${restricted.spent.toLocaleString()}`}
                    />
                    <StatBox
                      label="Remaining"
                      value={`Rs. ${restricted.remaining.toLocaleString()}`}
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
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0 text-text-secondary hover:text-red-500"
                          onClick={() => removeWorker.mutate(member.id)}
                        >
                          <X size={14} />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </ProtectedRoute>
  );
}

function StatBox({
  label,
  value,
  valueClassName,
}: {
  label: string;
  value: string | number;
  valueClassName?: string;
}) {
  return (
    <div className="bg-surface border border-border-brand p-6 min-h-[120px] flex flex-col justify-center rounded-card">
      <p className="text-xs text-text-secondary font-bold uppercase tracking-wider">{label}</p>
      <p className={`text-2xl font-bold font-heading mt-1.5 ${valueClassName ?? 'text-text-primary'}`}>{value}</p>
    </div>
  );
}