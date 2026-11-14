// frontend/src/app/clinics/page.tsx
'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { AlertTriangle, ArrowRight, CalendarHeart, PawPrint, RefreshCw, Search } from 'lucide-react';
import { ProgramService } from '@/services/program.service';
import { PROGRAM_TYPES, type ProgramType } from '@/types';
import { ClinicCard } from '@/components/clinics/ClinicCard';
import HomeHeader from '@/components/home/HomeHeader';
import HomeFooter from '@/components/home/HomeFooter';
import { cn } from '@/lib/utils';

// Where the public finds out a sterilization drive or free clinic is coming
// to their area. Staff publish a program from its details page; it shows here
// while Upcoming or Active and drops off by itself when it ends.
export default function PublicClinicsPage() {
  const [query, setQuery] = useState('');
  const [type, setType] = useState<ProgramType | 'All'>('All');

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['public-programs'],
    queryFn: ProgramService.listPublic,
  });

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data ?? []).filter((p) =>
      (type === 'All' || p.program_type === type) &&
      (!q || [p.location, p.public_venue, p.program_name].some((v) => v?.toLowerCase().includes(q))),
    );
  }, [data, query, type]);

  // Only offer the type filters that would show something.
  const typesPresent = PROGRAM_TYPES.filter((t) => data?.some((p) => p.program_type === t));
  const filtering = query.trim() !== '' || type !== 'All';

  return (
    <div className="min-h-screen bg-bg-subtle text-text-primary flex flex-col">
      <HomeHeader />

      <main className="flex-grow pt-16">
        <section className="relative overflow-hidden bg-[#0B0D12]">
          <PawPrint
            className="absolute -right-12 -bottom-20 text-white/[0.04] rotate-12 pointer-events-none select-none"
            size={300}
            strokeWidth={1}
            aria-hidden="true"
          />
          <div className="relative max-w-[1280px] mx-auto px-6 md:px-12 pt-14 pb-24 text-center space-y-4">
            <span className="inline-flex items-center gap-2 text-xs font-bold tracking-wider text-[#EF9F27] uppercase">
              <CalendarHeart size={14} />
              Clinics & Drives
            </span>
            <h1 className="text-3xl md:text-5xl font-bold font-heading text-white tracking-tight">
              Free clinics near you
            </h1>
            <p className="text-sm md:text-lg text-white/80 max-w-2xl mx-auto leading-relaxed">
              Sterilization drives, vaccination camps and free animal health clinics
              that VFF is running now or soon. Bring your own animals, or the street
              dogs and cats you look after.
            </p>
          </div>
        </section>

        <section className="max-w-[1100px] mx-auto px-6 md:px-12 -mt-14 relative space-y-6">
          <div className="rounded-card border border-border-brand bg-surface shadow-card p-4 md:p-5 space-y-4">
            <div className="flex flex-col sm:flex-row gap-3 sm:items-center">
              <label className="relative flex-1">
                <span className="sr-only">Search by town or district</span>
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" aria-hidden="true" />
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search your town or district, e.g. Kandy"
                  className="w-full h-11 rounded-xl border border-border-brand bg-bg-subtle pl-9 pr-3 text-sm placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-[#EF9F27]/50"
                />
              </label>
              <button
                type="button"
                onClick={() => refetch()}
                disabled={isFetching}
                className="inline-flex items-center justify-center gap-1.5 text-xs font-semibold text-text-secondary hover:text-text-primary disabled:opacity-50 transition-colors"
              >
                <RefreshCw size={13} className={isFetching ? 'animate-spin' : undefined} />
                Refresh
              </button>
            </div>

            {typesPresent.length > 1 && (
              <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by type">
                {(['All', ...typesPresent] as const).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setType(t)}
                    aria-pressed={type === t}
                    className={cn(
                      'text-xs font-semibold px-3 py-1.5 rounded-full border transition-colors',
                      type === t
                        ? 'bg-[#EF9F27] border-[#EF9F27] text-white'
                        : 'border-border-brand text-text-secondary hover:text-text-primary',
                    )}
                  >
                    {t}
                  </button>
                ))}
              </div>
            )}
          </div>

          {isLoading && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-56 rounded-card bg-surface border border-border-brand animate-pulse" />
              ))}
            </div>
          )}

          {error && (
            <div className="rounded-card border border-border-brand bg-surface p-10 flex flex-col items-center gap-3 text-center">
              <AlertTriangle className="w-7 h-7 text-negative" />
              <p className="text-sm text-text-secondary max-w-sm">
                Couldn&apos;t load the clinics. Check your connection and try again.
              </p>
              <button
                type="button"
                onClick={() => refetch()}
                className="inline-flex items-center gap-2 bg-surface text-text-primary border border-border-brand hover:bg-bg-subtle font-bold text-sm py-2.5 px-5 rounded-xl transition-colors"
              >
                <RefreshCw size={14} /> Try again
              </button>
            </div>
          )}

          {data && shown.length > 0 && (
            <>
              <p className="text-sm text-text-secondary">
                {shown.length} {shown.length === 1 ? 'clinic' : 'clinics'}
                {filtering ? ' match' : ' listed'}
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                {shown.map((p) => <ClinicCard key={p.id} program={p} />)}
              </div>
            </>
          )}

          {data && shown.length === 0 && (
            <div className="rounded-card border border-border-brand bg-surface p-10 flex flex-col items-center gap-3 text-center">
              <div className="w-14 h-14 rounded-2xl bg-[#EF9F27]/10 text-[#EF9F27] flex items-center justify-center">
                <CalendarHeart size={26} />
              </div>
              <h2 className="text-lg font-bold font-heading text-text-primary">
                {filtering ? 'Nothing matches that search' : 'No clinics announced right now'}
              </h2>
              <p className="text-sm text-text-secondary max-w-md leading-relaxed">
                {filtering
                  ? 'There is no clinic listed for that area yet. New ones are added here as soon as they are planned, so check back soon.'
                  : 'New sterilization drives and free clinics are added here as soon as they are planned. Check back soon.'}
              </p>
              {filtering && (
                <button
                  type="button"
                  onClick={() => { setQuery(''); setType('All'); }}
                  className="text-sm font-semibold text-[#EF9F27] hover:underline"
                >
                  Show all clinics
                </button>
              )}
            </div>
          )}
        </section>

        <section className="max-w-[1100px] mx-auto px-6 md:px-12 py-16">
          <div className="rounded-card border border-border-brand bg-surface shadow-card p-8 md:p-10 text-center space-y-4">
            <h2 className="text-2xl md:text-3xl font-bold font-heading tracking-tight">
              Want to help at the next one?
            </h2>
            <p className="text-sm md:text-base text-text-secondary max-w-xl mx-auto leading-relaxed">
              Every drive needs people to register animals, handle transport and look
              after them while they recover.
            </p>
            <div className="pt-2">
              <Link
                href="/volunteer"
                className="inline-flex items-center gap-2 bg-[#EF9F27] hover:bg-[#EF9F27]/90 text-white font-bold text-sm py-3.5 px-7 rounded-xl shadow-lg shadow-amber-500/20 hover:shadow-xl hover:shadow-amber-500/30 hover:scale-[1.03] transition-all"
              >
                Volunteer with us <ArrowRight size={16} />
              </Link>
            </div>
          </div>
        </section>
      </main>

      <HomeFooter />
    </div>
  );
}
