// frontend/src/services/rescue-cases.service.ts
import api from '@/lib/api-client';
import { RescueCaseGeo , CaseOut, OptimizedRoute, AssigneeOption, CaseEvent, CaseOutcome, CaseReport } from '@/types';

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
  // Required when moving into Resolved, refused otherwise.
  outcome?: CaseOutcome;
  outcome_note?: string;
}

// Matches PublicImpact in backend/app/api/rescue_cases.py: totals only.
export interface PublicImpact {
  year: number;
  reported: number;
  cared_for: number;
  rehomed: number;
  released: number;
  transferred: number;
  supplies_cost: number;
  as_of: string;
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
  getTimeline: async (caseId: string) => {
    const response = await api.get<CaseEvent[]>(`/rescue_cases/cases/${caseId}/timeline`);
    return response.data;
  },

  addNote: async (caseId: string, body: string) => {
    const response = await api.post<CaseEvent>(`/rescue_cases/cases/${caseId}/notes`, { body });
    return response.data;
  },

  getReport: async (year: number, month: number) => {
    const response = await api.get<CaseReport>('/rescue_cases/report', { params: { year, month } });
    return response.data;
  },

  // This year's public totals (GET /rescue_cases/impact, no sign-in).
  getImpact: async () => {
    const response = await api.get<PublicImpact>('/rescue_cases/impact');
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