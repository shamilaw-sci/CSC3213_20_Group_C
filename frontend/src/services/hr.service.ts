import api from '@/lib/api-client';
import { Employee, EmployeeUpdate, LinkableLogin, MyPayslip, AttendanceRecord, AttendanceMonth, PayrollRun, PayrollRunView, TrackingImpact } from '@/types';

export const HRService = {
  getEmployees: async () => {
    const response = await api.get<Employee[]>('/hr/employees');
    return response.data;
  },
  
  createEmployee: async (employee: Omit<Employee, 'id'>) => {
    const response = await api.post<Employee>('/hr/employees', employee);
    return response.data;
  },

  updateEmployee: async (id: number, changes: EmployeeUpdate) => {
    const response = await api.put<Employee>(`/hr/employees/${id}`, changes);
    return response.data;
  },

  getLinkableLogins: async () => {
    const response = await api.get<LinkableLogin[]>('/hr/linkable-logins');
    return response.data;
  },

  getAttendance: async (date?: string, month?: number, year?: number) => {
    const params: any = {};
    if (date) params.target_date = date;
    if (month && year) {
      params.month = month;
      params.year = year;
    }
    const response = await api.get<AttendanceRecord[]>('/hr/attendance', { params });
    return response.data;
  },

  getMyAttendance: async (month?: number, year?: number) => {
    const params = (month && year) ? { month, year } : {};
    const response = await api.get<AttendanceRecord[]>('/hr/attendance/me', { params });
    return response.data;
  },

  clockIn: async () => {
    const response = await api.post<AttendanceRecord>('/hr/attendance/clock-in');
    return response.data;
  },

  clockOut: async () => {
    const response = await api.post<AttendanceRecord>('/hr/attendance/clock-out');
    return response.data;
  },

  logAttendance: async (attendance: Omit<AttendanceRecord, 'id'>) => {
    const response = await api.post<AttendanceRecord>('/hr/attendance', attendance);
    return response.data;
  },

  lockAttendance: async (date: string) => {
    const response = await api.post<{ updated_count: number; skipped_incomplete: number }>(
      `/hr/attendance/lock-day`, null, { params: { target_date: date } },
    );
    return response.data;
  },

  unlockAttendance: async (id: number) => {
    const response = await api.post<AttendanceRecord>(`/hr/attendance/${id}/unlock`);
    return response.data;
  },

  // The monthly grid: everyone (HR, Director) or just oneself.
  getAttendanceMonth: async (year: number, month: number) =>
    (await api.get<AttendanceMonth>('/hr/attendance/month', { params: { year, month } })).data,

  getMyAttendanceMonth: async (year: number, month: number) =>
    (await api.get<AttendanceMonth>('/hr/attendance/me/month', { params: { year, month } })).data,

  // When attendance tracking starts: the organisation date, or one person's
  // override (null start clears it). Impact first, so HR sees what changes.
  getTrackingImpact: async (start: string | null, employeeId?: number) =>
    (await api.get<TrackingImpact>('/hr/attendance-tracking/impact', {
      params: { ...(start ? { start } : {}), ...(employeeId ? { employee_id: employeeId } : {}) },
    })).data,

  setTrackingStart: async (date: string) =>
    (await api.put('/hr/attendance-tracking', { tracking_start_date: date })).data,

  setEmployeeTracking: async (employeeId: number, date: string | null) =>
    (await api.put(`/hr/employees/${employeeId}/attendance-tracking`, { tracked_from: date })).data,

  getPayrollRun: async (month: number, year: number) => {
    const response = await api.get<PayrollRunView>('/hr/payroll/run', { params: { month, year } });
    return response.data;
  },

  // Creates or refreshes the month's Draft. Nothing reaches the ledger yet.
  generatePayroll: async (month: number, year: number) => {
    const response = await api.post<PayrollRun>(`/hr/payroll/generate`, null, { params: { month, year } });
    return response.data;
  },

  // Posts the run's total to the ledger as a payable. Refused for whoever
  // generated it.
  approvePayroll: async (runId: number) => {
    const response = await api.post<PayrollRun>(`/hr/payroll/runs/${runId}/approve`);
    return response.data;
  },

  // A payslip PDF, as a blob to save: anyone's for HR and approvers
  // (a draft's is marked DRAFT), one's own approved ones for staff.
  getPayslip: async (runId: number, employeeId: number) =>
    (await api.get<Blob>(`/hr/payroll/runs/${runId}/payslips/${employeeId}`, { responseType: 'blob' })).data,

  getMyPayslips: async () => (await api.get<MyPayslip[]>('/hr/payroll/me/payslips')).data,

  getMyPayslip: async (runId: number) =>
    (await api.get<Blob>(`/hr/payroll/me/payslips/${runId}`, { responseType: 'blob' })).data,

  // clock_out: null clears a wrong clock-out.
  updateAttendance: async (id: number, attendance: { clock_in?: string; clock_out?: string | null }) => {
  const response = await api.put<AttendanceRecord>(`/hr/attendance/${id}`, attendance);
  return response.data;
  },

  exportAttendance: async (date: string) => {
    const response = await api.get(`/hr/attendance/export`, {
      params: { target_date: date },
      responseType: 'blob', 
    });
    return response.data;
  }

};
