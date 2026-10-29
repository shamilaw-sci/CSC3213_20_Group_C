-- 008_work_schedules_holidays.sql
--
-- Work schedules and the holiday calendar: step 1 of the attendance rework.
--
-- Attendance could not say whether anyone was late, absent or on a holiday,
-- because the system had no idea when anyone was meant to work. These
-- tables are that knowledge. The monthly grid (step 3), corrections (step 4)
-- and month close (step 5) all read them through resolve_day() in
-- app/services/work_calendar.py.
--
-- Confirmed policy (2026-10-29):
--   * default schedule Mon-Fri 08:30-17:00, 15 minutes' grace before "late";
--   * per-employee overrides for vets and rescue staff;
--   * VFF's days off are the mercantile holidays plus every Full Moon Poya
--     Day; rescue staff work through holidays.
--
-- APPLY in the Supabase SQL editor. Safe to re-run.

-- ---------------------------------------------------------------------------
-- 1. Schedules
-- ---------------------------------------------------------------------------

-- A named weekly pattern. Employees with no assignment follow the default.
CREATE TABLE IF NOT EXISTS work_schedules (
    id                SERIAL PRIMARY KEY,
    name              VARCHAR(80) NOT NULL UNIQUE,
    is_default        BOOLEAN NOT NULL DEFAULT FALSE,
    grace_minutes     SMALLINT NOT NULL DEFAULT 15 CHECK (grace_minutes BETWEEN 0 AND 120),
    -- FALSE for schedules that work through holidays (the rescue rota).
    observes_holidays BOOLEAN NOT NULL DEFAULT TRUE,
    created_by        UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- At most one default, enforced here rather than trusted to the API.
CREATE UNIQUE INDEX IF NOT EXISTS work_schedules_one_default
    ON work_schedules (is_default) WHERE is_default;

-- Working days of a schedule. No row for a weekday means a day off.
CREATE TABLE IF NOT EXISTS work_schedule_days (
    schedule_id   INTEGER  NOT NULL REFERENCES work_schedules(id) ON DELETE CASCADE,
    weekday       SMALLINT NOT NULL CHECK (weekday BETWEEN 1 AND 7),  -- ISO: 1 = Monday
    start_time    TIME     NOT NULL,  -- local time, Asia/Colombo
    end_time      TIME     NOT NULL,  -- earlier than start_time = overnight shift
    break_minutes SMALLINT NOT NULL DEFAULT 60 CHECK (break_minutes BETWEEN 0 AND 600),
    PRIMARY KEY (schedule_id, weekday),
    CHECK (end_time <> start_time)
);

-- Who follows which schedule, from when. Effective-dated rather than a column
-- on employee_profile, so moving someone to the rescue rota in November does
-- not rewrite how their October is judged.
CREATE TABLE IF NOT EXISTS employee_schedule_assignments (
    id             SERIAL PRIMARY KEY,
    employee_id    INTEGER NOT NULL REFERENCES employee_profile(id) ON DELETE CASCADE,
    schedule_id    INTEGER NOT NULL REFERENCES work_schedules(id),
    effective_from DATE    NOT NULL,
    created_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    UNIQUE (employee_id, effective_from)
);

CREATE INDEX IF NOT EXISTS idx_schedule_assignments_employee
    ON employee_schedule_assignments (employee_id, effective_from DESC);

-- ---------------------------------------------------------------------------
-- 2. Holidays
-- ---------------------------------------------------------------------------
--
-- Every gazette entry with its official categories, plus VFF's own decision.
-- The calendar shows everything; attendance only reads is_day_off. Loaded
-- from backend/db/holidays/<year>.csv by the app's Import (see the README
-- there for sources), and editable by HR for amendments and holidays
-- declared at short notice.

CREATE TABLE IF NOT EXISTS holidays (
    id            SERIAL PRIMARY KEY,
    holiday_date  DATE         NOT NULL,
    name          VARCHAR(120) NOT NULL,
    is_public     BOOLEAN NOT NULL DEFAULT FALSE,  -- gazette *
    is_bank       BOOLEAN NOT NULL DEFAULT FALSE,  -- gazette =
    is_mercantile BOOLEAN NOT NULL DEFAULT FALSE,  -- Central Bank M list
    is_poya       BOOLEAN NOT NULL DEFAULT FALSE,
    is_day_off    BOOLEAN NOT NULL DEFAULT TRUE,   -- VFF policy
    source        VARCHAR(200),
    created_by    UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    -- Two holidays can share a date (1 May 2026 is Vesak and May Day).
    UNIQUE (holiday_date, name)
);

CREATE INDEX IF NOT EXISTS idx_holidays_date ON holidays (holiday_date);

-- ---------------------------------------------------------------------------
-- 3. Row level security, as in 003_rls_lockdown.sql
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'work_schedules',
        'work_schedule_days',
        'employee_schedule_assignments',
        'holidays'
    ]
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', t || '_authenticated_all', t);
        EXECUTE format(
            'CREATE POLICY %I ON public.%I '
            'FOR ALL TO authenticated USING (true) WITH CHECK (true)',
            t || '_authenticated_all', t);
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- 4. The default schedule: Mon-Fri 08:30-17:00, one hour's break
-- ---------------------------------------------------------------------------

INSERT INTO work_schedules (name, is_default, grace_minutes, observes_holidays)
SELECT 'Office hours', TRUE, 15, TRUE
WHERE NOT EXISTS (SELECT 1 FROM work_schedules WHERE is_default);

INSERT INTO work_schedule_days (schedule_id, weekday, start_time, end_time, break_minutes)
SELECT s.id, d.weekday, TIME '08:30', TIME '17:00', 60
FROM work_schedules s
CROSS JOIN (VALUES (1), (2), (3), (4), (5)) AS d(weekday)
WHERE s.name = 'Office hours'
ON CONFLICT (schedule_id, weekday) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 5. Make the API see the new tables now
-- ---------------------------------------------------------------------------

NOTIFY pgrst, 'reload schema';
