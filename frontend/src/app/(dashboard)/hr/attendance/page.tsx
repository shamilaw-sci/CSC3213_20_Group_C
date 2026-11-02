'use client';

import { useState } from 'react';
import { useAttendance, useLockAttendance, useExportAttendance, useUnlockAttendance } from '@/hooks/useHR';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { format } from 'date-fns';
import { Lock, LockOpen, AlertCircle, Clock, Search, Download } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';
import {Dialog,DialogContent,DialogDescription,DialogHeader,DialogTitle,DialogTrigger,DialogFooter,DialogClose,} from "@/components/ui/dialog";
import ProtectedRoute from '@/components/layout/protected-route';
import { MonthGrid } from '@/components/hr/attendance/MonthGrid';
import { useAuthStore } from '@/store/useAuthStore';
import { hasPermission } from '@/lib/permissions';
import { cn } from '@/lib/utils';

export default function HRAttendancePage() {
  return (
    // HR manages; Director reads the month without editing.
    <ProtectedRoute requiredPermission={['hr:attendance:manage', 'hr:attendance:read']}>
      <Attendance />
    </ProtectedRoute>
  );
}

function Attendance() {
  const { user } = useAuthStore();
  const canManage = hasPermission(user?.role as string, 'hr:attendance:manage');
  // HR Officer and Admin set when tracking starts; the Director sees it.
  const canChangeTracking = hasPermission(user?.role as string, 'hr:manage');
  const [tab, setTab] = useState<'month' | 'day'>('month');

  return (
    <div className="space-y-6 pb-12">
      <div>
        <h1 className="text-3xl font-bold font-heading tracking-tight mb-2 text-text-primary">Attendance</h1>
        <p className="text-text-secondary text-sm">
          Each day judged against the person&apos;s schedule, holidays and leave.
          {!canManage && ' Read-only.'}
        </p>
      </div>
      {canManage && (
        <div className="flex w-fit gap-1 rounded-lg border border-border-brand bg-bg-subtle p-1" role="tablist">
          {([['month', 'Month'], ['day', 'Day']] as const).map(([value, label]) => (
            <button key={value} role="tab" aria-selected={tab === value} onClick={() => setTab(value)}
              className={cn('rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
                tab === value ? 'bg-surface text-accent shadow-xs' : 'text-text-secondary hover:text-text-primary')}>
              {label}
            </button>
          ))}
        </div>
      )}
      {tab === 'month' || !canManage ? <MonthGrid canEdit={canManage} canChangeTracking={canChangeTracking} /> : <DayView />}
    </div>
  );
}

