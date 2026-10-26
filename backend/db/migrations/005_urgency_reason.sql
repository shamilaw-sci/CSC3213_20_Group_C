-- 005_urgency_reason.sql
--
-- Makes the AI urgency classification on rescue cases explainable.
--
-- classify_case_urgency() has always produced a one-sentence reason alongside
-- the urgency label, but create_case discarded it, so staff saw "Critical" on
-- the board with no way to tell why — or whether a model decided it at all.
-- The classifier is fail-soft: a missing description or a failed LLM call
-- yields "Medium" rather than blocking a public report. Until now that default
-- was indistinguishable from a genuine "Medium" judgement.
--
--   urgency_reason  the classifier's one-sentence justification, or for a
--                   default, a plain statement of why no judgement was made.
--
--   urgency_source  where the urgency value came from:
--                     'ai'                        the model classified it
--                     'default_no_description'    nothing to classify
--                     'default_classifier_error'  LLM call failed or its
--                                                 response was unparseable
--                     'default_invalid_label'     the model answered, but
--                                                 with a label outside
--                                                 Low/Medium/High/Critical
--                   Constrained rather than free text: the UI branches on
--                   these values, and a typo'd source would silently render a
--                   default as if it were a real classification.
--
-- Existing rows are left NULL in both columns. There is no record of how their
-- urgency was produced, and backfilling 'ai' would assert something we do not
-- know. NULL means "classified before this was recorded", and the UI shows
-- nothing for it.
--
--
-- RLS. rescue_cases has RLS enabled with the policy set recorded in
-- 003_rls_lockdown.sql section 3. ADD COLUMN does not alter policies, and all
-- three are row-level with USING/WITH CHECK true, so they cover new columns
-- without change. Writes come from create_case as service_role (bypasses RLS);
-- the staff board reads as `authenticated` via the SELECT policy. Table-level
-- SELECT grants extend to new columns; column-level grants would NOT, so the
-- second query below checks for those.
--
-- VERIFY, do not assume. Run BEFORE and AFTER applying, and diff:
--
--   SELECT policyname, cmd, roles, qual, with_check
--   FROM pg_policies WHERE tablename = 'rescue_cases' ORDER BY policyname;
--
--   SELECT grantee, privilege_type, column_name
--   FROM information_schema.column_privileges
--   WHERE table_name = 'rescue_cases'
--     AND column_name IN ('urgency', 'urgency_reason', 'urgency_source')
--   ORDER BY grantee, column_name, privilege_type;
--
-- The pg_policies output must be identical. In the column_privileges output,
-- `authenticated` must hold SELECT on urgency_reason and urgency_source exactly
-- as it does on urgency — if it has SELECT on urgency but not the new columns,
-- the board would read them back as missing.


ALTER TABLE rescue_cases
    ADD COLUMN IF NOT EXISTS urgency_reason text;

ALTER TABLE rescue_cases
    ADD COLUMN IF NOT EXISTS urgency_source text
        CONSTRAINT rescue_cases_urgency_source_known CHECK (
            urgency_source IN (
                'ai',
                'default_no_description',
                'default_classifier_error',
                'default_invalid_label'
            )
        );
