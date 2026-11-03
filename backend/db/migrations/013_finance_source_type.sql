-- 013_finance_source_type.sql
--
-- Records where each finance transaction came from, and posts the cost of
-- stock bought (Stock In) to the finance ledger as an Expense.
--
-- Covers manual, stock_in and (allowed, written later) donation. Payroll
-- rows are not changed by this file.
--
-- Additive only:
--   * One new column on financial_transactions. program_id is unchanged and
--     still links a transaction to its program whenever there is one.
--   * One new trigger on inventory_transactions for Stock In ('Restock').
--   * No existing function, trigger, policy or column is changed.
--     approve_payroll_run(), inventory_apply_movement() and the New
--     Transaction form are left exactly as they are.
--   * Stock Out (Issue) and Return stay inventory-only.
--
-- APPLY in the Supabase SQL editor: paste the whole file and press Run once.
-- Safe to re-run.

-- ---------------------------------------------------------------------------
-- STEP 1. The new required column
-- ---------------------------------------------------------------------------
-- NOT NULL DEFAULT 'manual' gives every existing row 'manual' at once, and
-- keeps every existing insert (the New Transaction form, payroll approval)
-- working without sending the column.
--
-- Payroll is not handled here: no row is re-tagged as 'payroll' and the
-- payroll_runs table and approve_payroll_run() are not touched. That is
-- left to the payroll owner.
ALTER TABLE public.financial_transactions
    ADD COLUMN IF NOT EXISTS source_type VARCHAR(20) NOT NULL DEFAULT 'manual';

-- ---------------------------------------------------------------------------
-- STEP 2. Only these four values are allowed
-- ---------------------------------------------------------------------------
ALTER TABLE public.financial_transactions
    DROP CONSTRAINT IF EXISTS financial_transactions_source_type_check;
ALTER TABLE public.financial_transactions
    ADD CONSTRAINT financial_transactions_source_type_check
    CHECK (source_type IN ('donation', 'stock_in', 'payroll', 'manual'));

COMMENT ON COLUMN public.financial_transactions.source_type IS
    'Where the row came from: donation, stock_in, payroll or manual (the default).';

-- ---------------------------------------------------------------------------
-- STEP 3. Stock In -> one Expense in finance
-- ---------------------------------------------------------------------------
-- Fires after every new inventory_transactions row. Only 'Restock' (Stock In)
-- rows post to finance; Issue and Return are ignored. The Expense is:
-- amount = the movement's total_cost, program_id NULL (General), status Cash,
-- dated the day of the stock movement, source_type 'stock_in'.
-- It runs in the same transaction as the stock movement, so if the finance
-- row cannot be written the stock movement is rolled back too.
CREATE OR REPLACE FUNCTION public.inventory_stock_in_to_ledger()
RETURNS trigger
LANGUAGE plpgsql
-- SECURITY INVOKER (the default): runs with the caller's own rights, so the
-- existing row level security still applies.
AS $$
BEGIN
    IF NEW.transaction_type = 'Restock' AND coalesce(NEW.total_cost, 0) > 0 THEN
        INSERT INTO public.financial_transactions
            (transaction_date, amount, transaction_type, status, program_id, is_restricted, source_type)
        VALUES
            (coalesce(NEW.transaction_date, CURRENT_DATE), NEW.total_cost,
             'Expense', 'Cash', NULL, FALSE, 'stock_in');
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS inventory_stock_in_to_ledger ON public.inventory_transactions;
CREATE TRIGGER inventory_stock_in_to_ledger
    AFTER INSERT ON public.inventory_transactions
    FOR EACH ROW
    EXECUTE FUNCTION public.inventory_stock_in_to_ledger();

-- ---------------------------------------------------------------------------
-- STEP 4. Make the API see the new column now
-- ---------------------------------------------------------------------------
NOTIFY pgrst, 'reload schema';

-- ---------------------------------------------------------------------------
-- AFTER RUNNING: check with these (screenshot the results)
-- ---------------------------------------------------------------------------
--   1. The column exists:
--      SELECT column_name, data_type, is_nullable, column_default
--        FROM information_schema.columns
--       WHERE table_name = 'financial_transactions' AND column_name = 'source_type';
--   2. Rows per source:
--      SELECT source_type, count(*) FROM financial_transactions GROUP BY 1;
--   3. The trigger exists:
--      SELECT tgname FROM pg_trigger WHERE tgname = 'inventory_stock_in_to_ledger';
