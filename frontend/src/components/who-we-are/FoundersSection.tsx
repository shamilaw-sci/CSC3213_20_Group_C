'use client';

import Image from 'next/image';
import { Award } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useScrollReveal } from '@/components/home/useScrollReveal';

// Names, qualifications and awards are as published on vetsforfuturesl.com.
// No portraits are shown because VFF does not publish headshots of either
// founder, and using a stand-in photograph of a person would misrepresent them.
const FOUNDERS = [
  {
    name: 'Dr. Chamith Nanayakkara',
    qualification: 'BVSc (Hons)',
    awards: ['Social Service Excellency Award', 'Lifetime Achievement Award — Dharma Voices for Animals'],
  },
  {
    name: 'Dr. Udaya Wijayawardana',
    qualification: 'BVSc (Hons)',
    awards: ['Social Service Excellency Award'],
  },
];

export default function FoundersSection() {
  const { ref, revealed } = useScrollReveal<HTMLElement>();

  return (
    <section ref={ref} className="bg-bg-brand border-b border-border-brand py-20 md:py-28">
      <div className="max-w-[1280px] mx-auto px-6 md:px-12">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          <div
            className={cn(
              'relative rounded-card overflow-hidden shadow-card transition-all duration-1000',
              revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
            )}
          >
            <Image
              src="/images/vff-team.jpg"
              alt="Vets For Future surgeons performing a sterilization in the field"
              width={1440}
              height={1440}
              className="w-full h-auto"
            />
          </div>

          <div
            className={cn(
              'space-y-8 transition-all duration-1000 delay-200',
              revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
            )}
          >
            <div className="space-y-4">
              <span className="text-xs font-bold tracking-wider text-text-secondary uppercase">
                ● The Founders
              </span>
              <h2 className="text-3xl md:text-4xl font-bold tracking-tight font-heading">
                Started by two veterinarians, run by a trained field team
              </h2>
              <p className="text-sm md:text-base text-text-secondary leading-relaxed">
                Between them, VFF&apos;s founders have personally performed some 93,000
                sterilizations — and built the training pipeline that lets the work
                continue without them.
              </p>
            </div>

            <div className="space-y-4">
              {FOUNDERS.map((f) => (
                <div
                  key={f.name}
                  className="rounded-card border border-border-brand bg-surface p-6 space-y-3 shadow-card"
                >
                  <div>
                    <h3 className="text-base font-bold text-text-primary font-heading">
                      {f.name}
                    </h3>
                    <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
                      Co-founder · {f.qualification}
                    </span>
                  </div>
                  <ul className="space-y-1.5">
                    {f.awards.map((a) => (
                      <li key={a} className="flex items-start gap-2 text-sm text-text-secondary">
                        <Award size={14} className="text-[#EF9F27] mt-0.5 shrink-0" />
                        <span>{a}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
