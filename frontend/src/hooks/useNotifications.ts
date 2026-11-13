import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { NotificationsService } from '@/services/notifications.service';
import { useAuthStore } from '@/store/useAuthStore';

// Keyed per user, like the inbox: the query cache outlives a sign-out.
function useKey(limit: number) {
  const { user } = useAuthStore();
  return { key: ['notifications', user?.id, limit], userId: user?.id };
}

export function useNotifications(limit = 50, options: { poll?: boolean } = {}) {
  const { isAuthenticated } = useAuthStore();
  const { key, userId } = useKey(limit);
  return useQuery({
    queryKey: key,
    queryFn: () => NotificationsService.list(limit),
    enabled: isAuthenticated && !!userId,
    // Decisions happen elsewhere, by other people: the bell polls gently.
    refetchInterval: options.poll ? 60_000 : false,
    refetchOnWindowFocus: 'always',
  });
}

function useInvalidate() {
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  return () => queryClient.invalidateQueries({ queryKey: ['notifications', user?.id] });
}

export function useMarkNotificationRead() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: NotificationsService.markRead, onSuccess: invalidate });
}

export function useMarkAllNotificationsRead() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: NotificationsService.markAllRead, onSuccess: invalidate });
}
