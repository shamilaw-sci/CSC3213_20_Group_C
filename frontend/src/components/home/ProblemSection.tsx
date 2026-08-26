'use client';

import Link from 'next/link';
import { ArrowRight, TrendingDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useScrollReveal } from './useScrollReveal';

export default function ProblemSection() {
  const { ref, revealed } = useScrollReveal<HTMLElement>();

  return (
    <section
      id="problem"
      ref={ref}
      className="bg-bg-brand border-b border-border-brand py-20"
    >
      <div className="max-w-[1280px] mx-auto px-6 md:px-12">
        <div
          className={cn(
            'max-w-3xl space-y-6 transition-all duration-1000',
            revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
          )}
        >
          <span className="text-xs font-bold tracking-wider text-text-secondary uppercase">
            ● The Problem
          </span>

          {/* Framed around the one verified, high-stakes number VFF has.
              Everything here is sourced from vetsforfuturesl.com — no
              invented figures about population size or suffering. */}
          <h2 className="text-3xl md:text-5xl font-bold leading-tight tracking-tight font-heading">
            Rabies once killed more than{' '}
            <span className="text-[#EF9F27]">60 people a year</span> in Sri Lanka.
          </h2>

          <p className="text-sm md:text-lg text-text-secondary leading-relaxed">
            Uncontrolled street animal populations drive rabies transmission and animal
            suffering alike. Culling had been the default response — effective at neither.
            Vets For Future was founded in 2000 to prove a humane alternative works.
          </p>

          <div className="flex items-center gap-3 pt-2 text-sm font-semibold text-positive">
            <TrendingDown size={18} />
            <span>Today that figure is between 20 and 30.</span>
          </div>

          <div className="flex flex-wrap gap-4 pt-4">
            <Link
              href="/donate"
              className="inline-flex items-center gap-2 bg-[#EF9F27] hover:bg-[#EF9F27]/90 text-white font-bold text-sm py-3.5 px-7 rounded-xl shadow-lg shadow-amber-500/20 hover:shadow-xl hover:shadow-amber-500/30 hover:scale-[1.03] transition-all"
            >
              Help us help them <ArrowRight size={16} />
            </Link>
            <Link
              href="/report"
              className="inline-flex items-center gap-2 bg-surface text-text-primary border border-border-brand/60 hover:bg-bg-subtle font-bold text-sm py-3.5 px-7 rounded-xl shadow-card hover:shadow-md transition-all"
            >
              Report an animal
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
