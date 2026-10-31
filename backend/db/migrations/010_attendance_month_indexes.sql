-- 010_attendance_month_indexes.sql
--
-- Indexes for the monthly attendance grid (attendance rework, step 3).
--
-- The grid adds no tables: every day's status is derived on request from
-- attendance_log, the schedules and holidays (008) and leave_request_days
-- (009). It reads a whole month of each, so these keep that query fast as
-- the history grows.
--
-- APPLY in the Supabase SQL editor. Safe to re-run; changes no data.

CREATE INDEX IF NOT EXISTS idx_attendance_log_target_date
    ON attendance_log (target_date);

CREATE INDEX IF NOT EXISTS idx_attendance_log_employee_date
    ON attendance_log (employee_id, target_date);

CREATE INDEX IF NOT EXISTS idx_leave_request_days_date
    ON leave_request_days (leave_date);

NOTIFY pgrst, 'reload schema';
