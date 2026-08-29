'use client';

import Image from 'next/image';
import { cn } from '@/lib/utils';
import { useScrollReveal } from './useScrollReveal';

// A full-bleed photographic band between two boxy card sections. Both
// reference sites break their card grids up with large photography rather
// than running section after section of the same rectangle, and the page
// had no full-width image between the hero and the footer.
export default function VisionBand() {
  const { ref, revealed } = useScrollReveal<HTMLElement>();

  return (
    <section ref={ref} className="relative overflow-hidden border-y border-border-brand">
      <div className="relative h-[420px] md:h-[520px]">
        {/* Slow Ken Burns settle: the photo starts fractionally over-scaled
            and eases back as the band comes into view. Long and small enough
            to register as depth rather than as an animation, and skipped
            entirely for anyone who has asked for less motion. */}
        <Image
          src="/images/bunny.webp"
          alt="A rescued rabbit being hand-fed"
          fill
          sizes="100vw"
          style={{ transitionDuration: '9000ms' }}
          className={cn(
            'object-cover object-center transition-transform ease-out motion-reduce:transition-none motion-reduce:scale-100',
            revealed ? 'scale-100' : 'scale-110'
          )}
        />

        <div className="absolute inset-0 bg-gradient-to-r from-black/85 via-black/60 to-black/30" />

        <div className="relative h-full flex items-center">
          <div className="max-w-[1280px] mx-auto px-6 md:px-12 w-full">
            <blockquote
              className={cn(
                'max-w-2xl transition-all duration-1000 delay-200',
                revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'
              )}
            >
              <p className="text-2xl md:text-4xl font-bold font-heading leading-snug tracking-tight text-white drop-shadow-lg">
                &ldquo;A future where all animals are treated with{' '}
                <span className="text-[#EF9F27]">respect and compassion</span>, living
                harmoniously within their communities.&rdquo;
              </p>
              <footer className="mt-5 text-xs font-bold uppercase tracking-wider text-white/70">
                Vets For Future — our vision
              </footer>
            </blockquote>
          </div>
        </div>
      </div>
    </section>
  );
}
