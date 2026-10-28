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
  // Donor earmarked this income for program_id. Only meaningful on Income
  // rows; expenses draw down restricted funds via program_id alone.
  is_restricted?: boolean;
  programs?: {
    program_name: string;
  };
}

export interface RestrictedBalance {
  program_id: number;
  raised: number;
  spent: number;
  remaining: number;
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

// Mirrors the CHECK constraint in backend/db/migrations/005_urgency_reason.sql.
// Anything but 'ai' means the urgency is a fail-soft placeholder, not a judgement.
export type UrgencySource =
  | 'ai'
  | 'default_no_description'
  | 'default_classifier_error'
  | 'default_invalid_label';

export interface CaseOut {
  id: string;
  animal_type: string;
  description?: string;
  status: 'Reported' | 'Assigned' | 'In Treatment' | 'Resolved';
  urgency: 'Low' | 'Medium' | 'High' | 'Critical';
  // Both null on cases created before reasons were recorded.
  urgency_reason?: string | null;
  urgency_source?: UrgencySource | null;
  lat: number;
  lng: number;
  photo_url?: string;
  reported_by?: string;
  assigned_to?: string;
  // Filled by GET /rescue_cases/cases only; null when unassigned or when the
  // assigned user no longer exists.
  assignee?: CaseAssignee | null;
  reported_at: string;
  updated_at: string;
}

export interface CaseAssignee {
  email: string;
  display_name?: string | null;
}

// A user the assign dropdown may offer (GET /rescue_cases/assignees,
// rescue:assign only). Eligibility is decided server-side.
export interface AssigneeOption extends CaseAssignee {
  id: string;
  role_name: string;
}

export interface RouteStop {
  sequence: number;              // 1-based, matches the numbered map markers
  case: CaseOut;
  leg_distance_km: number;       // from the previous stop (or the start, for #1)
  leg_duration_min: number;
  cumulative_distance_km: number;
  cumulative_duration_min: number;
}

export interface OptimizedRoute {
  stops: RouteStop[];
  total_distance_km: number;
  total_duration_min: number;
  // False when road routing was unavailable and these are straight-line
  // estimates. Surfaced in the UI rather than passed off as driving distances.
  used_road_distances: boolean;
  degraded_reason?: string | null;
  truncated: boolean;
}

export interface EmployeeBasic {
  id: number;
  first_name: string;
  last_name: string;
}

export interface ProgramAssignment {
  id: number;
  program_id: number;
  employee_id: number;
  role_on_program: string | null;
  assigned_at: string;
  employee_profile?: EmployeeBasic;
}

// Full program detail, including start_date/end_date added in the
// Step 1 migration (not present on the basic Program type used by
// the list page, since finance.py's list endpoint doesn't return them)
export interface ProgramDetail {
  id: number;
  program_name: string;
  total_animals_treated: number;
  status: string;
  start_date?: string | null;
  end_date?: string | null;
  total_cost?: number;
}

export interface ProgramFinancials {
  program_id: number;
  revenue: number;
  total_cost: number;
  profit: number;
}

// --- General ledger (GET /finance/ledger) ---

export interface LedgerRow extends Transaction {
  program_name: string;
  // Ledger-wide running net after this entry; null on voided rows.
  balance: number | null;
}

export interface LedgerFilters {
  start_date?: string;
  end_date?: string;
  transaction_type?: 'Income' | 'Expense';
  status?: 'Cash' | 'Receivable' | 'Voided';
  program?: string; // a program id, or 'general'
  restricted?: boolean;
  q?: string;
  sort?: 'newest' | 'oldest';
}

export interface LedgerPage {
  rows: LedgerRow[];
  total: number;
  page: number;
  pages: number;
  page_size: number;
  // Over every row the filters match, voided excluded.
  totals: { income: number; expense: number; net: number };
}

// --- Finance report (GET /reports/finance) ---
// Mirrors build_finance_report in backend/app/services/finance_reports.py.

export interface PeriodTotals {
  income: number;
  income_received: number;
  income_pending: number;
  expense: number;
  expense_paid: number;
  expense_unpaid: number;
  net: number;
}

export interface OutstandingItem {
  id: number;
  transaction_date: string;
  program_name: string;
  amount: number;
  days: number;
}

export interface OutstandingSide {
  total: number;
  count: number;
  buckets: Record<'0-30' | '31-60' | '61-90' | '90+', number>;
  items: OutstandingItem[];
}

export interface FinanceReport {
  period: { start: string; end: string; previous_start: string; previous_end: string };
  summary: {
    current: PeriodTotals;
    previous: PeriodTotals;
    // null when the previous period had nothing to compare against.
    change: { income_pct: number | null; expense_pct: number | null; net_difference: number };
  };
  monthly: { month: string; income: number; expense: number; net: number }[];
  programs: {
    rows: { program_id: number | null; program_name: string; income: number; expense: number; net: number }[];
    totals: { income: number; expense: number; net: number };
  };
  restricted: {
    rows: {
      program_id: number;
      program_name: string;
      opening: number;
      received: number;
      spent: number;
      closing: number;
      pledged: number;
    }[];
    totals: { opening: number; received: number; spent: number; closing: number; pledged: number };
  };
  outstanding: { as_of: string; receivables: OutstandingSide; payables: OutstandingSide };
}
