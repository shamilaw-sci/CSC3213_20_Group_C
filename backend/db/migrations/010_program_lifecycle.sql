-- 010_program_lifecycle.sql
--
-- Program lifecycle: every program moves Upcoming -> Active -> Completed,
-- forward only, one step at a time. New programs start as Upcoming.
--
-- Before this, status was free text with a default of 'Active'. The live data
-- held two values: 'Active' (6 rows) and 'In Progress' (1 row). 'In Progress'
-- meant "running", so it becomes 'Active'. Anything else unexpected is left
-- alone by step 2 and will make step 4 fail loudly instead of guessing, so run
-- the check at the top first if this is not the database it was written for.
--
-- The API (app/services/program_lifecycle.py) enforces the same rules; the
-- trigger here is the backstop for any write that does not go through it.
--
-- APPLY in the Supabase SQL editor. Safe to re-run.

-- 0. Look before changing anything (read-only):
--      SELECT status, count(*) FROM programs GROUP BY status ORDER BY status;

-- 1. Columns the lifecycle uses. They already exist on the live database;
--    init.sql never had them, so a fresh database needs them.
ALTER TABLE programs ADD COLUMN IF NOT EXISTS start_date date;
ALTER TABLE programs ADD COLUMN IF NOT EXISTS end_date   date;

-- 2. Map the old values onto the new set.
UPDATE programs SET status = 'Active'
 WHERE status IS NULL OR trim(lower(status)) IN ('active', 'in progress');
UPDATE programs SET status = 'Upcoming'
 WHERE trim(lower(status)) = 'upcoming' AND status <> 'Upcoming';
UPDATE programs SET status = 'Completed'
 WHERE trim(lower(status)) = 'completed' AND status <> 'Completed';

-- 3. New programs start as Upcoming.
ALTER TABLE programs ALTER COLUMN status SET DEFAULT 'Upcoming';
ALTER TABLE programs ALTER COLUMN status SET NOT NULL;

-- 4. Only the three lifecycle values.
ALTER TABLE programs DROP CONSTRAINT IF EXISTS programs_status_lifecycle;
ALTER TABLE programs ADD CONSTRAINT programs_status_lifecycle
    CHECK (status IN ('Upcoming', 'Active', 'Completed'));

-- An end date before the start date is a typing error, not a real program.
ALTER TABLE programs DROP CONSTRAINT IF EXISTS programs_dates_ordered;
ALTER TABLE programs ADD CONSTRAINT programs_dates_ordered
    CHECK (start_date IS NULL OR end_date IS NULL OR end_date >= start_date);

-- 5. Forward-only transitions. Fires only when status actually changes, so
--    the triggers that maintain total_cost (which UPDATE programs) are
--    unaffected.
CREATE OR REPLACE FUNCTION enforce_program_status_transition()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status
       AND NOT (
            (OLD.status = 'Upcoming' AND NEW.status = 'Active')
         OR (OLD.status = 'Active'   AND NEW.status = 'Completed')
       )
    THEN
        RAISE EXCEPTION
            'Program % cannot move from % to %: programs only move Upcoming -> Active -> Completed',
            OLD.id, OLD.status, NEW.status
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS programs_status_transition ON programs;
CREATE TRIGGER programs_status_transition
    BEFORE UPDATE OF status ON programs
    FOR EACH ROW
    EXECUTE FUNCTION enforce_program_status_transition();

COMMENT ON COLUMN programs.status IS
    'Lifecycle: Upcoming -> Active -> Completed, forward only (trigger programs_status_transition). New programs default to Upcoming.';


-- ---------------------------------------------------------------------------
-- VERIFY (read-only):
--
--   SELECT status, count(*) FROM programs GROUP BY status ORDER BY status;
--     -> only Upcoming / Active / Completed.
--
--   SELECT conname FROM pg_constraint
--    WHERE conrelid = 'programs'::regclass
--      AND conname IN ('programs_status_lifecycle', 'programs_dates_ordered');
--     -> 2 rows.
--
--   SELECT tgname FROM pg_trigger
--    WHERE tgrelid = 'programs'::regclass AND tgname = 'programs_status_transition';
--     -> 1 row.
--
--   SELECT column_default FROM information_schema.columns
--    WHERE table_name = 'programs' AND column_name = 'status';
--     -> 'Upcoming'::character varying
-- ---------------------------------------------------------------------------
