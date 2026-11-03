-- 017_stock_in_price.sql
--
-- Stock In records the unit price actually paid.
--
-- Before this, every movement was costed at the item's stored unit_cost, so
-- the expense 013 posts for a Stock In was wrong whenever the supplier's
-- price had changed. inventory_apply_movement() (012) gains one optional
-- parameter, p_unit_cost:
--
--   * Stock In with a price: total_cost = quantity x that price, and the
--     item's stored unit_cost becomes that price (last price paid). Both
--     happen under the same row lock as the stock change.
--   * Stock In without a price: as before, the stored unit_cost.
--   * Issue and Return refuse a price. They are costed at the stored
--     unit_cost exactly as before (that is what programs.total_cost uses).
--
-- The parameter defaults to NULL, so a caller that does not send it gets
-- 012's behaviour unchanged. The function is dropped and re-created rather
-- than replaced: an extra defaulted parameter would otherwise leave two
-- overloads that PostgREST cannot choose between.
--
-- Needs 012 first. Independent of 013-016.
--
-- APPLY in the Supabase SQL editor: paste the whole file and press Run once.
-- Safe to re-run.

DROP FUNCTION IF EXISTS public.inventory_apply_movement(integer, integer, integer, text, date, text);

CREATE OR REPLACE FUNCTION public.inventory_apply_movement(
    p_item_id          integer,
    p_program_id       integer,
    p_quantity         integer,
    p_transaction_type text,
    p_transaction_date date,
    p_notes            text DEFAULT NULL,
    p_unit_cost        numeric DEFAULT NULL
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
    v_unit_cost numeric;
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
    IF p_unit_cost IS NOT NULL THEN
        IF p_transaction_type <> 'Restock' THEN
            RAISE EXCEPTION 'A unit price is only entered for Stock In.';
        END IF;
        IF p_unit_cost <= 0 OR p_unit_cost > 100000000 THEN
            RAISE EXCEPTION 'Unit price must be greater than 0.';
        END IF;
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

    -- The price paid on this Stock In, else the item's stored cost.
    v_unit_cost := coalesce(round(p_unit_cost, 2), v_item.unit_cost, 0);

    -- A Stock In at a price becomes the item's stored cost (last price paid).
    UPDATE public.inventory_items
       SET current_stock = v_new_stock,
           unit_cost = CASE WHEN p_unit_cost IS NULL THEN unit_cost ELSE v_unit_cost END
     WHERE id = p_item_id;

    -- Existing triggers on this table (programs.total_cost, and 013's Stock
    -- In expense, which reads total_cost) still run as before on this insert.
    INSERT INTO public.inventory_transactions
        (item_id, program_id, quantity, transaction_type, transaction_date, notes, total_cost)
    VALUES
        (p_item_id, p_program_id, p_quantity, p_transaction_type, p_transaction_date, v_notes,
         round(p_quantity * v_unit_cost, 2))
    RETURNING to_jsonb(inventory_transactions.*) INTO v_row;

    RETURN v_row || jsonb_build_object(
        'stock_before', coalesce(v_item.current_stock, 0),
        'stock_after',  v_new_stock
    );
END;
$$;

-- Callable by signed-in users only (the API calls it with the caller's
-- token). Never by anonymous visitors.
REVOKE ALL ON FUNCTION public.inventory_apply_movement(integer, integer, integer, text, date, text, numeric) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.inventory_apply_movement(integer, integer, integer, text, date, text, numeric) FROM anon;
GRANT EXECUTE ON FUNCTION public.inventory_apply_movement(integer, integer, integer, text, date, text, numeric) TO authenticated;
GRANT EXECUTE ON FUNCTION public.inventory_apply_movement(integer, integer, integer, text, date, text, numeric) TO service_role;

NOTIFY pgrst, 'reload schema';

-- After applying, check (expect one row, with seven arguments):
--   SELECT proname, pronargs FROM pg_proc WHERE proname = 'inventory_apply_movement';
