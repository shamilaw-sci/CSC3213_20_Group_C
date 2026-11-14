import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { LeaveService } from '@/services/leave.service';
import { LeaveInput, LeaveStatus } from '@/types';

type ApiError = { response?: { data?: { detail?: unknown } } };

export function leaveErrorText(error: unknown, fallback: string) {
  const detail = (error as ApiError)?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  return fallback;
}

// Every leave change can move balances and lists, so they refresh together.
const KEY = 'leave';

function useLeaveMutation<T>(fn: (arg: T) => Promise<unknown>, success: string, failure: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [KEY] });
      toast.success(success);
    },
    onError: (error) => toast.error(leaveErrorText(error, failure)),
  });
}

export const useLeaveTypes = () => useQuery({ queryKey: [KEY, 'types'], queryFn: LeaveService.getTypes });

export const useMyLeave = (year?: number) =>
  useQuery({ queryKey: [KEY, 'me', year], queryFn: () => LeaveService.getMine(year), retry: false });

// Recomputed as the form changes; the server counts the days against the
// person's schedule and the holiday calendar.
export const useLeavePreview = (body: LeaveInput | null) =>
  useQuery({
    queryKey: [KEY, 'preview', body],
    queryFn: () => LeaveService.preview(body!),
    enabled: !!body,
    retry: false,
    placeholderData: (previous) => previous,
  });

export const useLeaveRequests = (status?: LeaveStatus, year?: number) =>
  useQuery({ queryKey: [KEY, 'requests', status, year], queryFn: () => LeaveService.list(status, year) });

export const useEntitlements = (year: number) =>
  useQuery({ queryKey: [KEY, 'entitlements', year], queryFn: () => LeaveService.getEntitlements(year) });

export const useRequestLeave = () =>
  useLeaveMutation((body: LeaveInput) => LeaveService.request(body), 'Leave requested', 'Failed to request leave');

export const useCancelLeave = () =>
  useLeaveMutation(LeaveService.cancel, 'Leave cancelled', 'Failed to cancel leave');

export const useApproveLeave = () =>
  useLeaveMutation(({ id, note }: { id: number; note?: string }) => LeaveService.approve(id, note), 'Leave approved', 'Failed to approve leave');

export const useRejectLeave = () =>
  useLeaveMutation(({ id, note }: { id: number; note: string }) => LeaveService.reject(id, note), 'Leave rejected', 'Failed to reject leave');

export const useGenerateEntitlements = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: LeaveService.generateEntitlements,
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: [KEY] });
      const flagged = result.needs_date_joined.length;
      if (flagged) {
        toast.warning(`Created ${result.created} entitlements. ${flagged} employee(s) need a join date before their annual or casual leave can be set.`);
      } else {
        toast.success(`Created ${result.created} entitlements`);
      }
    },
    onError: (error) => toast.error(leaveErrorText(error, 'Failed to generate entitlements')),
  });
};

export const useAdjustEntitlement = () =>
  useLeaveMutation(({ id, adjustment, note }: { id: number; adjustment: number; note?: string }) =>
    LeaveService.adjustEntitlement(id, adjustment, note), 'Entitlement adjusted', 'Failed to adjust the entitlement');

type DateJoinedResult = {
  entitlements_updated?: { year: number; leave_type: string; from: number; to: number }[];
};

// A join date decides annual and casual allowances, so the server recomputes
// this year's and later ones; the toast says what moved.
export function useSetDateJoined() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ employeeId, date }: { employeeId: number; date: string }) =>
      LeaveService.setDateJoined(employeeId, date) as Promise<DateJoinedResult>,
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: [KEY] });
      queryClient.invalidateQueries({ queryKey: ['employees'] });
      const changed = result?.entitlements_updated ?? [];
      toast.success(changed.length
        ? `Join date saved. Updated ${changed.map((c) => `${c.year} ${c.leave_type.toLowerCase()}: ${c.from} to ${c.to} days`).join('; ')}.`
        : 'Join date saved');
    },
    onError: (error) => toast.error(leaveErrorText(error, 'Failed to save the join date')),
  });
}
