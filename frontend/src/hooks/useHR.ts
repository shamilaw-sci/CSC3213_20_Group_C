import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { HRService } from '@/services/hr.service';
import { toast } from 'sonner';

export function useEmployees() {
  return useQuery({
    queryKey: ['employees'],
    queryFn: HRService.getEmployees,
  });
}

export function useAttendance(date?: string, month?: number, year?: number) {
  return useQuery({
    queryKey: ['attendance', { date, month, year }],
    queryFn: () => HRService.getAttendance(date, month, year),
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
    onError: (error: any) => {
      toast.error(error?.response?.data?.detail || 'Failed to add employee');
    }
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
    mutationFn: ({ id, ...data }: { id: number; clock_in?: string; clock_out?: string }) =>
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