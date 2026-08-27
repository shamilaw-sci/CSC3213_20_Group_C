'use client';

import Image from 'next/image';
import { Heart, ShieldCheck, Users, Lightbulb } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useScrollReveal } from '@/components/home/useScrollReveal';

// The four values VFF names on vetsforfuturesl.com. The one-line descriptions
// are ours — the site lists the values without elaborating on them — and are
// kept to what is evidenced elsewhere on their site.
const VALUES = [
  {
    icon: Heart,
    title: 'Compassion',
    desc: 'No healthy animal is killed to solve a population problem. That constraint has never been negotiable.',
  },
  {
    icon: ShieldCheck,
    title: 'Integrity',
    desc: 'Field results are reported as they are, including where rabies deaths have plateaued rather than fallen.',
  },
  {
    icon: Users,
    title: 'Partnership',
    desc: 'The national program exists because VFF built it with government, local authorities and communities.',
  },
  {
    icon: Lightbulb,
    title: 'Innovation',
    desc: 'Mobile clinics, island-wide catch-neuter-release logistics, and training that multiplies a small team.',
  },
];

export default function ValuesSection() {
  const { ref, revealed } = useScrollReveal<HTMLElement>();

  return (
    <section ref={ref} className="relative overflow-hidden border-b border-border-brand">
      {/* Photo band behind the heading, dark-scrimmed so the values read
          clearly on top of it. */}
      <Image
        src="/images/new4.jpg"
        alt="A volunteer bottle-feeding an orphaned kitten"
        width={4648}
        height={3153}
        className="absolute inset-0 w-full h-full object-cover"
      />
      <div className="absolute inset-0 bg-black/75" />

      <div className="relative max-w-[1280px] mx-auto px-6 md:px-12 py-20 md:py-28">
        <div
          className={cn(
            'max-w-2xl space-y-4 mb-14 transition-all duration-1000',
            revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
          )}
        >
          <span className="text-xs font-bold tracking-wider text-[#EF9F27] uppercase">
            ● What We Stand For
          </span>
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight font-heading text-white">
            Four values, applied in the field
          </h2>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
          {VALUES.map((v, i) => (
            <div
              key={v.title}
              style={{ transitionDelay: revealed ? `${200 + i * 120}ms` : '0ms' }}
              className={cn(
                'transition-all duration-700',
                revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'
              )}
            >
              <div className="group space-y-4">
                <div className="rounded-2xl w-14 h-14 flex items-center justify-center bg-white/10 text-[#EF9F27] backdrop-blur-sm transition-transform duration-200 group-hover:scale-105">
                  <v.icon size={24} />
                </div>
                <h3 className="text-lg font-bold text-white font-heading">{v.title}</h3>
                <p className="text-sm text-white/70 leading-relaxed">{v.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
