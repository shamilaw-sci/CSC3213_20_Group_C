// Small helpers shared by the three inventory pages (Stock, Issue, Returns),
// so the same input rules and error wording apply wherever stock is moved.

// Mirrors MAX_QUANTITY in backend/app/schemas/inventory.py.
export const MAX_QUANTITY = 100_000;

// Low-stock line for an item with no reorder level of its own. Mirrors
// DEFAULT_REORDER_LEVEL in backend/app/api/inventory.py.
export const DEFAULT_REORDER_LEVEL = 10;

/**
 * Parse a quantity typed by the user. Returns the number, or an error message
 * to show. parseInt('2.5') quietly became 2 before; now it is refused.
 */
export function parseQuantity(raw: string): { value: number } | { error: string } {
  const text = raw.trim();
  if (!text) return { error: 'Quantity is required.' };
  const value = Number(text);
  if (!Number.isInteger(value) || value <= 0) {
    return { error: 'Quantity must be a whole number greater than 0.' };
  }
  if (value > MAX_QUANTITY) {
    return { error: `Quantity cannot be more than ${MAX_QUANTITY.toLocaleString()}.` };
  }
  return { value };
}

/**
 * The message the server sent, for a toast or an inline error.
 *
 * axios's own `err.message` is "Request failed with status code 400", which
 * hid the server's reason (e.g. "Insufficient stock: only 3 available").
 * FastAPI sends `detail` as a string for our own errors and as a list for
 * validation (422) errors.
 */
export function getApiErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string; loc?: unknown[] };
    const field = Array.isArray(first?.loc) ? String(first.loc[first.loc.length - 1]) : '';
    if (first?.msg) return field ? `${field.replace(/_/g, ' ')}: ${first.msg}` : first.msg;
  }
  return fallback;
}

/**
 * Today as yyyy-MM-dd in the user's own time zone, for date inputs' default
 * and `max`. The API refuses dates after today (Sri Lanka time).
 */
export function todayISO(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

/**
 * True when stock may be issued to a program with this status. Mirrors
 * normalize_status() in backend/app/services/program_lifecycle.py: the old
 * value 'In Progress' (and an empty status) count as Active. Upcoming,
 * Completed and Cancelled programs never take stock.
 */
export function isActiveProgram(status: string | null | undefined): boolean {
  const v = (status ?? '').trim().toLowerCase();
  return v === '' || v === 'active' || v === 'in progress';
}
