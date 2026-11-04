-- 016_finance_source_links.sql
--
-- Follow-up to 013/014 (financial_transactions.source_type). Three things:
--
--   1. LINK. Each Stock In expense records the stock movement that created
--      it, in financial_transactions.inventory_transaction_id. A unique index
--      means one movement can never post two expenses. The ledger's void
--      warning uses the link to say which item, quantity and date to correct
--      in Inventory.
--   2. BACKFILL. Every Stock In recorded before 013 is posted to the ledger
--      now, linked the same way, so the balance includes all stock bought.
--      Expenses 013 already posted are linked first, so nothing is posted
--      twice, and re-running this file adds nothing.
--   3. RULES. payroll and stock_in rows are always Expense, and payroll rows
--      never have a program. A stock_in row MAY have a program, so restricted
--      program money can pay for stock later; nothing sets one yet (Stock In
--      itself never belongs to a program, see 012), so today every stock_in
--      row is still General.
--
-- Needs 013 and 014 first. 015 is used by the donations branch; this file
-- does not depend on it and can be applied before or after it.
--
-- inventory_transactions' primary key is `transaction_id` in the live
-- database but `id` in init.sql (see app/schemas/inventory.py). This file
-- looks the name up instead of assuming either.
--
-- APPLY in the Supabase SQL editor: paste the whole file and press Run once.
-- Safe to re-run.
--
-- Check first (read-only). Rows returned here break rule 3. They are
-- reported and left alone, and the rule still applies to every new write:
--   SELECT id, source_type, transaction_type, program_id
--     FROM financial_transactions
--    WHERE (source_type IN ('payroll', 'stock_in') AND transaction_type <> 'Expense')
--       OR (source_type = 'payroll' AND program_id IS NOT NULL);

-- ---------------------------------------------------------------------------
-- STEP 0. 013 must be applied
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = 'financial_transactions'
           AND column_name = 'source_type'
    ) THEN
        RAISE EXCEPTION 'Apply 013_finance_source_type.sql and 014_payroll_source_type.sql before this file.';
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- STEP 1. The link column, one expense per movement
-- ---------------------------------------------------------------------------
ALTER TABLE public.financial_transactions
    ADD COLUMN IF NOT EXISTS inventory_transaction_id INTEGER;

COMMENT ON COLUMN public.financial_transactions.inventory_transaction_id IS
    'The Stock In movement (inventory_transactions) this stock_in expense was posted for. NULL on every other row.';

-- Partial: every other row has NULL here, and only real links must be unique.
CREATE UNIQUE INDEX IF NOT EXISTS financial_transactions_inventory_transaction_unique
    ON public.financial_transactions (inventory_transaction_id)
    WHERE inventory_transaction_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- STEPS 2-5. Foreign key, trigger, link existing expenses, backfill
-- ---------------------------------------------------------------------------
-- One block, because each step needs the movement table's primary key name.
DO $$
DECLARE
    v_pk       text;
    v_linked   integer;
    v_posted   integer;
    v_unlinked integer;
    v_undated  integer;
