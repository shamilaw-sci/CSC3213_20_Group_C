-- 019_inventory_fixes.sql
--
-- Inventory fixes from the 2026-11-04 audit (I1, I3, I4, I7, I8). Apply after
-- 017_stock_in_price.sql.
--
-- What this does:
--   I1  Stock can only be ISSUED to an Active program. Returns are still
--       allowed from any program (leftovers come back after a program ends).
--   I3  A Return is costed at what that program paid for the stock it still
--       holds (its average issue cost), not at today's price. Before, a
--       price change between an Issue and its Return made the program's
--       total_cost drift.
--   I4  A new function, inventory_reverse_movement(), undoes a mistaken
--       movement by writing the opposite movement. Reversing a Stock In also
--       voids the expense it posted to the ledger (the link from 016).
--   I7  Each Stock In can record the expiry date of that batch
--       (inventory_transactions.expire_date). The item's expire_date then
--       shows the soonest expiry among the stock on hand.
--   I8  inventory_items.reorder_level: each item's own low-stock line. Empty
--       means the page's default (10).
--
-- Who may run the two functions: signed-in users (the API calls them with
-- the caller's token) and service_role, never anonymous visitors. Same as
-- 017. The API decides who may do what before it calls them.
--
-- APPLY in the Supabase SQL editor: paste the whole file and press Run once.
-- Safe to re-run. The API keeps working before this is applied, except for
-- the new features (reverse, batch expiry, reorder level), which say so.
--
-- UNDO: re-run 017_stock_in_price.sql (it drops nothing this file needs).
-- The new columns can stay.


-- ---------------------------------------------------------------------------
-- STEP 1. New columns
-- ---------------------------------------------------------------------------
ALTER TABLE public.inventory_items
    ADD COLUMN IF NOT EXISTS reorder_level INTEGER;
ALTER TABLE public.inventory_items
    DROP CONSTRAINT IF EXISTS inventory_items_reorder_level_check;
ALTER TABLE public.inventory_items
    ADD CONSTRAINT inventory_items_reorder_level_check
    CHECK (reorder_level IS NULL OR (reorder_level >= 0 AND reorder_level <= 100000));
COMMENT ON COLUMN public.inventory_items.reorder_level IS
    'Low stock when current_stock is below this. NULL = the default threshold (10).';

ALTER TABLE public.inventory_transactions
    ADD COLUMN IF NOT EXISTS expire_date DATE;
COMMENT ON COLUMN public.inventory_transactions.expire_date IS
    'Stock In only: expiry date of the batch received.';

ALTER TABLE public.inventory_transactions
    ADD COLUMN IF NOT EXISTS reverses_id INTEGER;
COMMENT ON COLUMN public.inventory_transactions.reverses_id IS
    'Set on a reversal: the movement it undoes. Each movement can be reversed once.';

CREATE UNIQUE INDEX IF NOT EXISTS inventory_transactions_reverses_unique
    ON public.inventory_transactions (reverses_id)
    WHERE reverses_id IS NOT NULL;


-- ---------------------------------------------------------------------------
-- STEP 2. inventory_apply_movement(): Active-only issues, Return costing,
-- batch expiry. Same rules as 017 otherwise.
-- ---------------------------------------------------------------------------
-- One more optional parameter (p_expire_date), so the 7-argument version is
-- dropped first; otherwise two versions would exist side by side.
DROP FUNCTION IF EXISTS public.inventory_apply_movement(integer, integer, integer, text, date, text, numeric);

CREATE OR REPLACE FUNCTION public.inventory_apply_movement(
    p_item_id          integer,
    p_program_id       integer,
    p_quantity         integer,
    p_transaction_type text,
    p_transaction_date date,
    p_notes            text DEFAULT NULL,
    p_unit_cost        numeric DEFAULT NULL,
    p_expire_date      date DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    v_item           public.inventory_items%ROWTYPE;
    v_notes          text := nullif(trim(coalesce(p_notes, '')), '');
    v_program_status text;
    v_held           integer;
    v_held_cost      numeric;
    v_new_stock      integer;
    v_unit_cost      numeric;
    v_total_cost     numeric;
    v_row            jsonb;
BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RAISE EXCEPTION 'Quantity must be greater than 0';
    END IF;
    IF p_transaction_type IS NULL OR p_transaction_type NOT IN ('Issue', 'Return', 'Restock') THEN
        RAISE EXCEPTION 'Unknown movement type: %', p_transaction_type;
    END IF;
    IF p_transaction_date IS NULL
       OR p_transaction_date > (now() AT TIME ZONE 'Asia/Colombo')::date THEN
        RAISE EXCEPTION 'Date cannot be in the future';
    END IF;
    IF p_unit_cost IS NOT NULL THEN
        IF p_transaction_type <> 'Restock' THEN
            RAISE EXCEPTION 'A unit price is only entered for Stock In.';
        END IF;
        IF p_unit_cost <= 0 OR p_unit_cost > 100000000 THEN
            RAISE EXCEPTION 'Unit price must be greater than 0.';
        END IF;
    END IF;
    IF p_expire_date IS NOT NULL THEN
        IF p_transaction_type <> 'Restock' THEN
            RAISE EXCEPTION 'An expiry date is only entered for Stock In.';
        END IF;
        IF p_expire_date < p_transaction_date THEN
            RAISE EXCEPTION 'This batch has already expired. Check the expiry date.';
        END IF;
    END IF;

    IF p_transaction_type = 'Restock' THEN
        p_program_id := NULL;
    END IF;
    IF p_transaction_type = 'Return' AND p_program_id IS NULL THEN
        RAISE EXCEPTION 'Choose the program this stock is returned from. Stock that was never issued is added with Stock In.';
    END IF;
    IF p_transaction_type = 'Issue' AND p_program_id IS NULL AND v_notes IS NULL THEN
        RAISE EXCEPTION 'A stock adjustment needs a reason in the notes.';
    END IF;

    SELECT * INTO v_item FROM public.inventory_items WHERE id = p_item_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Item not found' USING ERRCODE = 'P0002';
    END IF;

    IF p_program_id IS NOT NULL THEN
        SELECT status INTO v_program_status FROM public.programs WHERE id = p_program_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Program not found' USING ERRCODE = 'P0002';
        END IF;
        -- I1. 'In Progress' is the pre-010 spelling of Active.
        IF p_transaction_type = 'Issue'
           AND lower(trim(coalesce(v_program_status, 'Active'))) NOT IN ('active', 'in progress') THEN
            RAISE EXCEPTION 'Stock can only be issued to an Active program. This program is %.',
                v_program_status;
        END IF;
    END IF;

    -- What the program still holds of this item, and what it paid for it.
    IF p_transaction_type = 'Return' THEN
        SELECT coalesce(sum(CASE transaction_type
                                WHEN 'Issue'  THEN quantity
                                WHEN 'Return' THEN -quantity
                                ELSE 0 END), 0),
               coalesce(sum(CASE transaction_type
                                WHEN 'Issue'  THEN total_cost
                                WHEN 'Return' THEN -total_cost
                                ELSE 0 END), 0)
          INTO v_held, v_held_cost
          FROM public.inventory_transactions
         WHERE item_id = p_item_id AND program_id = p_program_id;
        IF p_quantity > v_held THEN
            RAISE EXCEPTION 'Cannot return %: that program holds only % of ''%'' (issued minus already returned).',
                p_quantity, greatest(v_held, 0), v_item.item_name;
        END IF;
    END IF;

    v_new_stock := coalesce(v_item.current_stock, 0)
                   + CASE WHEN p_transaction_type = 'Issue' THEN -p_quantity ELSE p_quantity END;
    IF v_new_stock < 0 THEN
        RAISE EXCEPTION 'Insufficient stock: only % of ''%'' available.',
            coalesce(v_item.current_stock, 0), v_item.item_name;
    END IF;

    v_unit_cost := coalesce(round(p_unit_cost, 2), v_item.unit_cost, 0);

    IF p_transaction_type = 'Return' THEN
        -- I3. Returning everything the program holds gives back exactly what
        -- it paid, so no rounding is left behind on the program.
        IF p_quantity = v_held THEN
            v_total_cost := greatest(round(v_held_cost, 2), 0);
        ELSE
            v_total_cost := greatest(round(p_quantity * v_held_cost / v_held, 2), 0);
        END IF;
    ELSE
        v_total_cost := round(p_quantity * v_unit_cost, 2);
    END IF;

    UPDATE public.inventory_items
       SET current_stock = v_new_stock,
           unit_cost = CASE WHEN p_unit_cost IS NULL THEN unit_cost ELSE v_unit_cost END,
           -- I7. The soonest expiry among the stock on hand. When the shelf
           -- was empty, the new batch's date replaces the old one.
           expire_date = CASE
               WHEN p_expire_date IS NULL THEN expire_date
               WHEN coalesce(v_item.current_stock, 0) = 0 OR expire_date IS NULL THEN p_expire_date
               ELSE least(expire_date, p_expire_date)
           END
     WHERE id = p_item_id;

    -- Triggers on this table (programs.total_cost, 013/016's Stock In
    -- expense) run as before.
    INSERT INTO public.inventory_transactions
        (item_id, program_id, quantity, transaction_type, transaction_date, notes, total_cost, expire_date)
    VALUES
        (p_item_id, p_program_id, p_quantity, p_transaction_type, p_transaction_date, v_notes,
         v_total_cost, p_expire_date)
    RETURNING to_jsonb(inventory_transactions.*) INTO v_row;

    RETURN v_row || jsonb_build_object(
        'stock_before', coalesce(v_item.current_stock, 0),
        'stock_after',  v_new_stock
    );
END;
$$;

REVOKE ALL ON FUNCTION public.inventory_apply_movement(integer, integer, integer, text, date, text, numeric, date)
    FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.inventory_apply_movement(integer, integer, integer, text, date, text, numeric, date)
    TO authenticated, service_role;


-- ---------------------------------------------------------------------------
-- STEP 3. I4: inventory_reverse_movement()
-- ---------------------------------------------------------------------------
-- Writes the opposite of one movement, dated today, at the same cost:
--   Stock In          -> stock goes back out (an adjustment with no program),
--                        and the expense it posted is voided in the ledger.
--   Stock Out         -> stock comes back (to the same program, if any).
--   Return            -> the stock goes out to that program again.
-- The original row is never changed or deleted, so the history stays
-- complete. A reversal cannot itself be reversed, and a movement can only be
-- reversed once (unique index above).
--
-- Built with EXECUTE because the primary key of inventory_transactions is
-- `id` in init.sql but may be `transaction_id` in the live database (016
-- handles it the same way).
DO $$
DECLARE
    v_pk text;
BEGIN
    SELECT a.attname INTO v_pk
      FROM pg_index i
      JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey)
     WHERE i.indrelid = 'public.inventory_transactions'::regclass
       AND i.indisprimary;
    IF v_pk IS NULL THEN
        RAISE EXCEPTION 'inventory_transactions has no primary key.';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'inventory_transactions_reverses_fk'
    ) THEN
        EXECUTE format(
            'ALTER TABLE public.inventory_transactions '
            'ADD CONSTRAINT inventory_transactions_reverses_fk '
            'FOREIGN KEY (reverses_id) REFERENCES public.inventory_transactions (%I) '
            'ON DELETE RESTRICT', v_pk);
    END IF;

    EXECUTE format($sql$
        CREATE OR REPLACE FUNCTION public.inventory_reverse_movement(
            p_transaction_id integer,
            p_reason         text
        )
        RETURNS jsonb
        LANGUAGE plpgsql
        AS $fn$
        DECLARE
            v_orig      public.inventory_transactions%%ROWTYPE;
            v_item      public.inventory_items%%ROWTYPE;
            v_reason    text := nullif(trim(coalesce(p_reason, '')), '');
            v_type      text;
            v_held      integer;
            v_new_stock integer;
            v_voided    integer := 0;
            v_row       jsonb;
        BEGIN
            IF v_reason IS NULL THEN
                RAISE EXCEPTION 'Give a reason for the reversal.';
            END IF;

            SELECT * INTO v_orig FROM public.inventory_transactions
             WHERE %1$I = p_transaction_id FOR UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Movement not found' USING ERRCODE = 'P0002';
            END IF;
            IF v_orig.reverses_id IS NOT NULL THEN
                RAISE EXCEPTION 'This movement is itself a reversal and cannot be reversed.';
            END IF;
            IF EXISTS (SELECT 1 FROM public.inventory_transactions WHERE reverses_id = p_transaction_id) THEN
                RAISE EXCEPTION 'This movement has already been reversed.';
            END IF;

            SELECT * INTO v_item FROM public.inventory_items WHERE id = v_orig.item_id FOR UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Item not found' USING ERRCODE = 'P0002';
            END IF;

            -- The opposite movement. 'Issue' takes stock out, the others add it.
            v_type := CASE v_orig.transaction_type
                          WHEN 'Restock' THEN 'Issue'
                          WHEN 'Issue'   THEN 'Return'
                          ELSE 'Issue' END;

            -- Undoing an Issue to a program: the program must still hold it all.
            IF v_orig.transaction_type = 'Issue' AND v_orig.program_id IS NOT NULL THEN
                SELECT coalesce(sum(CASE transaction_type
                                        WHEN 'Issue'  THEN quantity
                                        WHEN 'Return' THEN -quantity
                                        ELSE 0 END), 0)
                  INTO v_held
                  FROM public.inventory_transactions
                 WHERE item_id = v_orig.item_id AND program_id = v_orig.program_id;
                IF v_orig.quantity > v_held THEN
                    RAISE EXCEPTION 'Cannot reverse: that program now holds only %% of ''%%'' because some was already returned. Record a Return for what is left instead.',
                        greatest(v_held, 0), v_item.item_name;
                END IF;
            END IF;

            v_new_stock := coalesce(v_item.current_stock, 0)
                           + CASE WHEN v_type = 'Issue' THEN -v_orig.quantity ELSE v_orig.quantity END;
            IF v_new_stock < 0 THEN
                RAISE EXCEPTION 'Cannot reverse: only %% of ''%%'' is in stock, and the reversal takes out %%. Some of it has probably been issued already.',
                    coalesce(v_item.current_stock, 0), v_item.item_name, v_orig.quantity;
            END IF;

            UPDATE public.inventory_items SET current_stock = v_new_stock WHERE id = v_orig.item_id;

            INSERT INTO public.inventory_transactions
                (item_id, program_id, quantity, transaction_type, transaction_date, notes,
                 total_cost, reverses_id)
            VALUES
                (v_orig.item_id, v_orig.program_id, v_orig.quantity, v_type,
                 (now() AT TIME ZONE 'Asia/Colombo')::date,
                 left('Reversal of movement #' || p_transaction_id || ': ' || v_reason, 500),
                 coalesce(v_orig.total_cost, 0), p_transaction_id)
            RETURNING to_jsonb(inventory_transactions.*) INTO v_row;

            -- A Stock In's expense comes off the books with it.
            IF v_orig.transaction_type = 'Restock' THEN
                UPDATE public.financial_transactions
                   SET status = 'Voided'
                 WHERE inventory_transaction_id = p_transaction_id
                   AND status IS DISTINCT FROM 'Voided';
                GET DIAGNOSTICS v_voided = ROW_COUNT;
            END IF;

            RETURN v_row || jsonb_build_object(
                'stock_before',   coalesce(v_item.current_stock, 0),
                'stock_after',    v_new_stock,
                'ledger_voided',  v_voided
            );
        END;
        $fn$
    $sql$, v_pk);
