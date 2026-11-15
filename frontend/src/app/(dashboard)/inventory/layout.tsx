import { CompactScale } from '@/components/layout/compact-scale';

// Shown at 90% size: these pages were designed at 90% browser zoom.
export default function InventoryLayout({ children }: { children: React.ReactNode }) {
  return <CompactScale>{children}</CompactScale>;
}
