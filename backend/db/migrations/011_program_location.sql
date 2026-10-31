-- 011_program_location.sql
--
-- Where a program takes place, e.g. "Kandy" or "Peradeniya, Kandy District".
-- Asked for when a program is initialized and shown on every program card.
--
-- Nullable on purpose: the programs that existed before this column have no
-- location yet, and staff fill them in from the program's details page. The
-- API requires it for every NEW program (ProgramCreate), so NULL only ever
-- means "created before locations were recorded".
--
-- APPLY in the Supabase SQL editor. Safe to re-run.

ALTER TABLE programs ADD COLUMN IF NOT EXISTS location text;

-- A blank string is not a location. 200 characters is generous for a place.
ALTER TABLE programs DROP CONSTRAINT IF EXISTS programs_location_not_blank;
ALTER TABLE programs ADD CONSTRAINT programs_location_not_blank
    CHECK (location IS NULL OR (length(trim(location)) BETWEEN 1 AND 200));

COMMENT ON COLUMN programs.location IS
    'Where the program takes place. Required for new programs by the API; NULL only on programs created before it was recorded.';


-- ---------------------------------------------------------------------------
-- VERIFY (read-only):
--
--   SELECT column_name, data_type FROM information_schema.columns
--    WHERE table_name = 'programs' AND column_name = 'location';
--     -> 1 row: location | text
--
--   SELECT id, program_name, location FROM programs ORDER BY id;
--     -> existing programs show location NULL until it is filled in.
-- ---------------------------------------------------------------------------
