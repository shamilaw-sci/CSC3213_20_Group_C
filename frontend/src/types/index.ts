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

// --- Work schedules and holidays (app/api/hr_calendar.py) ---

export interface ScheduleDay {
  weekday: number; // ISO: 1 = Monday ... 7 = Sunday
  start_time: string; // HH:MM[:SS], Sri Lanka time
  end_time: string; // earlier than start_time = overnight shift
  break_minutes: number;
}

export interface WorkSchedule {
  id: number;
  name: string;
  is_default: boolean;
  grace_minutes: number;
  observes_holidays: boolean;
  days: ScheduleDay[];
}

export type WorkScheduleInput = Pick<WorkSchedule, 'name' | 'grace_minutes' | 'observes_holidays' | 'days'>;

export interface ScheduleAssignment {
  id: number;
  employee_id: number;
  schedule_id: number;
  schedule_name: string | null;
  effective_from: string;
}

export interface ScheduleAssignmentRow {
  employee_id: number;
  employee_name: string;
  status: string | null;
  current_schedule_id: number | null;
  current_schedule_name: string | null;
  follows_default: boolean;
  history: ScheduleAssignment[];
}

export interface Holiday {
  id: number;
  holiday_date: string;
  name: string;
  is_public: boolean;
  is_bank: boolean;
  is_mercantile: boolean;
  is_poya: boolean;
  // VFF policy: mercantile holidays and every Poya day are days off.
  is_day_off: boolean;
  source: string | null;
}

export type HolidayInput = Omit<Holiday, 'id' | 'is_poya'>;

export interface HolidayImportPreview {
  year: number;
  rows: Omit<Holiday, 'id'>[];
  new_count: number;
  existing_count: number;
  warnings: string[];
}

export interface MySchedule {
  schedule: WorkSchedule | null;
  today: { working: boolean; reason: 'scheduled' | 'rest_day' | 'holiday'; start: string | null; end: string | null; holidays: string[] };
  upcoming_holidays: Holiday[];
}

// --- Leave (app/api/leave.py) ---

export interface LeaveTypeRow {
  id: number;
  code: string;
  name: string;
  is_paid: boolean;
  uses_balance: boolean; // yearly allowance; false for event leave and no-pay
  default_days: number | null;
  max_days_per_request: number | null;
  counts_calendar_days: boolean;
  allow_half_day: boolean;
  carry_forward_max: number;
  first_year_rule: 'none' | 'soe_annual' | 'soe_casual';
}

export interface LeaveBalance {
  leave_type_id: number;
  code: string;
  name: string;
  set_up: boolean; // false: no entitlement generated for the year yet
  entitlement_id?: number | null;
  note?: string | null;
  entitled?: number;
  // First-year casual only: how much of `entitled` is earned so far (it
  // accrues one day per two complete months). Absent/null: all of it.
  earned_to_date?: number | null;
  carried_forward?: number;
  adjustment?: number;
  total?: number;
  approved?: number;
  pending?: number;
  available?: number;
}

export type LeaveStatus = 'Pending' | 'Approved' | 'Rejected' | 'Cancelled';

export interface LeaveRequest {
  id: number;
  employee_id: number;
  employee_name?: string;
  leave_type_id: number;
  leave_types?: { name: string; code: string } | null;
  start_date: string;
  end_date: string;
  half_day: 'none' | 'am' | 'pm';
  days: number;
  reason: string | null;
  status: LeaveStatus;
  requested_by: string | null;
  requested_at: string;
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
}

export interface LeaveInput {
  leave_type_id: number;
  start_date: string;
  end_date: string;
  half_day: 'none' | 'am' | 'pm';
  reason?: string;
  employee_id?: number; // HR filing on someone's behalf
}

export interface LeavePreview {
  days: { date: string; fraction: number }[];
  total: number;
  balances: Record<string, { total: number; approved: number; pending: number; available: number; after: number } | null>;
  errors: string[];
}

export interface MyLeave {
  employee_id: number;
  date_joined: string | null;
  year: number;
  balances: LeaveBalance[];
  requests: LeaveRequest[];
}

export interface EntitlementsView {
  year: number;
  employees: { employee_id: number; employee_name: string; date_joined: string | null; balances: LeaveBalance[] }[];
  needs_date_joined: { employee_id: number; employee_name: string }[];
}

// --- Monthly attendance grid (GET /hr/attendance/month) ---
// Mirrors build_month in backend/app/services/attendance_month.py.

export type DayStatus =
  | 'not_employed' | 'upcoming' | 'leave' | 'holiday' | 'rest' | 'worked_off_day'
  | 'absent' | 'missing_clock_out' | 'in_progress' | 'present';

export interface DayLeave {
  status: 'Approved' | 'Pending';
  type_name: string;
  type_code: string;
  fraction: number;
  half_day: 'none' | 'am' | 'pm';
  paid: boolean;
}

