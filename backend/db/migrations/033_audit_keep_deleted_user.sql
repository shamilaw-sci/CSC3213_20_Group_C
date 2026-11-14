-- 033_audit_keep_deleted_user.sql
--
-- Deleting a user must not rewrite the audit trail (policy confirmed
-- 2026-11-14).
--
-- system_audit_logs.user_id referenced users(id) ON DELETE SET NULL, so
-- deleting a user blanked user_id on every row they had written. user_id is
-- part of each row's hash (001_audit_hash_chain.sql), so those rows no longer
-- matched their stored hash and /api/admin/audit-logs/verify reported the
-- chain as tampered from the first of them onward. Every account deletion
-- broke the tamper-evidence, and it also erased who had done what.
--
-- The foreign key is dropped rather than changed: an audit row has to outlive
-- the account it names, and RESTRICT would make any user with audit history
-- impossible to delete. user_id keeps the deleted account's uuid. Nothing
-- reads it through the relationship; app/api/admin.py looks emails up
-- separately and already copes with a uuid that has no users row.
--
-- APPLY in the Supabase SQL editor. Safe to re-run.

DO $$
DECLARE
    fk text;
BEGIN
    FOR fk IN
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_attribute att
          ON att.attrelid = con.conrelid AND att.attnum = ANY (con.conkey)
        WHERE con.conrelid = 'public.system_audit_logs'::regclass
          AND con.contype = 'f'
          AND att.attname = 'user_id'
    LOOP
        EXECUTE format('ALTER TABLE public.system_audit_logs DROP CONSTRAINT %I', fk);
    END LOOP;
END $$;

COMMENT ON COLUMN public.system_audit_logs.user_id IS
    'Who performed the action. Deliberately not a foreign key (033): it keeps the uuid after the account is deleted, because it is hashed into the row.';
