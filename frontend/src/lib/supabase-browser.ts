import { createClient, SupabaseClient } from '@supabase/supabase-js';

// Realtime only. The frontend never queries Supabase tables directly — every
// read goes through FastAPI, which is where permissions are enforced.
//
// No session of its own: login is owned by the backend and the zustand auth
// store. Left to its defaults this client would persist and refresh a second
// copy of the session in localStorage, alongside the one the app actually uses.
//
// Null when the env vars are missing, so a misconfigured build degrades to the
// board's polling fallback rather than throwing.

let client: SupabaseClient | null | undefined;

export function getRealtimeClient(): SupabaseClient | null {
  if (client !== undefined) return client;

  // Literal references, not a lookup: Next only inlines NEXT_PUBLIC_ values it
  // can see statically at build time.
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  client = url && key
    ? createClient(url, key, {
        auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
      })
    : null;
  return client;
}
