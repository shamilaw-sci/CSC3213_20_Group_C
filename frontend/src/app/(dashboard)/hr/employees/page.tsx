'use client';

import { useMemo, useState } from 'react';
import { useEmployees } from '@/hooks/useHR';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { UserPlus, Download, Pencil, Search } from 'lucide-react';
import { formatDate, formatLKR } from '@/lib/formatters';
import { buildCsv, downloadCsv } from '@/lib/csv';
import ProtectedRoute from '@/components/layout/protected-route';
import { EditEmployeeDialog } from '@/components/hr/EditEmployeeDialog';
import { AddEmployeeDialog } from '@/components/hr/AddEmployeeDialog';
import { Employee } from '@/types';
import { toast } from 'sonner';

type StatusFilter = 'all' | 'Active' | 'Inactive';

const FILTER_TITLES: Record<StatusFilter, string> = {
  all: 'All Employees',
  Active: 'Active Employees',
  Inactive: 'Inactive Employees',
};

// The gate wraps the content rather than sitting inside it, so the content's
// requests never fire for a role that would only get 403s back.
export default function HRPage() {
  return (
    <ProtectedRoute requiredPermission="hr:manage">
      <HRContent />
    </ProtectedRoute>
  );
}

function HRContent() {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [editing, setEditing] = useState<Employee | null>(null);
  const [adding, setAdding] = useState(false);
  const [search, setSearch] = useState('');

  const { data: employees, isLoading: loadingEmployees, isError: employeesFailed } = useEmployees();

  // Name, NIC, EPF number or login email; the export follows what is shown.
  const shown = useMemo(() => {
    const term = search.trim().toLowerCase();
    return (employees ?? []).filter((emp) =>
      (statusFilter === 'all' || emp.status === statusFilter)
      && (!term || [`${emp.first_name} ${emp.last_name}`, emp.nic, emp.epf_number, emp.login_email]
        .some((v) => v?.toLowerCase().includes(term))));
  }, [employees, statusFilter, search]);

  const handleExport = () => {
    if (shown.length === 0) {
      toast.info('No employees to export');
      return;
    }
    const csv = buildCsv(
      ['First Name', 'Last Name', 'NIC', 'EPF Number', 'Base Salary (LKR)', 'Status', 'Date Joined', 'Last Working Day', 'Linked Login'],
      shown.map((emp) => [
        emp.first_name,
        emp.last_name,
        emp.nic,
        emp.epf_number,
        Number(emp.base_salary),
        emp.status,
        emp.date_joined,
        emp.date_left,
        emp.login_email ?? (emp.user_id ? 'Linked' : ''),
      ]),
    );
    const suffix = statusFilter === 'all' ? '' : `-${statusFilter.toLowerCase()}`;
    downloadCsv(`employees${suffix}-${new Date().toISOString().slice(0, 10)}.csv`, csv);
  };

  return (
    <>
      <div className="space-y-8">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold font-heading tracking-tight mb-2 text-text-primary">
              Human Resources
            </h1>
            <p className="text-text-secondary text-sm">
              Manage employee records. Attendance is on the Attendance page.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              onClick={handleExport}
              disabled={loadingEmployees}
              className="border-border-brand text-text-primary hover:bg-bg-subtle text-xs"
            >
              <Download className="mr-2 h-4 w-4" /> Export
            </Button>
            <Button
              onClick={() => setAdding(true)}
              className="bg-accent hover:bg-accent/80 text-white font-semibold text-xs py-2 px-4 rounded-lg shadow-sm"
            >
              <UserPlus className="mr-2 h-4 w-4" /> Add Employee
            </Button>
          </div>
        </div>

        <Card className="bg-surface border border-border-brand rounded-card shadow-card p-5">
          <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 p-0 pb-4">
            <div>
              <CardTitle className="text-base font-semibold font-heading text-text-primary">{FILTER_TITLES[statusFilter]}</CardTitle>
              <CardDescription className="text-text-secondary text-xs mt-1">
                {employees ? `Showing ${shown.length} of ${employees.length} employees.` : 'Directory of all personnel.'}
              </CardDescription>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-text-secondary" size={14} />
                <input
                  type="search"
                  aria-label="Search employees"
                  placeholder="Search name, NIC, EPF or login"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="w-60 bg-bg-subtle border border-border-brand rounded-lg pl-8 pr-3 py-2 text-xs text-text-primary focus:outline-none focus:border-accent"
                />
              </div>
              <select
                aria-label="Filter by status"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
                className="bg-bg-subtle border border-border-brand rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-accent"
              >
                <option value="all">All Statuses</option>
                <option value="Active">Active</option>
                <option value="Inactive">Inactive</option>
              </select>
            </div>
          </CardHeader>
          <CardContent className="p-0 pt-4">
            {loadingEmployees ? (
              <div className="space-y-2">
                <Skeleton className="h-10 w-full bg-bg-subtle" />
                <Skeleton className="h-10 w-full bg-bg-subtle" />
              </div>
            ) : (
              <div className="rounded-xl border border-border-brand overflow-hidden">
                <Table>
                  <TableHeader className="bg-bg-subtle">
                    <TableRow className="hover:bg-transparent border-border-brand">
                      <TableHead className="text-text-secondary font-heading text-xs">Name</TableHead>
                      <TableHead className="text-text-secondary font-heading text-xs">NIC</TableHead>
                      <TableHead className="text-text-secondary font-heading text-xs">Salary</TableHead>
                      <TableHead className="text-text-secondary font-heading text-xs">Date Joined</TableHead>
                      <TableHead className="text-text-secondary font-heading text-xs">Status</TableHead>
                      <TableHead className="text-text-secondary font-heading text-xs">Login</TableHead>
                      <TableHead className="text-text-secondary font-heading text-xs text-right"><span className="sr-only">Actions</span></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {shown.length === 0 ? (
                      <TableRow className="hover:bg-transparent border-border-brand">
                        <TableCell colSpan={7} className="text-center text-text-secondary text-xs py-8">
                          {employeesFailed
                            ? 'Could not load employees. Refresh to try again.'
                            : search.trim() ? `No employees match "${search.trim()}".`
                            : statusFilter === 'all' ? 'No employees yet.' : `No ${statusFilter.toLowerCase()} employees.`}
                        </TableCell>
                      </TableRow>
                    ) : shown.map((emp) => (
                      <TableRow key={emp.id} className="border-border-brand hover:bg-bg-subtle transition-colors">
                        <TableCell className="font-semibold text-text-primary text-xs">{emp.first_name} {emp.last_name}</TableCell>
                        <TableCell className="text-text-secondary text-xs font-mono">{emp.nic}</TableCell>
                        <TableCell className="text-text-primary font-mono text-xs font-semibold">{formatLKR(emp.base_salary)}</TableCell>
                        <TableCell className="text-text-secondary text-xs">{emp.date_joined ? formatDate(emp.date_joined) : 'Not set'}</TableCell>
                        <TableCell>
                          <Badge className={
                            emp.status === 'Active'
                              ? 'bg-green-500/10 text-positive border border-green-500/20 rounded-full px-2 py-0.5 text-[10px]'
                              : 'bg-red-500/10 text-negative border border-red-500/20 rounded-full px-2 py-0.5 text-[10px]'
                          }>
                            {emp.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs">
                          {emp.user_id
                            ? <span className="text-text-primary">{emp.login_email ?? 'Linked'}</span>
                            : <span className="text-text-secondary">Not linked</span>}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setEditing(emp)}
                            aria-label={`Edit ${emp.first_name} ${emp.last_name}`}
                            className="h-7 w-7 text-text-secondary hover:text-text-primary hover:bg-bg-subtle"
                          >
                            <Pencil size={14} />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        {editing && (
          <EditEmployeeDialog key={editing.id} employee={editing} onClose={() => setEditing(null)} />
        )}
        {adding && <AddEmployeeDialog onClose={() => setAdding(false)} />}
      </div>
    </>
  );
}