// One day at a time: lock the day, unlock a record, export. HR only.
function DayView() {
  const [targetDate, setTargetDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [filterIncomplete, setFilterIncomplete] = useState(false);

  const { data: attendanceLogs, isLoading } = useAttendance(targetDate);
  const { mutate: lockDay, isPending: isLocking } = useLockAttendance();
  const { mutateAsync: exportAttendance, isPending: isExporting } = useExportAttendance();
  const { mutate: unlock, isPending: isUnlocking, variables: unlockingId } = useUnlockAttendance();

  const handleLockDay = () => {
    lockDay(targetDate);
  };

  const handleExport = async () => {
    try {
      const blob = await exportAttendance(targetDate);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `attendance_${targetDate}.csv`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch {
      // error toast already handled by the hook's onError
    }
  };

  // Incomplete = no clock-out yet. Those are never locked by Lock Day (the
  // server skips them), so they stay correctable. Records locked blank under
  // the old rules can be unlocked and fixed.
  const isComplete = (log: { clock_in: string | null; clock_out: string | null }) => !!log.clock_in && !!log.clock_out;

  const filteredLogs = attendanceLogs?.filter(log => (filterIncomplete ? !isComplete(log) : true));

  const logs = attendanceLogs ?? [];
  const totalIncomplete = logs.filter(log => !isComplete(log)).length;
  const readyToLock = logs.filter(log => isComplete(log) && !log.is_locked).length;
  const totalLocked = logs.filter(log => log.is_locked).length;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <p className="text-sm text-text-secondary">Lock a day once its records are complete; unlock one to correct it.</p>

        <div className="flex items-center gap-3">
          <Input
            type="date"
            value={targetDate}
            onChange={(e) => setTargetDate(e.target.value)}
            className="w-40 bg-surface border-border-brand"
            max={format(new Date(), 'yyyy-MM-dd')}
          />
          <Button
            variant="outline"
            onClick={() => setFilterIncomplete(!filterIncomplete)}
            className={filterIncomplete ? 'bg-amber-500/10 text-amber-500 border-amber-500/30' : ''}
          >
            {filterIncomplete ? 'Show All' : 'Show Incomplete'}
          </Button>

          <Button
            variant="outline"
            onClick={handleExport}
            disabled={!attendanceLogs?.length || isExporting}
          >
            <Download className="w-4 h-4 mr-2" />
            {isExporting ? 'Exporting...' : 'Export'}
          </Button>

          <Dialog>
            <DialogTrigger render={
              <Button
                disabled={readyToLock === 0 || isLocking}
                className="bg-accent text-bg-brand hover:bg-accent/90"
              />
            }>
              <Lock className="w-4 h-4 mr-2" />
              {readyToLock === 0 && totalLocked > 0 && totalIncomplete === 0 ? 'Day Locked' : 'Lock Day'}
            </DialogTrigger>
            <DialogContent className="sm:max-w-[425px] bg-bg-brand text-text-primary border-border-brand">
              <DialogHeader>
                <DialogTitle>Lock Attendance for {targetDate}</DialogTitle>
                <DialogDescription className="text-text-secondary">
                  Locks the {readyToLock} complete record{readyToLock === 1 ? '' : 's'} so they can&apos;t be edited.
                  {totalIncomplete > 0 && ` ${totalIncomplete} without a clock-out will stay open until completed.`}
                  {' '}A locked record can be unlocked for correction until that month&apos;s payroll is approved.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter className="mt-4">
                <DialogClose render={<Button variant="outline" />}>
                  Cancel
                </DialogClose>
                <DialogClose render={
                  <Button
                    onClick={handleLockDay}
                    className="bg-accent text-bg-brand hover:bg-accent/90"
                  />
                }>
                  Confirm Lock
                </DialogClose>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      <div className="grid md:grid-cols-4 gap-4">
        <Card className="bg-surface border-border-brand">
          <CardContent className="p-4 flex flex-col items-center justify-center text-center space-y-1">
            <p className="text-sm font-medium text-text-secondary">Total Clocked In</p>
            <p className="text-2xl font-bold font-heading">{logs.length}</p>
          </CardContent>
        </Card>
        <Card className="bg-surface border-border-brand">
          <CardContent className="p-4 flex flex-col items-center justify-center text-center space-y-1">
            <p className="text-sm font-medium text-text-secondary">Ready to Lock</p>
            <p className="text-2xl font-bold font-heading text-amber-500">{readyToLock}</p>
          </CardContent>
        </Card>
        <Card className="bg-surface border-border-brand">
          <CardContent className="p-4 flex flex-col items-center justify-center text-center space-y-1">
            <p className="text-sm font-medium text-text-secondary">Locked</p>
            <p className="text-2xl font-bold font-heading text-emerald-500">{totalLocked}</p>
          </CardContent>
        </Card>
        <Card className="bg-surface border-border-brand">
          <CardContent className="p-4 flex flex-col items-center justify-center text-center space-y-1">
            <p className="text-sm font-medium text-text-secondary">No Clock-out</p>
            <p className="text-2xl font-bold font-heading text-rose-500">
              {totalIncomplete}
            </p>
          </CardContent>
        </Card>
      </div>

      <Card className="border-border-brand bg-surface">
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4 space-y-4">
              {[1, 2, 3, 4].map(i => <Skeleton key={i} className="w-full h-12" />)}
            </div>
          ) : filteredLogs && filteredLogs.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-text-secondary uppercase bg-bg-subtle/50">
                  <tr>
                    <th className="px-6 py-4">Employee</th>
                    <th className="px-6 py-4">Clock In</th>
                    <th className="px-6 py-4">Clock Out</th>
                    <th className="px-6 py-4">Hours</th>
                    <th className="px-6 py-4 text-right">Status</th>
                    <th className="px-6 py-4"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-brand">
                  {filteredLogs.map((log) => (
                    <tr key={log.id} className="hover:bg-bg-subtle/50 transition-colors">
                      <td className="px-6 py-4 font-medium">
                        {log.employee_profile?.first_name} {log.employee_profile?.last_name}
                      </td>
                      <td className="px-6 py-4 text-text-secondary">
                        {log.clock_in ? format(new Date(log.clock_in), 'HH:mm') : '-'}
                      </td>
                      <td className="px-6 py-4 text-text-secondary">
                        {log.clock_out ? format(new Date(log.clock_out), 'HH:mm') : '-'}
                      </td>
                      <td className="px-6 py-4 text-text-secondary">
                        {log.worked_hours ? `${log.worked_hours}h` : '-'}
                      </td>
                      <td className="px-6 py-4 flex justify-end">
                        {!isComplete(log) ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-rose-500/10 text-rose-500">
                            <AlertCircle className="w-3.5 h-3.5" /> {log.is_locked ? 'Locked, no clock-out' : 'No clock-out'}
                          </span>
                        ) : log.is_locked ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-500">
                            <Lock className="w-3.5 h-3.5" /> Locked
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-500/10 text-amber-500">
                            <Clock className="w-3.5 h-3.5" /> Ready to lock
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4 text-right">
                        {log.is_locked && (
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={isUnlocking}
                            onClick={() => unlock(log.id)}
                            title="Reopen this record for correction"
                            className="h-7 gap-1 px-2 text-xs text-text-secondary hover:text-text-primary"
                          >
                            <LockOpen className="h-3.5 w-3.5" />
                            {isUnlocking && unlockingId === log.id ? 'Unlocking…' : 'Unlock'}
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-12">
              <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-bg-subtle mb-4">
                <Search className="w-6 h-6 text-text-secondary" />
              </div>
              <p className="text-text-primary font-medium">No records found</p>
              <p className="text-text-secondary text-sm mt-1">
                {filterIncomplete ? 'Every record for this date has a clock-out.' : 'No attendance logs for this date.'}
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}