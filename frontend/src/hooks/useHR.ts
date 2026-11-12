import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { HRService } from '@/services/hr.service';
import { EmployeeUpdate } from '@/types';
import { toast } from 'sonner';

export function useEmployees() {
  return useQuery({
    queryKey: ['employees'],
    queryFn: HRService.getEmployees,
  });
}

// Used by the edit dialog, which mounts only while open. Under 'employees'
// so saving an edit refreshes it: linking one employee takes that login off
// everyone else's list.
export function useLinkableLogins() {
  return useQuery({
    queryKey: ['employees', 'linkable-logins'],
    queryFn: HRService.getLinkableLogins,
  });
}

export function useUpdateEmployee() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, changes }: { id: number; changes: EmployeeUpdate }) =>
      HRService.updateEmployee(id, changes),
    onSuccess: () => {
      // Status decides who appears on the attendance grid, leave and payroll.
      queryClient.invalidateQueries({ queryKey: ['employees'] });
      queryClient.invalidateQueries({ queryKey: ['attendance'] });
      toast.success('Employee record updated');
    },
    // No error toast: the edit dialog shows the server's reason in place.
  });
}

export function useAttendance(date?: string, month?: number, year?: number) {
  return useQuery({
    queryKey: ['attendance', { date, month, year }],
    queryFn: () => HRService.getAttendance(date, month, year),
  });
}

// Under 'attendance', so the existing log / edit / lock / unlock mutations,
// which invalidate that key, refresh the grid too.
export function useAttendanceMonth(year: number, month: number) {
  return useQuery({
    queryKey: ['attendance', 'month', { year, month }],
    queryFn: () => HRService.getAttendanceMonth(year, month),
    placeholderData: (previous) => previous,
  });
}

export function useMyAttendanceMonth(year: number, month: number) {
  return useQuery({
    queryKey: ['attendance', 'me', 'month', { year, month }],
    queryFn: () => HRService.getMyAttendanceMonth(year, month),
    retry: false,
  });
}

// What a new tracked-from date would do; only fetched once a date is chosen
// (or, for an employee, when clearing their override).
export function useTrackingImpact(start: string | null, employeeId: number | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ['attendance', 'tracking-impact', { start, employeeId }],
    queryFn: () => HRService.getTrackingImpact(start, employeeId),
    enabled,
    retry: false,
  });
}

export function useSetTracking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ employeeId, date }: { employeeId?: number; date: string | null }) =>
      employeeId ? HRService.setEmployeeTracking(employeeId, date) : HRService.setTrackingStart(date as string),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attendance'] });
      queryClient.invalidateQueries({ queryKey: ['work-calendar'] });
      toast.success('Tracking date saved');
    },
    onError: (error: { response?: { data?: { detail?: string } } }) => {
      toast.error(error?.response?.data?.detail || 'Failed to save the tracking date');
    },
  });
}

export function useMyAttendance(month?: number, year?: number) {
  return useQuery({
    queryKey: ['my-attendance', { month, year }],
    queryFn: () => HRService.getMyAttendance(month, year),
  });
}

export function useClockIn() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: HRService.clockIn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-attendance'] });
      queryClient.invalidateQueries({ queryKey: ['attendance', 'me'] });
      toast.success('Successfully clocked in');
    },
    onError: (error: any) => {
      toast.error(error?.response?.data?.detail || 'Failed to clock in');
    }
  });
}

export function useClockOut() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: HRService.clockOut,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-attendance'] });
      queryClient.invalidateQueries({ queryKey: ['attendance', 'me'] });
      toast.success('Successfully clocked out');
    },
    onError: (error: any) => {
      toast.error(error?.response?.data?.detail || 'Failed to clock out');
    }
  });
}

export function useLockAttendance() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: HRService.lockAttendance,
    onSuccess: ({ updated_count, skipped_incomplete }) => {
      queryClient.invalidateQueries({ queryKey: ['attendance'] });
      // Records without a clock-out are left open rather than frozen blank.
      if (skipped_incomplete > 0) {
        toast.warning(
          `Locked ${updated_count} record(s). ${skipped_incomplete} without a clock-out were left open; complete them, then lock again.`,
        );
      } else {
        toast.success(`Locked ${updated_count} record(s) for this date`);
      }
    },
    onError: () => {
      toast.error('Failed to lock attendance');
    }
  });
}
// --- Attendance correction requests ---

