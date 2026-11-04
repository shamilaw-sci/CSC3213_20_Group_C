import api from '@/lib/api-client';
import { Transaction, Program, RestrictedBalance, LedgerFilters, LedgerPage, StockMovementRef } from '@/types';

export const FinanceService = {
  getTransactions: async (params?: { start_date?: string, end_date?: string }) => {
    const response = await api.get<Transaction[]>('/finance/transactions', { params });
    return response.data;
  },

  // `all` returns every matching row unpaged, for CSV export.
  getLedger: async (filters: LedgerFilters, page = 1, pageSize = 50, all = false) => {
    const response = await api.get<LedgerPage>('/finance/ledger', {
      params: { ...filters, page, page_size: pageSize, all: all || undefined },
    });
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

  // Edits are checked against restricted funds the same way creates are, so
  // the same override applies — see createTransaction.
  updateTransaction: async (
    id: number,
    transaction: Omit<Transaction, 'id' | 'programs'>,
    overrideRestricted = false,
  ) => {
  const response = await api.put<Transaction>(`/finance/transactions/${id}`, transaction, {
    params: overrideRestricted ? { override_restricted: true } : undefined,
  });
  return response.data;
},

// The reason is written to the audit entry. The API requires one for a
// Stock In expense.
voidTransaction: async (id: number, reason?: string) => {
  const response = await api.patch<Transaction>(
    `/finance/transactions/${id}/void`,
    reason ? { reason } : undefined,
  );
  return response.data;
},

// The Stock In behind a stock_in expense; null when there is none or it is
// not linked yet.
getStockMovement: async (id: number) => {
  const response = await api.get<StockMovementRef | null>(`/finance/transactions/${id}/stock-movement`);
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
  }
};
