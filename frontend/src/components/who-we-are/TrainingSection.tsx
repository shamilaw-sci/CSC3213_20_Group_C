'use client';

import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { useScrollReveal } from '@/components/home/useScrollReveal';

// The training figures published on vetsforfuturesl.com. Kept as its own
// section because it is the part of VFF's record that explains how a two-person
// organization reached a million animals — it trained the people who did it.
const TRAINED = [
  { value: 130, suffix: '+', label: 'Veterinary surgeons' },
  { value: 300, suffix: '+', label: 'Veterinary assistants' },
  { value: 70, suffix: '+', label: 'Vaccinators' },
];

const DURATION = 1400;

function useCountUp(target: number, start: boolean) {
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (!start) return;

    // Counting up is decoration on top of a number that is already readable.
    // Anyone who has asked for less motion just gets the final figure.
    const prefersReduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (prefersReduced) {
      setValue(target);
      return;
    }

    let frame = 0;
    const startedAt = performance.now();

    const tick = (now: number) => {
      const progress = Math.min((now - startedAt) / DURATION, 1);
      // Ease-out cubic, so the number decelerates into its final value.
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(Math.round(target * eased));
      if (progress < 1) frame = requestAnimationFrame(tick);
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, start]);

  return value;
}

function TrainedStat({
  value,
  suffix,
  label,
  revealed,
  delay,
}: {
  value: number;
  suffix: string;
  label: string;
  revealed: boolean;
  delay: number;
}) {
  const count = useCountUp(value, revealed);

  return (
    <div
      style={{ transitionDelay: revealed ? `${delay}ms` : '0ms' }}
      className={cn(
        'space-y-2 transition-all duration-700',
        revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'
      )}
    >
      <span className="block text-4xl md:text-5xl font-bold font-heading text-[#EF9F27] tabular-nums">
        {count}
        {suffix}
      </span>
      <span className="block text-sm font-semibold text-text-secondary">{label}</span>
    </div>
  );
}

export default function TrainingSection() {
  const { ref, revealed } = useScrollReveal<HTMLElement>();

  return (
    <section ref={ref} className="bg-bg-brand border-b border-border-brand py-20 md:py-28">
      <div className="max-w-[1280px] mx-auto px-6 md:px-12">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          <div
            className={cn(
              'space-y-5 transition-all duration-1000',
              revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
            )}
          >
            <span className="text-xs font-bold tracking-wider text-text-secondary uppercase">
              ● How The Work Multiplies
            </span>
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight font-heading">
              We trained the people who do this work now
            </h2>
            <p className="text-sm md:text-base text-text-secondary leading-relaxed">
              Reaching a million animals was never something two veterinarians could do
              alone. VFF&apos;s answer was to teach — surgeons, assistants, dog handlers
              and vaccinators who now work across Sri Lanka and overseas.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-8">
            {TRAINED.map((t, i) => (
              <TrainedStat
                key={t.label}
                value={t.value}
                suffix={t.suffix}
                label={t.label}
                revealed={revealed}
                delay={200 + i * 120}
              />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
