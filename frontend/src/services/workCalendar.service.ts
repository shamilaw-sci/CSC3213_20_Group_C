import api from '@/lib/api-client';
import {
  HolidayImportPreview,
  HolidayInput,
  Holiday,
  MySchedule,
  ScheduleAssignmentRow,
  WorkSchedule,
  WorkScheduleInput,
} from '@/types';

// Work schedules and the holiday calendar (backend: app/api/hr_calendar.py).
export const WorkCalendarService = {
  getSchedules: async () => (await api.get<WorkSchedule[]>('/hr/schedules')).data,

  createSchedule: async (body: WorkScheduleInput) => (await api.post<WorkSchedule>('/hr/schedules', body)).data,

  updateSchedule: async (id: number, body: WorkScheduleInput) =>
    (await api.put<WorkSchedule>(`/hr/schedules/${id}`, body)).data,

  makeDefault: async (id: number) => (await api.post<WorkSchedule>(`/hr/schedules/${id}/default`)).data,

  deleteSchedule: async (id: number) => (await api.delete(`/hr/schedules/${id}`)).data,

  getAssignments: async () => (await api.get<ScheduleAssignmentRow[]>('/hr/schedule-assignments')).data,

  assign: async (employeeId: number, scheduleId: number, effectiveFrom: string) =>
    (await api.post(`/hr/employees/${employeeId}/schedule`, { schedule_id: scheduleId, effective_from: effectiveFrom })).data,

  deleteAssignment: async (id: number) => (await api.delete(`/hr/schedule-assignments/${id}`)).data,

  getHolidays: async (year: number) => (await api.get<Holiday[]>('/hr/holidays', { params: { year } })).data,

  previewImport: async (year: number) =>
    (await api.get<HolidayImportPreview>('/hr/holidays/import-preview', { params: { year } })).data,

  importHolidays: async (year: number) =>
    (await api.post<{ added: number; skipped_existing: number; warnings: string[] }>(
      '/hr/holidays/import', null, { params: { year } },
    )).data,

  createHoliday: async (body: HolidayInput) => (await api.post<Holiday>('/hr/holidays', body)).data,

  updateHoliday: async (id: number, body: HolidayInput) => (await api.put<Holiday>(`/hr/holidays/${id}`, body)).data,

  deleteHoliday: async (id: number) => (await api.delete(`/hr/holidays/${id}`)).data,

  getMySchedule: async () => (await api.get<MySchedule>('/hr/schedules/me')).data,
};
