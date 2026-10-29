'use client';

import { useState } from 'react';
import { CalendarDays, Clock } from 'lucide-react';
import ProtectedRoute from '@/components/layout/protected-route';
import { SchedulesTab } from '@/components/hr/calendar/SchedulesTab';
import { HolidaysTab } from '@/components/hr/calendar/HolidaysTab';
import { useAuthStore } from '@/store/useAuthStore';
import { hasPermission } from '@/lib/permissions';
import { cn } from '@/lib/utils';

export default function SchedulesPage() {
  return (
    // Attendance managers can look; only hr:manage can change.
    <ProtectedRoute requiredPermission={['hr:manage', 'hr:attendance:manage']}>
      <WorkCalendar />
    </ProtectedRoute>
  );
}

function WorkCalendar() {
  const { user } = useAuthStore();
  const canEdit = hasPermission(user?.role as string, 'hr:manage');
  const [tab, setTab] = useState<'schedules' | 'holidays'>('schedules');

  return (
    <div className="space-y-6 pb-12">
      <div>
        <h1 className="text-3xl font-bold font-heading tracking-tight mb-2 text-text-primary">Schedules & Holidays</h1>
        <p className="text-text-secondary text-sm">
          When each person is meant to work, and which days are off. Attendance is judged against these.
        </p>
      </div>

      <div className="flex gap-1 rounded-lg border border-border-brand bg-bg-subtle p-1 w-fit" role="tablist">
        {([['schedules', 'Schedules', Clock], ['holidays', 'Holidays', CalendarDays]] as const).map(([value, label, Icon]) => (
          <button
            key={value}
            role="tab"
            aria-selected={tab === value}
            onClick={() => setTab(value)}
            className={cn(
              'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
              tab === value ? 'bg-surface text-accent shadow-xs' : 'text-text-secondary hover:text-text-primary',
            )}
          >
            <Icon className="h-3.5 w-3.5" /> {label}
          </button>
        ))}
      </div>

      {tab === 'schedules' ? <SchedulesTab canEdit={canEdit} /> : <HolidaysTab canEdit={canEdit} />}
    </div>
  );
}
