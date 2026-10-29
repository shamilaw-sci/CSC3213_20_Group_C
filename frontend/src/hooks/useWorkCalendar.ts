import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { WorkCalendarService } from '@/services/workCalendar.service';
import { HolidayInput, WorkScheduleInput } from '@/types';

type ApiError = { response?: { data?: { detail?: unknown } } };

function errorText(error: ApiError, fallback: string) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  // FastAPI validation errors arrive as a list; show the first message.
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  return fallback;
}

// Every change to schedules or holidays can change how attendance reads, so
// they share one key family and refresh together.
const KEY = 'work-calendar';

function useCalendarMutation<T>(fn: (arg: T) => Promise<unknown>, success: string, failure: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [KEY] });
      toast.success(success);
    },
    onError: (error: ApiError) => toast.error(errorText(error, failure)),
  });
}

export function useSchedules() {
  return useQuery({ queryKey: [KEY, 'schedules'], queryFn: WorkCalendarService.getSchedules });
}

export function useScheduleAssignments() {
  return useQuery({ queryKey: [KEY, 'assignments'], queryFn: WorkCalendarService.getAssignments });
}

export function useHolidays(year: number) {
  return useQuery({ queryKey: [KEY, 'holidays', year], queryFn: () => WorkCalendarService.getHolidays(year) });
}

export function useHolidayImportPreview(year: number, enabled: boolean) {
  return useQuery({
    queryKey: [KEY, 'import-preview', year],
    queryFn: () => WorkCalendarService.previewImport(year),
    enabled,
    retry: false,
  });
}

export function useMySchedule() {
  return useQuery({ queryKey: [KEY, 'me'], queryFn: WorkCalendarService.getMySchedule, retry: false });
}

export const useSaveSchedule = () =>
  useCalendarMutation(
    ({ id, body }: { id?: number; body: WorkScheduleInput }) =>
      id ? WorkCalendarService.updateSchedule(id, body) : WorkCalendarService.createSchedule(body),
    'Schedule saved',
    'Failed to save the schedule',
  );

export const useMakeDefaultSchedule = () =>
  useCalendarMutation(WorkCalendarService.makeDefault, 'Default schedule changed', 'Failed to change the default');

export const useDeleteSchedule = () =>
  useCalendarMutation(WorkCalendarService.deleteSchedule, 'Schedule deleted', 'Failed to delete the schedule');

export const useAssignSchedule = () =>
  useCalendarMutation(
    ({ employeeId, scheduleId, effectiveFrom }: { employeeId: number; scheduleId: number; effectiveFrom: string }) =>
      WorkCalendarService.assign(employeeId, scheduleId, effectiveFrom),
    'Schedule assigned',
    'Failed to assign the schedule',
  );

export const useDeleteAssignment = () =>
  useCalendarMutation(WorkCalendarService.deleteAssignment, 'Assignment removed', 'Failed to remove the assignment');

export const useImportHolidays = () =>
  useCalendarMutation(WorkCalendarService.importHolidays, 'Holidays imported from the gazette', 'Failed to import holidays');

export const useSaveHoliday = () =>
  useCalendarMutation(
    ({ id, body }: { id?: number; body: HolidayInput }) =>
      id ? WorkCalendarService.updateHoliday(id, body) : WorkCalendarService.createHoliday(body),
    'Holiday saved',
    'Failed to save the holiday',
  );

export const useDeleteHoliday = () =>
  useCalendarMutation(WorkCalendarService.deleteHoliday, 'Holiday removed', 'Failed to remove the holiday');
