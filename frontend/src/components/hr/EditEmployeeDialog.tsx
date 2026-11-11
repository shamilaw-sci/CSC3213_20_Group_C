'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { field } from '@/components/leave/LeaveForm';
import { useLinkableLogins, useUpdateEmployee } from '@/hooks/useHR';
import { NIC_PATTERN, NIC_RULE } from '@/lib/employees';
import { getErrorMessage } from '@/lib/utils';
import { Employee, EmployeeUpdate } from '@/types';

type Props = {
  employee: Employee;
  onClose: () => void;
};

/**
 * Edit one employee: details, Active/Inactive, and the login it is linked to.
 * Sends only what changed (PUT /hr/employees/{id} is a partial update), so a
 * legacy NIC like DEMO5V is left alone unless HR actually edits it.
 *
 * Mounted only while editing, with key={employee.id} so the form starts
 * fresh for each employee.
 */
export function EditEmployeeDialog({ employee, onClose }: Props) {
  const [firstName, setFirstName] = useState(employee.first_name);
  const [lastName, setLastName] = useState(employee.last_name);
  const [nic, setNic] = useState(employee.nic);
  const [salary, setSalary] = useState(String(employee.base_salary));
  const [status, setStatus] = useState(employee.status);
  const [loginId, setLoginId] = useState(employee.user_id ?? '');
  const [error, setError] = useState<string | null>(null);

  const { data: logins, isLoading: loadingLogins, isError: loginsFailed } = useLinkableLogins();
  const { mutate: update, isPending } = useUpdateEmployee();

  const changes: EmployeeUpdate = {};
  if (firstName.trim() !== employee.first_name) changes.first_name = firstName.trim();
  if (lastName.trim() !== employee.last_name) changes.last_name = lastName.trim();
  if (nic.trim().toUpperCase() !== employee.nic) changes.nic = nic.trim().toUpperCase();
  if (Number(salary) !== Number(employee.base_salary)) changes.base_salary = Number(salary);
  if (status !== employee.status) changes.status = status;
  if (loginId !== (employee.user_id ?? '')) changes.user_id = loginId || null;
  const changed = Object.keys(changes).length > 0;

  const save = () => {
    if (changes.first_name === '' || changes.last_name === '') return setError('Names cannot be blank');
    if (changes.nic !== undefined && !NIC_PATTERN.test(changes.nic)) return setError(NIC_RULE);
    if (changes.base_salary !== undefined && !(changes.base_salary > 0)) return setError('Salary must be a positive number');
    setError(null);
    update({ id: employee.id, changes }, {
      onSuccess: onClose,
      onError: (err) => setError(getErrorMessage(err) || 'Failed to update the employee'),
    });
  };

  const label = 'space-y-1 text-xs font-medium text-text-secondary';

  return (
    <Dialog open onOpenChange={(open) => !open && !isPending && onClose()}>
      <DialogContent className="bg-surface border-border-brand sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Edit {employee.first_name} {employee.last_name}</DialogTitle>
          <DialogDescription>Salary and status changes are recorded in the audit log.</DialogDescription>
        </DialogHeader>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className={label}>
            First name
            <input value={firstName} onChange={(e) => setFirstName(e.target.value)} maxLength={100} className={field} />
          </label>
          <label className={label}>
            Last name
            <input value={lastName} onChange={(e) => setLastName(e.target.value)} maxLength={100} className={field} />
          </label>
          <label className={label}>
            NIC
            <input value={nic} onChange={(e) => setNic(e.target.value)} maxLength={20} className={`${field} font-mono`} />
          </label>
          <label className={label}>
            Base salary (LKR)
            <input type="number" min="1" value={salary} onChange={(e) => setSalary(e.target.value)} className={`${field} font-mono`} />
          </label>
          <label className={label}>
            Status
            <select value={status} onChange={(e) => setStatus(e.target.value)} className={field}>
              <option value="Active">Active</option>
              <option value="Inactive">Inactive</option>
            </select>
          </label>
          <label className={label}>
            Linked login
            <select value={loginId} onChange={(e) => setLoginId(e.target.value)} className={field} disabled={loadingLogins}>
              <option value="">Not linked</option>
              {employee.user_id && (
                <option value={employee.user_id}>{employee.login_email ?? 'Current login'}</option>
              )}
              {(logins ?? []).map((login) => (
                <option key={login.id} value={login.id}>
                  {login.email}{login.role ? ` (${login.role})` : ''}
                </option>
              ))}
            </select>
          </label>
        </div>

        {status === 'Inactive' && employee.status !== 'Inactive' && (
          <p className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-text-primary">
            Inactive employees are left off payroll, the attendance grid and leave lists, and can&apos;t clock in or
            request leave. Their login stays linked, and reactivating restores everything.
          </p>
        )}
        {loginId === '' && employee.user_id && (
          <p className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-text-primary">
            Without a linked login, this person can&apos;t clock in, see their attendance or request leave.
          </p>
        )}
        {loginsFailed && <p className="text-xs text-negative">Could not load login accounts to link.</p>}
        {error && <p className="text-xs text-negative">{error}</p>}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isPending}>Cancel</Button>
          <Button onClick={save} disabled={!changed || isPending} className="bg-accent text-white hover:bg-accent/90">
            {isPending ? 'Saving…' : 'Save changes'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
