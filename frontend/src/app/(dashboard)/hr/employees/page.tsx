'use client';

import { useMemo, useState } from 'react';
import { useEmployees, useCreateEmployee } from '@/hooks/useHR';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { UserPlus, Download, Pencil } from 'lucide-react';
import { formatLKR } from '@/lib/formatters';
import { buildCsv, downloadCsv } from '@/lib/csv';
import { getErrorMessage } from '@/lib/utils';
import { NIC_PATTERN, NIC_RULE } from '@/lib/employees';
import ProtectedRoute from '@/components/layout/protected-route';
import { EditEmployeeDialog } from '@/components/hr/EditEmployeeDialog';
import { Employee } from '@/types';
import { toast } from 'sonner';
import Swal from 'sweetalert2';
import { useThemeStore } from '@/store/useThemeStore';

type StatusFilter = 'all' | 'Active' | 'Inactive';

const FILTER_TITLES: Record<StatusFilter, string> = {
  all: 'All Employees',
  Active: 'Active Employees',
  Inactive: 'Inactive Employees',
};

export default function HRPage() {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [editing, setEditing] = useState<Employee | null>(null);

  const { data: employees, isLoading: loadingEmployees, isError: employeesFailed } = useEmployees();

  const createEmployee = useCreateEmployee();

  const shown = useMemo(
    () => (employees ?? []).filter((emp) => statusFilter === 'all' || emp.status === statusFilter),
    [employees, statusFilter],
  );

  const handleExport = () => {
    if (shown.length === 0) {
      toast.info('No employees to export');
      return;
    }
    const csv = buildCsv(
      ['First Name', 'Last Name', 'NIC', 'Base Salary (LKR)', 'Status', 'Date Joined', 'Linked Login'],
      shown.map((emp) => [
        emp.first_name,
        emp.last_name,
        emp.nic,
        Number(emp.base_salary),
        emp.status,
        emp.date_joined,
        emp.login_email ?? (emp.user_id ? 'Linked' : ''),
      ]),
    );
    const suffix = statusFilter === 'all' ? '' : `-${statusFilter.toLowerCase()}`;
    downloadCsv(`employees${suffix}-${new Date().toISOString().slice(0, 10)}.csv`, csv);
  };

  const handleAddEmployee = () => {
    const isDark = useThemeStore.getState().theme === 'dark';
    const inputStyle = `width: 100%; margin-top: 4px; box-sizing: border-box; font-size: 12px; height: 38px; background: ${isDark ? '#14161C' : '#FFFFFF'}; color: ${isDark ? '#F9FAFB' : '#111318'}; border: 1px solid ${isDark ? '#232730' : '#E5E7EB'}; border-radius: 8px; padding: 0 10px;`;
    const labelStyle = `font-size: 10px; font-weight: bold; letter-spacing: 0.05em; color: ${isDark ? '#9CA3AF' : '#6B7280'};`;

    Swal.fire({
      title: 'Add New Employee',
      html: `
        <div style="display: flex; flex-direction: column; gap: 12px; text-align: left; font-family: sans-serif;">
          <div>
            <label style="${labelStyle}">FIRST NAME</label>
            <input id="swal-fn" style="${inputStyle}" placeholder="First name" maxlength="100">
          </div>
          <div>
            <label style="${labelStyle}">LAST NAME</label>
            <input id="swal-ln" style="${inputStyle}" placeholder="Last name" maxlength="100">
          </div>
          <div>
            <label style="${labelStyle}">NIC NUMBER</label>
            <input id="swal-nic" style="${inputStyle}" placeholder="e.g. 199512345678 or 951234567V" maxlength="12">
          </div>
          <div>
            <label style="${labelStyle}">BASE SALARY (LKR)</label>
            <input id="swal-salary" type="number" min="1" style="${inputStyle}" placeholder="50000">
          </div>
        </div>
      `,
      background: isDark ? '#0F1520' : '#FFFFFF',
      color: isDark ? '#F9FAFB' : '#111318',
      showCancelButton: true,
      confirmButtonText: 'Create Record',
      confirmButtonColor: '#EF9F27',
      cancelButtonText: 'Cancel',
      // The button text is white, so the light-mode grey must be dark enough
      // to read it on (#E5E7EB left it all but invisible).
      cancelButtonColor: isDark ? '#232730' : '#6B7280',
      showLoaderOnConfirm: true,
      allowOutsideClick: () => !Swal.isLoading(),
      // Saving happens here rather than after the dialog closes, so a
      // server refusal (a NIC already on file) is shown in the dialog with
      // the details still filled in.
      preConfirm: async () => {
        const fn = (document.getElementById('swal-fn') as HTMLInputElement).value.trim();
        const ln = (document.getElementById('swal-ln') as HTMLInputElement).value.trim();
        const nic = (document.getElementById('swal-nic') as HTMLInputElement).value.trim().toUpperCase();
        const salary = (document.getElementById('swal-salary') as HTMLInputElement).value.trim();

        if (!fn || !ln || !nic || !salary) {
          Swal.showValidationMessage('All employee fields are required');
          return false;
        }

        if (!NIC_PATTERN.test(nic)) {
          Swal.showValidationMessage(NIC_RULE);
          return false;
        }

        const salVal = parseFloat(salary);
        if (isNaN(salVal) || salVal <= 0) {
          Swal.showValidationMessage('Salary must be a positive number');
          return false;
        }

        try {
          return await createEmployee.mutateAsync({ first_name: fn, last_name: ln, nic, base_salary: salVal, status: 'Active' });
        } catch (err) {
          Swal.showValidationMessage(getErrorMessage(err) || 'Failed to add employee');
          return false;
        }
      }
    });
  };

  return (
    <ProtectedRoute requiredPermission="hr:manage">
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
              onClick={handleAddEmployee}
              className="bg-accent hover:bg-accent/80 text-white font-semibold text-xs py-2 px-4 rounded-lg shadow-sm"
            >
              <UserPlus className="mr-2 h-4 w-4" /> Add Employee
            </Button>
          </div>
        </div>

        <Card className="bg-surface border border-border-brand rounded-card shadow-card p-5">
          <CardHeader className="flex flex-row items-center justify-between p-0 pb-4">
            <div>
              <CardTitle className="text-base font-semibold font-heading text-text-primary">{FILTER_TITLES[statusFilter]}</CardTitle>
              <CardDescription className="text-text-secondary text-xs mt-1">
                {employees ? `Showing ${shown.length} of ${employees.length} employees.` : 'Directory of all personnel.'}
              </CardDescription>
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
                      <TableHead className="text-text-secondary font-heading text-xs">Status</TableHead>
                      <TableHead className="text-text-secondary font-heading text-xs">Login</TableHead>
                      <TableHead className="text-text-secondary font-heading text-xs text-right"><span className="sr-only">Actions</span></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {shown.length === 0 ? (
                      <TableRow className="hover:bg-transparent border-border-brand">
                        <TableCell colSpan={6} className="text-center text-text-secondary text-xs py-8">
                          {employeesFailed
                            ? 'Could not load employees. Refresh to try again.'
                            : statusFilter === 'all' ? 'No employees yet.' : `No ${statusFilter.toLowerCase()} employees.`}
                        </TableCell>
                      </TableRow>
                    ) : shown.map((emp) => (
                      <TableRow key={emp.id} className="border-border-brand hover:bg-bg-subtle transition-colors">
                        <TableCell className="font-semibold text-text-primary text-xs">{emp.first_name} {emp.last_name}</TableCell>
                        <TableCell className="text-text-secondary text-xs font-mono">{emp.nic}</TableCell>
                        <TableCell className="text-text-primary font-mono text-xs font-semibold">{formatLKR(emp.base_salary)}</TableCell>
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
      </div>
    </ProtectedRoute>
  );
}
