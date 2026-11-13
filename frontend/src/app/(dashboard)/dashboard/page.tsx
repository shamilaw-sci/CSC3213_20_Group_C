'use client';

import { useAuthStore } from '@/store/useAuthStore';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useMyAttendance } from '@/hooks/useHR';
import { TodayClockCard } from '@/components/hr/attendance/TodayClockCard';
import { colomboDate } from '@/components/hr/attendance/dayStatus';
import { useFinanceSummary, useFinanceAging, useTransactions } from '@/hooks/useFinance';
import { useAuditLogs, useSystemStats } from '@/hooks/useAdmin';
import { format } from 'date-fns';
import { Lock, ArrowUpRight, ArrowDownRight, AlertTriangle, Users, Activity, ExternalLink, BookOpen, DollarSign, Package, Calendar, ArrowRight, Wallet, ArrowDownUp, FileText, CheckCircle2, TrendingUp } from 'lucide-react';
import { formatLKR, formatDate } from '@/lib/formatters';
import { Skeleton } from '@/components/ui/skeleton';
import Link from 'next/link';
import { hasPermission } from '@/lib/permissions';
import { RescueOutcomesCard } from '@/components/cases/RescueOutcomesCard';

export default function DashboardPage() {
  const { user } = useAuthStore();
  const role = user?.role || 'General Staff';

  // General Staff, Operations Lead and System Administrator all fall through to
  // the staff dashboard, which is the safe default: it shows only self-service
  // and rescue content, nothing role-privileged.
  switch (role) {
    case 'Admin':
      return <AdminDashboard />;
    case 'Director':
      return <DirectorDashboard />;
    case 'HR Officer':
      return <HROfficerDashboard />;
    case 'Finance Officer':
      return <FinanceOfficerDashboard />;
    default:
      return <StaffDashboard />;
  }
}

// Rescue outcomes for whoever can see the case board: Admin, Director and the
// staff dashboard's roles. Renders nothing for the rest.
function RescueOutcomesForRole() {
  const { user } = useAuthStore();
  return hasPermission(user?.role || '', 'rescue:read') ? <RescueOutcomesCard /> : null;
}

