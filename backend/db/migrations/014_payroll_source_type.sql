-- 014_payroll_source_type.sql
--
-- Marks payroll expenses in the finance ledger as source_type 'payroll'.
-- Needs 013_finance_source_type.sql (the source_type column) first.
--
-- Additive only. approve_payroll_run() (migration 007) is NOT edited: it
-- still inserts its Expense and then saves that row's id in
-- payroll_runs.finance_transaction_id. A new trigger on payroll_runs tags
-- the linked row 'payroll' the moment that link is written, in the same
-- transaction. Marking the expense paid (Settle) only changes its status,
-- so it stays 'payroll'.
--
-- APPLY in the Supabase SQL editor: paste the whole file and press Run once.
-- Safe to re-run.

-- ---------------------------------------------------------------------------
-- STEP 0 (optional, read-only): the existing rows STEP 1 will mark 'payroll'
-- ---------------------------------------------------------------------------
--   SELECT f.id, f.transaction_date, f.amount, f.status, r.payroll_month, r.payroll_year
--     FROM financial_transactions f
--     JOIN payroll_runs r ON r.finance_transaction_id = f.id
--    ORDER BY f.id;

-- ---------------------------------------------------------------------------
-- STEP 1. Existing payroll rows: the ones a payroll run links to
-- ---------------------------------------------------------------------------
UPDATE public.financial_transactions f
   SET source_type = 'payroll'
  FROM public.payroll_runs r
 WHERE r.finance_transaction_id = f.id
   AND f.source_type <> 'payroll';

-- ---------------------------------------------------------------------------
-- STEP 2. New approvals: tag the row as soon as the run links to it
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.payroll_run_tag_ledger_source()
RETURNS trigger
LANGUAGE plpgsql
-- SECURITY INVOKER (the default): runs with the caller's own rights, so the
-- existing row level security still applies.
AS $$
BEGIN
    IF NEW.finance_transaction_id IS NOT NULL
       AND NEW.finance_transaction_id IS DISTINCT FROM OLD.finance_transaction_id THEN
        UPDATE public.financial_transactions
           SET source_type = 'payroll'
         WHERE id = NEW.finance_transaction_id
           AND source_type <> 'payroll';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS payroll_run_tag_ledger_source ON public.payroll_runs;
CREATE TRIGGER payroll_run_tag_ledger_source
    AFTER UPDATE OF finance_transaction_id ON public.payroll_runs
    FOR EACH ROW
    EXECUTE FUNCTION public.payroll_run_tag_ledger_source();

-- ---------------------------------------------------------------------------
-- AFTER RUNNING: check (run each on its own and screenshot)
-- ---------------------------------------------------------------------------
--   1. SELECT tgname FROM pg_trigger WHERE tgname = 'payroll_run_tag_ledger_source';
--   2. SELECT source_type, count(*) FROM financial_transactions GROUP BY 1;