export interface DayCell {
  date: string;
  status: DayStatus;
  late_minutes: number;
  left_early_minutes: number;
  worked_minutes: number;
  expected_minutes: number;
  clock_in: string | null; // Sri Lanka time, ISO with offset
  clock_out: string | null;
  record_id: number | null;
  locked: boolean;
  expected_start: string | null;
  expected_end: string | null;
  schedule_name: string | null;
  holidays: string[];
  leave: DayLeave | null;
  leave_pending: DayLeave | null;
  reason: string;
}

export interface MonthRow {
  employee_id: number;
  employee_name: string;
  status: string | null;
  date_joined: string | null;
  cells: DayCell[];
  totals: {
    present: number; absent: number; late: number; left_early: number; missing_clock_out: number;
    leave_days: number; worked_off_days: number; worked_minutes: number; expected_minutes: number;
  };
}

export interface AttentionItem {
  employee_id: number;
  employee_name: string;
  date: string;
  kinds: ('absent' | 'missing_clock_out' | 'late' | 'left_early' | 'worked_off_day')[];
  reason: string;
  leave_pending: boolean;
  info?: boolean;
}

export interface AttendanceMonth {
  year: number;
  month: number;
  days: { date: string; weekday: number; holidays: string[] }[];
  employees: MonthRow[];
  attention: AttentionItem[];
  today: string;
  employee?: MonthRow | null; // /me/month only
}

// --- Payroll (GET /hr/payroll/run) ---
// A month's payroll run: Draft when generated, Approved when signed off by a
// second person, and only then posted to the finance ledger.

export interface PayrollRun {
  id: number;
  payroll_month: number;
  payroll_year: number;
  status: 'Draft' | 'Approved';
  total: number;
  generated_by: string | null;
  generated_at: string;
  approved_by: string | null;
  approved_at: string | null;
  finance_transaction_id: number | null;
  generator?: { email: string } | null;
  approver?: { email: string } | null;
}

export interface PayrollLine {
  id: number;
  employee_id: number;
  employee_name: string;
  nic: string | null;
  net_payable: number;
}

export interface PayrollRunView {
  run: PayrollRun | null;
  lines: PayrollLine[];
  incomplete_attendance: number;
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
  // Where the row came from (migration 013). Set by the database, never sent.
  source_type?: 'donation' | 'stock_in' | 'payroll' | 'manual';
  // The Stock In movement a stock_in row was posted for (migration 016).
  inventory_transaction_id?: number | null;
  programs?: {
    program_name: string;
  };
}

// What the client sends to record a movement. unit_cost is Stock In only:
// the price paid per unit, which costs the movement (and the finance
// expense) and becomes the item's stored cost. Never a total.
export type InventoryTransactionCreate = Omit<
  InventoryTransaction,
  'id' | 'total_cost' | 'reverses_id' | 'reversed_by' | 'inventory_items' | 'programs'
> & {
  unit_cost?: number;
};

// One delivery of an item (migration 020). Stock Out takes from the batch
// that expires first. Matches InventoryBatch in backend/app/schemas/inventory.py.
export interface InventoryBatch {
  id: number;
  item_id: number;
  batch_number: string;
  expire_date?: string | null;
  unit_cost: number;
  quantity_received: number;
  quantity_remaining: number;
  received_date?: string | null;
}

// PATCH /inventory/batches/{id}. Quantities change only through movements.
// A new unit price changes what later Stock Outs from the batch cost.
export interface InventoryBatchUpdate {
  batch_number?: string;
  expire_date?: string | null;
  unit_cost?: number;
}

// The Stock In behind a stock_in expense: what to correct in Inventory if
// the expense is voided. Matches StockMovementRef in backend/app/schemas/finance.py.
export interface StockMovementRef {
  inventory_transaction_id: number;
  item_name: string | null;
  quantity: number;
  transaction_date: string | null;
  total_cost: number;
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
  // Low stock below this many units. null = the default (10). Migration 019.
  reorder_level?: number | null;
}

// PATCH /inventory/items/{id}. Stock and unit cost are not editable, and
// expiry comes from the item's batches (edit the batch instead).
export interface InventoryItemUpdate {
  item_name?: string;
  supplier_name?: string | null;
  reorder_level?: number | null;
}

export interface InventoryTransaction {
  id: number;
  item_id: number;
  program_id: number | null;
  quantity: number;
  transaction_type: 'Issue' | 'Return' | 'Restock';
  transaction_date: string;
  total_cost: number; // calculated by the DB (quantity * unit_cost at the time), never sent by the client
  // Free-text reason. Required by the API for a Stock Out with no program (a stock adjustment).
  notes?: string | null;
  // Stock In only: expiry date of the batch received.
  expire_date?: string | null;
  // Stock In only: the batch's number. Left empty, one is made up (migration 020).
  batch_number?: string | null;
  // On a reversal: the movement it undoes.
  reverses_id?: number | null;
  // On a reversed movement: the reversal's id.
  reversed_by?: number | null;
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
  // The line it was compared with: its own reorder level, or the default.
  reorder_level: number;
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
  // Null for roles that may not see program money (no finance:read or
  // inventory:read).
  total_cost?: number | null;
  // Null on programs created before locations were recorded.
  location?: string | null;
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
  // "Source-Program", e.g. "Stock in-General". Optional so an older backend
  // without it still type-checks.
  description?: string;
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
