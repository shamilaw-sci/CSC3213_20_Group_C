-- 002_restricted_funds.sql
--
-- Adds restricted (earmarked) fund accounting to financial_transactions.
--
-- A restricted transaction is a donation given for a named purpose: the donor
-- earmarked it for one program, and it may not be spent on anything else.
-- Tracking that requires two facts per income row — that it is restricted, and
-- which program it is restricted TO — so is_restricted is only meaningful in
-- combination with the existing program_id column.
--
-- NOTE ON ENFORCEMENT: db/init.sql has drifted from the live Supabase schema
-- (it still declares attendance_log/payroll_ledger/employee_profile in the
-- singular, and its financial_transactions status CHECK omits 'Voided' even
-- though the application writes that value). init.sql is not replayed against
-- the live database, so a constraint declared only there enforces nothing.
-- This migration is the channel that actually reaches the database.
--
-- The CHECK below is therefore written for documentation and for whoever
-- eventually reconciles init.sql with reality. The rule it describes is
-- ALSO enforced in the application layer — see FinancialTransactionBase in
-- app/schemas/finance.py — and that validator is what will actually reject a
-- malformed request today.

ALTER TABLE financial_transactions
    ADD COLUMN IF NOT EXISTS is_restricted BOOLEAN NOT NULL DEFAULT FALSE;

-- A restricted transaction with no program is incoherent: it asserts the money
-- is earmarked but not what it is earmarked for. DEFAULT FALSE means every
-- pre-existing row satisfies this without a backfill.
ALTER TABLE financial_transactions
    DROP CONSTRAINT IF EXISTS financial_transactions_restricted_requires_program;

ALTER TABLE financial_transactions
    ADD CONSTRAINT financial_transactions_restricted_requires_program
    CHECK (is_restricted = FALSE OR program_id IS NOT NULL);

-- The restricted-balance helper filters on (program_id, transaction_type,
-- is_restricted, status). program_id is the selective column and the one the
-- per-program lookup always pins, so it leads the index.
CREATE INDEX IF NOT EXISTS idx_financial_transactions_program_restricted
    ON financial_transactions (program_id, transaction_type, is_restricted);

COMMENT ON COLUMN financial_transactions.is_restricted IS
    'TRUE when a donor earmarked this income for the linked program. Restricted income may only be drawn down by expenses against that same program. Meaningless on Expense rows, which draw from restricted funds implicitly via program_id.';
