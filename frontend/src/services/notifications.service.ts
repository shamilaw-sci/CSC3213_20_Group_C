import api from '@/lib/api-client';

// The signed-in person's own updates (backend/app/api/notifications.py,
// migration 032). Matches Notification / NotificationList there.
export interface AppNotification {
  id: number;
  kind: 'leave_decided' | 'correction_decided' | 'case_assigned' | 'payslip_ready';
  title: string;
  body?: string | null;
  href?: string | null;
  created_at: string;
  read_at?: string | null;
}

export interface NotificationList {
  items: AppNotification[];
  unread: number;
}

export const NotificationsService = {
  list: async (limit = 50) => {
    const response = await api.get<NotificationList>('/notifications', { params: { limit } });
    return response.data;
  },
  markRead: async (id: number) => {
    const response = await api.post<AppNotification>(`/notifications/${id}/read`);
    return response.data;
  },
  markAllRead: async () => {
    const response = await api.post<{ marked: number }>('/notifications/read-all');
    return response.data;
  },
};
