import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { InventoryService } from '@/services/inventory.service';
import { FinanceService } from '@/services/finance.service';
import { InventoryItem, InventoryTransaction, StockInPayload, StockOutPayload, StockReturnPayload, AddItemPayload } from '@/types';

const KEYS = {
  items:         ['inventoryItems'],
  transactions:  (id?: number) => ['inventoryTransactions', id],
  lowStock:      (t: number) => ['lowStockItems', t],
  costPerAnimal: ['costPerAnimal'],
  programs:      ['programs'],
} as const;

export function useInventoryItems() {
  return useQuery({ queryKey: KEYS.items, queryFn: InventoryService.getItems });
}

export function useInventoryTransactions(itemId?: number) {
  return useQuery({
    queryKey: KEYS.transactions(itemId),
    queryFn: () => InventoryService.getTransactions(itemId),
  });
}

export function usePrograms() {
  return useQuery({ queryKey: KEYS.programs, queryFn: FinanceService.getPrograms });
}

export function useCostPerAnimal() {
  return useQuery({ queryKey: KEYS.costPerAnimal, queryFn: InventoryService.getCostPerAnimal });
}

export function useLowStockItems(threshold = 10) {
  return useQuery({
    queryKey: KEYS.lowStock(threshold),
    queryFn: () => InventoryService.getLowStockItems(threshold),
  });
}

function useInvalidateInventory() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: KEYS.items });
    qc.invalidateQueries({ queryKey: KEYS.transactions() });
    qc.invalidateQueries({ queryKey: KEYS.lowStock(10) });
    qc.invalidateQueries({ queryKey: KEYS.costPerAnimal });
  };
}

export function useStockIn() {
  const invalidate = useInvalidateInventory();
  return useMutation({
    mutationFn: (payload: StockInPayload) => InventoryService.stockIn(payload),
    onSuccess: () => { invalidate(); toast.success('Stock added successfully.'); },
    onError: (error: any) => { toast.error(error?.response?.data?.detail ?? 'Failed to add stock.'); },
  });
}

export function useStockOut() {
  const invalidate = useInvalidateInventory();
  return useMutation({
    mutationFn: (payload: StockOutPayload) => InventoryService.stockOut(payload),
    onSuccess: () => { invalidate(); toast.success('Stock issued successfully.'); },
    onError: (error: any) => { toast.error(error?.response?.data?.detail ?? 'Failed to issue stock.'); },
  });
}

export function useStockReturn() {
  const invalidate = useInvalidateInventory();
  return useMutation({
    mutationFn: (payload: StockReturnPayload) => InventoryService.stockReturn(payload),
    onSuccess: () => { invalidate(); toast.success('Stock returned successfully.'); },
    onError: (error: any) => { toast.error(error?.response?.data?.detail ?? 'Failed to return stock.'); },
  });
}

export function useAddInventoryItem() {
  const invalidate = useInvalidateInventory();
  return useMutation({
    mutationFn: (payload: AddItemPayload) => InventoryService.addItem(payload),
    onSuccess: () => { invalidate(); toast.success('Item added to inventory.'); },
    onError: (error: any) => { toast.error(error?.response?.data?.detail ?? 'Failed to add item.'); },
  });
}

export function useCreateInventoryTransaction() {
  const invalidate = useInvalidateInventory();
  return useMutation({
    mutationFn: (tx: Omit<InventoryTransaction, 'id'>) => InventoryService.createTransaction(tx),
    onSuccess: () => { invalidate(); },
  });
}

export function useCreateInventoryItem() {
  const invalidate = useInvalidateInventory();
  return useMutation({
    mutationFn: (item: Omit<InventoryItem, 'id'>) => InventoryService.createItem(item),
    onSuccess: () => { invalidate(); },
  });
}
