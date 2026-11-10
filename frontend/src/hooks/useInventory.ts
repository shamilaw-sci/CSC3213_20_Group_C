import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { InventoryService } from '@/services/inventory.service';
import { InventoryBatchUpdate, InventoryItemUpdate, InventoryTransactionCreate } from '@/types';

// Everything a stock movement can change, refreshed after one is saved or
// reversed.
function invalidateAfterMovement(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ['inventoryItems'] });
  queryClient.invalidateQueries({ queryKey: ['inventoryTransactions'] });
  queryClient.invalidateQueries({ queryKey: ['inventoryOutstanding'] });
  queryClient.invalidateQueries({ queryKey: ['inventoryBatches'] });
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
  // A Stock In posts its cost to the finance ledger (migration 013), and
  // reversing one voids it, so the ledger and the finance totals refresh too.
  queryClient.invalidateQueries({ queryKey: ['transactions'] });
  queryClient.invalidateQueries({ queryKey: ['finance-summary'] });
  queryClient.invalidateQueries({ queryKey: ['financeSummary'] });
}

export function useInventoryItems() {
  return useQuery({
    queryKey: ['inventoryItems'],
    queryFn: InventoryService.getItems
  });
}

// `enabled` lets a page skip the request for a user who cannot read the
// movement history, instead of firing a request that is sure to be refused.
// `limit` fetches only the newest movements (the Stock page shows 10).
export function useInventoryTransactions(itemId?: number, enabled: boolean = true, limit?: number) {
  return useQuery({
    queryKey: ['inventoryTransactions', itemId, limit],
    queryFn: () => InventoryService.getTransactions(itemId, limit),
    enabled,
  });
}

// Every movement in one month. `month` is "YYYY-MM".
export function useInventoryMonthTransactions(month: string, enabled: boolean = true) {
  const [year, monthNumber] = month.split('-').map(Number);
  // Day 0 of the next month is the last day of this one.
  const lastDay = new Date(year, monthNumber, 0).getDate();
  const start = `${month}-01`;
  const end = `${month}-${String(lastDay).padStart(2, '0')}`;
  return useQuery({
    queryKey: ['inventoryTransactions', 'month', month],
    queryFn: () => InventoryService.getTransactions(undefined, undefined, start, end),
    enabled: enabled && /^\d{4}-\d{2}$/.test(month),
  });
}

// Every item's batches with stock left (Stock page list).
export function useAllBatches(enabled: boolean = true) {
  return useQuery({
    queryKey: ['inventoryBatches', 'all'],
    queryFn: InventoryService.getBatches,
    enabled,
  });
}

// An item's batches. Off until an item is chosen.
export function useItemBatches(itemId?: number) {
  return useQuery({
    queryKey: ['inventoryBatches', itemId],
    queryFn: () => InventoryService.getItemBatches(itemId as number),
    enabled: !!itemId,
  });
}

export function useUpdateInventoryBatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, changes }: { id: number; changes: InventoryBatchUpdate }) =>
      InventoryService.updateBatch(id, changes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['inventoryBatches'] });
      // The item's expiry is the soonest of its batches.
      queryClient.invalidateQueries({ queryKey: ['inventoryItems'] });
      queryClient.invalidateQueries({ queryKey: ['inventoryTransactions'] });
      queryClient.invalidateQueries({ queryKey: ['expiringItems'] });
    },
  });
}

export function useCreateInventoryTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tx: InventoryTransactionCreate) => InventoryService.createTransaction(tx),
    onSuccess: () => invalidateAfterMovement(queryClient),
  });
}

export function useReverseInventoryTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      InventoryService.reverseTransaction(id, reason),
    onSuccess: () => invalidateAfterMovement(queryClient),
  });
}

export function useUpdateInventoryItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, changes }: { id: number; changes: InventoryItemUpdate }) =>
      InventoryService.updateItem(id, changes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['inventoryItems'] });
      queryClient.invalidateQueries({ queryKey: ['inventoryTransactions'] });
      queryClient.invalidateQueries({ queryKey: ['lowStockItems'] });
      queryClient.invalidateQueries({ queryKey: ['expiringItems'] });
    },
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