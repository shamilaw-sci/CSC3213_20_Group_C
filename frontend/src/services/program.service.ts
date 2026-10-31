import api from '@/lib/api-client';
import { ProgramDetail, ProgramAssignment, CostPerAnimalResult, ProgramFinancials } from '@/types';

// Mirrors ProgramVolunteer in app/schemas/programs.py. No email or phone:
// programs:read reaches roles that do not hold volunteers:read.
export interface ProgramVolunteerShift {
  shift_id: string;
  title: string;
  shift_date: string;
  start_time: string;
  end_time: string;
  location?: string | null;
  responded_at?: string | null;
}

export interface ProgramVolunteer {
  volunteer_id: string;
  full_name: string;
  skills: string[];
  skills_other?: string | null;
  program_assignment: boolean;
  shifts: ProgramVolunteerShift[];
}

export const ProgramService = {
  getProgram: async (id: number) => {
    const response = await api.get<ProgramDetail>(`/programs/${id}`);
    return response.data;
  },

  getTeam: async (programId: number) => {
    const response = await api.get<ProgramAssignment[]>(`/programs/${programId}/team`);
    return response.data;
  },

  assignWorker: async (programId: number, data: { employee_id: number; role_on_program?: string }) => {
    const response = await api.post<ProgramAssignment>(`/programs/${programId}/team`, data);
    return response.data;
  },

  removeWorker: async (programId: number, assignmentId: number) => {
    const response = await api.delete(`/programs/${programId}/team/${assignmentId}`);
    return response.data;
  },

  // Reuses your existing, already-working Inventory endpoint.
  // Not duplicated here - just called from the Program module.
  getCostPerAnimal: async (programId: number) => {
    const response = await api.get<CostPerAnimalResult>(`/inventory/analytics/cost-per-animal/${programId}`);
    return response.data;
  },

  // Volunteers who accepted a (non-cancelled) shift for this program, or a
  // direct assignment to it. Pending and declined answers are not included.
  getVolunteers: async (programId: number) => {
    const response = await api.get<ProgramVolunteer[]>(`/programs/${programId}/volunteers`);
    return response.data;
  },

  getFinancials: async (programId: number) => {
    const response = await api.get<ProgramFinancials>(`/programs/${programId}/financials`);
    return response.data;
  },
};