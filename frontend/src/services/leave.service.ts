import api from '@/lib/api-client';
import { EntitlementsView, LeaveInput, LeavePreview, LeaveRequest, LeaveStatus, LeaveTypeRow, MyLeave } from '@/types';

// Leave (backend: app/api/leave.py).
export const LeaveService = {
  getTypes: async () => (await api.get<LeaveTypeRow[]>('/leave/types')).data,

  getMine: async (year?: number) => (await api.get<MyLeave>('/leave/me', { params: { year } })).data,

  preview: async (body: LeaveInput) => (await api.post<LeavePreview>('/leave/preview', body)).data,

  request: async (body: LeaveInput) => (await api.post<LeaveRequest>('/leave/requests', body)).data,

  cancel: async (id: number) => (await api.post<LeaveRequest>(`/leave/requests/${id}/cancel`)).data,

  list: async (status?: LeaveStatus, year?: number) =>
    (await api.get<LeaveRequest[]>('/leave/requests', { params: { status, year } })).data,

  approve: async (id: number, note?: string) => (await api.post<LeaveRequest>(`/leave/requests/${id}/approve`, { note })).data,

  reject: async (id: number, note: string) => (await api.post<LeaveRequest>(`/leave/requests/${id}/reject`, { note })).data,

  getEntitlements: async (year: number) => (await api.get<EntitlementsView>('/leave/entitlements', { params: { year } })).data,

  generateEntitlements: async (year: number) =>
    (await api.post<{ created: number; skipped_existing: number; needs_date_joined: { employee_name: string; leave_types: string[] }[] }>(
      '/leave/entitlements/generate', null, { params: { year } },
    )).data,

  adjustEntitlement: async (id: number, adjustment: number, note?: string) =>
    (await api.put(`/leave/entitlements/${id}`, { adjustment, note })).data,

  setDateJoined: async (employeeId: number, dateJoined: string) =>
    (await api.patch(`/leave/employees/${employeeId}/date-joined`, { date_joined: dateJoined })).data,
};
