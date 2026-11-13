'use client';

import RecentRescueActivity from './RecentRescueActivity';
import ImpactNumbers from './ImpactNumbers';
import { useScrollReveal } from './useScrollReveal';

export default function ActivitySection() {
  const { ref, revealClass } = useScrollReveal<HTMLElement>();

  return (
    <section
      id="activity"
      ref={ref}
      className={`py-20 ${revealClass}`}
    >
      <div className="max-w-[1280px] mx-auto px-6 md:px-12 space-y-12">
        <div className="space-y-4">
          <span className="text-xs font-bold tracking-wider text-text-secondary uppercase">
            ● Live From The Field
          </span>
          <h2 className="text-3xl font-bold tracking-tight font-heading">Rescue Activity</h2>
          <p className="text-text-secondary text-sm md:text-base leading-relaxed max-w-2xl">
            Cases reported by the public over the last 30 days, and where they stand today.
          </p>
        </div>

        <ImpactNumbers />

        <RecentRescueActivity />
      </div>
    </section>
  );
}
