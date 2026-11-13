'use client';

import { useQuery } from '@tanstack/react-query';
import { HeartHandshake, Home, PawPrint, Pill, Stethoscope, Trees, Truck } from 'lucide-react';
import { RescueCasesService, type PublicImpact } from '@/services/rescue-cases.service';
import { Skeleton } from '@/components/ui/skeleton';

const LKR = new Intl.NumberFormat('en-LK', { style: 'currency', currency: 'LKR', maximumFractionDigits: 0 });
const COUNT = new Intl.NumberFormat('en-LK');

type Stat = { key: string; value: string; label: string; icon: typeof PawPrint };

// Live totals for this year (confirmed 2026-11-13): good outcomes only,
// supplies spent but never donation totals. A figure of zero is left out
// rather than shown, so an early-year "0 rehomed" never sits on the page.
function stats(d: PublicImpact): Stat[] {
  const all: (Stat & { n: number })[] = [
    { key: 'reported', n: d.reported, value: COUNT.format(d.reported), label: 'animals reported to us', icon: PawPrint },
    { key: 'cared', n: d.cared_for, value: COUNT.format(d.cared_for), label: 'cared for by our team', icon: Stethoscope },
    { key: 'rehomed', n: d.rehomed, value: COUNT.format(d.rehomed), label: 'rehomed', icon: Home },
    { key: 'released', n: d.released, value: COUNT.format(d.released), label: 'treated and released', icon: Trees },
    { key: 'transferred', n: d.transferred, value: COUNT.format(d.transferred), label: 'transferred to vets', icon: Truck },
    { key: 'supplies', n: d.supplies_cost, value: LKR.format(d.supplies_cost), label: 'on medicine and supplies', icon: Pill },
  ];
  return all.filter((s) => s.n > 0);
}

function useImpact() {
  return useQuery({
    queryKey: ['public', 'impact'],
    queryFn: RescueCasesService.getImpact,
    // The backend caches for 10 minutes; no need to ask more often.
    staleTime: 10 * 60 * 1000,
  });
}

/**
 * This year's rescue work, live from the system. Renders nothing on an error
 * or before anything has been reported: a public page shouldn't show a
 * broken or empty box.
 */
export default function ImpactNumbers({ variant = 'full' }: { variant?: 'full' | 'compact' }) {
  const { data, isLoading, isError } = useImpact();

  if (variant === 'compact') {
    if (!data || isError || data.reported === 0) return null;
    // Three at most: the donate hero has a fixed height, and a long line
    // would push its heading out of view on a phone.
    const shown = stats(data).slice(0, 3);
    return (
      <p className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-sm text-white/90">
        <HeartHandshake className="h-4 w-4 text-[#EF9F27]" aria-hidden="true" />
        <span className="font-semibold">In {data.year} so far:</span>
        {shown.map((s, i) => (
          <span key={s.key}>
            <span className="font-bold text-white">{s.value}</span> {s.label}{i < shown.length - 1 ? ' ·' : ''}
          </span>
        ))}
      </p>
    );
  }

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24 w-full bg-surface" />)}
      </div>
    );
  }
  if (!data || isError || data.reported === 0) return null;

  return (
    <div className="space-y-3">
      <p className="text-xs font-bold uppercase tracking-wider text-text-secondary">In {data.year} so far</p>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {stats(data).map((s) => {
          const Icon = s.icon;
          return (
            <div key={s.key} className="rounded-2xl border border-border-brand bg-surface p-4 shadow-card">
              <Icon className="h-5 w-5 text-[#EF9F27]" aria-hidden="true" />
              <p className="mt-2 text-2xl font-extrabold tracking-tight font-heading text-text-primary">{s.value}</p>
              <p className="text-xs text-text-secondary">{s.label}</p>
            </div>
          );
        })}
      </div>
      <p className="text-[11px] text-text-muted">
        Live from our rescue records. Updated every few minutes.
      </p>
    </div>
  );
}
