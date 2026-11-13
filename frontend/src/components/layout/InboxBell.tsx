'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, Bell, CheckCircle2, ChevronRight, CircleDot, Loader2 } from 'lucide-react';
import { InboxService } from '@/services/inbox.service';
import type { AppNotification } from '@/services/notifications.service';
import { useMarkAllNotificationsRead, useMarkNotificationRead, useNotifications } from '@/hooks/useNotifications';
import { useAuthStore } from '@/store/useAuthStore';
import { cn } from '@/lib/utils';
import { KIND_ICON, timeAgo } from './notification-kinds';

// How many updates the bell shows; the rest are in Settings.
const UPDATES_SHOWN = 5;

/**
 * The top-bar bell, in two parts:
 *   Needs your action: work waiting on you, per queue, worked out live
 *     (app/api/inbox.py); an item goes when its work is done.
 *   Updates: decisions about you (migration 032), with read state.
 * The badge counts both: everything waiting plus every unread update.
 */
export function InboxBell() {
  const router = useRouter();
  const { isAuthenticated, user } = useAuthStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const inbox = useQuery({
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
  const updates = useNotifications(UPDATES_SHOWN, { poll: true });
  const { mutate: markRead } = useMarkNotificationRead();
  const { mutate: markAllRead, isPending: markingAll } = useMarkAllNotificationsRead();

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const waiting = inbox.data?.total ?? 0;
  const unread = updates.data?.unread ?? 0;
  const total = waiting + unread;
  const loaded = inbox.data || updates.data;
  const label = !loaded ? 'Inbox' : total > 0 ? `Inbox, ${total} waiting or unread` : 'Inbox, nothing new';

  const go = (href: string) => { setOpen(false); router.push(href); };
  const openUpdate = (n: AppNotification) => {
    if (!n.read_at) markRead(n.id);
    if (n.href) go(n.href);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => {
          // Opening shows the latest, not up to a minute old.
          if (!open) { inbox.refetch(); updates.refetch(); }
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
        <div className="absolute right-0 mt-2 w-80 max-h-[70vh] overflow-y-auto bg-surface border border-border-brand rounded-xl shadow-xl animate-in fade-in duration-100">
          <div className="px-4 py-2 border-b border-border-brand">
            <span className="text-xs font-semibold text-text-primary">Needs your action</span>
          </div>

          {inbox.isLoading ? (
            <p className="flex items-center gap-2 p-4 text-xs text-text-secondary">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Checking…
            </p>
          ) : inbox.isError || !inbox.data ? (
            <p className="p-4 text-xs text-negative">Couldn&apos;t load your inbox. Try again in a moment.</p>
          ) : inbox.data.items.length === 0 ? (
            <p className="flex items-center gap-2 p-4 text-xs text-text-secondary">
              <CheckCircle2 className="h-4 w-4 text-positive" /> You&apos;re all caught up.
            </p>
          ) : (
            <ul className="divide-y divide-border-brand">
              {inbox.data.items.map((item) => {
                const Icon = item.tone === 'alert' ? AlertTriangle : CircleDot;
                return (
                  <li key={item.key}>
                    <button onClick={() => go(item.href)}
                      className="flex w-full items-center gap-3 p-3 text-left hover:bg-bg-subtle">
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

          <div className="flex items-center justify-between px-4 py-2 border-y border-border-brand">
            <span className="text-xs font-semibold text-text-primary">Updates</span>
            {unread > 0 && (
              <button onClick={() => markAllRead()} disabled={markingAll}
                className="text-[11px] font-medium text-accent hover:underline disabled:opacity-50">
                Mark all read
              </button>
            )}
          </div>

          {updates.isLoading ? (
            <p className="flex items-center gap-2 p-4 text-xs text-text-secondary">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading…
            </p>
          ) : updates.isError || !updates.data ? (
            <p className="p-4 text-xs text-negative">Couldn&apos;t load your updates.</p>
          ) : updates.data.items.length === 0 ? (
            <p className="p-4 text-xs text-text-secondary">No updates yet.</p>
          ) : (
            <ul className="divide-y divide-border-brand">
              {updates.data.items.map((n) => {
                const Icon = KIND_ICON[n.kind];
                return (
                  <li key={n.id}>
                    <button onClick={() => openUpdate(n)}
                      className={cn('flex w-full items-start gap-3 p-3 text-left hover:bg-bg-subtle', !n.read_at && 'bg-accent/5')}>
                      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-text-secondary" aria-hidden="true" />
                      <span className="min-w-0 flex-1">
                        <span className={cn('block text-xs', n.read_at ? 'text-text-secondary' : 'font-semibold text-text-primary')}>
                          {n.title}
                        </span>
                        {n.body && <span className="mt-0.5 block text-[11px] text-text-secondary line-clamp-2">{n.body}</span>}
                        <span className="mt-0.5 block text-[10px] text-text-muted">{timeAgo(n.created_at)}</span>
                      </span>
                      {!n.read_at && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-accent" aria-label="Unread" />}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

          <div className="p-2 border-t border-border-brand text-center">
            <button onClick={() => go('/settings')} className="text-[11px] font-medium text-accent hover:underline">
              See all updates
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
