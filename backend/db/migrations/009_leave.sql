-- 009_leave.sql
--
-- Leave management: step 2 of the attendance rework.
--
-- Leave types, yearly entitlements, requests, and the individual days each
-- request covers. Days are counted against the employee's schedule and the
-- holiday calendar (008), so a Mon-Fri request across a Poya day is 4 days,
-- and the rescue rota is charged only for its own working days.
--
-- Policy confirmed 2026-10-29:
--   Annual 14 (first year per the Shop and Office Employees Act s.6(1)(a)
--   table, taken the following year per s.6(2)), carry forward up to 7.
--   Casual 7 (first year: one day per complete two months' service, taken
--   that year, s.6(4)(a)); no carry-forward.
--   Sick 7, no carry-forward (VFF policy; the Act's casual leave already
--   covers ill health, s.6(3)).
--   Paternity 3. Maternity 84 working days, 42 for a stillbirth: more
--   generous than the Act (s.18B: 14 days before + 70 after, or 28 after a
--   stillbirth; days, not working days). counts_calendar_days switches a
--   type to the statutory way of counting.
--   No-pay unlimited; month close (step 5) sends these days to payroll.
--   Approval needs leave:approve (HR Officer, Admin), never one's own.
--
-- APPLY in the Supabase SQL editor. Safe to re-run.

-- For the no-overlap constraint on leave_requests.
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- First-year entitlements depend on when someone joined. Existing staff have
-- none recorded; entitlement generation lists them for HR rather than guess.
ALTER TABLE employee_profile ADD COLUMN IF NOT EXISTS date_joined DATE;

-- ---------------------------------------------------------------------------
-- 1. Leave types
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS leave_types (
    id                   SERIAL PRIMARY KEY,
    code                 VARCHAR(20) NOT NULL UNIQUE,
    name                 VARCHAR(60) NOT NULL,
    is_paid              BOOLEAN NOT NULL,
    -- Yearly allowance tracked in leave_entitlements. FALSE for event-based
    -- leave (maternity, paternity) and for no-pay.
    uses_balance         BOOLEAN NOT NULL,
    default_days         NUMERIC(5,1),          -- yearly allowance when uses_balance
    max_days_per_request NUMERIC(5,1),          -- cap for event-based leave
    counts_calendar_days BOOLEAN NOT NULL DEFAULT FALSE,  -- FALSE: working days on the schedule
    allow_half_day       BOOLEAN NOT NULL DEFAULT FALSE,
    carry_forward_max    NUMERIC(5,1) NOT NULL DEFAULT 0,
    first_year_rule      VARCHAR(12) NOT NULL DEFAULT 'none'
                         CHECK (first_year_rule IN ('none', 'soe_annual', 'soe_casual')),
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order           SMALLINT NOT NULL DEFAULT 0
);

INSERT INTO leave_types
    (code, name, is_paid, uses_balance, default_days, max_days_per_request,
     counts_calendar_days, allow_half_day, carry_forward_max, first_year_rule, sort_order)
VALUES
    ('ANNUAL',       'Annual leave',            TRUE,  TRUE,  14,   NULL, FALSE, TRUE,  7, 'soe_annual', 1),
    ('CASUAL',       'Casual leave',            TRUE,  TRUE,  7,    NULL, FALSE, TRUE,  0, 'soe_casual', 2),
    ('SICK',         'Sick leave',              TRUE,  TRUE,  7,    NULL, FALSE, TRUE,  0, 'none',       3),
    ('PATERNITY',    'Paternity leave',         TRUE,  FALSE, NULL, 3,    FALSE, FALSE, 0, 'none',       4),
    ('MATERNITY',    'Maternity leave',         TRUE,  FALSE, NULL, 84,   FALSE, FALSE, 0, 'none',       5),
    ('MATERNITY_SB', 'Maternity (stillbirth)',  TRUE,  FALSE, NULL, 42,   FALSE, FALSE, 0, 'none',       6),
    ('NOPAY',        'No-pay leave',            FALSE, FALSE, NULL, NULL, FALSE, TRUE,  0, 'none',       7)
ON CONFLICT (code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. Entitlements
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS leave_entitlements (
    id              SERIAL PRIMARY KEY,
    employee_id     INTEGER  NOT NULL REFERENCES employee_profile(id) ON DELETE CASCADE,
    leave_type_id   INTEGER  NOT NULL REFERENCES leave_types(id),
    year            SMALLINT NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    entitled_days   NUMERIC(5,1) NOT NULL CHECK (entitled_days >= 0),
    carried_forward NUMERIC(5,1) NOT NULL DEFAULT 0 CHECK (carried_forward >= 0),
    adjustment      NUMERIC(5,1) NOT NULL DEFAULT 0,
    note            VARCHAR(200),
    updated_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    UNIQUE (employee_id, leave_type_id, year)
);

-- ---------------------------------------------------------------------------
-- 3. Requests and the days they cover
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS leave_requests (
    id            SERIAL PRIMARY KEY,
    employee_id   INTEGER NOT NULL REFERENCES employee_profile(id) ON DELETE CASCADE,
    leave_type_id INTEGER NOT NULL REFERENCES leave_types(id),
    start_date    DATE NOT NULL,
    end_date      DATE NOT NULL,
    half_day      VARCHAR(4) NOT NULL DEFAULT 'none' CHECK (half_day IN ('none', 'am', 'pm')),
    days          NUMERIC(5,1) NOT NULL CHECK (days > 0),
    reason        VARCHAR(500),
    status        VARCHAR(10) NOT NULL DEFAULT 'Pending'
                  CHECK (status IN ('Pending', 'Approved', 'Rejected', 'Cancelled')),
    requested_by  UUID REFERENCES users(id) ON DELETE SET NULL,
    requested_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    decided_by    UUID REFERENCES users(id) ON DELETE SET NULL,
    decided_at    TIMESTAMP WITH TIME ZONE,
    decision_note VARCHAR(500),
    CHECK (end_date >= start_date),
    CHECK (half_day = 'none' OR start_date = end_date)
);

-- Two live requests for one person may not overlap. The API checks first to
-- give a readable message; this makes it true even under concurrent submits.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'leave_requests_no_overlap') THEN
        ALTER TABLE leave_requests ADD CONSTRAINT leave_requests_no_overlap
            EXCLUDE USING gist (employee_id WITH =, daterange(start_date, end_date, '[]') WITH &&)
            WHERE (status IN ('Pending', 'Approved'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_leave_requests_status ON leave_requests (status, start_date);

-- The working days a request covers, fixed when it is submitted so a later
-- schedule change cannot silently alter leave already granted. Steps 3 and 5
-- read these: the grid shows them as Leave, month close sends no-pay days to
-- payroll, and a request across New Year draws on each year's balance.
CREATE TABLE IF NOT EXISTS leave_request_days (
    request_id INTEGER NOT NULL REFERENCES leave_requests(id) ON DELETE CASCADE,
    leave_date DATE    NOT NULL,
    fraction   NUMERIC(2,1) NOT NULL CHECK (fraction IN (0.5, 1.0)),
    PRIMARY KEY (request_id, leave_date)
);

-- ---------------------------------------------------------------------------
-- 4. Row level security, as in 003_rls_lockdown.sql
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['leave_types', 'leave_entitlements', 'leave_requests', 'leave_request_days']
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', t || '_authenticated_all', t);
        EXECUTE format(
            'CREATE POLICY %I ON public.%I '
            'FOR ALL TO authenticated USING (true) WITH CHECK (true)',
            t || '_authenticated_all', t);
    END LOOP;
END $$;

NOTIFY pgrst, 'reload schema';
