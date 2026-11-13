-- 031_case_supplies.sql
--
-- Supplies used on a rescue case (policy confirmed 2026-11-13). Apply after
-- 030_case_timeline_outcome.sql and 021_inventory_batch_costing.sql.
--
-- Staff who can issue stock (inventory:issue or inventory:manage) can issue
-- it to an open rescue case, the way they issue it to a program. The Stock
-- Out is costed from the batches it takes, as every Stock Out is (021), so a
-- case's supplies cost is the sum of its Stock Outs.
--
--   * Issue only. There are no returns from a case: what is used on an
--     animal is consumed. A mistake is undone with Reverse on the Stock page,
--     and the reversal carries the case (trigger below), so the case's cost
--     goes back down with it.
--   * Open cases only (Reported or In Treatment), like Active programs only.
--   * A program or a case, never both.
--   * No finance posting: as with programs, the money was spent when the
--     stock was bought (Stock In posts the expense).
--
-- Changes:
--   1. inventory_transactions.rescue_case_id, plus two columns for new rows:
--      created_at (so supplies sort among the case's notes on its timeline)
--      and recorded_by (who issued them, which a medical record needs).
--      recorded_by defaults to auth.uid(): staff requests reach the database
--      as the signed-in user, so it is filled without any function change;
--      service_role writes leave it NULL. Rows already there stay NULL in
--      both rather than all getting today's time and nobody.
--   2. Reversals copy the case of the movement they undo (trigger), so
--      inventory_reverse_movement() is left as it is.
--   3. inventory_apply_movement() gains p_rescue_case_id as a 10th argument,
--      DEFAULT NULL, so every existing call still works. The 9-argument
--      version is dropped first: two versions differing only in a defaulted
--      argument would leave PostgREST unable to choose between them.
--
-- APPLY in the Supabase SQL editor: paste the whole file and press Run once.
-- Safe to re-run. Run the checks at the bottom afterwards.


-- ---------------------------------------------------------------------------
-- STEP 1. Columns
-- ---------------------------------------------------------------------------
ALTER TABLE public.inventory_transactions
    ADD COLUMN IF NOT EXISTS rescue_case_id UUID REFERENCES public.rescue_cases(id),
    ADD COLUMN IF NOT EXISTS created_at     TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS recorded_by    UUID;
-- Set after adding, so rows already there stay NULL.
ALTER TABLE public.inventory_transactions ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE public.inventory_transactions ALTER COLUMN recorded_by SET DEFAULT auth.uid();

ALTER TABLE public.inventory_transactions DROP CONSTRAINT IF EXISTS inventory_transactions_case_check;
ALTER TABLE public.inventory_transactions ADD CONSTRAINT inventory_transactions_case_check CHECK (
    rescue_case_id IS NULL
    OR (program_id IS NULL AND (transaction_type = 'Issue' OR reverses_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_inventory_transactions_case
    ON public.inventory_transactions (rescue_case_id) WHERE rescue_case_id IS NOT NULL;


-- ---------------------------------------------------------------------------
-- STEP 2. A reversal keeps the case of the movement it undoes
-- ---------------------------------------------------------------------------
-- Built with the live primary key's name, as 020 does for the reverse
-- function (it is transaction_id on the live database, id in init.sql).
DO $$
DECLARE
    v_pk text;
BEGIN
    SELECT a.attname INTO v_pk
      FROM pg_index i
      JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey)
     WHERE i.indrelid = 'public.inventory_transactions'::regclass
       AND i.indisprimary;

    EXECUTE format($sql$
        CREATE OR REPLACE FUNCTION public.inventory_reversal_keeps_case()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $fn$
        BEGIN
            IF NEW.reverses_id IS NOT NULL AND NEW.rescue_case_id IS NULL THEN
                SELECT rescue_case_id INTO NEW.rescue_case_id
                  FROM public.inventory_transactions
                 WHERE %1$I = NEW.reverses_id;
            END IF;
            RETURN NEW;
        END;
        $fn$
    $sql$, v_pk);
END $$;

DROP TRIGGER IF EXISTS trg_inventory_reversal_keeps_case ON public.inventory_transactions;
CREATE TRIGGER trg_inventory_reversal_keeps_case
    BEFORE INSERT ON public.inventory_transactions
    FOR EACH ROW EXECUTE FUNCTION public.inventory_reversal_keeps_case();


-- ---------------------------------------------------------------------------
-- STEP 3. inventory_apply_movement(): 021's rules, plus a rescue case
-- ---------------------------------------------------------------------------
DROP FUNCTION IF EXISTS public.inventory_apply_movement(integer, integer, integer, text, date, text, numeric, date, text);

CREATE OR REPLACE FUNCTION public.inventory_apply_movement(
    p_item_id          integer,
    p_program_id       integer,
    p_quantity         integer,
    p_transaction_type text,
    p_transaction_date date,
    p_notes            text DEFAULT NULL,
    p_unit_cost        numeric DEFAULT NULL,
    p_expire_date      date DEFAULT NULL,
    p_batch_number     text DEFAULT NULL,
    p_rescue_case_id   uuid DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    v_item           public.inventory_items%ROWTYPE;
    v_notes          text := nullif(trim(coalesce(p_notes, '')), '');
    v_batch_number   text := nullif(trim(coalesce(p_batch_number, '')), '');
    v_program_status text;
    v_case_status    text;
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

    -- 031: supplies used on a rescue case. Issue only (no returns from a
    -- case, confirmed 2026-11-13), never together with a program.
    IF p_rescue_case_id IS NOT NULL THEN
        IF p_transaction_type <> 'Issue' THEN
            RAISE EXCEPTION 'Supplies can only be issued to a rescue case. Undo a mistake with Reverse on the Stock page.';
        END IF;
        IF p_program_id IS NOT NULL THEN
            RAISE EXCEPTION 'Issue to a program or to a rescue case, not both.';
        END IF;
    END IF;

    IF p_transaction_type = 'Restock' THEN
        p_program_id := NULL;
    END IF;
    IF p_transaction_type = 'Return' AND p_program_id IS NULL THEN
        RAISE EXCEPTION 'Choose the program this stock is returned from. Stock that was never issued is added with Stock In.';
    END IF;
    IF p_transaction_type = 'Issue' AND p_program_id IS NULL AND p_rescue_case_id IS NULL
       AND v_notes IS NULL THEN
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

    IF p_rescue_case_id IS NOT NULL THEN
        SELECT status INTO v_case_status FROM public.rescue_cases WHERE id = p_rescue_case_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Rescue case not found' USING ERRCODE = 'P0002';
        END IF;
        IF v_case_status = 'Resolved' THEN
            RAISE EXCEPTION 'This case is resolved. Reopen it to record more supplies.';
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
         expire_date, previous_unit_cost, rescue_case_id)
    VALUES
        (p_item_id, p_program_id, p_quantity, p_transaction_type, p_transaction_date, v_notes,
         v_total_cost, p_expire_date,
         CASE WHEN p_transaction_type = 'Restock' THEN v_item.unit_cost END, p_rescue_case_id)
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
-- STEP 4. Who may run it (same as 021)
-- ---------------------------------------------------------------------------
REVOKE ALL ON FUNCTION public.inventory_apply_movement(integer, integer, integer, text, date, text, numeric, date, text, uuid)
    FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.inventory_apply_movement(integer, integer, integer, text, date, text, numeric, date, text, uuid)
    TO authenticated, service_role;

NOTIFY pgrst, 'reload schema';


-- ---------------------------------------------------------------------------
-- AFTER RUNNING: check
-- ---------------------------------------------------------------------------
-- 1. One movement function, now with 10 arguments. Expect one row, 10:
--      SELECT proname, pronargs FROM pg_proc WHERE proname = 'inventory_apply_movement';
-- 2. The new columns. Expect 3 rows:
--      SELECT column_name FROM information_schema.columns
--       WHERE table_name = 'inventory_transactions'
--         AND column_name IN ('rescue_case_id', 'created_at', 'recorded_by');
-- 3. The reversal trigger. Expect 1 row:
--      SELECT tgname FROM pg_trigger WHERE tgname = 'trg_inventory_reversal_keeps_case';
