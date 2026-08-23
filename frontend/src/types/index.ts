import { UserRole } from '../lib/permissions';
export type { UserRole };

export interface User {
  id: string;
  email: string;
  name?: string;
  role: UserRole;
}


export interface Employee {
  id: number;
  first_name: string;
  last_name: string;
  nic: string;
  base_salary: number;
  status: string;
  user_id?: string;
}

export interface AttendanceRecord {
  id: number;
  employee_id: number;
  target_date: string;
  clock_in: string | null;
  clock_out: string | null;
  worked_hours: number | null;
  is_locked: boolean;
  employee_profile?: {
    first_name: string;
    last_name: string;
  };
}

export interface Transaction {
  id: number;
  transaction_date: string;
  amount: number;
  transaction_type: 'Income' | 'Expense';
  status: 'Cash' | 'Receivable' | 'Voided';
  program_id: number | null;
  programs?: {
    program_name: string;
  };
}

export interface Program {
  id: number;
  program_name: string;
  total_animals_treated: number;
  status: string;
  budget?: number; // legacy field — not present in the actual DB schema, left untouched (not your module)
  total_cost?: number; // new: auto-maintained by a DB trigger whenever inventory or finance transactions change
}

export interface InventoryItem {
  id: number;
  item_name: string;
  current_stock: number;
  unit_cost: number;
  expire_date?: string | null;   // ISO date string e.g. "2026-12-31", optional since not every item has one
  supplier_name?: string | null;
}

export interface InventoryTransaction {
  id: number;
  item_id: number;
  program_id: number | null;
  quantity: number;
  transaction_type: 'Issue' | 'Return' | 'Restock';
  transaction_date: string;
  total_cost: number; // calculated by the DB (quantity * unit_cost at the time), never sent by the client
  inventory_items?: {
    item_name: string;
  };
  programs?: {
    program_name: string;
  };
}

// Response shape for GET /inventory/alerts/low-stock
export interface LowStockItem {
  id: number;
  item_name: string;
  current_stock: number;
  supplier_name?: string | null;
}

// Response shape for GET /inventory/alerts/expiring
export interface ExpiringItem {
  id: number;
  item_name: string;
  expire_date: string;
  current_stock: number;
}

// Response shape for GET /inventory/analytics/cost-per-animal/{program_id}
export interface CostPerAnimalResult {
  program_id: number;
  program_name: string;
  inventory_cost: number;
  other_cost: number;
  total_cost: number;
  animals_treated: number;
  cost_per_animal: number;
}

export interface AuditLog {
  id: number;
  user_id: string | null;
  action_type: string;
  table_name: string;
  old_payload: any;
  new_payload: any;
  timestamp: string;
  users?: {
    email: string;
    roles?: {
      role_name: string;
    };
  };
}

export interface RescueCaseGeo {
  id: string;
  animal_type: string;
  status: 'Reported' | 'In Treatment' | 'Resolved';
  lat: number;
  lng: number;
  reported_at: string;
}

export interface CaseOut {
  id: string;
  animal_type: string;
  description?: string;
  status: 'Reported' | 'In Treatment' | 'Resolved';
  lat: number;
  lng: number;
  photo_url?: string;
  reported_by?: string;
  assigned_to?: string;
  reported_at: string;
  updated_at: string;
}
