'use client';

import { useAuthStore } from '@/store/useAuthStore';
import { Button } from '@/components/ui/button';
import { ArrowRight, PawPrint } from 'lucide-react';
import Link from 'next/link';
import { cn } from '@/lib/utils';
import { useScrollReveal } from './useScrollReveal';

export default function HeroSection() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const { ref, revealed } = useScrollReveal<HTMLElement>();

  return (
    <section id="hero" ref={ref} className="max-w-[1280px] mx-auto px-6 md:px-12 py-16">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
        {/* Copy column — fades up. The paw print behind the headline is the
            recurring visual signature; it shows up again, smaller, in the
            stats band below. */}
        <div
          className={cn(
            'relative space-y-6 transition-all duration-1000',
            revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
          )}
        >
          <PawPrint
            className="absolute -left-6 -top-10 text-[#EF9F27]/[0.07] -rotate-12 pointer-events-none select-none"
            size={220}
            strokeWidth={1}
            aria-hidden="true"
          />

          <h1 className="relative text-4xl md:text-5xl lg:text-6xl font-bold leading-tight tracking-tight text-text-primary font-heading">
            A <span className="text-[#EF9F27]">humane future</span> for <br />
            Sri Lanka&apos;s street animals.
          </h1>

          <p className="relative text-sm md:text-base text-text-secondary leading-relaxed max-w-lg">
            The first and only organization in Sri Lanka specializing in humane animal population control. Since 2000, we&apos;ve reached over a million animals through sterilization and vaccinated 1.3 million against rabies.
          </p>

          {/* Public actions lead. Staff access is a quiet link below, not a
              primary CTA — most visitors here are reporting an animal, not
              signing in to the internal system. */}
          <div className="relative flex flex-wrap gap-4 pt-4">
            <Link href="/report">
              <Button className="bg-[#EF9F27] hover:bg-[#EF9F27]/90 text-white font-bold text-sm h-auto py-3.5 px-7 rounded-xl shadow-lg shadow-amber-500/20 hover:shadow-xl hover:shadow-amber-500/30 hover:scale-[1.03] transition-all border-none">
                Report an Animal <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
            <Link href="/outbreak-map">
              <Button variant="outline" className="bg-surface text-text-primary border-border-brand/60 hover:bg-bg-subtle font-bold text-sm h-auto py-3.5 px-7 rounded-xl shadow-card hover:shadow-md transition-all">
                View Case Map
              </Button>
            </Link>
          </div>

          <div className="relative pt-1">
            {isAuthenticated ? (
              <Link href="/dashboard" className="text-sm font-semibold text-[#EF9F27] hover:underline inline-flex items-center gap-1.5">
                Go to staff dashboard <ArrowRight size={13} />
              </Link>
            ) : (
              <Link href="/login" className="text-sm font-semibold text-text-secondary hover:text-text-primary transition-colors inline-flex items-center gap-1.5">
                VFF staff? Sign in to the management system <ArrowRight size={13} />
              </Link>
            )}
          </div>
        </div>

        {/* Image column — one committed image. A rotating carousel split
            attention across three stories and gave none of them time to
            land; the projects now have their own section below. Scales in
            rather than sliding, so it doesn't just mirror the copy column. */}
        <div
          className={cn(
            'relative w-full h-[280px] md:h-[380px] rounded-2xl overflow-hidden shadow-2xl bg-surface group transition-all duration-1000',
            revealed ? 'opacity-100 scale-100' : 'opacity-0 scale-95'
          )}
        >
          <div
            className="absolute inset-0 bg-cover bg-center transition-transform duration-700 group-hover:scale-105"
            style={{ backgroundImage: "url('/images/galle-project.jpg')" }}
          />
          {/* Gradient is concentrated at the bottom purely so the caption
              stays legible — the top two-thirds of the photo is left clear.
              Always dark + white text so it reads in both themes without
              depending on a `light:` variant (which isn't registered). */}
          <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/5 to-transparent" />

          <div className="absolute bottom-6 left-6 right-6 space-y-1">
            <p className="text-xs tracking-wider text-white font-bold uppercase drop-shadow">
              Galle Sterilization Project
            </p>
            <p className="text-xs tracking-wider text-white/80 font-medium uppercase">
              Sri Lanka&apos;s largest sterilization initiative
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