type DetailError = { response?: { data?: { detail?: unknown } } };
const detailText = (error: unknown, fallback: string) => {
  const detail = (error as DetailError)?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg).replace(/^Value error, /, '');
  return fallback;
};

// Any decision moves the grid, the attention list and both request lists.
function useCorrectionMutation<T>(fn: (arg: T) => Promise<unknown>, success: string, failure: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['corrections'] });
      queryClient.invalidateQueries({ queryKey: ['attendance'] });
      queryClient.invalidateQueries({ queryKey: ['my-attendance'] });
      toast.success(success);
    },
    onError: (error) => toast.error(detailText(error, failure)),
  });
}

export const useMyCorrections = () =>
  useQuery({ queryKey: ['corrections', 'me'], queryFn: HRService.getMyCorrections, retry: false });

export const useCorrections = (status?: string) =>
  useQuery({ queryKey: ['corrections', 'all', status], queryFn: () => HRService.getCorrections(status) });

export const useRequestCorrection = () =>
  useCorrectionMutation(HRService.requestCorrection, 'Correction sent to HR', 'Failed to send the correction');

export const useCancelCorrection = () =>
  useCorrectionMutation(HRService.cancelCorrection, 'Request withdrawn', 'Failed to withdraw the request');

export const useApproveCorrection = () =>
  useCorrectionMutation(({ id, note }: { id: number; note?: string }) => HRService.approveCorrection(id, note),
    'Correction approved and applied', 'Failed to approve the correction');

export const useRejectCorrection = () =>
  useCorrectionMutation(({ id, note }: { id: number; note: string }) => HRService.rejectCorrection(id, note),
    'Correction rejected', 'Failed to reject the correction');

export function useUnlockAttendance() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: HRService.unlockAttendance,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attendance'] });
      toast.success('Record unlocked for correction');
    },
    onError: (error: { response?: { data?: { detail?: unknown } } }) => {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Failed to unlock the record');
    },
  });
}

// One's own payslips: approved payrolls only.
export function useMyPayslips() {
  return useQuery({ queryKey: ['payroll', 'me'], queryFn: HRService.getMyPayslips, retry: false });
}

export function usePayrollRun(month: number, year: number) {
  return useQuery({
    queryKey: ['payroll', 'run', { month, year }],
    queryFn: () => HRService.getPayrollRun(month, year),
  });
}

export function useApprovePayroll() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (runId: number) => HRService.approvePayroll(runId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['payroll'] });
      // Approval posts an expense, so the finance views change too.
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['financeSummary'] });
      toast.success('Payroll approved and posted to the ledger as a payable');
    },
    onError: (error: { response?: { data?: { detail?: unknown } } }) => {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Failed to approve payroll');
    },
  });
}

export function useRunPayroll() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ month, year }: { month: number; year: number }) =>
      HRService.generatePayroll(month, year),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['payroll'] });
      toast.success('Draft payroll generated. It still needs approval.');
    },
    onError: (error: any) => {
      const detail = error?.response?.data?.detail;
      const message = typeof detail === 'string' ? detail : 'Failed to generate payroll';
      toast.error(message);
    },
  });
}

export function useCreateEmployee() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: HRService.createEmployee,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['employees'] });
      toast.success('Employee record created successfully');
    },
    // No error toast: the Add Employee dialog shows the server's reason
    // itself and stays open so the details can be corrected.
  });
}

export function useLogAttendance() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: HRService.logAttendance,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attendance'] });
      toast.success('Attendance logged');
    },
    onError: (error: any) => toast.error(error?.response?.data?.detail || 'Failed to log attendance'),
  });
}

export function useUpdateAttendance() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: number; clock_in?: string; clock_out?: string | null }) =>
      HRService.updateAttendance(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attendance'] });
      toast.success('Attendance updated');
    },
    onError: (error: any) => toast.error(error?.response?.data?.detail || 'Failed to update attendance'),
  });
}

export function useExportAttendance() {
  return useMutation({
    mutationFn: HRService.exportAttendance,
    onError: (error: any) => {
      toast.error(error?.response?.data?.detail || 'Failed to export attendance');
    },
  });
}