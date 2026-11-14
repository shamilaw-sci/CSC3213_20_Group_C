import { CalendarCheck, Clock, PawPrint, Receipt } from 'lucide-react';
import type { AppNotification } from '@/services/notifications.service';

export const KIND_ICON: Record<AppNotification['kind'], typeof Clock> = {
  leave_decided: CalendarCheck,
  correction_decided: Clock,
  case_assigned: PawPrint,
  payslip_ready: Receipt,
};

/** "Just now", "5m ago", "3h ago", "2d ago", then the date. */
export function timeAgo(iso: string): string {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (!Number.isFinite(mins)) return '';
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString('en-LK', { day: 'numeric', month: 'short', year: 'numeric' });
}
