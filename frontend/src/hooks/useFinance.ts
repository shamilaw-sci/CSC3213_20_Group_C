import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { FinanceService } from '@/services/finance.service';
import { ReportsService } from '@/services/reports.service';
import { LedgerFilters } from '@/types';

export function useTransactions(start_date?: string, end_date?: string) {
  return useQuery({
    queryKey: ['transactions', { start_date, end_date }],
    queryFn: () => FinanceService.getTransactions({ start_date, end_date })
  });
}

export function useFinanceSummary() {
  return useQuery({
    queryKey: ['finance-summary'],
    queryFn: FinanceService.getSummary
  });
}

export function useFinanceAging() {
  return useQuery({
    queryKey: ['finance-aging'],
    queryFn: FinanceService.getAging
  });
}

export function useFinanceReport(start: string, end: string) {
  return useQuery({
    queryKey: ['finance-report', { start, end }],
    queryFn: () => ReportsService.getFinanceReport(start, end),
    enabled: !!start && !!end && start <= end,
    // Changing the period swaps the data in place rather than flashing the
    // page back to skeletons.
    placeholderData: (previous) => previous,
  });
}

// Keyed under 'transactions' so every create / edit / void / settle, which
// already invalidates that key, refreshes the ledger too.
export function useLedger(filters: LedgerFilters, page: number, pageSize: number) {
  return useQuery({
    queryKey: ['transactions', 'ledger', { filters, page, pageSize }],
    queryFn: () => FinanceService.getLedger(filters, page, pageSize),
    placeholderData: (previous) => previous,
  });
}

export function usePrograms() {
  return useQuery({
    queryKey: ['programs'],
    queryFn: FinanceService.getPrograms
  });
}

export function useSettleTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: FinanceService.settleTransaction,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['finance-summary'] });
      queryClient.invalidateQueries({ queryKey: ['finance-aging'] });
    }
  });
}
