'use client';

import { CalendarDays, Clock, MapPin, Info } from 'lucide-react';
import type { ProgramType, PublicProgram } from '@/types';
import { cn } from '@/lib/utils';

// One colour per type so a scan of the page shows what kind of help is where.
const TYPE_STYLE: Record<ProgramType, string> = {
  Sterilization: 'bg-[#EF9F27]/15 text-[#B86E0A] dark:text-[#EF9F27]',
  Vaccination: 'bg-sky-500/15 text-sky-700 dark:text-sky-400',
  'Free Clinic': 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400',
  Awareness: 'bg-violet-500/15 text-violet-700 dark:text-violet-400',
  Other: 'bg-zinc-500/15 text-text-secondary',
};

export function formatPublicDay(day?: string | null): string {
  if (!day) return '';
  const [y, m, d] = day.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-GB', {
    weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
  });
}

function localToday(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
}

/** "Happening now", "Starts Sat 22 Nov 2026", or "Starting soon" for an
 *  upcoming program whose planned date has passed but has not begun yet. */
export function whenLabel(p: PublicProgram): string {
  if (p.status === 'Active') {
    return p.start_date ? `Happening now · since ${formatPublicDay(p.start_date)}` : 'Happening now';
  }
  if (!p.start_date || p.start_date < localToday()) return 'Starting soon';
  return `Starts ${formatPublicDay(p.start_date)}`;
}

export function ClinicCard({ program, compact = false }: { program: PublicProgram; compact?: boolean }) {
  const type = program.program_type ?? 'Other';
  const active = program.status === 'Active';

  return (
    <article className="h-full rounded-card border border-border-brand bg-surface shadow-card p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <span className={cn('text-[11px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full', TYPE_STYLE[type])}>
          {type}
        </span>
        {active && (
          <span className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-positive">
            <span className="w-2 h-2 rounded-full bg-positive animate-pulse" aria-hidden="true" />
            Now on
          </span>
        )}
      </div>

      <h3 className="text-lg font-bold font-heading text-text-primary leading-snug">{program.program_name}</h3>

      <ul className="space-y-2 text-sm text-text-secondary">
        <li className="flex items-start gap-2">
          <MapPin size={16} className="mt-0.5 shrink-0 text-[#EF9F27]" aria-hidden="true" />
          <span>
            {program.public_venue && <span className="text-text-primary font-medium">{program.public_venue}, </span>}
            {program.location}
          </span>
        </li>
        <li className="flex items-start gap-2">
          <CalendarDays size={16} className="mt-0.5 shrink-0 text-[#EF9F27]" aria-hidden="true" />
          <span>{whenLabel(program)}</span>
        </li>
        {program.public_schedule && (
          <li className="flex items-start gap-2">
            <Clock size={16} className="mt-0.5 shrink-0 text-[#EF9F27]" aria-hidden="true" />
            <span>{program.public_schedule}</span>
          </li>
        )}
      </ul>

      {!compact && program.public_notes && (
        <p className="mt-auto flex items-start gap-2 rounded-xl bg-bg-subtle p-3 text-xs text-text-secondary leading-relaxed whitespace-pre-line">
          <Info size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
          {program.public_notes}
        </p>
      )}
    </article>
  );
}
