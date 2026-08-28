'use client';

import Link from 'next/link';
import { Heart, ArrowRight, PawPrint } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useScrollReveal } from './useScrollReveal';

// The page used to end on passive contact details. A closing call to action
// gives a visitor who has read the whole way down something to actually do.
export default function ClosingCTA() {
  const { ref, revealed } = useScrollReveal<HTMLElement>();

  return (
    <section
      ref={ref}
      className="relative overflow-hidden bg-gradient-to-br from-[#EF9F27] to-[#D97706]"
    >
      <PawPrint
        className="absolute -right-10 -bottom-12 text-white/10 rotate-12 pointer-events-none select-none"
        size={260}
        strokeWidth={1}
        aria-hidden="true"
      />

      <div
        className={cn(
          'relative max-w-[1280px] mx-auto px-6 md:px-12 py-20 text-center space-y-6 transition-all duration-1000',
          revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
        )}
      >
        <h2 className="text-3xl md:text-5xl font-bold tracking-tight font-heading text-white max-w-3xl mx-auto leading-tight">
          Help build a humane future for Sri Lanka&apos;s street animals.
        </h2>
        <p className="text-sm md:text-lg text-white/85 max-w-xl mx-auto leading-relaxed">
          Every donation funds sterilization, vaccination, and free clinic care.
        </p>

        <div className="flex flex-wrap gap-4 justify-center pt-4">
          <Link
            href="/donate"
            className="inline-flex items-center gap-2 bg-white text-[#B45309] font-bold text-sm py-3.5 px-7 rounded-xl shadow-lg hover:shadow-xl hover:scale-[1.03] transition-all"
          >
            <Heart size={16} fill="currentColor" />
            Donate now
          </Link>
          <Link
            href="/report"
            className="inline-flex items-center gap-2 bg-white/15 text-white border border-white/40 hover:bg-white/25 font-bold text-sm py-3.5 px-7 rounded-xl backdrop-blur-sm transition-all"
          >
            Report an animal <ArrowRight size={16} />
          </Link>
        </div>
      </div>
    </section>
  );
}
