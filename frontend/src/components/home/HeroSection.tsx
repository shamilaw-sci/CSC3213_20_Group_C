'use client';

import { useAuthStore } from '@/store/useAuthStore';
import { Button } from '@/components/ui/button';
import { ArrowRight } from 'lucide-react';
import Link from 'next/link';
import Image from 'next/image';
import { cn } from '@/lib/utils';
import { useScrollReveal } from './useScrollReveal';

export default function HeroSection() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const { ref, revealed } = useScrollReveal<HTMLElement>();

  return (
    <section id="hero" ref={ref} className="relative overflow-hidden">
      {/* Full-bleed real photo (new1.jpg, supplied directly — a street dog
          resting on a wall) at its natural 6000x4000 / 1.5:1 aspect via
          next/image, not a fixed-height bg-cover box, so nothing gets
          cropped. At typical desktop widths that renders 800-950px tall —
          genuinely the first, dominant thing on the page, the way GoFundMe
          and Humane World lead with photography rather than a text block. */}
      <Image
        src="/images/new1.jpg"
        alt="A street dog cared for by Vets For Future"
        width={6000}
        height={4000}
        priority
        className="w-full h-auto"
      />

      {/* Gradient concentrated at the bottom, same as every other photo hero
          on the site, so the top of the image — where the dog's face is —
          stays fully visible. */}
      <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/25 to-transparent" />

      <div
        className={cn(
          'absolute inset-x-0 bottom-0 transition-all duration-1000',
          revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
        )}
      >
        <div className="max-w-[1280px] mx-auto px-6 md:px-12 pb-10 md:pb-16 pt-24 space-y-6">
          <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold leading-tight tracking-tight text-white font-heading drop-shadow-lg max-w-3xl">
            A <span className="text-[#EF9F27]">humane future</span> for Sri Lanka&apos;s street animals.
          </h1>

          <p className="text-sm md:text-base text-white/85 leading-relaxed max-w-lg drop-shadow">
            The first and only organization in Sri Lanka specializing in humane animal population control. Since 2000, we&apos;ve reached over a million animals through sterilization and vaccinated 1.3 million against rabies.
          </p>

          {/* Public actions lead. Staff access is a quiet link below, not a
              primary CTA — most visitors here are reporting an animal, not
              signing in to the internal system. */}
          <div className="flex flex-wrap gap-4 pt-2">
            <Link href="/report">
              <Button className="bg-[#EF9F27] hover:bg-[#EF9F27]/90 text-white font-bold text-sm h-auto py-3.5 px-7 rounded-xl shadow-lg shadow-amber-500/30 hover:shadow-xl hover:shadow-amber-500/40 hover:scale-[1.03] transition-all border-none">
                Report an Animal <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
            <Link href="/outbreak-map">
              <Button
                variant="outline"
                className="bg-white/10 backdrop-blur-sm text-white border-white/40 hover:bg-white/20 font-bold text-sm h-auto py-3.5 px-7 rounded-xl transition-all"
              >
                View Case Map
              </Button>
            </Link>
          </div>

          <div className="pt-1">
            {isAuthenticated ? (
              <Link href="/dashboard" className="text-sm font-semibold text-[#EF9F27] hover:underline inline-flex items-center gap-1.5">
                Go to staff dashboard <ArrowRight size={13} />
              </Link>
            ) : (
              <Link href="/login" className="text-sm font-semibold text-white/75 hover:text-white transition-colors inline-flex items-center gap-1.5">
                VFF staff? Sign in to the management system <ArrowRight size={13} />
              </Link>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
