'use client';

import { Scissors, Syringe, Stethoscope, GraduationCap } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useScrollReveal } from './useScrollReveal';

// VFF's actual service areas, per vetsforfuturesl.com. The page previously
// showed what VFF has achieved (Impact) and where it works (Projects) but
// never what it actually does day to day.
const PROGRAMS = [
  {
    icon: Scissors,
    title: 'Sterilization',
    desc: 'Humane population control through nationwide catch-neuter-vaccinate-release campaigns, rather than culling.',
    accent: 'text-red-500',
    bg: 'bg-red-500/10',
  },
  {
    icon: Syringe,
    title: 'Rabies Vaccination',
    desc: 'Mass vaccination drives that underpin the National Rabies Eradication Program VFF co-founded in 2006.',
    accent: 'text-green-500',
    bg: 'bg-green-500/10',
  },
  {
    icon: Stethoscope,
    title: 'Free Animal Clinics',
    desc: 'Free health clinics and monthly outreach bringing veterinary care to rural communities.',
    accent: 'text-blue-500',
    bg: 'bg-blue-500/10',
  },
  {
    icon: GraduationCap,
    title: 'Veterinary Training',
    desc: 'Training surgeons, assistants, dog handlers and vaccinators who now work across Sri Lanka and abroad.',
    accent: 'text-amber-500',
    bg: 'bg-amber-500/10',
  },
];

export default function ProgramsSection() {
  const { ref, revealed, revealClass } = useScrollReveal<HTMLElement>();

  return (
    <section
      id="programs"
      ref={ref}
      className={`max-w-[1280px] mx-auto px-6 md:px-12 py-20 space-y-12 ${revealClass}`}
    >
      <div className="space-y-4 max-w-2xl">
        <span className="text-xs font-bold tracking-wider text-text-secondary uppercase">
          ● What We Do
        </span>
        <h2 className="text-3xl md:text-4xl font-bold tracking-tight font-heading">
          Four programs, one approach
        </h2>
        <p className="text-sm md:text-base text-text-secondary leading-relaxed">
          Every VFF program is built on the same principle: manage animal populations
          humanely, and public health improves alongside animal welfare.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
        {PROGRAMS.map((p, i) => (
          // Reveal and hover are split across two elements so their differing
          // durations don't collide on one transition-all.
          <div
            key={p.title}
            style={{ transitionDelay: revealed ? `${i * 100}ms` : '0ms' }}
            className={cn(
              'transition-all duration-700',
              revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'
            )}
          >
            <div className="group space-y-4">
              <div
                className={cn(
                  'rounded-2xl w-16 h-16 flex items-center justify-center transition-transform duration-200 group-hover:scale-105',
                  p.bg,
                  p.accent
                )}
              >
                <p.icon size={28} />
              </div>
              <h3 className="text-lg font-bold text-text-primary font-heading">{p.title}</h3>
              <p className="text-sm text-text-secondary leading-relaxed">{p.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
