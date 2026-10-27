// frontend/src/services/volunteers.service.ts
import api from '@/lib/api-client';

export type VolunteerStatus = 'pending' | 'approved' | 'rejected' | 'inactive';
export type AssignmentResponse = 'pending' | 'accepted' | 'declined';
export type AssignmentType = 'shift' | 'rescue_case' | 'program';

// Mirrors the CHECK constraints in db/migrations/004_volunteers.sql and the
// enums in app/schemas/volunteer.py. A value here that the database rejects is
// a 500 the user cannot act on, so these three lists must move together.
export const SKILLS = [
  { value: 'animal_handling', label: 'Animal handling' },
  { value: 'transport_driving', label: 'Transport / driving' },
  { value: 'veterinary', label: 'Veterinary experience' },
  { value: 'fostering', label: 'Fostering' },
  { value: 'fundraising', label: 'Fundraising' },
  { value: 'admin_office', label: 'Admin / office help' },
  { value: 'media_photography', label: 'Photography / social media' },
  { value: 'community_outreach', label: 'Community outreach' },
] as const;

export const AVAILABILITY = [
  { value: 'weekday_mornings', label: 'Weekday mornings' },
  { value: 'weekday_afternoons', label: 'Weekday afternoons' },
  { value: 'weekday_evenings', label: 'Weekday evenings' },
  { value: 'weekends', label: 'Weekends' },
  { value: 'on_call', label: 'On call for emergencies' },
] as const;

export interface VolunteerApplyPayload {
  full_name: string;
  email: string;
  phone?: string;
  skills: string[];
  skills_other?: string;
  availability: string[];
}

export interface Volunteer {
  id: string;
  full_name: string;
  email: string;
  phone?: string | null;
  skills: string[];
  skills_other?: string | null;
  availability: string[];
  status: VolunteerStatus;
  access_token: string;
  link_shared_at?: string | null;
  applied_at: string;
  reviewed_at?: string | null;
  reviewed_by?: string | null;
  staff_notes?: string | null;
}

export interface ShiftConfirmation {
  assigned: number;
  accepted: number;
  declined: number;
  awaiting: number;
  needed: number;
}

export interface Shift {
  id: string;
  title: string;
  description?: string | null;
  location?: string | null;
  shift_date: string;
  start_time: string;
  end_time: string;
  volunteers_needed: number;
  is_cancelled: boolean;
  created_by?: string | null;
  created_at: string;
  confirmation: ShiftConfirmation;
}

export interface ShiftCreatePayload {
  title: string;
  description?: string;
  location?: string;
  shift_date: string;
  start_time: string;
  end_time: string;
  volunteers_needed: number;
}

export interface Assignment {
  id: string;
  volunteer_id: string;
  shift_id?: string | null;
  rescue_case_id?: string | null;
  program_id?: number | null;
  response: AssignmentResponse;
  decline_reason?: string | null;
  responded_at?: string | null;
  assigned_by?: string | null;
  assigned_at: string;
}

export interface MyAssignment {
  id: string;
  assignment_type: AssignmentType;
  title: string;
  description?: string | null;
  location?: string | null;
  shift_date?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  is_cancelled: boolean;
  response: AssignmentResponse;
  decline_reason?: string | null;
  responded_at?: string | null;
  assigned_at: string;
}

export interface MyAssignments {
  volunteer_name: string;
  assignments: MyAssignment[];
}

export const VolunteersService = {
  // ---- public, no auth ----
  apply: async (payload: VolunteerApplyPayload) => {
    const response = await api.post<{ message: string }>('/volunteers/apply', payload);
    return response.data;
  },

  getMyAssignments: async (token: string) => {
    const response = await api.get<MyAssignments>(
      `/volunteers/my-assignments/${encodeURIComponent(token)}`
    );
    return response.data;
  },

  respond: async (
    token: string,
    assignmentId: string,
    payload: { response: 'accepted' | 'declined'; decline_reason?: string }
  ) => {
    const response = await api.post<MyAssignment>(
      `/volunteers/my-assignments/${encodeURIComponent(token)}/${assignmentId}/respond`,
      payload
    );
    return response.data;
  },

  // ---- staff ----
  list: async (status?: VolunteerStatus) => {
    const response = await api.get<Volunteer[]>('/volunteers', {
      params: status ? { status } : undefined,
    });
    return response.data;
  },

  review: async (
    id: string,
    payload: { status: 'approved' | 'rejected' | 'inactive'; staff_notes?: string }
  ) => {
    const response = await api.patch<Volunteer>(`/volunteers/${id}/review`, payload);
    return response.data;
  },

  markLinkShared: async (id: string) => {
    const response = await api.post<Volunteer>(`/volunteers/${id}/link-shared`);
    return response.data;
  },

  listShifts: async (includePast = false) => {
    const response = await api.get<Shift[]>('/volunteers/shifts', {
      params: { include_past: includePast },
    });
    return response.data;
  },

  createShift: async (payload: ShiftCreatePayload) => {
    const response = await api.post<Shift>('/volunteers/shifts', payload);
    return response.data;
  },

  updateShift: async (id: string, payload: Partial<ShiftCreatePayload> & { is_cancelled?: boolean }) => {
    const response = await api.patch<Shift>(`/volunteers/shifts/${id}`, payload);
    return response.data;
  },

  listAssignments: async (params?: { shift_id?: string; volunteer_id?: string }) => {
    const response = await api.get<Assignment[]>('/volunteers/assignments', { params });
    return response.data;
  },

  assign: async (payload: {
    volunteer_id: string;
    shift_id?: string;
    rescue_case_id?: string;
    program_id?: number;
  }) => {
    const response = await api.post<Assignment>('/volunteers/assignments', payload);
    return response.data;
  },

  unassign: async (assignmentId: string) => {
    const response = await api.delete(`/volunteers/assignments/${assignmentId}`);
    return response.data;
  },
};

/** The volunteer's personal link, for the roster's Copy link button. */
export function volunteerLinkFor(token: string): string {
  const origin = typeof window !== 'undefined' ? window.location.origin : '';
  return `${origin}/my-assignments/${token}`;
}
