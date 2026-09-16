-- 003_rls_lockdown.sql
--
-- Closes the public anon key's read AND write access to eleven tables.
--
-- WHY THIS IS URGENT, not housekeeping. NEXT_PUBLIC_SUPABASE_ANON_KEY ships in
-- the browser bundle, so it is public by construction. Probed against the live
-- REST API with that key (backend/scripts/audit_rls.py), eleven of thirteen
-- tables were fully readable and writable by anyone:
--
--   employee_profile        14 rows readable - NIC (national identity number)
--                           and base_salary for every employee
--   users                   56 rows readable - emails and role assignments
--                           (password_hash is NULL in all 56, so no credential
--                           material was exposed)
--   payroll_ledger          net pay per employee
--   financial_transactions  the whole ledger, WRITABLE
--   system_audit_logs       the entire audit trail, WRITABLE
--   plus attendance_log, inventory_items, inventory_transactions,
--   program_assignments, programs, roles
--
-- The writable audit log is the worst of it. The hash chain still detects
-- mutation of existing rows, but anyone could APPEND. A forged row chains onto
-- the real head and subsequent genuine rows chain onto the forgery, so the
-- chain stays internally valid while containing fabricated events — the
-- tamper-evidence property survives in the narrow sense and fails in the
-- practical one. Hence it is locked first: system_audit_logs' old_payload /
-- new_payload are JSONB snapshots of rows from every other table, so leaving it
-- open would make locking the other ten partly cosmetic.
--
--
-- WHY A PERMISSIVE `authenticated` POLICY IS THE RIGHT SHAPE.
--
-- SUPABASE_KEY in backend/.env is the service_role key, not the anon key. So:
--
--   get_public_supabase()               -> service_role -> bypasses RLS
--   get_supabase(request), no token     -> service_role -> bypasses RLS
--   get_supabase(request), with token   -> role `authenticated` -> RLS APPLIES
--
-- Every public endpoint therefore runs as service_role and is untouched by this
-- migration. Only the authenticated staff path and direct anon access to
-- PostgREST are affected. Real authorization already lives in FastAPI's
-- require_permission(); encoding the role matrix in SQL as well would make
-- app/core/permissions.py one of three places that must agree, and a policy
-- that looks like authorization but merely duplicates it is worse than an
-- honest permissive one.
--
-- This is also not a new convention. rescue_cases and outbreak_zones already
-- carry exactly this shape (anon denied or narrowly filtered, `authenticated`
-- permissive) — it was applied to two tables of thirteen and never finished.
--
-- Measured before writing this: `authenticated` currently sees every row of
-- every table listed here. A permissive policy is therefore a provably
-- zero-behaviour-change migration for staff; only anon loses access.
--
-- FORCE ROW LEVEL SECURITY is deliberately NOT used. service_role bypasses RLS
-- via the BYPASSRLS role attribute rather than via table ownership, so FORCE
-- would add no protection against anything while risking the owner's access.


-- ---------------------------------------------------------------------------
-- 1. system_audit_logs — append-only
-- ---------------------------------------------------------------------------
--
-- SELECT and INSERT only. No UPDATE or DELETE policy is created, so both are
-- denied to `authenticated`. Verified against the codebase before relying on
-- it: app/core/audit.py and app/api/admin.py are the only readers and writers,
-- and between them they only ever SELECT and INSERT. Withholding UPDATE and
-- DELETE therefore costs nothing and makes append-only an enforced property
-- rather than a convention.
--
-- Both policies are required, and the SELECT one is the subtle half.
-- log_audit_action() runs on the CALLER's client, which for staff endpoints is
-- the authenticated one. It first SELECTs the previous row's hash to chain
-- onto. Without a SELECT policy that read returns empty, prev_hash silently
-- falls through to GENESIS, and every subsequent row starts a fresh chain —
-- the log keeps writing, looks healthy, and forks into unverifiable fragments.
-- Without the INSERT policy the write fails and audit.py's fail-soft `except`
-- swallows it, so audit logging simply stops with nothing surfacing anywhere.

ALTER TABLE public.system_audit_logs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS system_audit_logs_authenticated_read ON public.system_audit_logs;
CREATE POLICY system_audit_logs_authenticated_read
    ON public.system_audit_logs
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS system_audit_logs_authenticated_append ON public.system_audit_logs;
CREATE POLICY system_audit_logs_authenticated_append
    ON public.system_audit_logs
    FOR INSERT TO authenticated
    WITH CHECK (true);