BEGIN
    SELECT a.attname INTO v_pk
      FROM pg_index i
      JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey)
     WHERE i.indrelid = 'public.inventory_transactions'::regclass
       AND i.indisprimary;
    IF v_pk IS NULL THEN
        RAISE EXCEPTION 'inventory_transactions has no primary key, so expenses cannot be linked to it.';
    END IF;

    -- No Stock In can land while this runs, so a movement cannot slip in
    -- between linking and backfilling and end up posted twice. Readers are
    -- not blocked.
    LOCK TABLE public.inventory_transactions IN SHARE ROW EXCLUSIVE MODE;

    -- STEP 2. Foreign key. RESTRICT: a movement that has money posted
    -- against it cannot be deleted out from under the ledger.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'financial_transactions_inventory_transaction_fk'
    ) THEN
        EXECUTE format(
            'ALTER TABLE public.financial_transactions '
            'ADD CONSTRAINT financial_transactions_inventory_transaction_fk '
            'FOREIGN KEY (inventory_transaction_id) '
            'REFERENCES public.inventory_transactions (%I) ON DELETE RESTRICT',
            v_pk);
    END IF;

    -- STEP 3. 013's trigger function, now also recording the link. Same
    -- name, so 013's trigger keeps calling it. Still SECURITY INVOKER, still
    -- in the same transaction as the movement, still program NULL (General).
    EXECUTE format($sql$
        CREATE OR REPLACE FUNCTION public.inventory_stock_in_to_ledger()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $fn$
        BEGIN
            IF NEW.transaction_type = 'Restock' AND coalesce(NEW.total_cost, 0) > 0 THEN
                INSERT INTO public.financial_transactions
                    (transaction_date, amount, transaction_type, status, program_id,
                     is_restricted, source_type, inventory_transaction_id)
                VALUES
                    (coalesce(NEW.transaction_date, CURRENT_DATE), NEW.total_cost,
                     'Expense', 'Cash', NULL, FALSE, 'stock_in', NEW.%1$I);
            END IF;
            RETURN NEW;
        END;
        $fn$
    $sql$, v_pk);

    -- STEP 4. Link the expenses 013 already posted. 013 did not store the
    -- movement, so they are paired on what it did copy: the date and the
    -- amount. Equal date and amount are paired oldest first on both sides;
    -- 013 posted each expense in the same transaction as its movement, so
    -- ids rise together.
    EXECUTE format($sql$
        WITH movements AS (
            SELECT m.%1$I AS movement_id,
                   m.transaction_date,
                   round(m.total_cost, 2) AS amount,
                   row_number() OVER (PARTITION BY m.transaction_date, round(m.total_cost, 2)
                                      ORDER BY m.%1$I) AS n
              FROM public.inventory_transactions m
             WHERE m.transaction_type = 'Restock'
               AND coalesce(m.total_cost, 0) > 0
               AND NOT EXISTS (SELECT 1 FROM public.financial_transactions f
                                WHERE f.inventory_transaction_id = m.%1$I)
        ), expenses AS (
            SELECT f.id,
                   f.transaction_date,
                   f.amount,
                   row_number() OVER (PARTITION BY f.transaction_date, f.amount
                                      ORDER BY f.id) AS n
              FROM public.financial_transactions f
             WHERE f.source_type = 'stock_in'
               AND f.inventory_transaction_id IS NULL
        )
        UPDATE public.financial_transactions f
           SET inventory_transaction_id = mv.movement_id
          FROM expenses e
          JOIN movements mv
            ON mv.transaction_date = e.transaction_date
           AND mv.amount = e.amount
           AND mv.n = e.n
         WHERE f.id = e.id
    $sql$, v_pk);
    GET DIAGNOSTICS v_linked = ROW_COUNT;

    -- STEP 5. Backfill: every Stock In that still has no expense. Dated the
    -- day of the movement, so the balance is right at every past date.
    EXECUTE format($sql$
        INSERT INTO public.financial_transactions
            (transaction_date, amount, transaction_type, status, program_id,
             is_restricted, source_type, inventory_transaction_id)
        SELECT m.transaction_date, round(m.total_cost, 2), 'Expense', 'Cash', NULL,
               FALSE, 'stock_in', m.%1$I
          FROM public.inventory_transactions m
         WHERE m.transaction_type = 'Restock'
           AND coalesce(m.total_cost, 0) > 0
           AND m.transaction_date IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM public.financial_transactions f
                            WHERE f.inventory_transaction_id = m.%1$I)
         ORDER BY m.%1$I
    $sql$, v_pk);
    GET DIAGNOSTICS v_posted = ROW_COUNT;

    SELECT count(*) INTO v_unlinked
      FROM public.financial_transactions
     WHERE source_type = 'stock_in' AND inventory_transaction_id IS NULL;

    -- 013's trigger dated such a movement's expense CURRENT_DATE, so it
    -- cannot be paired by date and is not backfilled either.
    EXECUTE format($sql$
        SELECT count(*) FROM public.inventory_transactions m
         WHERE m.transaction_type = 'Restock'
           AND coalesce(m.total_cost, 0) > 0
           AND m.transaction_date IS NULL
           AND NOT EXISTS (SELECT 1 FROM public.financial_transactions f
                            WHERE f.inventory_transaction_id = m.%1$I)
    $sql$, v_pk) INTO v_undated;

    RAISE NOTICE 'Stock In expenses linked: %, past Stock Ins posted: %.', v_linked, v_posted;
    IF v_unlinked > 0 THEN
        RAISE NOTICE '% stock_in expense(s) could not be matched to a movement and stay unlinked. Check them with: SELECT * FROM financial_transactions WHERE source_type = ''stock_in'' AND inventory_transaction_id IS NULL;', v_unlinked;
    END IF;
    IF v_undated > 0 THEN
        RAISE NOTICE '% Stock In movement(s) have no date and were not posted. Give them a date, then re-run this file.', v_undated;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- STEP 6. Rules per source
-- ---------------------------------------------------------------------------
-- Added NOT VALID first, as in 012: it applies to every new write at once.
-- VALIDATE then checks the old rows; if some break a rule, a notice says so
-- and the rule stays on for new writes.
ALTER TABLE public.financial_transactions
    DROP CONSTRAINT IF EXISTS financial_transactions_source_rules;
ALTER TABLE public.financial_transactions
    ADD CONSTRAINT financial_transactions_source_rules CHECK (
        -- Money out: stock bought, salaries paid.
        (source_type NOT IN ('payroll', 'stock_in') OR transaction_type = 'Expense')
        -- Salaries are an organisation cost, never a program's.
        AND (source_type <> 'payroll' OR program_id IS NULL)
        -- Only a Stock In expense points at a stock movement.
        AND (inventory_transaction_id IS NULL OR source_type = 'stock_in')
    ) NOT VALID;

COMMENT ON CONSTRAINT financial_transactions_source_rules ON public.financial_transactions IS
    'payroll and stock_in rows are Expense; payroll rows have no program; only stock_in rows link to a stock movement.';

DO $$
BEGIN
    ALTER TABLE public.financial_transactions VALIDATE CONSTRAINT financial_transactions_source_rules;
EXCEPTION WHEN check_violation THEN
    RAISE NOTICE 'Some existing rows break the source rules (see the check query at the top of this file). New writes are already held to them; correct those rows, then re-run this file.';
END $$;

-- ---------------------------------------------------------------------------
-- STEP 7. Make the API see the new column and link now
-- ---------------------------------------------------------------------------
NOTIFY pgrst, 'reload schema';

-- ---------------------------------------------------------------------------
-- AFTER RUNNING: check (run each on its own and screenshot)
-- ---------------------------------------------------------------------------
--   1. Every Stock In has exactly one expense (expect no rows):
--      SELECT f.inventory_transaction_id, count(*) FROM financial_transactions f
--       WHERE f.inventory_transaction_id IS NOT NULL GROUP BY 1 HAVING count(*) > 1;
--   2. Rows per source:
--      SELECT source_type, count(*), sum(amount) FROM financial_transactions GROUP BY 1;
--   3. The rule is on and validated (convalidated = true):
--      SELECT conname, convalidated FROM pg_constraint
--       WHERE conname IN ('financial_transactions_source_rules',
--                         'financial_transactions_inventory_transaction_fk');
