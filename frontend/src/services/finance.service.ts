import api from '@/lib/api-client';
import { Transaction, Program, MonthlySummary, RestrictedBalance } from '@/types';

export const FinanceService = {
  getTransactions: async (params?: { start_date?: string, end_date?: string }) => {
    const response = await api.get<Transaction[]>('/finance/transactions', { params });
    return response.data;
  },
  
  // overrideRestricted authorizes an expense that overspends a program's
  // earmarked funds. The backend rejects it with 403 unless the caller holds
  // finance:restricted:override, and records every use to the audit log.
  createTransaction: async (
    transaction: Omit<Transaction, 'id'>,
    overrideRestricted = false,
  ) => {
    const response = await api.post<Transaction>('/finance/transactions', transaction, {
      params: overrideRestricted ? { override_restricted: true } : undefined,
    });
    return response.data;
  },

  getRestrictedBalance: async (programId: number) => {
    const response = await api.get<RestrictedBalance>(
      `/finance/programs/${programId}/restricted-balance`,
    );
    return response.data;
  },

  getPrograms: async () => {
    const response = await api.get<Program[]>('/finance/programs');
    return response.data;
  },

  createProgram: async (program: Omit<Program, 'id'>) => {
    const response = await api.post<Program>('/finance/programs', program);
    return response.data;
  },

  updateTransaction: async (id: number, transaction: Omit<Transaction, 'id' | 'programs'>) => {
  const response = await api.put<Transaction>(`/finance/transactions/${id}`, transaction);
  return response.data;
},

voidTransaction: async (id: number) => {
  const response = await api.patch<Transaction>(`/finance/transactions/${id}/void`);
  return response.data;
},

settleTransaction: async (id: number) => {
  const response = await api.patch<Transaction>(`/finance/transactions/${id}/settle`);
  return response.data;
},

  getSummary: async () => {
    const response = await api.get<{
      cash_available: number;
      receivables: number;
      monthly_expenses: number;
    }>('/finance/summary');
    return response.data;
  },

  getAging: async () => {
    const response = await api.get<Record<string, number>>('/finance/aging');
    return response.data;
  },

  getMonthlySummary: async (year: number, month: number) => {
    const response = await api.get<MonthlySummary>('/finance/summary/monthly', {
      params: { year, month },
    });
    return response.data;
  }
};
