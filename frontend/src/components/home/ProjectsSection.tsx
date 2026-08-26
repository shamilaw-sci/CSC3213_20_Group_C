'use client';

import { cn } from '@/lib/utils';
import { useScrollReveal } from './useScrollReveal';

// Real field projects, per vetsforfuturesl.com. These used to flash past in a
// 5-second hero carousel; they get their own section now so each one is
// actually readable.
const PROJECTS = [
  {
    image: '/images/galle-project.jpg',
    name: 'Galle Project',
    detail: "Sri Lanka's largest sterilization initiative.",
  },
  {
    image: '/images/mannar-project.jpg',
    name: 'Mannar Island Project',
    detail: 'Targeting 75% vaccination and sterilization of roughly 4,500 stray dogs.',
  },
  {
    image: '/images/anuradhapura-project.jpg',
    name: 'Anuradhapura Project',
    detail: 'A five-year collaboration spanning 30 divisions.',
  },
  {
    image: '/images/sigiriya-project.jpg',
    name: 'Sigiriya Ancient City Project',
    detail: 'Biannual population management at the ancient city.',
  },
];

export default function ProjectsSection() {
  const { ref, revealed, revealClass } = useScrollReveal<HTMLElement>();

  return (
    <section
      id="projects"
      ref={ref}
      className={`bg-bg-subtle border-y border-border-brand py-20 ${revealClass}`}
    >
      <div className="max-w-[1280px] mx-auto px-6 md:px-12 space-y-12">
        <div className="space-y-4">
          <span className="text-xs font-bold tracking-wider text-text-secondary uppercase">
            ● Where We Work
          </span>
          <h2 className="text-3xl font-bold tracking-tight font-heading">Field Projects</h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {PROJECTS.map((p, i) => (
            <div
              key={p.image}
              style={{ transitionDelay: revealed ? `${i * 100}ms` : '0ms' }}
              className={cn(
                'transition-all duration-700',
                revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'
              )}
            >
              <div className="group rounded-2xl overflow-hidden border border-border-brand/50 bg-surface shadow-card hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200">
                <div className="h-44 relative overflow-hidden">
                  <div
                    className="absolute inset-0 bg-cover bg-center transition-transform duration-500 group-hover:scale-105"
                    style={{ backgroundImage: `url('${p.image}')` }}
                  />
                </div>
                <div className="p-6 space-y-2">
                  <h3 className="text-base font-bold text-text-primary">{p.name}</h3>
                  <p className="text-sm text-text-secondary leading-relaxed">{p.detail}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
