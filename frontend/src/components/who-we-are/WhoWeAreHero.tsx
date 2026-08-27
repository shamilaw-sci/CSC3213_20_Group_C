'use client';

import Image from 'next/image';
import { cn } from '@/lib/utils';
import { useScrollReveal } from '@/components/home/useScrollReveal';

// Same full-bleed treatment as the homepage hero: the photo renders at its
// natural aspect via next/image rather than a fixed-height bg-cover box, so
// nothing gets cropped, and the gradient is weighted to the bottom where the
// text sits.
export default function WhoWeAreHero() {
  const { ref, revealed } = useScrollReveal<HTMLElement>();

  return (
    <section ref={ref} className="relative overflow-hidden">
      <Image
        src="/images/new3.jpg"
        alt="A rescued kitten held by a Vets For Future volunteer"
        width={5184}
        height={3456}
        priority
        className="w-full h-auto"
      />

      <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/30 to-transparent" />

      <div
        className={cn(
          'absolute inset-x-0 bottom-0 transition-all duration-1000',
          revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
        )}
      >
        <div className="max-w-[1280px] mx-auto px-6 md:px-12 pb-10 md:pb-16 pt-24 space-y-5">
          <span className="text-xs font-bold tracking-[0.2em] text-[#EF9F27] uppercase drop-shadow">
            Who We Are
          </span>
          <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold leading-tight tracking-tight text-white font-heading drop-shadow-lg max-w-3xl">
            Two vets who refused to accept culling as the answer.
          </h1>
          <p className="text-sm md:text-base text-white/85 leading-relaxed max-w-xl drop-shadow">
            Vets For Future has spent twenty-five years proving that Sri Lanka can
            control its street animal population — and eradicate rabies — without
            killing a single healthy animal.
          </p>
        </div>
      </div>
    </section>
  );
}