-- ---------------------------------------------------------------------------
-- 2. The remaining ten tables — permissive for staff, closed to anon
-- ---------------------------------------------------------------------------
--
-- The policy body is identical for all ten by design, so the reviewable part is
-- the table list itself rather than ten copies of the same four lines. No anon
-- policy is created anywhere: RLS defaults to deny, so enabling it is what
-- closes both the read exposure and the forged-row write vector in one step.
--
-- `users` and `roles` are deliberately permissive rather than self-scoped.
-- app/api/admin.py reads system_audit_logs with an embedded
-- users(email, roles(role_name)) join, and PostgREST applies RLS to embedded
-- resources independently — a restrictive policy there would make that join
-- silently return NULL for the embedded object rather than raising, quietly
-- blanking out the audit viewer's attribution column.

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'employee_profile',
        'users',
        'payroll_ledger',
        'financial_transactions',
        'attendance_log',
        'inventory_items',
        'inventory_transactions',
        'program_assignments',
        'programs',
        'roles'
    ]
    LOOP
        EXECUTE format(
            'ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);

        -- Idempotent: re-running the migration replaces its own policy rather
        -- than failing on the duplicate name.
        EXECUTE format(
            'DROP POLICY IF EXISTS %I ON public.%I', t || '_authenticated_all', t);

        EXECUTE format(
            'CREATE POLICY %I ON public.%I '
            'FOR ALL TO authenticated USING (true) WITH CHECK (true)',
            t || '_authenticated_all', t);
    END LOOP;
END $$;


-- ---------------------------------------------------------------------------
-- 3. rescue_cases and outbreak_zones — deliberately NOT touched
-- ---------------------------------------------------------------------------
--
-- Both already have RLS enabled and correct policies. Reproduced here from
-- pg_policies so the current state is recorded in version control, since this
-- project's policies otherwise exist only in the Supabase dashboard and have
-- never been visible to code review:
--
--   rescue_cases
--     "authenticated staff can select cases"   SELECT authenticated  USING true
--     "authenticated staff can update cases"   UPDATE authenticated  USING true
--     "public can insert cases"                INSERT {anon,authenticated}
--                                                     WITH CHECK true
--   outbreak_zones
--     "authenticated staff can view all outbreak zones"  SELECT authenticated
--     "authenticated staff can insert outbreak zones"    INSERT authenticated
--     "authenticated staff can update outbreak zones"    UPDATE authenticated
--     "public can view active outbreak zones"            SELECT anon
--                                                          USING is_active
--
-- The anon INSERT on rescue_cases is "public can insert cases" above, and it is
-- preserved by this migration doing nothing to it. An earlier draft of this
-- file re-declared it under a new name for the sake of version control; that
-- was dropped because two policies granting the same thing is worse to
-- maintain than one, and the comment above records it just as well.
--
-- MORE IMPORTANTLY, that draft also added FOR ALL to rescue_cases for
-- `authenticated`, which would have been a mistake in the opposite direction
-- from the rest of this migration. rescue_cases has SELECT, UPDATE and INSERT
-- policies and NO DELETE policy, so no one but service_role can currently
-- delete a case. FOR ALL would have granted authenticated DELETE — widening
-- access inside a migration whose purpose is to narrow it.
--
-- That reasoning does not apply to the ten tables in section 2. RLS is
-- currently disabled on those, so Supabase's default grants already give
-- `authenticated` full access including DELETE; FOR ALL preserves their status
-- quo exactly rather than extending it. The difference is only that
-- rescue_cases already had RLS, and its existing policy set is narrower than
-- FOR ALL.
--
-- Neither table grants anon UPDATE or DELETE, confirmed from pg_policies rather
-- than inferred — the write probe in scripts/audit_rls.py tests INSERT only.
--
-- VERIFY, do not assume. This project has repeatedly shipped policies that read
-- correctly and behaved differently at runtime, so confirm against the live
-- REST API after applying:
--
--   python scripts/audit_rls.py --as-staff EMAIL PASSWORD
--       The `authenticated` column must be unchanged from before the migration.
--       Any table dropping to 0 is a broken feature, not a secured one.
--
--   python scripts/audit_rls.py
--       Every table must read 0 as anon and report `blocked` for insert, except
--       rescue_cases (insert still WRITABLE, by design above) and
--       outbreak_zones (reads 3, insert blocked).
--
--   Then log in through the running application, not just the REST layer.
--   get_current_user in app/core/security.py resolves every request's user by
--   reading users joined to roles with the CALLER's token, so it is the single
--   thing most likely to turn this fix into an outage.
