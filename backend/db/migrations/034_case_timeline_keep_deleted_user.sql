-- 034_case_timeline_keep_deleted_user.sql
--
-- Deleting a user must not need to rewrite the case timeline (policy
-- confirmed 2026-11-14, as for the audit log in 033).
--
-- rescue_case_events.author_id and assignee_id referenced users(id)
-- ON DELETE SET NULL, but the table is append-only: its trigger refuses every
-- UPDATE (030_case_timeline_outcome.sql). Deleting a user who had ever
-- reported on, been assigned or noted a case made Postgres try to null those
-- columns, the trigger refused, and the whole delete failed with "rescue_case_events
-- is append-only". Nobody who had worked a case could be deleted.
--
-- Both foreign keys are dropped, so timeline rows keep the deleted account's
-- uuid, which is also what the timeline should say. The API already looks
-- people up separately (_people in app/api/rescue_cases.py) and shows a stored
-- id with no account as "Deleted user". rescue_cases.reported_by and
-- assigned_to were never foreign keys.
--
-- APPLY in the Supabase SQL editor. Safe to re-run.

DO $$
DECLARE
    fk text;
BEGIN
    FOR fk IN
        SELECT DISTINCT con.conname
        FROM pg_constraint con
        JOIN pg_attribute att
          ON att.attrelid = con.conrelid AND att.attnum = ANY (con.conkey)
        WHERE con.conrelid = 'public.rescue_case_events'::regclass
          AND con.contype = 'f'
          AND att.attname IN ('author_id', 'assignee_id')
    LOOP
        EXECUTE format('ALTER TABLE public.rescue_case_events DROP CONSTRAINT %I', fk);
    END LOOP;
END $$;
