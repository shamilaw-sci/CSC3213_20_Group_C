-- 035_program_public_listing.sql
--
-- Lets staff announce a program on the public site (/clinics), so people in
-- the area know a sterilization drive or free clinic is coming and can bring
-- their animals.
--
-- Off by default: a program is internal until someone with programs:manage
-- publishes it. Only Upcoming and Active programs are listed; a program that
-- is completed or cancelled drops off the public page on its own, without
-- anyone having to unpublish it.
--
-- The public endpoint (GET /api/programs/public) selects these columns plus
-- name, location and dates, and nothing else: no costs, team or volunteers.
--
-- APPLY in the Supabase SQL editor. Safe to re-run.

ALTER TABLE programs ADD COLUMN IF NOT EXISTS is_public       boolean NOT NULL DEFAULT false;
ALTER TABLE programs ADD COLUMN IF NOT EXISTS program_type    text;
ALTER TABLE programs ADD COLUMN IF NOT EXISTS public_venue    text;
ALTER TABLE programs ADD COLUMN IF NOT EXISTS public_schedule text;
ALTER TABLE programs ADD COLUMN IF NOT EXISTS public_notes    text;

-- What the public is told the program is. NULL until someone sets it.
ALTER TABLE programs DROP CONSTRAINT IF EXISTS programs_program_type_known;
ALTER TABLE programs ADD CONSTRAINT programs_program_type_known
    CHECK (program_type IS NULL OR program_type IN
        ('Sterilization', 'Vaccination', 'Free Clinic', 'Awareness', 'Other'));

-- Blank strings are not values; lengths are generous for a public card.
ALTER TABLE programs DROP CONSTRAINT IF EXISTS programs_public_text_sane;
ALTER TABLE programs ADD CONSTRAINT programs_public_text_sane CHECK (
        (public_venue    IS NULL OR length(trim(public_venue))    BETWEEN 1 AND 200)
    AND (public_schedule IS NULL OR length(trim(public_schedule)) BETWEEN 1 AND 200)
    AND (public_notes    IS NULL OR length(trim(public_notes))    BETWEEN 1 AND 1000)
);

-- A public listing has to say what and where, and an Upcoming one when.
-- Active programs are exempt from the date: they are on now, and several
-- older ones never recorded a start date (it cannot be set after starting).
-- The API checks the same thing with a readable message; this is the backstop.
ALTER TABLE programs DROP CONSTRAINT IF EXISTS programs_public_listing_complete;
ALTER TABLE programs ADD CONSTRAINT programs_public_listing_complete CHECK (
    NOT is_public
    OR (program_type IS NOT NULL AND location IS NOT NULL
        AND (start_date IS NOT NULL OR status <> 'Upcoming'))
);

-- The public page reads only published rows.
CREATE INDEX IF NOT EXISTS programs_public_idx ON programs (start_date) WHERE is_public;

COMMENT ON COLUMN programs.is_public IS
    'Shown on the public /clinics page while Upcoming or Active. Off by default.';
COMMENT ON COLUMN programs.program_type IS
    'What the public is told this is: Sterilization, Vaccination, Free Clinic, Awareness or Other.';
COMMENT ON COLUMN programs.public_venue IS
    'The exact place to bring animals, e.g. "Peradeniya Community Hall". Optional; location is the area.';
COMMENT ON COLUMN programs.public_schedule IS
    'Days and hours as people should read them, e.g. "Sat 22 - Mon 24 Nov, 8am - 1pm".';
COMMENT ON COLUMN programs.public_notes IS
    'What to know before coming, e.g. "Free. Do not feed your dog after 10pm the night before."';


-- ---------------------------------------------------------------------------
-- VERIFY (read-only):
--
--   SELECT column_name FROM information_schema.columns
--    WHERE table_name = 'programs'
--      AND column_name IN ('is_public', 'program_type', 'public_venue',
--                          'public_schedule', 'public_notes');
--     -> 5 rows.
--
--   SELECT conname FROM pg_constraint
--    WHERE conrelid = 'programs'::regclass
--      AND conname IN ('programs_program_type_known', 'programs_public_text_sane',
--                      'programs_public_listing_complete');
--     -> 3 rows.
-- ---------------------------------------------------------------------------
