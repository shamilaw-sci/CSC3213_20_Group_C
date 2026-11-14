import api from '@/lib/api-client';

// GET /inbox: the work waiting on the signed-in person, worked out live by the
// backend (app/api/inbox.py). Matches InboxItem / Inbox there.
export interface InboxItem {
  key: string;
  title: string;
  count: number;
  href: string;
  // action: a decision waiting on you. alert: something going wrong.
  tone: 'action' | 'alert';
}

export interface Inbox {
  items: InboxItem[];
  total: number;
}

export const InboxService = {
  get: async () => {
    const response = await api.get<Inbox>('/inbox');
    return response.data;
  },
};
