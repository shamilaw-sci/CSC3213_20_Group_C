'use client';

import { PawPrint } from 'lucide-react';
import { useScrollReveal } from './useScrollReveal';

// Used to live inside the hero as a plain text/border strip — a full-bleed
// colour band instead, since the amber accent otherwise appears in exactly
// one place on this whole page (the primary button).
const STATS = [
  { label: 'Animals Sterilized', val: '1M+' },
  { label: 'Rabies Vaccinations', val: '1.3M+' },
  { label: 'Veterinarians Trained', val: '130+' },
  { label: 'Years in the Field', val: '25+' },
];

export default function StatsBand() {
  const { ref, revealClass } = useScrollReveal<HTMLElement>();

  return (
    <section
      id="stats"
      ref={ref}
      // A subtle diagonal top edge instead of a hard rectangle — the same
      // reason no other section here is a plain straight-edged block.
      style={{ clipPath: 'polygon(0 22px, 100% 0, 100% 100%, 0 100%)' }}
      className={`relative overflow-hidden bg-[#EF9F27] ${revealClass}`}
    >
      <PawPrint
        className="absolute right-8 -bottom-6 text-white/10 rotate-12 pointer-events-none select-none"
        size={140}
        strokeWidth={1}
        aria-hidden="true"
      />

      <div className="relative max-w-[1280px] mx-auto px-6 md:px-12 py-12 grid grid-cols-2 md:grid-cols-4 gap-6">
        {STATS.map((stat) => (
          <div
            key={stat.label}
            className="flex flex-col gap-1 md:pr-4 md:border-r md:border-white/25 md:last:border-none"
          >
            <span className="text-3xl md:text-4xl font-extrabold text-white tracking-tight font-heading">
              {stat.val}
            </span>
            <span className="text-xs font-bold text-white/85 uppercase tracking-wider">
              {stat.label}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
