import api from '@/lib/api-client';
import {
  InventoryItem,
  InventoryTransaction,
  CostPerAnimal,
  StockInPayload,
  StockOutPayload,
  StockReturnPayload,
  AddItemPayload,
} from '@/types';

export const InventoryService = {
  // ── Reads ──────────────────────────────────────────────────────────────────

  getItems: async (): Promise<InventoryItem[]> => { 
    const response = await api.get<InventoryItem[]>('/inventory/items');
    return response.data;
  },

  getTransactions: async (item_id?: number): Promise<InventoryTransaction[]> => {
    const params = item_id ? { item_id } : {};
    const response = await api.get<InventoryTransaction[]>('/inventory/transactions', { params });
    return response.data;
  },

  getSummary: async () => {
    const items = await InventoryService.getItems();
    const total_items = items.length;
    const total_stock_value = items.reduce(
      (acc, item) => acc + item.current_stock * item.unit_cost,
      0
    );
    const low_stock_items = items.filter((item) => item.current_stock < 10).length;
    return { total_items, total_stock_value, low_stock_items };
  },

  getCostPerAnimal: async (): Promise<CostPerAnimal[]> => {
    const response = await api.get<CostPerAnimal[]>('/inventory/cost-per-animal');
    return response.data;
  },

  getLowStockItems: async (threshold = 10): Promise<InventoryItem[]> => {
    const response = await api.get<InventoryItem[]>('/inventory/low-stock', {
      params: { threshold },
    });
    return response.data;
  },

  // ── Stock Mutations ────────────────────────────────────────────────────────

  /** Stock In — adds stock via a 'restock' transaction */
  stockIn: async (payload: StockInPayload) => {
    const response = await api.post('/inventory/stock-in', payload);
    return response.data;
  },

  /** Stock Out — removes stock via an 'Issue' transaction */
  stockOut: async (payload: StockOutPayload) => {
    const response = await api.post('/inventory/stock-out', payload);
    return response.data;
  },

  /** Stock Return — returns stock via a 'Return' transaction */
  stockReturn: async (payload: StockReturnPayload) => {
    const response = await api.post('/inventory/stock-return', payload);
    return response.data;
  },

  /** Add Item — creates a new inventory_items row */
  addItem: async (payload: AddItemPayload) => {
    const response = await api.post<InventoryItem>('/inventory/items', payload);
    return response.data;
  },

  // ── Legacy (kept for backward compat) ─────────────────────────────────────

  createItem: async (item: Omit<InventoryItem, 'id'>) => {
    const response = await api.post<InventoryItem>('/inventory/items', item);
    return response.data;
  },

  createTransaction: async (transaction: Omit<InventoryTransaction, 'id'>) => {
    const response = await api.post<InventoryTransaction>(
      '/inventory/transactions',
      transaction
    );
    return response.data;
  },
};
