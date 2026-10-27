-- 004_volunteers.sql
--
-- Volunteer management: roster, shifts, and assignments to shifts / rescue
-- cases / programs.
--
-- Volunteers deliberately have NO login and NO row in `users`. Adding a second
-- user type would mean touching the whole existing staff auth and permission
-- surface. Instead each volunteer gets an unguessable tokenized link; knowing
-- the link is the authorization. That is a weaker guarantee than real auth and
-- is accepted for what it protects — one person's own shift schedule — so the
-- pages behind it must never expose anything beyond that volunteer's own
-- assignments.


-- ---------------------------------------------------------------------------
-- 1. volunteers
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS volunteers (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name       text NOT NULL,
    email           text NOT NULL,
    phone           text,

    -- Fixed vocabularies rather than join tables: both sets are small, closed,
    -- and only ever read whole. text[] keeps them queryable (`skills && ...`)
    -- without two more tables and two more sets of RLS policies.
    skills          text[] NOT NULL DEFAULT '{}',
    skills_other    text,
    availability    text[] NOT NULL DEFAULT '{}',

    status          text NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','approved','rejected','inactive')),

    -- 256 bits from secrets.token_urlsafe(32), generated in the application at
    -- INSERT rather than at approval. Generating it here would need pgcrypto
    -- and put a security-relevant constant in the schema; generating it at
    -- approval would mean a nullable window and a second write path.
    --
    -- The token is INERT until status = 'approved' — the lookup endpoint
    -- filters on status, so a pending or rejected applicant's link returns the
    -- same "not found" as a token that was never issued.
    access_token    text NOT NULL UNIQUE,

    -- Set when a coordinator copies the link to send by WhatsApp. Email is the
    -- default path, but Brevo's free tier sending from an unauthenticated
    -- sender lands in spam often enough that this is expected to carry real
    -- traffic. NULL means nobody has ever manually shared this link.
    link_shared_at  timestamptz,

    applied_at      timestamptz NOT NULL DEFAULT now(),
    reviewed_at     timestamptz,
    reviewed_by     uuid REFERENCES users(id) ON DELETE SET NULL,
    staff_notes     text,

    CONSTRAINT volunteers_skills_known CHECK (
        skills <@ ARRAY[
            'animal_handling','transport_driving','veterinary','fostering',
            'fundraising','admin_office','media_photography','community_outreach'
        ]::text[]
    ),
    CONSTRAINT volunteers_availability_known CHECK (
        availability <@ ARRAY[
            'weekday_mornings','weekday_afternoons','weekday_evenings',
            'weekends','on_call'
        ]::text[]
    )
);

-- Email is deliberately NOT globally unique. A globally unique constraint would
-- permanently bar a rejected applicant from ever reapplying, and would make a
-- duplicate submission a 500 instead of a shrug. Partial on the live statuses:
-- one person cannot hold two active records, but a rejected one can reapply.
--
-- lower() because the public form is typed by hand and "Nimal@..." and
-- "nimal@..." are the same person.
CREATE UNIQUE INDEX IF NOT EXISTS volunteers_active_email_uniq
    ON volunteers (lower(email))
    WHERE status IN ('pending','approved');

-- The roster's default view is "pending applications first, newest first".
CREATE INDEX IF NOT EXISTS idx_volunteers_status_applied
    ON volunteers (status, applied_at DESC);


-- ---------------------------------------------------------------------------
-- 2. volunteer_shifts
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS volunteer_shifts (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title             text NOT NULL,
    description       text,
    location          text,

    -- Wall-clock date and time, NOT timestamptz. The organisation operates
    -- entirely in Asia/Colombo and "Saturday clinic, 9am-1pm" is a wall-clock
    -- fact about a place, not an instant. timestamptz would be technically
    -- purer and would invite off-by-one rendering bugs between a UTC server
    -- and a +05:30 browser for no benefit anyone here would ever observe.
    shift_date        date NOT NULL,
    start_time        time NOT NULL,
    end_time          time NOT NULL,

    volunteers_needed integer NOT NULL DEFAULT 1 CHECK (volunteers_needed > 0),

    -- Cancelled rather than deleted, so a cancelled shift's assignments and the
    -- responses volunteers already gave survive in the roster and audit log.
    is_cancelled      boolean NOT NULL DEFAULT false,

    created_by        uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT volunteer_shifts_ends_after_start CHECK (end_time > start_time)
);

