-- 012_inventory_integrity.sql
--
-- Inventory stock integrity. Makes every stock movement one locked,
-- all-or-nothing step and adds the database-level rules behind it.
--
-- Numbered 012 because 010 and 011 are used by the programmes branch.
--
-- What this does:
--   1. inventory_apply_movement(): a NEW function the API calls for every
--      Issue, Return and Stock In. It locks the item row, checks the rules,
--      updates current_stock and inserts the movement in one transaction.
--      It does not replace process_inventory_transaction(), which is left
--      exactly as it is.
--   2. current_stock can never be below 0.
--   3. A movement quantity must be above 0.
--   4. Item names are unique, ignoring case and surrounding spaces.
--
-- Safe to apply before or after the matching API change: the API falls back
-- to its own compare-and-set path while this function does not exist.
-- Safe to re-run.
--
-- APPLY in the Supabase SQL editor (whole file, one run).
--
-- Check first (read-only). Rows returned here are reported and left alone
-- by steps 2-4; fix them, then re-run this file to switch the rule on fully:
--   SELECT id, item_name, current_stock FROM inventory_items WHERE current_stock < 0;
--   SELECT * FROM inventory_transactions WHERE quantity <= 0;
--   SELECT lower(trim(item_name)) AS name, count(*) FROM inventory_items
--    GROUP BY 1 HAVING count(*) > 1;

-- ---------------------------------------------------------------------------
-- 1. One locked, all-or-nothing movement
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.inventory_apply_movement(
    p_item_id          integer,
    p_program_id       integer,
    p_quantity         integer,
    p_transaction_type text,
    p_transaction_date date,
    p_notes            text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
-- SECURITY INVOKER (the default): runs with the caller's own rights, so the
-- existing row level security on both tables still applies.
AS $$
DECLARE
    v_item      public.inventory_items%ROWTYPE;
    v_notes     text := nullif(trim(coalesce(p_notes, '')), '');
    v_held      integer;
    v_new_stock integer;
    v_row       jsonb;
BEGIN
    -- Rules that need no data. The API checks these too; repeating them here
    -- means nothing can skip them by calling the function directly.
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

    -- Stock In never belongs to a program.
    IF p_transaction_type = 'Restock' THEN
        p_program_id := NULL;
    END IF;
    IF p_transaction_type = 'Return' AND p_program_id IS NULL THEN
        RAISE EXCEPTION 'Choose the program this stock is returned from. Stock that was never issued is added with Stock In.';
    END IF;
    IF p_transaction_type = 'Issue' AND p_program_id IS NULL AND v_notes IS NULL THEN
        RAISE EXCEPTION 'A stock adjustment needs a reason in the notes.';
    END IF;

    -- Lock the item. A second movement on the same item waits here until
    -- this one commits, so two requests can never both pass the stock check
    -- against the same starting number.
    SELECT * INTO v_item FROM public.inventory_items WHERE id = p_item_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Item not found' USING ERRCODE = 'P0002';
    END IF;

    IF p_program_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM public.programs WHERE id = p_program_id) THEN
        RAISE EXCEPTION 'Program not found' USING ERRCODE = 'P0002';
    END IF;

    -- A return cannot be more than the program still holds. Counted after
    -- the lock, so two returns at once cannot both use the same balance.
    IF p_transaction_type = 'Return' THEN
        SELECT coalesce(sum(CASE transaction_type
                                WHEN 'Issue'  THEN quantity
                                WHEN 'Return' THEN -quantity
                                ELSE 0 END), 0)
          INTO v_held
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

    UPDATE public.inventory_items SET current_stock = v_new_stock WHERE id = p_item_id;

    -- Cost at the item's current unit cost. Existing triggers on this table
    -- (for example the one keeping programs.total_cost up to date) still run
    -- as before on this insert.
    INSERT INTO public.inventory_transactions
        (item_id, program_id, quantity, transaction_type, transaction_date, notes, total_cost)
    VALUES
        (p_item_id, p_program_id, p_quantity, p_transaction_type, p_transaction_date, v_notes,
         round(p_quantity * coalesce(v_item.unit_cost, 0), 2))
    RETURNING to_jsonb(inventory_transactions.*) INTO v_row;

    RETURN v_row || jsonb_build_object(
        'stock_before', coalesce(v_item.current_stock, 0),
        'stock_after',  v_new_stock
    );
END;
$$;

-- Callable by signed-in users only (the API calls it with the caller's
-- token). Never by anonymous visitors.
REVOKE ALL ON FUNCTION public.inventory_apply_movement(integer, integer, integer, text, date, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.inventory_apply_movement(integer, integer, integer, text, date, text) FROM anon;
GRANT EXECUTE ON FUNCTION public.inventory_apply_movement(integer, integer, integer, text, date, text) TO authenticated;
GRANT EXECUTE ON FUNCTION public.inventory_apply_movement(integer, integer, integer, text, date, text) TO service_role;

-- ---------------------------------------------------------------------------
-- 2-3. Stock never below 0; quantities above 0
-- ---------------------------------------------------------------------------
-- Added NOT VALID first: it applies to every new write straight away,
-- whatever the old rows look like. VALIDATE then checks the old rows too;
-- if some break the rule, a notice names the check above and the rule stays
-- on for new writes.
ALTER TABLE public.inventory_items
    DROP CONSTRAINT IF EXISTS inventory_items_stock_not_negative;
ALTER TABLE public.inventory_items
    ADD CONSTRAINT inventory_items_stock_not_negative CHECK (current_stock >= 0) NOT VALID;

ALTER TABLE public.inventory_transactions
    DROP CONSTRAINT IF EXISTS inventory_transactions_quantity_positive;
ALTER TABLE public.inventory_transactions
    ADD CONSTRAINT inventory_transactions_quantity_positive CHECK (quantity > 0) NOT VALID;

DO $$
BEGIN
    BEGIN
        ALTER TABLE public.inventory_items VALIDATE CONSTRAINT inventory_items_stock_not_negative;
    EXCEPTION WHEN check_violation THEN
        RAISE NOTICE 'Some items have negative stock. New writes are already blocked; correct those rows, then re-run this file.';
    END;
    BEGIN
        ALTER TABLE public.inventory_transactions VALIDATE CONSTRAINT inventory_transactions_quantity_positive;
    EXCEPTION WHEN check_violation THEN
        RAISE NOTICE 'Some movements have a quantity of 0 or less. New writes are already blocked; correct those rows, then re-run this file.';
    END;
END $$;

-- ---------------------------------------------------------------------------
-- 4. Unique item names (ignoring case and surrounding spaces)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.inventory_items
         GROUP BY lower(trim(item_name)) HAVING count(*) > 1
    ) THEN
        RAISE NOTICE 'Duplicate item names exist, so the unique index was not created. Merge or rename them, then re-run this file.';
    ELSE
        CREATE UNIQUE INDEX IF NOT EXISTS inventory_items_name_unique
            ON public.inventory_items (lower(trim(item_name)));
    END IF;
END $$;

-- After applying, check:
--   SELECT proname FROM pg_proc WHERE proname = 'inventory_apply_movement';
--   SELECT conname, convalidated FROM pg_constraint
--    WHERE conname IN ('inventory_items_stock_not_negative', 'inventory_transactions_quantity_positive');
--   SELECT indexname FROM pg_indexes WHERE indexname = 'inventory_items_name_unique';
