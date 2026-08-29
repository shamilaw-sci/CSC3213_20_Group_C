'use client';

import { useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { Play, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useScrollReveal } from './useScrollReveal';

const VIDEO_ID = 'KnRmx6dTyZQ';
const VIDEO_TITLE =
  'BIG FOCUS — සත්ත්ව ගහන පාලනය කිරීමේ විද්‍යාත්මක සැලසුම් (Ada Derana, 17 December 2024)';

export default function VideoSection() {
  const { ref, revealed } = useScrollReveal<HTMLElement>();

  // The player is only mounted once someone asks for it. Embedding the iframe
  // on load would pull in YouTube's player bundle — and set its cookies — for
  // every visitor, including the ones who came here on mobile data to report
  // an injured animal and will never press play.
  const [playing, setPlaying] = useState(false);

  return (
    <section
      id="in-the-media"
      ref={ref}
      className="bg-bg-subtle border-b border-border-brand py-20 md:py-28"
    >
      <div className="max-w-[1280px] mx-auto px-6 md:px-12">
        <div
          className={cn(
            'max-w-2xl mx-auto text-center space-y-4 mb-10 transition-all duration-1000',
            revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
          )}
        >
          <span className="text-xs font-bold tracking-wider text-text-secondary uppercase">
            ● In The Media
          </span>
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight font-heading">
            Humane population control, on national television
          </h2>
          <p className="text-sm md:text-base text-text-secondary leading-relaxed">
            Ada Derana&apos;s <em>BIG FOCUS</em>{' '}
            gave a full segment to the science behind controlling Sri Lanka&apos;s
            animal population humanely — the approach Vets For Future has been
            building since 2000.
          </p>
        </div>

        <div
          className={cn(
            'max-w-3xl mx-auto transition-all duration-1000 delay-200',
            revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
          )}
        >
          <div className="relative aspect-video rounded-card overflow-hidden shadow-card border border-border-brand bg-black">
            {playing ? (
              <iframe
                src={`https://www.youtube-nocookie.com/embed/${VIDEO_ID}?autoplay=1&rel=0`}
                title={VIDEO_TITLE}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                referrerPolicy="strict-origin-when-cross-origin"
                allowFullScreen
                className="absolute inset-0 w-full h-full"
              />
            ) : (
              <button
                type="button"
                onClick={() => setPlaying(true)}
                aria-label={`Play video: ${VIDEO_TITLE}`}
                className="group absolute inset-0 w-full h-full cursor-pointer"
              >
                <Image
                  src="/images/ada-derana-big-focus.jpg"
                  alt=""
                  fill
                  sizes="(max-width: 768px) 100vw, 768px"
                  className="object-cover"
                />
                <span className="absolute inset-0 bg-black/20 group-hover:bg-black/35 transition-colors duration-200" />
                <span className="absolute inset-0 flex items-center justify-center">
                  <span className="flex items-center justify-center w-16 h-16 md:w-20 md:h-20 rounded-full bg-[#EF9F27] text-white shadow-lg shadow-black/30 transition-transform duration-200 group-hover:scale-110">
                    {/* Nudged right so the triangle looks centred in the circle. */}
                    <Play className="w-7 h-7 md:w-8 md:h-8 ml-1" fill="currentColor" />
                  </span>
                </span>
              </button>
            )}
          </div>

          <p className="text-xs text-text-secondary text-center mt-3">
            Ada Derana · <em>BIG FOCUS</em> · 17 December 2024 · in Sinhala
          </p>
        </div>

        <div
          className={cn(
            'text-center mt-10 transition-all duration-1000 delay-300',
            revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
          )}
        >
          <Link
            href="/who-we-are"
            className="inline-flex items-center gap-2 bg-[#EF9F27] hover:bg-[#EF9F27]/90 text-white font-bold text-sm py-3.5 px-7 rounded-xl shadow-lg shadow-amber-500/20 hover:shadow-xl hover:shadow-amber-500/30 hover:scale-[1.03] transition-all"
          >
            Learn how we work <ArrowRight size={16} />
          </Link>
        </div>
      </div>
    </section>
  );
}
