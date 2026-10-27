'use client';

import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { createPingScheduler, PingScheduler } from '@/lib/board-live';
import { getRealtimeClient } from '@/lib/supabase-browser';
import { useAuthStore } from '@/store/useAuthStore';

// Must match BOARD_TOPIC / BOARD_EVENT in backend/app/services/board_events.py
// and the topic in db/migrations/006_realtime_board_channel.sql.
const BOARD_TOPIC = 'rescue-board';
const BOARD_EVENT = 'cases_changed';

/**
 * Refetch the case queries when the backend pings that a case changed.
 *
 * The ping is only a trigger. Data still comes from GET /rescue_cases/cases,
 * so rescue:read is enforced exactly as before; a dropped socket costs
 * freshness, never access. The board's own refetchInterval covers that case.
 *
 * Private channel: joining sends the user's Supabase access token, and the
 * realtime.messages policy admits `authenticated` only.
 *
 * Returns the scheduler so the board can mark itself busy and drop a held ping
 * when it is about to refetch on its own.
 */
export function useRescueBoardLive(busy: boolean): PingScheduler {
  const queryClient = useQueryClient();
  const token = useAuthStore((s) => s.token);

  // Prefix, so the map and home-page activity queries are marked stale too.
  const [scheduler] = useState(() =>
    createPingScheduler(() => queryClient.invalidateQueries({ queryKey: ['rescueCases'] }))
  );

  useEffect(() => {
    scheduler.setBusy(busy);
  }, [scheduler, busy]);

  useEffect(() => () => scheduler.dispose(), [scheduler]);

  useEffect(() => {
    const supabase = getRealtimeClient();
    if (!supabase || !token) return;

    let cancelled = false;
    let dropped = false;
    let channel: ReturnType<typeof supabase.channel> | null = null;

    supabase.realtime.setAuth(token).then(() => {
      if (cancelled) return;
      channel = supabase
        .channel(BOARD_TOPIC, { config: { private: true } })
        .on('broadcast', { event: BOARD_EVENT }, () => scheduler.ping())
        .subscribe((status, err) => {
          if (status === 'SUBSCRIBED') {
            // Pings sent while the socket was down are gone; one refetch on
            // rejoin covers whatever they would have said.
            if (dropped) scheduler.ping();
            dropped = false;
          } else {
            dropped = true;
            if (status === 'CHANNEL_ERROR') {
              console.warn('rescue board: live updates unavailable, polling instead', err?.message);
            }
          }
        });
    });

    return () => {
      cancelled = true;
      if (channel) supabase.removeChannel(channel);
    };
  }, [scheduler, token]);

  return scheduler;
}