-- Every staff view of shifts is "upcoming, soonest first"; every volunteer view
-- is the same filtered to their own assignments.
CREATE INDEX IF NOT EXISTS idx_volunteer_shifts_date
    ON volunteer_shifts (shift_date);


-- ---------------------------------------------------------------------------
-- 3. volunteer_assignments
-- ---------------------------------------------------------------------------
--
-- ONE table for all three assignable things (shift / rescue case / program)
-- rather than three tables.
--
-- The response lifecycle — response, decline_reason, responded_at, assigned_by,
-- assigned_at — is identical across all three, and that lifecycle IS the
-- operational point of the feature. Three tables would mean three copies of
-- those columns, three sets of policies, three near-identical endpoints, and
-- three audit action types for what is one act. The volunteer's own page is
-- inherently "everything I have been asked to do, in date order, whatever the
-- type": one query here, three queries and a merge in Python there, on the
-- most-requested endpoint in the feature.
--
-- This is NOT the polymorphic anti-pattern. That one is `target_type` plus an
-- untyped `target_id`, and it throws away referential integrity. Three real,
-- typed foreign key columns keep integrity and ON DELETE CASCADE; the cost is
-- two NULLs per row, which at this scale is nothing. It is also forced: the
-- three ids are uuid, uuid and integer, so they could not be one column even
-- if we wanted that.
--
-- There is deliberately no stored `assignment_type`. It is derivable from which
-- FK is populated, and a stored copy admits rows that claim to be a shift
-- assignment while carrying a program_id. The API derives it.

CREATE TABLE IF NOT EXISTS volunteer_assignments (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    volunteer_id   uuid NOT NULL REFERENCES volunteers(id) ON DELETE CASCADE,

    shift_id       uuid    REFERENCES volunteer_shifts(id) ON DELETE CASCADE,
    rescue_case_id uuid    REFERENCES rescue_cases(id)     ON DELETE CASCADE,
    program_id     integer REFERENCES programs(id)         ON DELETE CASCADE,

    response       text NOT NULL DEFAULT 'pending'
                       CHECK (response IN ('pending','accepted','declined')),
    decline_reason text,
    responded_at   timestamptz,

    assigned_by    uuid REFERENCES users(id) ON DELETE SET NULL,
    assigned_at    timestamptz NOT NULL DEFAULT now(),

    -- "Exactly one target" as a database invariant rather than an API
    -- convention. num_nonnulls is a Postgres builtin.
    CONSTRAINT volunteer_assignments_one_target CHECK (
        num_nonnulls(shift_id, rescue_case_id, program_id) = 1
    ),

    -- A decline reason on an accepted or pending row is incoherent. Volunteers
    -- may change their answer later, and clearing the reason on the way out of
    -- 'declined' is the API's job; this makes forgetting it a hard error.
    CONSTRAINT volunteer_assignments_reason_only_on_decline CHECK (
        response = 'declined' OR decline_reason IS NULL
    ),

    -- Not partial, and they do not need to be: Postgres treats NULLs as
    -- distinct in unique indexes, so many rows can share shift_id IS NULL while
    -- no volunteer can be assigned the same shift twice.
    CONSTRAINT volunteer_assignments_unique_shift   UNIQUE (volunteer_id, shift_id),
    CONSTRAINT volunteer_assignments_unique_case    UNIQUE (volunteer_id, rescue_case_id),
    CONSTRAINT volunteer_assignments_unique_program UNIQUE (volunteer_id, program_id)
);

