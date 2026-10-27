'use client';

import { useQuery } from '@tanstack/react-query';
import { RescueCasesService } from '@/services/rescue-cases.service';
import { RescueCaseGeo } from '@/types';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDistanceToNow } from 'date-fns';
import { PawPrint, Dog, Cat, Bird, ArrowRight } from 'lucide-react';
import Link from 'next/link';

// Matches the stage colours used on the internal triage board so the public
// and staff views speak the same visual language.
const STATUS_ACCENT: Record<string, string> = {
  Reported: '#6B7280',
  'In Treatment': '#EF9F27',
  Resolved: '#16A34A',
};

const ANIMAL_ICON: Record<string, typeof PawPrint> = {
  Dog: Dog,
  Cat: Cat,
  Bird: Bird,
};

const LOOKBACK_DAYS = 30;

function iconFor(animalType: string) {
  return ANIMAL_ICON[animalType] ?? PawPrint;
}

export default function RecentRescueActivity() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['rescueCases', 'geo', 'home-activity'],
    queryFn: () => RescueCasesService.getCaseGeo({ days: LOOKBACK_DAYS }),
  });

  if (error) return null; // A failed public feed shouldn't break the homepage.

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Skeleton className="h-24 w-full bg-surface" />
          <Skeleton className="h-24 w-full bg-surface" />
          <Skeleton className="h-24 w-full bg-surface" />
        </div>
        <Skeleton className="h-48 w-full bg-surface" />
      </div>
    );
  }

  const cases: RescueCaseGeo[] = data ?? [];

  if (cases.length === 0) {
    return (
      <p className="text-sm text-text-secondary py-12 text-center border border-dashed border-border-brand rounded-2xl">
        No cases reported in the last {LOOKBACK_DAYS} days.
      </p>
    );
  }

  const counts = {
    Reported: cases.filter((c) => c.status === 'Reported').length,
    'In Treatment': cases.filter((c) => c.status === 'In Treatment').length,
    Resolved: cases.filter((c) => c.status === 'Resolved').length,
  };

  const recent = [...cases]
    .sort((a, b) => new Date(b.reported_at).getTime() - new Date(a.reported_at).getTime())
    .slice(0, 6);

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {(Object.keys(counts) as Array<keyof typeof counts>).map((status) => (
          <div
            key={status}
            style={{ borderTopColor: STATUS_ACCENT[status] }}
            className="bg-surface border border-t-4 border-border-brand/50 rounded-2xl p-7 shadow-card hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200"
          >
            <span className="text-4xl font-extrabold font-heading text-text-primary tracking-tight">
              {counts[status]}
            </span>
            <p className="text-xs font-bold uppercase tracking-wider text-text-secondary mt-1.5">
              {status}
            </p>
          </div>
        ))}
      </div>

      <div className="bg-surface border border-border-brand/50 rounded-2xl divide-y divide-border-brand/50 overflow-hidden shadow-card">
        {recent.map((c) => {
          const Icon = iconFor(c.animal_type);
          return (
            <div key={c.id} className="flex items-center gap-4 px-6 py-4 hover:bg-bg-subtle/50 transition-colors">
              <div className="w-10 h-10 rounded-xl bg-bg-subtle flex items-center justify-center shrink-0">
                <Icon size={17} className="text-text-secondary" />
              </div>
              <span className="text-sm font-semibold text-text-primary flex-1">
                {c.animal_type}
              </span>
              <span
                className="text-xs font-bold uppercase tracking-wider shrink-0"
                style={{ color: STATUS_ACCENT[c.status] }}
              >
                {c.status}
              </span>
              <span className="text-xs font-mono text-text-muted shrink-0 w-28 text-right">
                {formatDistanceToNow(new Date(c.reported_at), { addSuffix: true })}
              </span>
            </div>
          );
        })}
      </div>

      <Link
        href="/outbreak-map"
        className="text-sm font-semibold text-[#EF9F27] hover:underline inline-flex items-center gap-1.5"
      >
        See where cases are being reported <ArrowRight size={13} />
      </Link>
    </div>
  );
}
