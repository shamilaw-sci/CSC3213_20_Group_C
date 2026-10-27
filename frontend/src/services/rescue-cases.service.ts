// frontend/src/services/rescue-cases.service.ts
import api from '@/lib/api-client';
import { RescueCaseGeo , CaseOut, OptimizedRoute, AssigneeOption } from '@/types';

export interface CaseCreatePayload {
  animal_type: string;
  description?: string;
  lat: number;
  lng: number;
  photo_url?: string;
}



export interface CaseStatusUpdatePayload {
  new_status: string;
  assigned_to?: string;
}

export interface OutbreakZone {
  id: string;
  animal_type: string;
  title: string;
  description?: string;
  center_lat: number;
  center_lng: number;
  radius_km: number;
  declared_at: string;
  is_active: boolean;
  resolved_at?: string | null;
}

export interface OutbreakZoneCreatePayload {
  animal_type: string;
  title: string;
  description?: string;
  center_lat: number;
  center_lng: number;
  radius_km: number;
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
    listAssignees: async () => {
    const response = await api.get<AssigneeOption[]>('/rescue_cases/assignees');
    return response.data;
  },

    listCases: async (status?: string) => {
    const response = await api.get<CaseOut[]>('/rescue_cases/cases', {
      params: status ? { status } : undefined,
    });
    return response.data;
  },

  // Optimized visiting order for the caller's own open cases. The backend
  // scopes this to the authenticated user, so there is no user id to pass.
  getMyRoute: async (lat: number, lng: number) => {
    const response = await api.get<OptimizedRoute>('/rescue_cases/my-route', {
      params: { lat, lng },
    });
    return response.data;
  },

  updateCaseStatus: async (caseId: string, payload: CaseStatusUpdatePayload) => {
    const response = await api.patch<CaseOut>(`/rescue_cases/cases/${caseId}/status`, payload);
    return response.data;
  },
  getOutbreakZones: async () => {
    const response = await api.get<OutbreakZone[]>('/rescue_cases/outbreak-zones');
    return response.data;
  },

  declareOutbreakZone: async (payload: OutbreakZoneCreatePayload) => {
    const response = await api.post<OutbreakZone>('/rescue_cases/outbreak-zones', payload);
    return response.data;
  },

  resolveOutbreakZone: async (zoneId: string) => {
    const response = await api.patch<OutbreakZone>(`/rescue_cases/outbreak-zones/${zoneId}/resolve`);
    return response.data;
  },
};