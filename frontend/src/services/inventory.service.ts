import api from '@/lib/api-client';
import {
  InventoryBatch,
  InventoryBatchUpdate,
  InventoryItem,
  InventoryItemUpdate,
  InventoryTransaction,
  InventoryTransactionCreate,
  LowStockItem,
  ExpiringItem,
  CostPerAnimalResult,
} from '@/types';

// One row per program for a single item: issued, already returned, and what
// is still out. Matches OutstandingByProgram in backend/app/schemas/inventory.py.
// Declared here rather than in @/types so this fix touches inventory files only.
export interface OutstandingByProgram {
  program_id: number;
  program_name: string | null;
  issued: number;
  returned: number;
  outstanding: number;
}

export const InventoryService = {
  getItems: async () => {
    const response = await api.get<InventoryItem[]>('/inventory/items');
    return response.data;
  },

  createItem: async (item: Omit<InventoryItem, 'id'>) => {
    const response = await api.post<InventoryItem>('/inventory/items', item);
    return response.data;
  },

  // Correct an item's name, supplier or reorder level.
  updateItem: async (id: number, changes: InventoryItemUpdate) => {
    const response = await api.patch<InventoryItem>(`/inventory/items/${id}`, changes);
    return response.data;
  },

  // `limit` asks for only the newest movements instead of the whole history.
  // `startDate`/`endDate` (YYYY-MM-DD, inclusive) ask for one period.
  getTransactions: async (item_id?: number, limit?: number, startDate?: string, endDate?: string) => {
    const params: Record<string, number | string> = {};
    if (item_id) params.item_id = item_id;
    if (limit) params.limit = limit;
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    const response = await api.get<InventoryTransaction[]>('/inventory/transactions', { params });
    return response.data;
  },

  // Undo a mistaken movement by recording the opposite one. Reversing a
  // Stock In also voids its expense in Finance.
  reverseTransaction: async (id: number, reason: string) => {
    const response = await api.post<InventoryTransaction>(`/inventory/transactions/${id}/reverse`, { reason });
    return response.data;
  },

  // Every item's batches with stock left, in Stock Out order.
  getBatches: async () => {
    const response = await api.get<InventoryBatch[]>('/inventory/batches');
    return response.data;
  },

  // An item's batches with stock left, soonest expiry first.
  getItemBatches: async (itemId: number) => {
    const response = await api.get<InventoryBatch[]>(`/inventory/items/${itemId}/batches`);
    return response.data;
  },

  // Correct a batch's number or expiry date.
  updateBatch: async (id: number, changes: InventoryBatchUpdate) => {
    const response = await api.patch<InventoryBatch>(`/inventory/batches/${id}`, changes);
    return response.data;
  },

  createTransaction: async (transaction: InventoryTransactionCreate) => {
    const response = await api.post<InventoryTransaction>('/inventory/transactions', transaction);
    return response.data;
  },

  // What each program still holds of one item (Returns form).
  getOutstanding: async (itemId: number) => {
    const response = await api.get<OutstandingByProgram[]>(`/inventory/items/${itemId}/outstanding`);
    return response.data;
  },

  // NEW: matches GET /inventory/alerts/low-stock in inventory_api.py
  getLowStockItems: async (threshold: number = 10) => {
    const response = await api.get<LowStockItem[]>('/inventory/alerts/low-stock', {
      params: { threshold },
    });
    return response.data;
  },

  // NEW: matches GET /inventory/alerts/expiring in inventory_api.py
  getExpiringItems: async (days: number = 30) => {
    const response = await api.get<ExpiringItem[]>('/inventory/alerts/expiring', {
      params: { days },
    });
    return response.data;
  },

  // NEW: matches GET /inventory/analytics/cost-per-animal/{program_id}
  getCostPerAnimal: async (programId: number) => {
    const response = await api.get<CostPerAnimalResult>(
      `/inventory/analytics/cost-per-animal/${programId}`
    );
    return response.data;
  },

  // CHANGED: this used to recompute "low stock" client-side with a
  // hardcoded threshold of 10 (item.current_stock < 10), completely
  // separate from the backend's own low-stock logic. That meant if
  // anyone ever changed the threshold on the backend, the frontend
  // number would silently stop matching it. Now it asks the backend
  // for the actual low-stock list and just takes the count — there's
  // exactly one place in the whole system that defines "low stock".
  getSummary: async () => {
    const items = await InventoryService.getItems();
    const lowStockItems = await InventoryService.getLowStockItems();

    const total_items = items.length;
    const total_stock_value = items.reduce(
      (acc, item) => acc + item.current_stock * item.unit_cost,
      0
    );

    return {
      total_items,
      total_stock_value,
      low_stock_items: lowStockItems.length,
    };
  },
};