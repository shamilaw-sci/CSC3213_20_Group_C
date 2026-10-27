// frontend/src/app/outbreak-map/page.tsx
'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import {
  AlertTriangle,
  ArrowRight,
  PawPrint,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';
import { RescueCasesService } from '@/services/rescue-cases.service';
import OutbreakZoneMapWrapper from '@/components/heatmap/OutbreakZoneMapWrapper';
import HomeHeader from '@/components/home/HomeHeader';
import HomeFooter from '@/components/home/HomeFooter';

export default function PublicOutbreakMapPage() {
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['outbreakZones'],
    queryFn: () => RescueCasesService.getOutbreakZones(),
  });

  const zoneCount = data?.length ?? 0;

  return (
    // The page previously rendered bare, with no header or footer at all —
    // anyone arriving from the "Hotspot Map" nav link had no way back out.
    <div className="min-h-screen bg-bg-subtle text-text-primary flex flex-col">
      <HomeHeader />

      <main className="flex-grow pt-16">
        {/* Same hero-then-floated-card shape as the donate and report pages,
            minus a photograph — there is no honest VFF image of an outbreak,
            so the band carries the paw-print motif instead. */}
        <section className="relative overflow-hidden bg-[#0B0D12]">
          <PawPrint
            className="absolute -right-12 -bottom-20 text-white/[0.04] rotate-12 pointer-events-none select-none"
            size={300}
            strokeWidth={1}
            aria-hidden="true"
          />

          <div className="relative max-w-[1280px] mx-auto px-6 md:px-12 pt-14 pb-24 text-center space-y-4">
            <span className="inline-flex items-center gap-2 text-xs font-bold tracking-wider text-[#EF9F27] uppercase">
              <AlertTriangle size={14} />
              Outbreak Map
            </span>
            <h1 className="text-3xl md:text-5xl font-bold font-heading text-white tracking-tight">
              Declared outbreak zones
            </h1>
            <p className="text-sm md:text-lg text-white/80 max-w-2xl mx-auto leading-relaxed">
              Areas with a confirmed outbreak, reviewed and declared by VFF staff.
              If you are near one, take extra care around street animals — and tell
              us about any animal that looks unwell.
            </p>
          </div>
        </section>

        <section className="max-w-[1100px] mx-auto px-6 md:px-12 -mt-14 relative">
          <div className="rounded-card border border-border-brand bg-surface shadow-card overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-4 border-b border-border-brand">
              <div className="flex items-center gap-3">
                <span
                  className="w-3.5 h-3.5 rounded-full border-2 border-[#DC2626] bg-[#DC2626]/15 shrink-0"
                  aria-hidden="true"
                />
                <span className="text-sm text-text-secondary">
                  Each circle marks a declared zone and its radius
                </span>
              </div>

              <div className="flex items-center gap-3">
                {!isLoading && !error && (
                  <span className="text-sm font-semibold text-text-primary">
                    {zoneCount} active {zoneCount === 1 ? 'zone' : 'zones'}
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => refetch()}
                  disabled={isFetching}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-text-secondary hover:text-text-primary disabled:opacity-50 transition-colors"
                >
                  <RefreshCw size={13} className={isFetching ? 'animate-spin' : undefined} />
                  Refresh
                </button>
              </div>
            </div>

            {isLoading && (
              <div className="h-[420px] md:h-[560px] bg-bg-subtle animate-pulse" />
            )}

            {error && (
              <div className="h-[420px] md:h-[560px] flex flex-col items-center justify-center gap-3 text-center px-6">
                <AlertTriangle className="w-7 h-7 text-negative" />
                <p className="text-sm text-text-secondary max-w-sm">
                  Couldn&apos;t load the outbreak zones. Check your connection and
                  try again.
                </p>
                <button
                  type="button"
                  onClick={() => refetch()}
                  className="inline-flex items-center gap-2 bg-surface text-text-primary border border-border-brand hover:bg-bg-subtle font-bold text-sm py-2.5 px-5 rounded-xl transition-colors"
                >
                  <RefreshCw size={14} />
                  Try again
                </button>
              </div>
            )}

            {/* No outbreaks is good news, so it reads as reassurance rather
                than an empty-data shrug. */}
            {data && zoneCount === 0 && (
              <div className="h-[420px] md:h-[560px] flex flex-col items-center justify-center gap-3 text-center px-6">
                <div className="w-14 h-14 rounded-2xl bg-positive/10 text-positive flex items-center justify-center">
                  <ShieldCheck size={26} />
                </div>
                <h2 className="text-lg font-bold font-heading text-text-primary">
                  No active outbreaks right now
                </h2>
                <p className="text-sm text-text-secondary max-w-sm leading-relaxed">
                  There are no zones currently declared. This map updates as soon as
                  VFF staff confirm and declare one.
                </p>
              </div>
            )}

            {data && zoneCount > 0 && (
              <div className="h-[420px] md:h-[560px]">
                <OutbreakZoneMapWrapper zones={data} />
              </div>
            )}
          </div>
        </section>

        <section className="max-w-[1100px] mx-auto px-6 md:px-12 py-16">
          <div className="rounded-card border border-border-brand bg-surface shadow-card p-8 md:p-10 text-center space-y-4">
            <h2 className="text-2xl md:text-3xl font-bold font-heading tracking-tight">
              Seen an animal that needs help?
            </h2>
            <p className="text-sm md:text-base text-text-secondary max-w-xl mx-auto leading-relaxed">
              Reports from the public are how most zones get spotted in the first
              place. It takes about a minute.
            </p>
            <div className="pt-2">
              <Link
                href="/report"
                className="inline-flex items-center gap-2 bg-[#EF9F27] hover:bg-[#EF9F27]/90 text-white font-bold text-sm py-3.5 px-7 rounded-xl shadow-lg shadow-amber-500/20 hover:shadow-xl hover:shadow-amber-500/30 hover:scale-[1.03] transition-all"
              >
                Report an animal <ArrowRight size={16} />
              </Link>
            </div>
          </div>
        </section>
      </main>

      <HomeFooter />
    </div>
  );
}
