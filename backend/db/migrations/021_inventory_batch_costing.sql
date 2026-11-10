-- 021_inventory_batch_costing.sql
--
-- Stock Out is costed at the price of the batches it uses. Apply after
-- 020_inventory_batches.sql.
--
-- Before: a Stock Out was costed at the item's latest price. For example,
-- with 10 chains bought at 50 and 50 more at 100, issuing 10 cost 1,000.
-- Now it uses the batch that expires first (no expiry last, then the oldest),
-- so the same Stock Out costs 500 (10 x 50). Issuing 20 would cost
-- 10 x 50 + 10 x 100 = 1,500.
--
-- A Return goes back into the batches the program took from and is costed
-- at those batches' prices. Returning everything a program holds still
-- gives back exactly what it was charged.
--
-- Movements already recorded keep their cost. Reverse one and record it
-- again to re-cost it.
--
-- No tables change. Access is the same as 020: signed-in users and
-- service_role, never anonymous visitors.
--
-- APPLY in the Supabase SQL editor: paste the whole file and press Run once.
-- Safe to re-run. Run the checks at the bottom afterwards.
--
-- UNDO: re-run STEP 4 of 020_inventory_batches.sql.


-- ---------------------------------------------------------------------------
-- STEP 1. What a Stock Out or Return will cost, worked out before it is saved
-- ---------------------------------------------------------------------------

-- The cost of taking p_qty from the item's batches, in the order
-- inventory_batch_take() takes them. Called while the item row is locked,
-- so the batches cannot change in between.
CREATE OR REPLACE FUNCTION public.inventory_batch_take_cost(p_item_id integer, p_qty integer)
RETURNS numeric
LANGUAGE plpgsql
AS $$
DECLARE
    v_left  integer := p_qty;
    v_take  integer;
    v_cost  numeric := 0;
    v_batch record;
BEGIN
    FOR v_batch IN
        SELECT quantity_remaining, unit_cost FROM public.inventory_batches
         WHERE item_id = p_item_id AND quantity_remaining > 0
         ORDER BY expire_date NULLS LAST, received_date, id
    LOOP
        EXIT WHEN v_left <= 0;
        v_take := least(v_left, v_batch.quantity_remaining);
        v_cost := v_cost + v_take * coalesce(v_batch.unit_cost, 0);
        v_left := v_left - v_take;
    END LOOP;
    -- Any shortfall is refused later by inventory_batch_take().
    RETURN round(v_cost, 2);
END;
$$;

-- The cost of putting p_qty back into the given batches (as
-- inventory_batch_put() does). Units with no batch record (issued before
-- 020) are costed at p_fallback_unit_cost, the program's average price.
CREATE OR REPLACE FUNCTION public.inventory_batch_put_cost(
    p_item_id             integer,
    p_qty                 integer,
    p_pref_batches        integer[],
    p_pref_qty            integer[],
    p_fallback_unit_cost  numeric
)
RETURNS numeric
LANGUAGE plpgsql
AS $$
DECLARE
    v_left  integer := p_qty;
    v_put   integer;
    v_cost  numeric := 0;
    v_price numeric;
    i       integer;
BEGIN
    IF p_pref_batches IS NOT NULL THEN
        FOR i IN 1 .. coalesce(array_length(p_pref_batches, 1), 0) LOOP
            EXIT WHEN v_left <= 0;
            v_put := least(v_left, p_pref_qty[i]);
            CONTINUE WHEN v_put <= 0;
            SELECT unit_cost INTO v_price FROM public.inventory_batches
             WHERE id = p_pref_batches[i] AND item_id = p_item_id;
            CONTINUE WHEN NOT FOUND;
            v_cost := v_cost + v_put * coalesce(v_price, 0);
            v_left := v_left - v_put;
        END LOOP;
    END IF;
    IF v_left > 0 THEN
        v_cost := v_cost + v_left * coalesce(p_fallback_unit_cost, 0);
    END IF;
    RETURN round(v_cost, 2);
END;
$$;


