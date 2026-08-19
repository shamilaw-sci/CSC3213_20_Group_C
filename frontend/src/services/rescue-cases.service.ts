// frontend/src/services/rescue-cases.service.ts
import api from '@/lib/api-client';
import { RescueCaseGeo , CaseOut } from '@/types';

export interface CaseCreatePayload {
  animal_type: string;
  description?: string;
  lat: number;
  lng: number;
  photo_url?: string;
}

export interface Hotspot {
  grid_lat: number;
  grid_lng: number;
  count: number;
  animal_breakdown: Record<string, number>;
  latest_report_at: string;
  is_active_outbreak: boolean;
  outbreak_animal_types: string[];
}



export interface CaseStatusUpdatePayload {
  new_status: string;
  assigned_to?: string;
}

export const RescueCasesService = {
  getCaseGeo: async (params?: { status?: string; days?: number }) => {
    const response = await api.get<RescueCaseGeo[]>('/rescue_cases/geo', { params });
    return response.data;
  },

  createCase: async (payload: CaseCreatePayload) => {
    const response = await api.post('/rescue_cases/cases', payload);
    return response.data;
  },
    uploadPhoto: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post<{ photo_url: string }>(
      '/rescue_cases/upload-photo',
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    );
    return response.data.photo_url;
  },
    getHotspots: async (days = 30) => {
    const response = await api.get<Hotspot[]>('/rescue_cases/hotspots', { params: { days } });
    return response.data;
  },
    listCases: async (status?: string) => {
    const response = await api.get<CaseOut[]>('/rescue_cases/cases', {
      params: status ? { status } : undefined,
    });
    return response.data;
  },

  updateCaseStatus: async (caseId: string, payload: CaseStatusUpdatePayload) => {
    const response = await api.patch<CaseOut>(`/rescue_cases/cases/${caseId}/status`, payload);
    return response.data;
  }
};