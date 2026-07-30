import api from '@/lib/api-client';
import { RescueCaseGeo } from '@/types';

export const RescueCasesService = {
  getCaseGeo: async (params?: { status?: string; days?: number }) => {
    const response = await api.get<RescueCaseGeo[]>('/rescue_cases/geo', { params });
    return response.data;
  },
};