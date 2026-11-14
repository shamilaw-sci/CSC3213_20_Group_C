'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { field } from '@/components/leave/LeaveForm';
import { useCreateEmployee, useLinkableLogins } from '@/hooks/useHR';
import { NIC_PATTERN, NIC_RULE } from '@/lib/employees';
import { colomboDate } from '@/components/hr/attendance/dayStatus';
import { getErrorMessage } from '@/lib/utils';
import { EmployeeCreate } from '@/types';

type Props = {
  onClose: () => void;
};

/**
 * Add an employee with everything payroll, leave and self-service need in one
 * step: the EPF number for payslips, the join date for first-year leave and
 * pro-rating, and the login they clock in with. Laid out like
 * EditEmployeeDialog. Mounted only while open, so each opening starts blank.
 */
export function AddEmployeeDialog({ onClose }: Props) {
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [nic, setNic] = useState('');
  const [salary, setSalary] = useState('');
  const [epfNumber, setEpfNumber] = useState('');
  const [dateJoined, setDateJoined] = useState(colomboDate());
  const [loginId, setLoginId] = useState('');
  const [error, setError] = useState<string | null>(null);

  const { data: logins, isLoading: loadingLogins, isError: loginsFailed } = useLinkableLogins();
  const { mutate: create, isPending } = useCreateEmployee();

  const save = () => {
    const body: EmployeeCreate = {
      first_name: firstName.trim(),
      last_name: lastName.trim(),
      nic: nic.trim().toUpperCase(),
      base_salary: Number(salary),
      status: 'Active',
      epf_number: epfNumber.trim() || null,
      date_joined: dateJoined || null,
      user_id: loginId || null,
    };
    if (!body.first_name || !body.last_name) return setError('First and last name are required');
    if (!NIC_PATTERN.test(body.nic)) return setError(NIC_RULE);
    if (!(body.base_salary > 0)) return setError('Salary must be a positive number');
    if (!body.date_joined) return setError('Give the date they joined, so first-year leave and pay come out right.');
    setError(null);
    // The server's refusal (a NIC or login already taken) is shown here, with
    // the details still filled in.
    create(body, {
      onSuccess: onClose,
      onError: (err) => setError(getErrorMessage(err) || 'Failed to add the employee'),
    });
  };

  const label = 'space-y-1 text-xs font-medium text-text-secondary';

  return (
    <Dialog open onOpenChange={(open) => !open && !isPending && onClose()}>
      <DialogContent className="bg-surface border-border-brand sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add employee</DialogTitle>
          <DialogDescription>New employees start as Active. The record is written to the audit log.</DialogDescription>
        </DialogHeader>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className={label}>
            First name
            <input value={firstName} onChange={(e) => setFirstName(e.target.value)} maxLength={100} className={field} autoFocus />
          </label>
          <label className={label}>
            Last name
            <input value={lastName} onChange={(e) => setLastName(e.target.value)} maxLength={100} className={field} />
          </label>
          <label className={label}>
            NIC
            <input value={nic} onChange={(e) => setNic(e.target.value)} maxLength={12}
              placeholder="199512345678 or 951234567V" className={`${field} font-mono`} />
          </label>
          <label className={label}>
            Base salary (LKR)
            <input type="number" min="1" value={salary} onChange={(e) => setSalary(e.target.value)}
              placeholder="50000" className={`${field} font-mono`} />
          </label>
          <label className={label}>
            Date joined
            <input type="date" value={dateJoined} onChange={(e) => setDateJoined(e.target.value)} className={`${field} font-mono`} />
          </label>
          <label className={label}>
            EPF number <span className="font-normal text-text-muted">(optional, on payslips)</span>
            <input value={epfNumber} onChange={(e) => setEpfNumber(e.target.value)} maxLength={20} className={`${field} font-mono`} />
          </label>
          <label className={`${label} sm:col-span-2`}>
            Linked login <span className="font-normal text-text-muted">(optional)</span>
            <select value={loginId} onChange={(e) => setLoginId(e.target.value)} className={field} disabled={loadingLogins}>
              <option value="">Not linked</option>
              {(logins ?? []).map((login) => (
                <option key={login.id} value={login.id}>
                  {login.email}{login.role ? ` (${login.role})` : ''}
                </option>
              ))}
            </select>
          </label>
        </div>

        {loginId === '' && (
          <p className="text-xs text-text-muted">
            Without a linked login they can&apos;t clock in, see their attendance or request leave. You can link one later.
          </p>
        )}
        {loginsFailed && <p className="text-xs text-negative">Could not load login accounts to link.</p>}
        {error && <p className="text-xs text-negative">{error}</p>}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isPending}>Cancel</Button>
          <Button onClick={save} disabled={isPending} className="bg-accent text-white hover:bg-accent/90">
            {isPending ? 'Adding…' : 'Add employee'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
