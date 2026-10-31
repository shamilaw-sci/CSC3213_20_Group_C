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

// Program lifecycle. Mirrors app/services/program_lifecycle.py: programs only
// move Upcoming -> Active -> Completed, one step at a time.
export type ProgramStage = 'Upcoming' | 'Active' | 'Completed';

/** One card on a lifecycle page. Mirrors ProgramSummary in app/schemas/programs.py. */
export interface ProgramSummary extends ProgramDetail {
  team_count: number;
  volunteer_count: number;
  revenue: number;
  profit: number;
  cost_per_animal: number | null;
}

export const ProgramService = {
  listByStage: async (status: ProgramStage) => {
    const response = await api.get<ProgramSummary[]>('/programs', { params: { status } });
    return response.data;
  },

  // Every new program starts as Upcoming; the API ignores any status sent.
  create: async (data: { program_name: string; location: string; start_date?: string }) => {
    const response = await api.post<ProgramDetail>('/finance/programs', {
      ...data,
      total_animals_treated: 0,
    });
    return response.data;
  },

  // Set or change a program's location (programs:manage).
  updateLocation: async (programId: number, location: string) => {
    const response = await api.patch<ProgramDetail>(`/programs/${programId}`, { location });
    return response.data;
  },

  // Correct a COMPLETED program's final animal count (programs:manage).
  updateAnimalsTreated: async (programId: number, totalAnimalsTreated: number) => {
    const response = await api.patch<ProgramDetail>(`/programs/${programId}`, {
      total_animals_treated: totalAnimalsTreated,
    });
    return response.data;
  },

  start: async (programId: number) => {
    const response = await api.post<ProgramDetail>(`/programs/${programId}/start`);
    return response.data;
  },

  // The final animal count is required: it is stored with the status change
  // and drives the Completed page's cost per animal.
  complete: async (programId: number, totalAnimalsTreated: number) => {
    const response = await api.post<ProgramDetail>(`/programs/${programId}/complete`, {
      total_animals_treated: totalAnimalsTreated,
    });
    return response.data;
  },

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