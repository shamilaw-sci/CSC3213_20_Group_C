// frontend/src/services/donations.service.ts
import api from '@/lib/api-client';

export type DonationPurpose = 'program' | 'general';
export type DonationStatus = 'pending' | 'paid' | 'failed' | 'cancelled';

// Mirrors the amount CHECK in db/migrations/015_donations.sql and
// MIN_DONATION / MAX_DONATION in app/schemas/donations.py.
export const MIN_DONATION = 100;
export const MAX_DONATION = 999999.99;

export interface DonationProgram {
  id: number;
  program_name: string;
  status: 'Upcoming' | 'Active';
  start_date?: string | null;
  end_date?: string | null;
}

export interface DonationCheckoutPayload {
  amount: number;
  purpose: DonationPurpose;
  program_id?: number;
  is_anonymous: boolean;
  donor_name?: string;
  donor_email?: string;
  donor_phone?: string;
  message?: string;
}

export interface DonationCheckout {
  order_id: string;
  action_url: string;
  fields: Record<string, string>;
}

export interface DonationConfirmation {
  order_id: string;
  status: DonationStatus;
  amount: string;
  purpose: DonationPurpose;
  program_name?: string | null;
  is_anonymous: boolean;
}

export interface Donation {
  id: number;
  amount: string;
  currency: string;
  purpose: DonationPurpose;
  program_id?: number | null;
  program_name?: string | null;
  is_anonymous: boolean;
  donor_name?: string | null;
  donor_email?: string | null;
  donor_phone?: string | null;
  message?: string | null;
  status: DonationStatus;
  gateway: string;
  gateway_ref?: string | null;
  finance_transaction_id?: number | null;
  thank_you_sent_at?: string | null;
  created_at: string;
  paid_at?: string | null;
}

export interface DonorContribution {
  donor_name: string;
  donor_email: string;
  total: string;
  count: number;
  first_donation_at?: string | null;
  last_donation_at?: string | null;
}

export interface DonationSummary {
  total_raised: string;
  donation_count: number;
  average_donation: string;
  largest_donation: string;
  named_total: string;
  named_count: number;
  unique_donors: number;
  anonymous_total: string;
  anonymous_count: number;
  program_total: string;
  general_total: string;
  pending_count: number;
  by_program: { program_id: number; program_name: string; total: string; count: number }[];
  donors: DonorContribution[];
  monthly: { month: string; total: string; count: number }[];
}

const LAST_ORDER_KEY = 'vff-last-donation-order';

/** The order this tab last sent to PayHere, as a fallback for the thank-you page. */
export function lastOrderId(): string {
  try {
    return sessionStorage.getItem(LAST_ORDER_KEY) ?? '';
  } catch {
    return '';
  }
}

/**
 * Send the browser to PayHere's checkout page. PayHere takes a form POST, not
 * a link, so a hidden form is built from the fields the backend signed and
 * submitted. The merchant secret never reaches the browser; only the hash does.
 */
export function redirectToPayHere(checkout: DonationCheckout): void {
  try {
    sessionStorage.setItem(LAST_ORDER_KEY, checkout.order_id);
  } catch {
    // Private mode or storage blocked: the return URL still carries the id.
  }
  const form = document.createElement('form');
  form.method = 'POST';
  form.action = checkout.action_url;
  for (const [name, value] of Object.entries(checkout.fields)) {
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = name;
    input.value = value;
    form.appendChild(input);
  }
  document.body.appendChild(form);
  form.submit();
}

export const DonationsService = {
  // ---- public, no auth ----
  listPrograms: async () => {
    const response = await api.get<DonationProgram[]>('/donations/programs');
    return response.data;
  },

  checkout: async (payload: DonationCheckoutPayload) => {
    const response = await api.post<DonationCheckout>('/donations/checkout', payload);
    return response.data;
  },

  confirm: async (orderId: string) => {
    const response = await api.post<DonationConfirmation>(
      `/donations/confirm/${encodeURIComponent(orderId)}`
    );
    return response.data;
  },

  cancel: async (orderId: string) => {
    const response = await api.post<DonationConfirmation>(
      `/donations/cancel/${encodeURIComponent(orderId)}`
    );
    return response.data;
  },

  // ---- staff (finance:read) ----
  list: async (params?: { status?: DonationStatus; purpose?: DonationPurpose }) => {
    const response = await api.get<Donation[]>('/donations', { params });
    return response.data;
  },

  summary: async () => {
    const response = await api.get<DonationSummary>('/donations/summary');
    return response.data;
  },
};
