'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { useEffect, useState } from 'react';
import { useAuthStore } from '@/store/useAuthStore';

export default function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000,
            retry: 1,
          },
        },
      })
  );

  // A new person, or nobody, starts with an empty cache. The client outlives
  // a sign-out, so without this the next person to sign in on this browser
  // briefly saw the last one's cached pages before they refetched.
  useEffect(() => {
    let current = useAuthStore.getState().user?.id;
    return useAuthStore.subscribe((state) => {
      const next = state.user?.id;
      if (next !== current) {
        queryClient.clear();
        current = next;
      }
    });
  }, [queryClient]);

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      {/* Off unless asked for: its floating button sat on top of the assistant
          button. It is left out of production builds either way. */}
      {process.env.NEXT_PUBLIC_QUERY_DEVTOOLS === 'true' && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  );
}
