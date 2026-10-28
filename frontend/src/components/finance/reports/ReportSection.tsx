'use client';

import { ReactNode } from 'react';
import { ArrowDownRight, ArrowUpRight, FileSpreadsheet, Minus } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { formatLKR } from '@/lib/formatters';
import { cn } from '@/lib/utils';

export function ReportSection({
  title,
  description,
  onExport,
  actions,
  children,
}: {
  title: string;
  description?: ReactNode;
  onExport?: () => void;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card className="bg-surface border border-border-brand rounded-card shadow-card p-5">
      <CardHeader className="flex flex-row items-start justify-between gap-4 p-0 pb-4">
        <div className="min-w-0">
          <CardTitle className="text-base font-semibold font-heading text-text-primary">{title}</CardTitle>
          {description && (
            <CardDescription className="text-text-secondary text-xs mt-1 leading-relaxed">
              {description}
            </CardDescription>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {actions}
          {onExport && (
            <Button
              variant="outline"
              size="sm"
              onClick={onExport}
              className="border-border-brand text-text-secondary hover:text-text-primary text-xs h-8 gap-1.5"
            >
              <FileSpreadsheet className="h-3.5 w-3.5" /> CSV
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="p-0">{children}</CardContent>
    </Card>
  );
}

// A money cell for report tables: right-aligned, tabular figures so columns
// line up, and negative values marked by colour and by their minus sign.
export function Money({ value, strong = false }: { value: number; strong?: boolean }) {
  return (
    <span
      className={cn(
        'font-mono tabular-nums whitespace-nowrap',
        value < 0 ? 'text-negative' : 'text-text-primary',
        strong && 'font-semibold',
      )}
    >
      {formatLKR(value)}
    </span>
  );
}

// Change against the previous period. The arrow carries the direction and
// the colour carries whether that direction is good for this figure: income
// up is good, expenditure up is not. Never colour alone.
export function Delta({
  pct,
  upIsGood,
  label,
}: {
  pct: number | null;
  upIsGood: boolean;
  label: string;
}) {
  if (pct === null) {
    return <span className="text-xs text-text-muted">No {label} to compare</span>;
  }
  if (pct === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-text-secondary">
        <Minus className="h-3.5 w-3.5" /> No change vs {label}
      </span>
    );
  }
  const up = pct > 0;
  const good = up === upIsGood;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <span className="inline-flex items-center gap-1 text-xs">
      <span className={cn('inline-flex items-center gap-0.5 font-semibold', good ? 'text-positive' : 'text-negative')}>
        <Icon className="h-3.5 w-3.5" />
        {up ? '+' : ''}{pct.toLocaleString('en-LK', { maximumFractionDigits: 1 })}%
      </span>
      <span className="text-text-secondary">vs {label}</span>
    </span>
  );
}

export const th = 'px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-text-secondary';
export const td = 'px-3 py-2.5 text-sm';