-- ---------------------------------------------------------------------------
-- STEP 2. inventory_apply_movement(): 020's rules, with batch prices
-- ---------------------------------------------------------------------------
-- Same 9 arguments as 020, so it is replaced in place.
CREATE OR REPLACE FUNCTION public.inventory_apply_movement(
    p_item_id          integer,
    p_program_id       integer,
    p_quantity         integer,
    p_transaction_type text,
    p_transaction_date date,
    p_notes            text DEFAULT NULL,
    p_unit_cost        numeric DEFAULT NULL,
    p_expire_date      date DEFAULT NULL,
    p_batch_number     text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    v_item           public.inventory_items%ROWTYPE;
    v_notes          text := nullif(trim(coalesce(p_notes, '')), '');
    v_batch_number   text := nullif(trim(coalesce(p_batch_number, '')), '');
    v_program_status text;
    v_held           integer;
    v_held_cost      numeric;
    v_new_stock      integer;
    v_unit_cost      numeric;
    v_total_cost     numeric;
    v_row            jsonb;
    v_movement_id    integer;
    v_pref_batches   integer[];
    v_pref_qty       integer[];
    v_batch_id       integer;
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
    IF v_batch_number IS NOT NULL THEN
        IF p_transaction_type <> 'Restock' THEN
            RAISE EXCEPTION 'A batch number is only entered for Stock In.';
        END IF;
        IF length(v_batch_number) > 100 THEN
            RAISE EXCEPTION 'Batch number can be at most 100 characters.';
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
        IF p_transaction_type = 'Issue'
           AND lower(trim(coalesce(v_program_status, 'Active'))) NOT IN ('active', 'in progress') THEN
            RAISE EXCEPTION 'Stock can only be issued to an Active program. This program is %.',
                v_program_status;
        END IF;
    END IF;

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
        -- Back into the batches this program took from, most recent first,
        -- and costed at those batches' prices.
        SELECT array_agg(batch_id ORDER BY last_id DESC), array_agg(held ORDER BY last_id DESC)
          INTO v_pref_batches, v_pref_qty
          FROM (SELECT batch_id, sum(-direction * quantity) AS held, max(id) AS last_id
                  FROM public.inventory_batch_allocations
                 WHERE item_id = p_item_id AND program_id = p_program_id
                 GROUP BY batch_id) t
         WHERE held > 0;
        IF p_quantity = v_held THEN
            -- Everything comes back: the program's cost goes back to 0.
            v_total_cost := greatest(round(v_held_cost, 2), 0);
        ELSE
            v_total_cost := public.inventory_batch_put_cost(
                p_item_id, p_quantity, v_pref_batches, v_pref_qty, v_held_cost / v_held);
            v_total_cost := least(greatest(v_total_cost, 0), greatest(round(v_held_cost, 2), 0));
        END IF;
    ELSIF p_transaction_type = 'Issue' THEN
        -- Costed at the prices of the batches it takes (soonest expiry first).
        v_total_cost := public.inventory_batch_take_cost(p_item_id, p_quantity);
    ELSE
        v_total_cost := round(p_quantity * v_unit_cost, 2);
    END IF;

    UPDATE public.inventory_items
       SET current_stock = v_new_stock,
           unit_cost = CASE WHEN p_unit_cost IS NULL THEN unit_cost ELSE v_unit_cost END
     WHERE id = p_item_id;

    INSERT INTO public.inventory_transactions
        (item_id, program_id, quantity, transaction_type, transaction_date, notes, total_cost,
         expire_date, previous_unit_cost)
    VALUES
        (p_item_id, p_program_id, p_quantity, p_transaction_type, p_transaction_date, v_notes,
         v_total_cost, p_expire_date,
         CASE WHEN p_transaction_type = 'Restock' THEN v_item.unit_cost END)
    RETURNING to_jsonb(inventory_transactions.*) INTO v_row;

    -- The movement's own id, whatever the primary key column is called.
    v_movement_id := coalesce(v_row ->> 'id', v_row ->> 'transaction_id')::integer;

    IF p_transaction_type = 'Restock' THEN
        INSERT INTO public.inventory_batches
            (item_id, batch_number, expire_date, unit_cost, quantity_received, quantity_remaining,
             received_date, stock_in_id)
        VALUES
            (p_item_id,
             coalesce(v_batch_number, to_char(p_transaction_date, 'YYYYMMDD') || '-' || v_movement_id),
             p_expire_date, v_unit_cost, p_quantity, p_quantity, p_transaction_date, v_movement_id)
        RETURNING id INTO v_batch_id;
        INSERT INTO public.inventory_batch_allocations
            (movement_id, batch_id, item_id, program_id, direction, quantity)
        VALUES (v_movement_id, v_batch_id, p_item_id, NULL, 1, p_quantity);
        v_row := v_row || jsonb_build_object(
            'batch_number',
            coalesce(v_batch_number, to_char(p_transaction_date, 'YYYYMMDD') || '-' || v_movement_id));
    ELSIF p_transaction_type = 'Issue' THEN
        PERFORM public.inventory_batch_take(p_item_id, p_quantity, v_movement_id, p_program_id);
    ELSE
        PERFORM public.inventory_batch_put(p_item_id, p_quantity, v_movement_id, p_program_id,
                                           v_pref_batches, v_pref_qty);
    END IF;

    PERFORM public.inventory_refresh_expiry(p_item_id);

    RETURN v_row || jsonb_build_object(
        'stock_before', coalesce(v_item.current_stock, 0),
        'stock_after',  v_new_stock
    );
END;
$$;




-- ---------------------------------------------------------------------------
-- STEP 3. Who may run the functions (same as 020)
-- ---------------------------------------------------------------------------
REVOKE ALL ON FUNCTION public.inventory_apply_movement(integer, integer, integer, text, date, text, numeric, date, text)
    FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.inventory_apply_movement(integer, integer, integer, text, date, text, numeric, date, text)
    TO authenticated, service_role;
REVOKE ALL ON FUNCTION public.inventory_batch_take_cost(integer, integer) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.inventory_batch_take_cost(integer, integer) TO authenticated, service_role;
REVOKE ALL ON FUNCTION public.inventory_batch_put_cost(integer, integer, integer[], integer[], numeric) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.inventory_batch_put_cost(integer, integer, integer[], integer[], numeric) TO authenticated, service_role;

NOTIFY pgrst, 'reload schema';


-- ---------------------------------------------------------------------------
-- AFTER RUNNING: check (screenshot each result)
-- ---------------------------------------------------------------------------
-- 1. The two new helper functions exist. Expect 2 rows:
--      SELECT proname FROM pg_proc
--       WHERE proname IN ('inventory_batch_take_cost', 'inventory_batch_put_cost');
-- 2. Still one movement function with 9 arguments. Expect one row, 9:
--      SELECT proname, pronargs FROM pg_proc WHERE proname = 'inventory_apply_movement';
-- 3. Each item's batches, with price and value. Expect your batches listed:
--      SELECT i.item_name, b.batch_number, b.quantity_remaining, b.unit_cost,
--             b.quantity_remaining * b.unit_cost AS value
--        FROM inventory_batches b JOIN inventory_items i ON i.id = b.item_id
--       WHERE b.quantity_remaining > 0
--       ORDER BY i.item_name, b.expire_date NULLS LAST, b.received_date, b.id;
