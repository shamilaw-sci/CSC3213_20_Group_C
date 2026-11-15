'use client';

/**
 * Shows a section at 90% size, so pages designed with the browser at 90%
 * zoom look the same to people browsing at 100%. Styles are unchanged; only
 * the size is scaled.
 *
 * Used only by the Inventory, Programs, Donations and Volunteers layouts.
 * Dialogs open in a portal outside the page, so the <style> below scales
 * them too; it exists only while one of those sections is open, so no other
 * page is affected.
 */
export function CompactScale({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ zoom: 0.9 }}>
      <style>{`[data-slot="dialog-content"] { zoom: 0.9; }`}</style>
      {children}
    </div>
  );
}
