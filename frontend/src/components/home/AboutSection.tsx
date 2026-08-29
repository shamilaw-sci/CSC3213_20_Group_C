'use client';

import { Heart } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useScrollReveal } from './useScrollReveal';

export default function AboutSection() {
  const { ref, revealed } = useScrollReveal<HTMLElement>();

  return (
    <section
      id="about"
      ref={ref}
      // Plain background rather than tinted, so this alternates with the
      // tinted Programs band directly below — two tinted sections running
      // together merge into one slab, which is most of what reads as flat.
      className="bg-bg-brand border-y border-border-brand py-20"
    >
      <div className="max-w-[1280px] mx-auto px-6 md:px-12 grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
        {/* The two columns enter from opposite sides rather than both
            sliding up together — the same directional split reads more
            deliberate than the identical fade-up every other section uses. */}
        <div
          className={cn(
            'h-[280px] md:h-[340px] rounded-2xl overflow-hidden shadow-lg relative order-2 lg:order-1 transition-all duration-1000',
            revealed ? 'opacity-100 translate-x-0' : 'opacity-0 -translate-x-10'
          )}
        >
          <div
            className="absolute inset-0 bg-cover bg-center"
            style={{ backgroundImage: "url('/images/mannar-project.jpg')" }}
          />
          {/* No text sits over this image, so it needs no scrim — the old
              overlay was dimming it for no reason. */}
        </div>

        <div
          className={cn(
            'space-y-6 order-1 lg:order-2 transition-all duration-1000',
            revealed ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-10'
          )}
        >
          <span className="text-xs font-bold tracking-wider text-text-secondary uppercase flex items-center gap-1.5">
            <Heart size={12} className="text-red-500" /> About Vets For Future
          </span>
          <h2 className="text-3xl md:text-4xl font-bold leading-tight tracking-tight text-text-primary font-heading">
            The first and only organization in Sri Lanka specializing in humane animal population control.
          </h2>
          <p className="text-text-secondary text-sm md:text-base leading-relaxed">
            Founded in 2000, Vets For Future co-founded the National Rabies Eradication and Humane Animal Population Control Program in 2006, launched nationally in 2008. Beyond sterilization and vaccination, VFF runs free animal health clinics, community feeding and awareness programs, and monthly outreach to rural communities.
          </p>
          <blockquote className="border-l-2 border-[#EF9F27] pl-4 text-text-secondary text-sm md:text-base leading-relaxed italic">
            Our initiatives aim to inspire change, integrate humane practices into animal population management, and nurture a healthier coexistence between humans and animals.
          </blockquote>
        </div>
      </div>
    </section>
  );
}