function AdminDashboard() {
  const { data: stats, isLoading: isStatsLoading } = useSystemStats();
  const { data: logs, isLoading: isLogsLoading } = useAuditLogs(10);

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold font-heading text-text-primary">System Overview</h1>
      
      <div className="grid md:grid-cols-4 gap-4">
        <Card className="bg-surface border-border-brand">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-text-secondary">Total Users</CardTitle>
          </CardHeader>
          <CardContent>
            {isStatsLoading ? <Skeleton className="h-8 w-16" /> : (
              <div className="text-3xl font-bold font-heading">{stats?.total_users || 0}</div>
            )}
          </CardContent>
        </Card>
        <Card className="bg-surface border-border-brand">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-text-secondary">System Health</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <span className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
              </span>
              <span className="font-medium text-emerald-500">Online</span>
            </div>
          </CardContent>
        </Card>
        <Card className="md:col-span-2 bg-surface border-border-brand">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-text-secondary">Quick Links</CardTitle>
          </CardHeader>
          <CardContent className="flex gap-2 flex-wrap">
            <Link href="/hr/employees"><Button variant="outline" size="sm">Manage Users</Button></Link>
            <Link href="/programs"><Button variant="outline" size="sm">Manage Programs</Button></Link>
            <Link href="/inventory/stock"><Button variant="outline" size="sm">View Inventory</Button></Link>
          </CardContent>
        </Card>
      </div>

      <Card className="border-border-brand bg-surface">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-accent" />
            Recent System Events
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLogsLoading ? (
            <div className="space-y-4">
              {[1, 2, 3].map(i => <Skeleton key={i} className="w-full h-12" />)}
            </div>
          ) : logs && logs.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-text-secondary uppercase bg-bg-subtle/50">
                  <tr>
                    <th className="px-4 py-3">Time</th>
                    <th className="px-4 py-3">Action</th>
                    <th className="px-4 py-3">Table</th>
                    <th className="px-4 py-3">User</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-brand">
                  {logs.map((log) => (
                    <tr key={log.id} className="hover:bg-bg-subtle/50 transition-colors">
                      <td className="px-4 py-3 text-text-secondary">
                        {format(new Date(log.timestamp), 'MMM dd HH:mm')}
                      </td>
                      <td className="px-4 py-3 font-medium">{log.action_type}</td>
                      <td className="px-4 py-3 text-text-secondary">{log.table_name}</td>
                      <td className="px-4 py-3 text-text-secondary">
                        {log.users?.email || 'System'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-8 text-text-secondary">No recent events.</div>
          )}
        </CardContent>
      </Card>
      <RescueOutcomesForRole />
    </div>
  );
}

function DirectorDashboard() {
  const { data: summary, isLoading: isSummaryLoading } = useFinanceSummary();
  const { data: aging, isLoading: isAgingLoading } = useFinanceAging();

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <h1 className="text-3xl font-bold font-heading text-text-primary">Financial & Impact Overview</h1>
      </div>
      
      <div className="grid md:grid-cols-3 gap-6">
        <Card className="bg-emerald-500/10 border-emerald-500/30">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-emerald-600 dark:text-emerald-400">Available Cash</CardTitle>
          </CardHeader>
          <CardContent>
            {isSummaryLoading ? <Skeleton className="h-10 w-32" /> : (
              <div className="text-4xl font-bold font-heading text-emerald-600 dark:text-emerald-400">
                {formatLKR(summary?.cash_available || 0)}
              </div>
            )}
          </CardContent>
        </Card>
        
        <Card className="bg-surface border-border-brand">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-text-secondary">Outstanding Receivables</CardTitle>
          </CardHeader>
          <CardContent>
            {isSummaryLoading ? <Skeleton className="h-10 w-32" /> : (
              <div className="text-3xl font-bold text-text-primary mb-1">
                {formatLKR(summary?.receivables || 0)}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="bg-rose-500/5 border-rose-500/20">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-rose-500 flex items-center gap-2">
              Monthly Expenses
              {(summary?.cash_available || 0) < (summary?.monthly_expenses || 0) && (
                <AlertTriangle className="w-4 h-4" />
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isSummaryLoading ? <Skeleton className="h-10 w-32" /> : (
              <div className="text-3xl font-bold text-text-primary mb-1">
                {formatLKR(summary?.monthly_expenses || 0)}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <Card className="border-border-brand bg-surface">
          <CardHeader>
            <CardTitle>Receivables Aging</CardTitle>
          </CardHeader>
          <CardContent>
            {isAgingLoading ? (
              <div className="space-y-4">
                {[1, 2, 3].map(i => <Skeleton key={i} className="w-full h-8" />)}
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex justify-between items-center p-3 bg-surface border border-border/50 rounded-lg">
                  <span className="text-text-secondary">0-30 Days</span>
                  <span className="font-medium text-emerald-500">{formatLKR(aging?.['0-30'] || 0)}</span>
                </div>
                <div className="flex justify-between items-center p-3 bg-surface border border-border/50 rounded-lg">
                  <span className="text-text-secondary">31-60 Days</span>
                  <span className="font-medium text-amber-500">{formatLKR(aging?.['31-60'] || 0)}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-text-secondary">61+ Days (Overdue)</span>
                  <span className="font-medium text-rose-500">{formatLKR(aging?.['61+'] || 0)}</span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="border-border-brand bg-surface border-l-4 border-l-accent">
          <CardHeader>
            <CardTitle>Pending Approvals</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="p-4 bg-bg-subtle rounded-lg border border-border-brand flex items-center justify-between">
              <div>
                <p className="font-medium text-text-primary">Monthly Payroll</p>
                <p className="text-sm text-text-secondary">Awaiting final Director approval.</p>
              </div>
              <Link href="/hr/payroll">
                <Button variant="outline" size="sm" className="gap-2">
                  View <ExternalLink className="w-4 h-4" />
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
      <RescueOutcomesForRole />
    </div>
  );
}

function HROfficerDashboard() {
  const currentMonth = new Date().getMonth() + 1;
  const currentYear = new Date().getFullYear();
  
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold font-heading text-text-primary">Attendance & Payroll Status</h1>
      <div className="grid md:grid-cols-2 gap-6">
        <Card className="bg-surface border-border-brand">
          <CardHeader>
            <CardTitle>Quick Links</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-4">
            <Link href="/hr/attendance">
              <Button variant="outline" className="w-full h-24 flex flex-col gap-2">
                <Lock className="w-6 h-6 text-accent" />
                Manage Today's Attendance
              </Button>
            </Link>
            <Link href="/hr/payroll">
              <Button variant="outline" className="w-full h-24 flex flex-col gap-2">
                <Activity className="w-6 h-6 text-emerald-500" />
                Payroll Readiness
              </Button>
            </Link>
            <Link href="/hr/employees">
              <Button variant="outline" className="w-full h-24 flex flex-col gap-2 col-span-2">
                <Users className="w-6 h-6 text-amber-500" />
                Employee Profiles
              </Button>
            </Link>
          </CardContent>
        </Card>

        <Card className="bg-surface border-border-brand">
          <CardHeader>
            <CardTitle>Payroll Cycle: {format(new Date(), 'MMMM yyyy')}</CardTitle>
          </CardHeader>
          <CardContent>
             <div className="space-y-6">
              <div className="flex items-center gap-4">
                <div className="w-8 h-8 rounded-full bg-emerald-500/20 text-emerald-500 flex items-center justify-center font-bold">1</div>
                <div>
                  <p className="font-medium">Attendance Logging</p>
                  <p className="text-sm text-text-secondary">Staff record daily hours.</p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div className="w-8 h-8 rounded-full bg-amber-500/20 text-amber-500 flex items-center justify-center font-bold">2</div>
                <div>
                  <p className="font-medium">Attendance Lock</p>
                  <p className="text-sm text-text-secondary">HR finalizes daily logs.</p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div className="w-8 h-8 rounded-full bg-bg-subtle text-text-secondary flex items-center justify-center font-bold">3</div>
                <div>
                  <p className="font-medium text-text-secondary">Payroll Generation</p>
                  <p className="text-sm text-text-secondary">Run readiness check and generate.</p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function FinanceOfficerDashboard() {
  const { data: summary, isLoading } = useFinanceSummary();

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold font-heading text-text-primary">Ledger Workbench</h1>
      
      <div className="grid md:grid-cols-3 gap-6">
        <Card className="bg-surface border-border-brand">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-text-secondary">Available Cash</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? <Skeleton className="h-8 w-24" /> : (
              <div className="text-3xl font-bold text-text-primary mb-1">
                {formatLKR(summary?.cash_available || 0)}
              </div>
            )}
          </CardContent>
        </Card>
        <Card className="bg-surface border-border-brand">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-text-secondary">Unsettled Receivables</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? <Skeleton className="h-8 w-24" /> : (
              <div className="text-2xl font-bold font-heading text-amber-500">
                LKR {(summary?.receivables || 0).toLocaleString()}
              </div>
            )}
          </CardContent>
        </Card>
        <Card className="bg-surface border-border-brand">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-text-secondary">Quick Entry</CardTitle>
          </CardHeader>
          <CardContent>
            <Link href="/finance/ledger">
              <Button className="w-full bg-accent text-bg-brand hover:bg-accent/90">
                + New Transaction
              </Button>
            </Link>
          </CardContent>
        </Card>
      </div>
      
      <div className="grid md:grid-cols-2 gap-6">
        <Card className="bg-surface border-border-brand">
          <CardHeader>
            <CardTitle>Due Soon</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-center py-8 text-text-secondary">
              Review{' '}
              <Link href="/finance/ledger?status=Receivable&type=Income&sort=oldest" className="text-accent underline">
                open receivables in the Ledger
              </Link>
              , oldest first, for items needing attention.
            </div>
          </CardContent>
        </Card>
        <Card className="bg-surface border-border-brand border-l-4 border-l-accent">
          <CardHeader>
            <CardTitle>Payroll Status</CardTitle>
          </CardHeader>
          <CardContent>
             <div className="p-4 bg-bg-subtle rounded-lg border border-border-brand flex items-center justify-between">
              <div>
                <p className="font-medium text-text-primary">Monthly Payroll</p>
                <p className="text-sm text-text-secondary">
                  HR generates and the Director approves; approved payroll arrives in the Ledger as a payable to mark paid.
                </p>
              </div>
              <Link href="/finance/ledger?status=Receivable&type=Expense&sort=oldest">
                <Button variant="outline" size="sm" className="gap-2">
                  Payables <ExternalLink className="w-4 h-4" />
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function StaffDashboard() {
  // For the monthly summary; clocking in is TodayClockCard's.
  const [year, month] = colomboDate().split('-').map(Number);
  const { data: attendanceLogs } = useMyAttendance(month, year);

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold font-heading text-text-primary">My Day</h1>
      
      <div className="grid md:grid-cols-3 gap-6">
        <div className="md:col-span-1">
          <TodayClockCard title="Today's Attendance" />
        </div>
        
        <Card className="md:col-span-2 border-border-brand bg-surface">
          <CardHeader>
            <CardTitle>My Assignments & Tools</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
             <div className="grid grid-cols-2 gap-4">
                <Link href="/programs">
                  <div className="p-4 rounded-lg border border-border-brand hover:border-accent transition-colors bg-bg-subtle cursor-pointer flex items-center gap-3">
                    <BookOpen className="w-8 h-8 text-accent" />
                    <div>
                      <p className="font-medium text-text-primary">Programs</p>
                      <p className="text-sm text-text-secondary">View my assigned tasks.</p>
                    </div>
                  </div>
                </Link>
                <div className="p-4 rounded-lg border border-border-brand hover:border-accent transition-colors bg-bg-subtle cursor-pointer flex items-center gap-3 opacity-50">
                   <Activity className="w-8 h-8 text-amber-500" />
                    <div>
                      <p className="font-medium text-text-primary">IT Support</p>
                      <p className="text-sm text-text-secondary">Coming soon.</p>
                    </div>
                </div>
             </div>
             
             <div className="mt-8 p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-lg">
                <p className="text-emerald-500 font-medium">Monthly Summary</p>
                <p className="text-sm text-emerald-500/80 mt-1">You have logged {(attendanceLogs?.reduce((acc, log) => acc + (log.worked_hours || 0), 0) || 0).toFixed(1)} hours this month.</p>
             </div>
          </CardContent>
        </Card>
      </div>
      <RescueOutcomesForRole />
    </div>
  );
}
