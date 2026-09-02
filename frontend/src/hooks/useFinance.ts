import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { FinanceService } from '@/services/finance.service';
import { Transaction, Program } from '@/types';

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

export function useMonthlySummary(year: number, month: number) {
  return useQuery({
    queryKey: ['finance-monthly-summary', { year, month }],
    queryFn: () => FinanceService.getMonthlySummary(year, month)
  });
}

export function usePrograms() {
  return useQuery({
    queryKey: ['programs'],
    queryFn: FinanceService.getPrograms
  });
}

export function useCreateTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    // Wrapped rather than passed by reference: createTransaction now takes an
    // optional second argument (overrideRestricted), and a two-parameter
    // function is not assignable to React Query's single-argument
    // MutationFunction. This hook has no override affordance, so it always
    // uses the default — an overspend from here is refused with 409, which is
    // the correct outcome for a caller that cannot authorize one.
    mutationFn: (transaction: Parameters<typeof FinanceService.createTransaction>[0]) =>
      FinanceService.createTransaction(transaction),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['finance-summary'] });
      queryClient.invalidateQueries({ queryKey: ['finance-aging'] });
    }
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
