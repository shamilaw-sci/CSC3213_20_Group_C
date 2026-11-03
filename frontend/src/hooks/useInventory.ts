import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { InventoryService } from '@/services/inventory.service';
import { InventoryTransactionCreate } from '@/types';

export function useInventoryItems() {
  return useQuery({
    queryKey: ['inventoryItems'],
    queryFn: InventoryService.getItems
  });
}

// `enabled` lets a page skip the request for a user who cannot read the
// movement history, instead of firing a request that is sure to be refused.
export function useInventoryTransactions(itemId?: number, enabled: boolean = true) {
  return useQuery({
    queryKey: ['inventoryTransactions', itemId],
    queryFn: () => InventoryService.getTransactions(itemId),
    enabled,
  });
}

export function useCreateInventoryTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tx: InventoryTransactionCreate) => InventoryService.createTransaction(tx),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['inventoryItems'] });
      queryClient.invalidateQueries({ queryKey: ['inventoryTransactions'] });
      queryClient.invalidateQueries({ queryKey: ['inventoryOutstanding'] });
      // A movement changes stock levels, which both alert lists show.
      queryClient.invalidateQueries({ queryKey: ['lowStockItems'] });
      queryClient.invalidateQueries({ queryKey: ['expiringItems'] });
      // A transaction can change a program's total_cost (via the DB
      // trigger), so the program views that show it refresh too.
      queryClient.invalidateQueries({ queryKey: ['programs'] });
      queryClient.invalidateQueries({ queryKey: ['program'] });
      queryClient.invalidateQueries({ queryKey: ['program-financials'] });
      queryClient.invalidateQueries({ queryKey: ['programs-stage'] });
      queryClient.invalidateQueries({ queryKey: ['costPerAnimal'] });
      // A Stock In posts its cost to the finance ledger (migration 013), so
      // the ledger and the finance totals refresh too.
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['finance-summary'] });
      queryClient.invalidateQueries({ queryKey: ['financeSummary'] });
    }
  });
}

export function useCreateInventoryItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: InventoryService.createItem,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['inventoryItems'] });
      queryClient.invalidateQueries({ queryKey: ['lowStockItems'] });
      queryClient.invalidateQueries({ queryKey: ['expiringItems'] });
    }
  });
}

// What each program still holds of one item. Off until an item is chosen.
export function useItemOutstanding(itemId?: number) {
  return useQuery({
    queryKey: ['inventoryOutstanding', itemId],
    queryFn: () => InventoryService.getOutstanding(itemId as number),
    enabled: !!itemId,
  });
}

// NEW: Section 7 of your write-up — Low Stock Alert.
// Refetches every 60s so the alert banner stays current even if the
// user leaves the tab open while someone else issues stock elsewhere.
export function useLowStockItems(threshold: number = 10) {
  return useQuery({
    queryKey: ['lowStockItems', threshold],
    queryFn: () => InventoryService.getLowStockItems(threshold),
    refetchInterval: 60_000,
  });
}

// NEW: Section 8 of your write-up — Expiry Alert.
export function useExpiringItems(days: number = 30) {
  return useQuery({
    queryKey: ['expiringItems', days],
    queryFn: () => InventoryService.getExpiringItems(days),
    refetchInterval: 60_000,
  });
}

// NEW: Section 11 of your write-up — Cost-per-Animal.
// `enabled: !!programId` means this query simply won't run until a real
// programId is passed in — useful when the program to analyze is chosen
// from a dropdown and starts out unselected.
export function useCostPerAnimal(programId?: number) {
  return useQuery({
    queryKey: ['costPerAnimal', programId],
    queryFn: () => InventoryService.getCostPerAnimal(programId as number),
    enabled: !!programId,
  });
}