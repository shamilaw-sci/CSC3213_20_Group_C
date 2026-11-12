'use client';

import { useMyAttendance } from '@/hooks/useHR';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Clock, Lock, AlertCircle, CheckCircle2 } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';
import { MyScheduleCard } from '@/components/hr/calendar/MyScheduleCard';
import { MyMonth } from '@/components/hr/attendance/MyMonth';
import { MyCorrections } from '@/components/hr/attendance/Corrections';
import { TodayClockCard } from '@/components/hr/attendance/TodayClockCard';
import { colomboDate, hhmm } from '@/components/hr/attendance/dayStatus';

export default function MyAttendancePage() {
  // Sri Lanka's date and times throughout, whatever the browser's zone.
  const todayStr = colomboDate();
  const [currentYear, currentMonth] = todayStr.split('-').map(Number);

  const { data: attendanceLogs, isLoading } = useMyAttendance(currentMonth, currentYear);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold font-heading text-text-primary">My Attendance</h1>
          <p className="text-text-secondary mt-1">Manage your daily clock-ins and view attendance history.</p>
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-6">
        <div className="md:col-span-1">
          <TodayClockCard title="Today's Status" />
        </div>

        <Card className="md:col-span-2 border-border-brand bg-surface">
          <CardHeader>
            <CardTitle>My Attendance This Month</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="space-y-4">
                {[1, 2, 3].map(i => <Skeleton key={i} className="w-full h-12" />)}
              </div>
            ) : attendanceLogs && attendanceLogs.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead className="text-xs text-text-secondary uppercase bg-bg-subtle/50">
                    <tr>
                      <th className="px-4 py-3 rounded-l-lg">Date</th>
                      <th className="px-4 py-3">Clock In</th>
                      <th className="px-4 py-3">Clock Out</th>
                      <th className="px-4 py-3">Hours</th>
                      <th className="px-4 py-3 rounded-r-lg">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {attendanceLogs.map((log) => (
                      <tr key={log.id} className="border-b border-border-brand last:border-0">
                        <td className="px-4 py-3 font-medium">{log.target_date}</td>
                        <td className="px-4 py-3 text-text-secondary">{log.clock_in ? hhmm(log.clock_in) : '-'}</td>
                        <td className="px-4 py-3 text-text-secondary">{log.clock_out ? hhmm(log.clock_out) : '-'}</td>
                        <td className="px-4 py-3 text-text-secondary">
                          {log.worked_hours ? `${log.worked_hours}h` : '-'}
                        </td>
                        <td className="px-4 py-3">
                          {log.clock_out ? (
                            log.is_locked ? (
                              <span className="flex items-center gap-1.5 text-emerald-500">
                                <Lock className="w-3.5 h-3.5" /> Locked
                              </span>
                            ) : (
                              <span className="flex items-center gap-1.5 text-emerald-500">
                                <CheckCircle2 className="w-3.5 h-3.5" /> Completed
                              </span>
                            )
                          ) : log.target_date === todayStr ? (
                            <span className="flex items-center gap-1.5 text-amber-500">
                              <Clock className="w-3.5 h-3.5" /> Active
                            </span>
                          ) : (
                            <span className="flex items-center gap-1.5 text-rose-500">
                              <AlertCircle className="w-3.5 h-3.5" /> No clock-out
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-center py-8 text-text-secondary">
                No attendance records found for this month.
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <MyMonth />

      <MyCorrections />

      <MyScheduleCard />
    </div>
  );
}
