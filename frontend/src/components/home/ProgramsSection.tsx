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
    ring: 'ring-red-500/15',
  },
  {
    icon: Syringe,
    title: 'Rabies Vaccination',
    desc: 'Mass vaccination drives that underpin the National Rabies Eradication Program VFF co-founded in 2006.',
    accent: 'text-green-600',
    bg: 'bg-green-500/10',
    ring: 'ring-green-500/15',
  },
  {
    icon: Stethoscope,
    title: 'Free Animal Clinics',
    desc: 'Free health clinics and monthly outreach bringing veterinary care to rural communities.',
    accent: 'text-blue-600',
    bg: 'bg-blue-500/10',
    ring: 'ring-blue-500/15',
  },
  {
    icon: GraduationCap,
    title: 'Veterinary Training',
    desc: 'Training surgeons, assistants, dog handlers and vaccinators who now work across Sri Lanka and abroad.',
    accent: 'text-amber-600',
    bg: 'bg-amber-500/10',
    ring: 'ring-amber-500/15',
  },
];

export default function ProgramsSection() {
  const { ref, revealed } = useScrollReveal<HTMLElement>();

  return (
    // A tinted band rather than the same white as the sections either side —
    // the page previously ran several full-width white blocks together, which
    // is most of why this read as flat.
    <section
      id="programs"
      ref={ref}
      className="bg-bg-subtle border-y border-border-brand py-20 md:py-28"
    >
      <div className="max-w-[1280px] mx-auto px-6 md:px-12">
        <div
          className={cn(
            'max-w-2xl mx-auto text-center space-y-4 mb-14 transition-all duration-1000',
            revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
          )}
        >
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

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
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
              <article className="group relative h-full overflow-hidden rounded-card border border-border-brand bg-surface p-7 shadow-card transition-all duration-300 hover:-translate-y-1 hover:shadow-xl hover:border-[#EF9F27]/40">
                {/* Index sits behind the content as a watermark — it gives the
                    four cards a rhythm without adding another line of text. */}
                <span
                  aria-hidden="true"
                  className="absolute -top-1 right-5 text-6xl font-bold font-heading text-text-primary/[0.05] select-none transition-colors duration-300 group-hover:text-[#EF9F27]/15"
                >
                  {String(i + 1).padStart(2, '0')}
                </span>

                <div className="relative space-y-4">
                  <div
                    className={cn(
                      'rounded-2xl w-14 h-14 flex items-center justify-center ring-1 transition-transform duration-300 group-hover:scale-105',
                      p.bg,
                      p.accent,
                      p.ring
                    )}
                  >
                    <p.icon size={26} />
                  </div>

                  <h3 className="text-lg font-bold text-text-primary font-heading">
                    {p.title}
                  </h3>
                  <p className="text-sm text-text-secondary leading-relaxed">{p.desc}</p>
                </div>
              </article>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
