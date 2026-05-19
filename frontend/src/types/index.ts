// ─── Inventory ────────────────────────────────────────────────────────────────

export interface InventoryItem {
  id: number;
  item_name: string;
  current_stock: number;
  unit_cost: number;
  supplier?: string | null;
}

export interface InventoryTransaction {
  id: number;
  item_id: number;
  program_id?: number | null;
  quantity: number;
  transaction_type: 'Issue' | 'Return' | 'restock';
  transaction_date: string;
  /** Joined relation — present when fetched with select("*, inventory_items(item_name)") */
  inventory_items?: { item_name: string } | null;
  /** Joined relation — present when fetched with select("*, programs(program_name)") */
  programs?: { program_name: string } | null;
}

export interface CostPerAnimal {
  program_id: number;
  program_name: string;
  total_cost: number;
  animals_treated: number;
  cost_per_animal: number;
}

// ─── Inventory Mutation Payloads ──────────────────────────────────────────────

export interface StockInPayload {
  item_id: number;
  quantity: number;
  unit_price?: number;
  supplier?: string;
  transaction_date: string;
  reason_notes?: string;
  program_id?: number | null;
}

export interface StockOutPayload {
  item_id: number;
  quantity: number;
  transaction_date: string;
  reason_notes?: string;
  program_id?: number | null;
}

export interface StockReturnPayload {
  item_id: number;
  quantity: number;
  supplier?: string;
  reason_notes?: string;
  program_id?: number | null;
}

export interface AddItemPayload {
  item_name: string;
  initial_quantity: number;
  unit_cost: number;
}

// ─── Finance ──────────────────────────────────────────────────────────────────

export interface Program {
  id: number;
  program_name: string;
  total_animals_treated: number;
  status: string;
}

export interface Transaction {
  id: number;
  transaction_date: string;
  amount: number;
  transaction_type: 'Income' | 'Expense';
  status: 'Cash' | 'Receivable';
  program_id?: number | null;
}
