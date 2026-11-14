'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, CalendarHeart } from 'lucide-react';
import { ProgramService } from '@/services/program.service';
import { ClinicCard } from '@/components/clinics/ClinicCard';

const SHOWN = 3;

// The next few published clinics, straight under the hero, so someone landing
// on the site sees "there is a drive in Kandy on Saturday" first. Renders
// nothing while loading, on error, or when none are published: the homepage
// reads the same as before rather than showing an empty box.
export default function UpcomingClinicsStrip() {
  const { data } = useQuery({
    queryKey: ['public-programs'],
    queryFn: ProgramService.listPublic,
  });

  if (!data || data.length === 0) return null;

  return (
    <section className="bg-bg-subtle border-y border-border-brand">
      <div className="max-w-[1280px] mx-auto px-6 md:px-12 py-12 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
          <div className="space-y-1">
            <span className="inline-flex items-center gap-2 text-xs font-bold tracking-wider text-[#EF9F27] uppercase">
              <CalendarHeart size={14} /> Coming to your area
            </span>
            <h2 className="text-2xl md:text-3xl font-bold font-heading tracking-tight text-text-primary">
              Free clinics & sterilization drives
            </h2>
          </div>
          <Link
            href="/clinics"
            className="inline-flex items-center gap-1.5 text-sm font-semibold text-[#EF9F27] hover:underline"
          >
            {data.length > SHOWN ? `See all ${data.length}` : 'See details'} <ArrowRight size={15} />
          </Link>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {data.slice(0, SHOWN).map((p) => (
            <Link key={p.id} href="/clinics" className="block hover:-translate-y-0.5 transition-transform">
              <ClinicCard program={p} compact />
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}
