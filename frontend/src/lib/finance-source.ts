// Where a finance row came from (financial_transactions.source_type,
// migration 013), shared by the Ledger and the Overview. Mirrors
// SOURCE_LABELS and describe() in backend/app/services/ledger.py.

type SourceType = 'donation' | 'stock_in' | 'payroll' | 'manual';

type SourcedRow = {
  source_type?: SourceType;
  program_id: number | null;
  // Ledger rows carry these two; Overview rows only have the joined program.
  description?: string;
  program_name?: string;
  programs?: { program_name: string };
};

export const SOURCE_LABELS: Record<SourceType, string> = {
  donation: 'Donation',
  stock_in: 'Stock in',
  payroll: 'Payroll',
  manual: 'Manual',
};

// A row read before migration 013 has no source_type; the column's default
// is 'manual', so it counts as manual.
export const sourceOf = (row: SourcedRow): SourceType => row.source_type ?? 'manual';

// Stock In, payroll and donations post their own rows. The API refuses to
// edit them; they are corrected by voiding and recording a new transaction.
export const isAutoPosted = (row: SourcedRow) => sourceOf(row) !== 'manual';

export const AUTO_POSTED_HINT =
  'Posted automatically, so it cannot be edited. Void it and record a new transaction instead.';

// "Source-Program", e.g. "Stock in-General" or "Donation-Rabies Drive". The
// Ledger API sends it ready-made; this builds the same text for other rows.
export function describeTransaction(row: SourcedRow): string {
  if (row.description) return row.description;
  const program =
    row.program_id === null
      ? 'General'
      : row.program_name ?? row.programs?.program_name ?? `Program #${row.program_id}`;
  return `${SOURCE_LABELS[sourceOf(row)]}-${program}`;
}
