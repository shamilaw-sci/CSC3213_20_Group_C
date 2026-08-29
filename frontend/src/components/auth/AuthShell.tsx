'use client';

import Link from 'next/link';
import Image from 'next/image';
import { ArrowLeft } from 'lucide-react';

// All four auth pages (login, register, and their admin variants) previously
// carried their own copy of a two-pane layout with a hotlinked stock photo.
// They are the same screen with different fields, so the chrome lives here
// once and each page supplies only its heading and form.
export default function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div className="relative min-h-screen bg-bg-brand text-text-primary font-sans selection:bg-[#EF9F27]/30 flex flex-col">
      {/* Decorative only — the illustration is knocked back to a few percent
          opacity and sat under a scrim in the theme's own background colour,
          so it reads as faint texture rather than artwork competing with the
          form. The scrim is tinted rather than hard-coded black so this still
          works in light mode. */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
        {/* The two themes need different strengths. The illustration is pale,
            so on the dark background it registers by lightening and a little
            goes a long way; on white only its dark linework shows at all, and
            it needs roughly three times the opacity to be visible. */}
        <Image
          src="/images/login.jpg"
          alt=""
          fill
          sizes="100vw"
          className="object-cover opacity-[0.42] dark:opacity-[0.15]"
        />
        {/* Flat knock-back, then a vignette that fades the centre out so the
            card sits on clean background while the texture survives at the
            edges. Both use the theme's own background token. The ellipse is
            kept tight to the card so it doesn't leave a bright halo. */}
        <div className="absolute inset-0 bg-bg-brand/25 dark:bg-bg-brand/50" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_42%_42%_at_50%_50%,var(--color-bg)_8%,transparent_100%)]" />
      </div>

      <div className="relative z-10 p-6">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-xs font-bold text-text-secondary hover:text-text-primary transition-colors"
        >
          <ArrowLeft size={14} />
          Back to website
        </Link>
      </div>

      <div className="relative z-10 flex-grow flex flex-col items-center justify-center px-6 pb-12">
        <Link href="/" className="mb-6 hover:opacity-90 transition-opacity">
          <Image
            src="/images/vff-logo.png"
            alt="Vets For Future"
            width={56}
            height={56}
            priority
            className="h-12 w-12 object-contain"
          />
        </Link>

        {/* Surface-on-background rather than a hard-coded dark panel, so the
            card still reads as raised in light mode, where the two tokens are
            both white and only the border and shadow separate them. */}
        <div className="w-full max-w-md rounded-2xl border border-border-brand bg-surface shadow-xl p-8">
          <h1 className="text-2xl font-bold font-heading tracking-tight text-text-primary">
            {title}
          </h1>
          <div className="text-xs text-text-secondary mt-1.5">{subtitle}</div>

          <div className="mt-7">{children}</div>
        </div>

        {footer && <div className="w-full max-w-md mt-5">{footer}</div>}
      </div>

      <p className="relative z-10 pb-8 text-[10px] text-text-secondary/45 text-center">
        Internal use only by VFF. Proprietary and Confidential.
      </p>
    </div>
  );
}
