-- 030_case_timeline_outcome.sql
--
-- Rescue case timeline and outcome (policy confirmed 2026-11-13).
--
-- Until now a case went Reported -> In Treatment -> Resolved and recorded
-- nothing in between: not what was done, nor what happened to the animal.
--
--   rescue_cases.outcome     what "Resolved" meant for this animal. One of five
--                            fixed values so reports can count them. Required
--                            to resolve a case (app/api/rescue_cases.py);
--                            reopening clears it, and the timeline keeps the
--                            old one.
--   rescue_cases.resolved_at when it was last resolved; cleared with outcome.
--
--   rescue_case_events       the case's timeline: notes written by the staff
--                            working it (rescue:manage), plus a line for every
--                            status change, assignment and outcome. Append-only:
--                            a mistake is corrected by a follow-up note, so the
--                            record of what was done to an animal can be
--                            trusted. Enforced by the trigger below, which
--                            also binds service_role, not only by RLS.
--
-- Cases resolved before this migration keep a NULL outcome. Nobody recorded
-- one, and backfilling a guess would assert something we do not know; reports
-- count them as "not recorded". The CHECK only forbids an outcome on a case
-- that is not Resolved.
--
-- The case's "Reported" line is not stored: it is reported_at on the case
-- itself, and the API adds it to the front of the timeline. That way cases
-- from before this migration still get one.
--
-- APPLY in the Supabase SQL editor. Safe to re-run.

ALTER TABLE public.rescue_cases
    ADD COLUMN IF NOT EXISTS outcome     VARCHAR(30),
    ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE public.rescue_cases DROP CONSTRAINT IF EXISTS rescue_cases_outcome_check;
ALTER TABLE public.rescue_cases ADD CONSTRAINT rescue_cases_outcome_check CHECK (
    outcome IS NULL
    OR (status = 'Resolved'
        AND outcome IN ('Released', 'Rehomed', 'Transferred', 'Died', 'Not found'))
);

CREATE TABLE IF NOT EXISTS public.rescue_case_events (
    id          BIGSERIAL PRIMARY KEY,
    -- No ON DELETE CASCADE: the trigger below would refuse the cascaded
    -- delete anyway, and cases are never deleted (rescue_cases has no DELETE
    -- policy, see 003_rls_lockdown.sql section 3).
    case_id     UUID NOT NULL REFERENCES public.rescue_cases(id),
    event_type  VARCHAR(20) NOT NULL
                CHECK (event_type IN ('note', 'status', 'assign', 'outcome')),
    -- note: the text. outcome: an optional explanation. Otherwise NULL.
    body        VARCHAR(2000),
    from_status VARCHAR(20),
    to_status   VARCHAR(20),
    outcome     VARCHAR(30)
                CHECK (outcome IS NULL
                       OR outcome IN ('Released', 'Rehomed', 'Transferred', 'Died', 'Not found')),
    -- assign: who the case went to (NULL = released back to unassigned).
    assignee_id UUID REFERENCES public.users(id) ON DELETE SET NULL,
    author_id   UUID REFERENCES public.users(id) ON DELETE SET NULL,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CHECK (event_type <> 'note' OR length(trim(body)) > 0),
    CHECK (event_type <> 'outcome' OR outcome IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_rescue_case_events_case
    ON public.rescue_case_events (case_id, created_at);

CREATE OR REPLACE FUNCTION public.rescue_case_events_append_only()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'rescue_case_events is append-only; add a follow-up note instead';
END;
$$;

DROP TRIGGER IF EXISTS trg_rescue_case_events_append_only ON public.rescue_case_events;
CREATE TRIGGER trg_rescue_case_events_append_only
    BEFORE UPDATE OR DELETE ON public.rescue_case_events
    FOR EACH ROW EXECUTE FUNCTION public.rescue_case_events_append_only();

-- Same shape as rescue_cases (003_rls_lockdown.sql section 3): staff read and
-- write as `authenticated`, permission checks live in FastAPI. SELECT and
-- INSERT only; no UPDATE or DELETE policy, matching the trigger.
ALTER TABLE public.rescue_case_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rescue_case_events_authenticated_select ON public.rescue_case_events;
CREATE POLICY rescue_case_events_authenticated_select ON public.rescue_case_events
    FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS rescue_case_events_authenticated_insert ON public.rescue_case_events;
CREATE POLICY rescue_case_events_authenticated_insert ON public.rescue_case_events
    FOR INSERT TO authenticated WITH CHECK (true);

NOTIFY pgrst, 'reload schema';
