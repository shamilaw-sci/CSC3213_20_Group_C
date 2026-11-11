-- 024_attendance_one_per_day.sql
--
-- One attendance record per employee per day.
--
-- Clock-in and HR's "record times" both check for an existing record and
-- then insert, so two requests arriving together (a double click) could
-- both pass the check. The month grid keeps one record per employee-day and
-- would silently ignore the other. The API now answers a violation of this
-- index as "already clocked in" / "a log already exists".
--
-- Replaces idx_attendance_log_employee_date (010), which indexed the same
-- columns without enforcing anything.
--
-- APPLY in the Supabase SQL editor. Safe to re-run. If it fails with a
-- duplicate key error, list the duplicates with
--
--   SELECT employee_id, target_date, array_agg(id ORDER BY id)
--   FROM attendance_log GROUP BY 1, 2 HAVING count(*) > 1;
--
-- and delete or merge the extra rows first.

CREATE UNIQUE INDEX IF NOT EXISTS uq_attendance_log_employee_date
    ON attendance_log (employee_id, target_date);

DROP INDEX IF EXISTS idx_attendance_log_employee_date;
