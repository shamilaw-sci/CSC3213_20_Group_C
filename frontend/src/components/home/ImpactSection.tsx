'use client';

import { ShieldCheck, Heart, Users, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useScrollReveal } from './useScrollReveal';

// Every other card here states a number. This one states a change — the
// clearest, highest-stakes number VFF has — so it gets its own visual
// register instead of the same icon+title+paragraph treatment as the rest.
const COMPACT_CARDS = [
  { title: '1M+ Sterilized', desc: 'Over one million dogs and cats reached through nationwide sterilization campaigns since 2000.', icon: Heart, bg: 'bg-red-500', glow: 'shadow-red-500/30' },
  { title: '1.3M+ Vaccinated', desc: 'Approximately 1.3 million animals vaccinated against rabies across every province.', icon: ShieldCheck, bg: 'bg-green-500', glow: 'shadow-green-500/30' },
  { title: '500+ Trained', desc: 'More than 130 veterinary surgeons, 300 assistants and dog handlers, and over 70 vaccinators now working across Sri Lanka and abroad.', icon: Users, bg: 'bg-amber-500', glow: 'shadow-amber-500/30' },
];

export default function ImpactSection() {
  const { ref, revealed, revealClass } = useScrollReveal<HTMLElement>();

  return (
    <section
      id="impact"
      ref={ref}
      className={`max-w-[1280px] mx-auto px-6 md:px-12 py-20 space-y-12 ${revealClass}`}
    >
      <div className="space-y-4">
        <span className="text-xs font-bold tracking-wider text-text-secondary uppercase">
          ● Accomplishments
        </span>
        <h2 className="text-3xl font-bold tracking-tight font-heading">Our Operational Footprint</h2>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Featured stat — before/after, not another counter */}
        <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-blue-600 to-blue-800 p-8 md:p-10 text-white shadow-xl shadow-blue-500/20 flex flex-col justify-between min-h-[280px]">
          <Heart className="absolute -right-6 -top-6 text-white/10" size={200} strokeWidth={1.5} />

          <span className="relative text-xs font-bold uppercase tracking-wider text-blue-200">
            Human Lives Saved
          </span>

          <div className="relative space-y-4 mt-6">
            <div className="flex items-baseline gap-3 flex-wrap">
              <span className="text-2xl md:text-3xl font-bold text-blue-200/70 line-through decoration-2">60+</span>
              <ArrowRight size={22} className="text-blue-200/70" />
              <span className="text-5xl md:text-6xl font-extrabold font-heading tracking-tight">20–30</span>
            </div>
            <p className="text-sm text-blue-100 leading-relaxed max-w-sm">
              Annual human rabies deaths in Sri Lanka, before VFF&apos;s programs began and today.
            </p>
          </div>
        </div>

        {/* Supporting stats — staggered in one after another rather than
            appearing all at once with the featured card. */}
        <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-1 gap-6">
          {COMPACT_CARDS.map((card, i) => (
            // Reveal (opacity/translate, 700ms, staggered) and hover feedback
            // (shadow/lift, 200ms) both animate via transition-all, so they're
            // split onto two elements — combining them on one node means
            // whichever duration class comes last in the stylesheet wins for
            // both, and hover feedback ends up sluggish.
            <div
              key={card.title}
              style={{ transitionDelay: revealed ? `${150 + i * 120}ms` : '0ms' }}
              className={cn(
                'transition-all duration-700',
                revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'
              )}
            >
              <div className="bg-surface border border-border-brand/50 rounded-2xl p-6 flex items-center gap-4 shadow-card hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200">
                <div className={cn('rounded-xl w-12 h-12 flex items-center justify-center text-white shadow-md shrink-0', card.bg, card.glow)}>
                  <card.icon size={20} />
                </div>
                <div>
                  <h3 className="text-base font-bold text-text-primary">{card.title}</h3>
                  <p className="text-xs text-text-secondary leading-relaxed mt-0.5">{card.desc}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
