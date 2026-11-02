-- 012_attendance_tracking_start.sql
--
-- When attendance tracking began.
--
-- BEFORE. The monthly grid (step 3) judged every working day since each
-- person joined. Nobody clocked in before the attendance rework went live,
-- so months of history showed as one long run of "Absent", the
-- needs-attention list was unusable, and the payroll close (step 5) would
-- have turned all of it into unpaid days.
--
-- AFTER. One organisation-wide date, set by HR (hr:manage), from which
-- attendance counts. Each employee may override it in either direction (a
-- vet who clocked in properly from earlier, a branch that started later).
-- A person's tracked-from date is their override if set, otherwise the
-- organisation's. Days before it show as "Not tracked": not counted in the
-- month's totals, never in needs-attention, and never sent to payroll.
-- Month close refuses a month in which nobody is tracked.
--
-- Moving a date earlier brings days into tracking, which can turn them into
-- absences. The API allows it after showing the impact, but refuses when any
-- of those days falls in a month whose payroll is already Approved: once a
-- month is paid, its attendance cannot become absences.
--
-- Policy confirmed with the project owner on 2026-11-02.
--
-- The organisation row is seeded with today's date in Sri Lanka, so the
-- moment this is applied the backlog stops showing as absences. HR then sets
-- the real start date from the attendance page.
--
-- APPLY in the Supabase SQL editor. Safe to re-run; re-running keeps any
-- date HR has already set.

-- ---------------------------------------------------------------------------
-- 1. The organisation setting: exactly one row
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS attendance_settings (
    id                  SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    tracking_start_date DATE NOT NULL,
    updated_by          UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

INSERT INTO attendance_settings (id, tracking_start_date)
VALUES (1, (now() AT TIME ZONE 'Asia/Colombo')::date)
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. Per-employee override (NULL: follows the organisation date)
-- ---------------------------------------------------------------------------

ALTER TABLE employee_profile
    ADD COLUMN IF NOT EXISTS attendance_tracked_from DATE;

-- ---------------------------------------------------------------------------
-- 3. Row level security, as in 003_rls_lockdown.sql
-- ---------------------------------------------------------------------------

ALTER TABLE public.attendance_settings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS attendance_settings_authenticated_all ON public.attendance_settings;
CREATE POLICY attendance_settings_authenticated_all ON public.attendance_settings
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

NOTIFY pgrst, 'reload schema';