END $$;

REVOKE ALL ON FUNCTION public.inventory_reverse_movement(integer, text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.inventory_reverse_movement(integer, text) TO authenticated, service_role;


-- ---------------------------------------------------------------------------
-- STEP 4. Make the REST API see the change now
-- ---------------------------------------------------------------------------
NOTIFY pgrst, 'reload schema';


-- ---------------------------------------------------------------------------
-- AFTER RUNNING: check (screenshot each result)
-- ---------------------------------------------------------------------------
-- 1. One movement function, with 8 arguments, and the reverse function.
--    Expect two rows: inventory_apply_movement 8, inventory_reverse_movement 2.
--      SELECT proname, pronargs FROM pg_proc
--       WHERE proname IN ('inventory_apply_movement', 'inventory_reverse_movement');
-- 2. Never anonymous. Expect false, true, true on both rows:
--      SELECT p.proname,
--             has_function_privilege('anon', p.oid, 'EXECUTE')          AS anon,
--             has_function_privilege('authenticated', p.oid, 'EXECUTE') AS authenticated,
--             has_function_privilege('service_role', p.oid, 'EXECUTE')  AS service_role
--        FROM pg_proc p
--       WHERE p.proname IN ('inventory_apply_movement', 'inventory_reverse_movement');
-- 3. The new columns exist. Expect three rows:
--      SELECT table_name, column_name FROM information_schema.columns
--       WHERE table_schema = 'public'
--         AND (column_name IN ('reorder_level', 'reverses_id')
--              OR (table_name = 'inventory_transactions' AND column_name = 'expire_date'));
