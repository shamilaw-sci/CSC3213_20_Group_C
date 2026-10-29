// CSV export for report tables.

export type CsvCell = string | number | null | undefined;

// A cell starting with one of these is run as a formula by Excel and Sheets.
// Program names are typed in by staff, so a program called "=HYPERLINK(...)"
// would otherwise execute on whoever opens the export.
const FORMULA_START = /^[=+\-@\t\r]/;

export function csvCell(value: CsvCell): string {
  if (value === null || value === undefined) return '';
  // Numbers are written as-is: a negative amount must stay a number, not
  // become the text "'-300".
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : '';

  let text = FORMULA_START.test(value) ? `'${value}` : value;
  if (/[",\r\n]/.test(text)) text = `"${text.replace(/"/g, '""')}"`;
  return text;
}

export function buildCsv(header: string[], rows: CsvCell[][]): string {
  return [header, ...rows].map((row) => row.map(csvCell).join(',')).join('\r\n');
}

export function downloadCsv(filename: string, csv: string): void {
  // The BOM makes Excel read the file as UTF-8 rather than the system code
  // page, which would mangle the en dash in period labels.
  const blob = new Blob(['﻿', csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
