import api from '@/lib/api-client';
import { ProgramDetail, ProgramAssignment, CostPerAnimalResult, ProgramFinancials } from '@/types';

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

  getFinancials: async (programId: number) => {
    const response = await api.get<ProgramFinancials>(`/programs/${programId}/financials`);
    return response.data;
  },
};