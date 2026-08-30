-- 001_audit_hash_chain.sql
--
-- Adds tamper-evident hash chaining to system_audit_logs.
--
-- Each row stores the SHA-256 digest of its own contents (`hash`) together
-- with the digest of the row before it (`prev_hash`). Altering any historical
-- row changes its digest and breaks every link after it, so tampering cannot
-- be hidden without rewriting the entire remainder of the table.
--
-- Both columns are nullable on purpose. Rows written before this migration
-- have no digest, and backfilling one would be a fabrication — we would be
-- asserting those rows are verified when nothing ever verified them. The
-- verification endpoint skips NULL-hash rows and reports how many it skipped.

ALTER TABLE system_audit_logs
    ADD COLUMN IF NOT EXISTS prev_hash text,
    ADD COLUMN IF NOT EXISTS hash      text;

-- The chain is walked in id order on every verification pass, and new rows
-- look up the most recent hash via ORDER BY id DESC LIMIT 1. The primary key
-- already indexes id, so no additional index is required.

COMMENT ON COLUMN system_audit_logs.prev_hash IS
    'SHA-256 of the preceding audit row, or the literal ''GENESIS'' when this row starts a chain.';

COMMENT ON COLUMN system_audit_logs.hash IS
    'SHA-256 over canonical JSON of {prev_hash, user_id, action_type, table_name, old_payload, new_payload, timestamp}, serialized with sorted keys.';
