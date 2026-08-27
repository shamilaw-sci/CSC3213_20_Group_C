'use client';

import { cn } from '@/lib/utils';
import { useScrollReveal } from '@/components/home/useScrollReveal';

// Every milestone here is stated on vetsforfuturesl.com. Nothing has been
// filled in to round out the timeline — gaps in their public record stay gaps.
const MILESTONES = [
  {
    year: '2000',
    title: 'Vets For Future is founded',
    desc: 'Dr. Chamith Nanayakkara and Dr. Udaya Wijayawardana start mobile veterinary services in response to rising rabies cases, rejecting culling as a population control method.',
  },
  {
    year: '2006',
    title: 'A national program takes shape',
    desc: 'VFF co-founds the National Rabies Eradication and Humane Animal Population Control Program alongside local partners.',
  },
  {
    year: '2008',
    title: 'Adopted by the Ministry of Health',
    desc: 'The program is taken up as a national initiative, moving humane population control from a private effort to government policy.',
  },
  {
    year: 'Since',
    title: 'The national emergency response team',
    desc: 'VFF is designated the official emergency response team for rabies eradication, and continues to run field projects in Galle, Mannar, Anuradhapura and Sigiriya.',
  },
];

export default function StoryTimeline() {
  const { ref, revealed } = useScrollReveal<HTMLElement>();

  return (
    <section ref={ref} className="bg-bg-subtle border-b border-border-brand py-20 md:py-28">
      <div className="max-w-[1280px] mx-auto px-6 md:px-12">
        <div
          className={cn(
            'max-w-2xl space-y-4 mb-16 transition-all duration-1000',
            revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
          )}
        >
          <span className="text-xs font-bold tracking-wider text-text-secondary uppercase">
            ● Our Story
          </span>
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight font-heading">
            From two vets with a van to national policy
          </h2>
        </div>

        <div className="relative">
          {/* The rail sits behind the markers and is hidden from assistive
              tech — the year text already conveys the sequence. */}
          <div
            aria-hidden="true"
            className={cn(
              'absolute left-[7px] top-2 w-px bg-border-brand origin-top transition-transform duration-1000 ease-out md:left-1/2 md:-translate-x-1/2',
              revealed ? 'scale-y-100' : 'scale-y-0'
            )}
            style={{ height: 'calc(100% - 1rem)' }}
          />

          <ol className="space-y-12">
            {MILESTONES.map((m, i) => (
              <li
                key={m.year}
                style={{ transitionDelay: revealed ? `${200 + i * 150}ms` : '0ms' }}
                className={cn(
                  'relative pl-10 transition-all duration-700 md:pl-0',
                  // Alternating sides on desktop, single column on mobile.
                  'md:grid md:grid-cols-2 md:gap-12',
                  revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'
                )}
              >
                <span
                  aria-hidden="true"
                  className="absolute left-0 top-1.5 w-[15px] h-[15px] rounded-full bg-[#EF9F27] ring-4 ring-bg-subtle md:left-1/2 md:-translate-x-1/2"
                />

                <div
                  className={cn(
                    'space-y-2',
                    i % 2 === 0
                      ? 'md:col-start-1 md:text-right md:pr-4'
                      : 'md:col-start-2 md:pl-4'
                  )}
                >
                  <span className="block text-2xl md:text-3xl font-bold font-heading text-[#EF9F27]">
                    {m.year}
                  </span>
                  <h3 className="text-lg font-bold text-text-primary font-heading">
                    {m.title}
                  </h3>
                  <p className="text-sm text-text-secondary leading-relaxed">{m.desc}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
