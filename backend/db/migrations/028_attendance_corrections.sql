-- 028_attendance_corrections.sql
--
-- Attendance correction requests (attendance rework, step 4; policy
-- confirmed 2026-10-29 and 2026-11-12).
--
-- Staff ask for a past day's clock-in and/or clock-out to be corrected, with
-- a reason; HR (hr:attendance:manage) approves or rejects. Approving writes
-- the times to attendance_log, creating the record if the day had none; a
-- locked record stays locked, approval being HR's review. Nobody decides
-- their own request, and days frozen by an approved payroll are refused when
-- requesting and when deciding (app/api/hr.py).
--
-- The original times are kept with the request, so HR sees what would change
-- and the history shows what did.
--
-- APPLY in the Supabase SQL editor. Safe to re-run.

CREATE TABLE IF NOT EXISTS attendance_correction_requests (
    id                  SERIAL PRIMARY KEY,
    employee_id         INTEGER NOT NULL REFERENCES employee_profile(id) ON DELETE CASCADE,
    target_date         DATE NOT NULL,
    -- NULL: leave that end as it is.
    requested_clock_in  TIMESTAMP WITH TIME ZONE,
    requested_clock_out TIMESTAMP WITH TIME ZONE,
    original_clock_in   TIMESTAMP WITH TIME ZONE,
    original_clock_out  TIMESTAMP WITH TIME ZONE,
    reason              VARCHAR(500) NOT NULL CHECK (length(trim(reason)) > 0),
    status              VARCHAR(20) NOT NULL DEFAULT 'Pending'
                        CHECK (status IN ('Pending', 'Approved', 'Rejected', 'Cancelled')),
    requested_by        UUID REFERENCES users(id) ON DELETE SET NULL,
    requested_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    decided_by          UUID REFERENCES users(id) ON DELETE SET NULL,
    decided_at          TIMESTAMP WITH TIME ZONE,
    decision_note       VARCHAR(500),
    -- The record changed or created when approved.
    attendance_log_id   INTEGER REFERENCES attendance_log(id) ON DELETE SET NULL,
    CHECK (requested_clock_in IS NOT NULL OR requested_clock_out IS NOT NULL)
);

-- One open request per person per day.
CREATE UNIQUE INDEX IF NOT EXISTS uq_attendance_corrections_pending
    ON attendance_correction_requests (employee_id, target_date)
    WHERE status = 'Pending';

CREATE INDEX IF NOT EXISTS idx_attendance_corrections_status
    ON attendance_correction_requests (status, target_date);

-- Same shape as 003_rls_lockdown.sql: permission checks live in FastAPI.
ALTER TABLE public.attendance_correction_requests ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS attendance_corrections_authenticated_all ON public.attendance_correction_requests;
CREATE POLICY attendance_corrections_authenticated_all ON public.attendance_correction_requests
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

NOTIFY pgrst, 'reload schema';
