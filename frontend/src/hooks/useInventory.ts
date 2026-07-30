import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { InventoryService } from '@/services/inventory.service';
import { InventoryItem, InventoryTransaction } from '@/types';

export function useInventoryItems() {
  return useQuery({
    queryKey: ['inventoryItems'],
    queryFn: InventoryService.getItems
  });
}

export function useInventoryTransactions(itemId?: number) {
  return useQuery({
    queryKey: ['inventoryTransactions', itemId],
    queryFn: () => InventoryService.getTransactions(itemId)
  });
}

export function useCreateInventoryTransaction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tx: Omit<InventoryTransaction, 'id' | 'total_cost'>) => InventoryService.createTransaction(tx),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['inventoryItems'] });
      queryClient.invalidateQueries({ queryKey: ['inventoryTransactions'] });
      // NEW: a transaction can change a program's total_cost (via the DB
      // trigger), and it can change whether an item now counts as low
      // stock. Invalidating these too means the Programs page and any
      // low-stock banner refresh automatically instead of showing stale
      // numbers until the user manually reloads the page.
      queryClient.invalidateQueries({ queryKey: ['programs'] });
      queryClient.invalidateQueries({ queryKey: ['lowStockItems'] });
      queryClient.invalidateQueries({ queryKey: ['costPerAnimal'] });
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