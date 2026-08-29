'use client';

import Image from 'next/image';
import { cn } from '@/lib/utils';
import { useScrollReveal } from '@/components/home/useScrollReveal';

// Mission and vision are quoted from vetsforfuturesl.com. The lead paragraph
// paraphrases their founding account rather than inventing motivation for
// the founders.
export default function MissionStatement() {
  const { ref, revealed } = useScrollReveal<HTMLElement>();

  return (
    <section ref={ref} className="bg-bg-brand border-b border-border-brand py-20 md:py-28">
      <div className="max-w-[1280px] mx-auto px-6 md:px-12">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          <div
            className={cn(
              'space-y-6 transition-all duration-1000',
              revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
            )}
          >
            <span className="text-xs font-bold tracking-wider text-text-secondary uppercase">
              ● Our Purpose
            </span>

            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold leading-tight tracking-tight font-heading">
              We manage animal populations{' '}
              <span className="text-[#EF9F27]">humanely</span> — and public health
              improves with them.
            </h2>

            <p className="text-sm md:text-base text-text-secondary leading-relaxed">
              When Vets For Future began in 2000, culling was Sri Lanka&apos;s default
              answer to street dogs and rising rabies cases. Our founders, both
              practising veterinarians, rejected it and set out with mobile vet
              services instead — catching, sterilizing, vaccinating and releasing.
            </p>

            <p className="text-sm md:text-base text-text-secondary leading-relaxed">
              A quarter of a century later that approach is national policy, and
              Sri Lanka&apos;s annual human rabies deaths have fallen from more than
              sixty to between twenty and thirty.
            </p>
          </div>

          <div
            className={cn(
              'space-y-6 transition-all duration-1000 delay-200',
              revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
            )}
          >
            <div className="relative rounded-card overflow-hidden shadow-card">
              <Image
                src="/images/new2.jpg"
                alt="A street dog resting against a painted wall in Sri Lanka"
                width={4075}
                height={2717}
                className="w-full h-auto"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="rounded-card border border-border-brand bg-surface p-6 space-y-2 shadow-card">
                <span className="text-xs font-bold uppercase tracking-wider text-[#EF9F27]">
                  Mission
                </span>
                <p className="text-sm text-text-secondary leading-relaxed">
                  To promote humane animal population control programs that enhance
                  animal welfare and eradicate rabies in Sri Lanka.
                </p>
              </div>
              <div className="rounded-card border border-border-brand bg-surface p-6 space-y-2 shadow-card">
                <span className="text-xs font-bold uppercase tracking-wider text-[#EF9F27]">
                  Vision
                </span>
                <p className="text-sm text-text-secondary leading-relaxed">
                  A future where all animals are treated with respect and compassion,
                  living harmoniously within their communities.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