-- The tokenized page's only query: this volunteer's assignments.
CREATE INDEX IF NOT EXISTS idx_volunteer_assignments_volunteer
    ON volunteer_assignments (volunteer_id);

-- The roster's headline number — "6 assigned: 4 accepted, 1 declined, 1
-- awaiting response" — is a group-by over one shift's assignments.
CREATE INDEX IF NOT EXISTS idx_volunteer_assignments_shift_response
    ON volunteer_assignments (shift_id, response);


-- ---------------------------------------------------------------------------
-- 4. RLS
-- ---------------------------------------------------------------------------
--
-- Follows the pattern established in 003_rls_lockdown.sql: no anon policy,
-- permissive `authenticated` policy, with FastAPI's require_permission() as the
-- actual authorization.
--
-- NO ANON POLICY AT ALL — not even INSERT for the public application form.
--
-- That is deliberate and differs from rescue_cases, which does carry an anon
-- INSERT policy. rescue_cases does not actually need it either: after 003
-- landed, anon reads 0 rows from rescue_cases while GET /api/rescue_cases/geo
-- still returns all 32, because get_public_supabase() is a service_role client
-- and bypasses RLS. The public path demonstrably never runs as anon. The
-- rescue_cases anon policy is preserved legacy, not a working dependency, and
-- removing it is tracked as a separate change rather than folded in here —
-- it is a live public form and being wrong about it breaks reporting.
--
-- All three public volunteer flows go through FastAPI on service_role:
--
--   POST /api/volunteers/apply                          (public application)
--   GET  /api/volunteers/my-assignments/{token}         (tokenized view)
--   POST /api/volunteers/my-assignments/{token}/respond (accept / decline)
--
-- The alternative — an anon policy matching the token out of
-- current_setting('request.headers') — works, but requires the browser to talk
-- to PostgREST directly, which nothing in this frontend does, and puts the
-- token on a second network path. With no anon policy, someone holding the
-- public anon key AND a valid volunteer token still gets nothing from
-- PostgREST. Strictly stronger, and it matches the architecture already here.
--
-- Because the SELECT policy is USING (true), an UPDATE can never move a row out
-- of SELECT visibility — so the returning-row-checked-against-SELECT-policy
-- 42501 that has bitten this project repeatedly cannot occur on these tables.
-- That is by construction, not by luck.

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'volunteers',
        'volunteer_shifts',
        'volunteer_assignments'
    ]
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);

        EXECUTE format(
            'DROP POLICY IF EXISTS %I ON public.%I', t || '_authenticated_all', t);

        EXECUTE format(
            'CREATE POLICY %I ON public.%I '
            'FOR ALL TO authenticated USING (true) WITH CHECK (true)',
            t || '_authenticated_all', t);
    END LOOP;
END $$;


COMMENT ON COLUMN volunteers.access_token IS
    'Unguessable 256-bit link token. Possession of the link is the authorization for /my-assignments/[token]. Inert until status = ''approved''. Never exposed to anon via PostgREST — all reads go through FastAPI on the service_role client.';

COMMENT ON COLUMN volunteers.link_shared_at IS
    'When a coordinator last copied this volunteer''s link to share manually (WhatsApp). NULL means never shared. Email is the default channel; this is the fallback that in practice carries much of the traffic.';

COMMENT ON CONSTRAINT volunteer_assignments_one_target ON volunteer_assignments IS
    'Exactly one of shift_id / rescue_case_id / program_id is set. The assignment type is derived from which one, never stored.';


-- ---------------------------------------------------------------------------
-- VERIFY against the live REST API, do not assume:
--
--   python scripts/audit_rls.py
--       volunteers, volunteer_shifts and volunteer_assignments must all read 0
--       as anon and report `blocked` for insert.
--
--   python scripts/audit_rls.py --as-staff EMAIL PASSWORD
--       All three must be readable as `authenticated`, or every staff endpoint
--       in this feature is broken.
-- ---------------------------------------------------------------------------
