import api from '@/lib/api-client';
import {
  InventoryItem,
  InventoryTransaction,
  LowStockItem,
  ExpiringItem,
  CostPerAnimalResult,
} from '@/types';

export const InventoryService = {
  getItems: async () => {
    const response = await api.get<InventoryItem[]>('/api/inventory/items');
    return response.data;
  },

  createItem: async (item: Omit<InventoryItem, 'id'>) => {
    const response = await api.post<InventoryItem>('/api/inventory/items', item);
    return response.data;
  },

  getTransactions: async (item_id?: number) => {
    const params = item_id ? { item_id } : {};
    const response = await api.get<InventoryTransaction[]>('/api/inventory/transactions', { params });
    return response.data;
  },

  createTransaction: async (transaction: Omit<InventoryTransaction, 'id' | 'total_cost'>) => {
    const response = await api.post<InventoryTransaction>('/api/inventory/transactions', transaction);
    return response.data;
  },

  // NEW: matches GET /inventory/alerts/low-stock in inventory_api.py
  getLowStockItems: async (threshold: number = 10) => {
    const response = await api.get<LowStockItem[]>('/api/inventory/alerts/low-stock', {
      params: { threshold },
    });
    return response.data;
  },

  // NEW: matches GET /inventory/alerts/expiring in inventory_api.py
  getExpiringItems: async (days: number = 30) => {
    const response = await api.get<ExpiringItem[]>('/api/inventory/alerts/expiring', {
      params: { days },
    });
    return response.data;
  },

  // NEW: matches GET /inventory/analytics/cost-per-animal/{program_id}
  getCostPerAnimal: async (programId: number) => {
    const response = await api.get<CostPerAnimalResult>(
      `/api/inventory/analytics/cost-per-animal/${programId}`
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