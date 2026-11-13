'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, Bell, CheckCircle2, ChevronRight, CircleDot, Loader2 } from 'lucide-react';
import { InboxService } from '@/services/inbox.service';
import { useAuthStore } from '@/store/useAuthStore';
import { cn } from '@/lib/utils';

/**
 * The top-bar bell: what is waiting on you, per queue, each linking to the
 * page where it is handled. Live from the backend, so nothing is marked read;
 * an item goes when its work is done.
 */
export function InboxBell() {
  const router = useRouter();
  const { isAuthenticated, user } = useAuthStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const { data, isLoading, isError, refetch } = useQuery({
    // Per user: the query cache outlives a sign-out, and one person's
    // count must never show on the next person's bell.
    queryKey: ['inbox', user?.id],
    queryFn: InboxService.get,
    enabled: isAuthenticated && !!user?.id,
    // Decisions are made on other pages (and by other people), so poll gently
    // and refresh whenever the tab comes back.
    refetchInterval: 60_000,
    refetchOnWindowFocus: 'always',
  });

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const total = data?.total ?? 0;
  const label = !data ? 'Inbox' : total > 0 ? `Inbox, ${total} waiting` : 'Inbox, nothing waiting';

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => {
          // Opening shows the latest, not up to a minute old.
          if (!open) refetch();
          setOpen(!open);
        }}
        aria-label={label}
        aria-expanded={open}
        className="relative p-1.5 text-text-secondary hover:text-text-primary rounded-lg hover:bg-bg-subtle transition-colors"
      >
        <Bell className="w-5 h-5" />
        {total > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-accent text-white text-[10px] font-bold leading-[18px] text-center">
            {total > 99 ? '99+' : total}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 bg-surface border border-border-brand rounded-xl shadow-xl overflow-hidden animate-in fade-in duration-100">
          <div className="px-4 py-2 border-b border-border-brand">
            <span className="text-xs font-semibold text-text-primary">Needs your action</span>
          </div>

          {isLoading ? (
            <p className="flex items-center gap-2 p-4 text-xs text-text-secondary">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Checking…
            </p>
          ) : isError || !data ? (
            <p className="p-4 text-xs text-negative">Couldn&apos;t load your inbox. Try again in a moment.</p>
          ) : data.items.length === 0 ? (
            <p className="flex items-center gap-2 p-4 text-xs text-text-secondary">
              <CheckCircle2 className="h-4 w-4 text-positive" /> You&apos;re all caught up.
            </p>
          ) : (
            <ul className="divide-y divide-border-brand">
              {data.items.map((item) => {
                const Icon = item.tone === 'alert' ? AlertTriangle : CircleDot;
                return (
                  <li key={item.key}>
                    <button
                      onClick={() => { setOpen(false); router.push(item.href); }}
                      className="flex w-full items-center gap-3 p-3 text-left hover:bg-bg-subtle"
                    >
                      <Icon
                        className={cn('h-4 w-4 shrink-0', item.tone === 'alert' ? 'text-amber-500' : 'text-accent')}
                        aria-hidden="true"
                      />
                      <span className="flex-1 text-xs text-text-primary">{item.title}</span>
                      <ChevronRight className="h-3.5 w-3.5 shrink-0 text-text-muted" aria-hidden="true" />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
