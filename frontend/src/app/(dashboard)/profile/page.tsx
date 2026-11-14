'use client';

import { useAuthStore } from '@/store/useAuthStore';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Mail, Shield, IdCard } from 'lucide-react';
import { useMyEmployee } from '@/hooks/useHR';
import { hasPermission } from '@/lib/permissions';
import { formatDate, formatLKR } from '@/lib/formatters';
import { Employee } from '@/types';

/**
 * The signed-in person's own employee record, read-only. HR keeps these
 * details (Human Resources > Employees), so a change goes through them.
 * Every role but System Administrator is an employee; that one sees its
 * account only.
 */
export default function ProfilePage() {
  const user = useAuthStore((s) => s.user);
  const isEmployee = hasPermission(user?.role || '', 'hr:attendance:self');
  const { data: employee, isLoading, error } = useMyEmployee(isEmployee);
  const notLinked = (error as { response?: { status?: number } } | null)?.response?.status === 404;

  const name = employee ? `${employee.first_name} ${employee.last_name}` : user?.name || user?.email || '';

  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      <div>
        <h1 className="text-3xl font-bold font-heading tracking-tight mb-2 text-text-primary">
          My Profile
        </h1>
        <p className="text-text-secondary text-sm">
          Your account and employee record. HR keeps the record, so ask them to change anything on it.
        </p>
      </div>

      <div className="grid md:grid-cols-3 gap-8">
        <Card className="bg-surface border border-border-brand rounded-card shadow-card p-5 text-center relative overflow-hidden self-start">
          <div className="absolute top-0 left-0 right-0 h-2 bg-accent" />
          <CardContent className="p-0 pt-4 space-y-4">
            <div className="w-24 h-24 mx-auto rounded-full bg-accent/10 border-2 border-accent/20 flex items-center justify-center text-4xl font-extrabold text-accent">
              {(name[0] || '?').toUpperCase()}
            </div>
            <div>
              <h3 className="text-base font-bold text-text-primary break-all">{name}</h3>
              {name !== user?.email && (
                <p className="flex items-center justify-center gap-1.5 text-xs text-text-secondary mt-1 break-all">
                  <Mail size={12} className="shrink-0" /> {user?.email}
                </p>
              )}
            </div>
            <div className="flex flex-wrap justify-center gap-2 pt-1">
              <Badge className="bg-accent/10 text-accent border border-accent/20 rounded-full px-3 py-1 text-[10px] font-bold uppercase tracking-wider">
                <Shield size={10} className="mr-1" /> {user?.role || 'Unknown role'}
              </Badge>
              {employee && <StatusBadge status={employee.status} />}
            </div>
          </CardContent>
        </Card>

        <Card className="md:col-span-2 bg-surface border border-border-brand rounded-card shadow-card p-5">
          <CardHeader className="p-0 pb-4">
            <CardTitle className="flex items-center gap-2 text-base font-semibold font-heading text-text-primary">
              <IdCard className="h-4 w-4 text-accent" /> Employee Record
            </CardTitle>
            <CardDescription className="text-text-secondary text-xs mt-1">
              Read-only. Salary changes, a new NIC or EPF number are made by HR.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0 pt-2">
            {!isEmployee ? (
              <Notice>System Administrator accounts aren&apos;t employees, so there is no employee record.</Notice>
            ) : isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-10 w-full bg-bg-subtle" />
                <Skeleton className="h-10 w-full bg-bg-subtle" />
                <Skeleton className="h-10 w-full bg-bg-subtle" />
              </div>
            ) : notLinked ? (
              <Notice>Your login isn&apos;t linked to an employee record yet. Ask HR to link it.</Notice>
            ) : error || !employee ? (
              <Notice>Could not load your employee record. Refresh to try again.</Notice>
            ) : (
              <EmployeeDetails employee={employee} />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function EmployeeDetails({ employee }: { employee: Employee }) {
  const rows: [string, React.ReactNode, boolean?][] = [
    ['First name', employee.first_name],
    ['Last name', employee.last_name],
    ['NIC', employee.nic, true],
    ['EPF number', employee.epf_number || 'Not set', true],
    ['Date joined', formatDate(employee.date_joined)],
    ['Base salary', formatLKR(Number(employee.base_salary)), true],
    ['Status', <StatusBadge key="status" status={employee.status} />],
  ];
  if (employee.date_left) rows.push(['Last working day', formatDate(employee.date_left)]);

  return (
    <dl className="grid sm:grid-cols-2 gap-x-6 gap-y-4">
      {rows.map(([label, value, mono]) => (
        <div key={label} className="space-y-1 border-b border-border-brand pb-3">
          <dt className="text-[10px] font-bold uppercase tracking-wider text-text-secondary">{label}</dt>
          <dd className={`text-sm text-text-primary ${mono ? 'font-mono' : ''}`}>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function StatusBadge({ status }: { status: string }) {
  return (
    <Badge className={
      status === 'Active'
        ? 'bg-green-500/10 text-positive border border-green-500/20 rounded-full px-2 py-0.5 text-[10px]'
        : 'bg-red-500/10 text-negative border border-red-500/20 rounded-full px-2 py-0.5 text-[10px]'
    }>
      {status}
    </Badge>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return <p className="rounded-md border border-border-brand bg-bg-subtle px-4 py-6 text-center text-sm text-text-secondary">{children}</p>;
}
