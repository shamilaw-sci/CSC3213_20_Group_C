-- 020_inventory_batches.sql
--
-- Stock batches, and the right price after undoing a Stock In. Apply after
-- 019_inventory_fixes.sql.
--
-- What this does:
--   O4  Every Stock In becomes a batch (inventory_batches) with its own batch
--       number, expiry date, price and quantity left. Stock Out takes from
--       the batch that expires first. A Return goes back into the batches
--       that program took from. inventory_batch_allocations records which
--       batch each movement used, so a reversal can undo it exactly. The
--       item's expire_date is now always the soonest expiry among batches
--       that still have stock.
--   O3  Reversing the item's latest Stock In also puts back the unit price
--       the item had before it. The previous price is now saved on each Stock
--       In (inventory_transactions.previous_unit_cost). Older Stock Ins fall
--       back to the price of the Stock In before them.
--
-- Stock already on the shelf becomes one "OPENING" batch per item, with the
-- item's current expiry date and price, so the batch totals match
-- current_stock from the start.
--
-- Access is the same as 019: signed-in users and service_role, never
-- anonymous visitors. The API decides who may do what.
--
-- APPLY in the Supabase SQL editor: paste the whole file and press Run once.
-- Safe to re-run (the opening batches are only made for items with none).
-- Run the checks at the bottom afterwards.
--
-- UNDO: re-run 019_inventory_fixes.sql. The new tables can stay; nothing
-- else reads them.


-- ---------------------------------------------------------------------------
-- STEP 1. Tables and columns
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.inventory_batches (
    id                 SERIAL PRIMARY KEY,
    item_id            INTEGER NOT NULL REFERENCES public.inventory_items (id) ON DELETE CASCADE,
    batch_number       TEXT NOT NULL,
    expire_date        DATE,
    unit_cost          NUMERIC(12, 2),
    quantity_received  INTEGER NOT NULL CHECK (quantity_received >= 0),
    -- Returns can put stock back into a batch, so this is not capped at
    -- quantity_received; it only never goes below 0.
    quantity_remaining INTEGER NOT NULL CHECK (quantity_remaining >= 0),
    received_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    -- The Stock In movement that brought it in. NULL for the opening batch.
    stock_in_id        INTEGER,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS inventory_batches_item_idx
    ON public.inventory_batches (item_id, expire_date);
CREATE UNIQUE INDEX IF NOT EXISTS inventory_batches_stock_in_unique
    ON public.inventory_batches (stock_in_id) WHERE stock_in_id IS NOT NULL;

-- One row per batch a movement used. direction -1 = taken out of the batch
-- (Stock Out), +1 = put into it (Stock In, Return). item_id and program_id
-- are copied from the movement so "what does this program hold of each
-- batch" needs no join.
CREATE TABLE IF NOT EXISTS public.inventory_batch_allocations (
    id          SERIAL PRIMARY KEY,
    movement_id INTEGER NOT NULL,
    batch_id    INTEGER NOT NULL REFERENCES public.inventory_batches (id) ON DELETE CASCADE,
    item_id     INTEGER NOT NULL,
    program_id  INTEGER,
    direction   SMALLINT NOT NULL CHECK (direction IN (-1, 1)),
    quantity    INTEGER NOT NULL CHECK (quantity > 0)
);
CREATE INDEX IF NOT EXISTS inventory_batch_allocations_movement_idx
    ON public.inventory_batch_allocations (movement_id);
CREATE INDEX IF NOT EXISTS inventory_batch_allocations_program_idx
    ON public.inventory_batch_allocations (item_id, program_id);

ALTER TABLE public.inventory_transactions
    ADD COLUMN IF NOT EXISTS previous_unit_cost NUMERIC(12, 2);
COMMENT ON COLUMN public.inventory_transactions.previous_unit_cost IS
    'Stock In only: the item''s unit cost before this Stock In, put back if it is reversed.';

-- Links to the movements table. Its primary key is `id` in init.sql but may
-- be `transaction_id` in the live database, so it is looked up (as in 016).
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
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'inventory_batches_stock_in_fk') THEN
        EXECUTE format(
            'ALTER TABLE public.inventory_batches ADD CONSTRAINT inventory_batches_stock_in_fk '
            'FOREIGN KEY (stock_in_id) REFERENCES public.inventory_transactions (%I) ON DELETE RESTRICT', v_pk);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'inventory_batch_allocations_movement_fk') THEN
        EXECUTE format(
            'ALTER TABLE public.inventory_batch_allocations ADD CONSTRAINT inventory_batch_allocations_movement_fk '
            'FOREIGN KEY (movement_id) REFERENCES public.inventory_transactions (%I) ON DELETE CASCADE', v_pk);
    END IF;
END $$;

-- Same access model as the other inventory tables today (003): signed-in
-- users through the API, never anonymous visitors.
ALTER TABLE public.inventory_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.inventory_batch_allocations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS inventory_batches_authenticated_all ON public.inventory_batches;
CREATE POLICY inventory_batches_authenticated_all ON public.inventory_batches
    FOR ALL TO authenticated USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS inventory_batch_allocations_authenticated_all ON public.inventory_batch_allocations;
CREATE POLICY inventory_batch_allocations_authenticated_all ON public.inventory_batch_allocations
    FOR ALL TO authenticated USING (true) WITH CHECK (true);
REVOKE ALL ON public.inventory_batches, public.inventory_batch_allocations FROM anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.inventory_batches, public.inventory_batch_allocations
    TO authenticated, service_role;
REVOKE ALL ON SEQUENCE public.inventory_batches_id_seq, public.inventory_batch_allocations_id_seq FROM anon;
GRANT USAGE, SELECT ON SEQUENCE public.inventory_batches_id_seq, public.inventory_batch_allocations_id_seq
    TO authenticated, service_role;


-- ---------------------------------------------------------------------------
-- STEP 2. Stock already on the shelf becomes an OPENING batch
-- ---------------------------------------------------------------------------
INSERT INTO public.inventory_batches
    (item_id, batch_number, expire_date, unit_cost, quantity_received, quantity_remaining, received_date)
SELECT i.id, 'OPENING', i.expire_date, i.unit_cost, i.current_stock, i.current_stock, CURRENT_DATE
  FROM public.inventory_items i
 WHERE coalesce(i.current_stock, 0) > 0
   AND NOT EXISTS (SELECT 1 FROM public.inventory_batches b WHERE b.item_id = i.id);


-- ---------------------------------------------------------------------------
-- STEP 3. Batch helpers (used only by the two movement functions)
-- ---------------------------------------------------------------------------

-- The item's expire_date = the soonest expiry among batches with stock left.
CREATE OR REPLACE FUNCTION public.inventory_refresh_expiry(p_item_id integer)
RETURNS void
LANGUAGE sql
AS $$
    UPDATE public.inventory_items
       SET expire_date = (SELECT min(expire_date) FROM public.inventory_batches
                           WHERE item_id = p_item_id AND quantity_remaining > 0)
     WHERE id = p_item_id;
$$;

-- Take p_qty out of the item's batches for one movement. The preferred
-- batches (with how many to take from each) go first; the rest comes from
-- the batch that expires soonest (no expiry last, then oldest first).
CREATE OR REPLACE FUNCTION public.inventory_batch_take(
    p_item_id     integer,
    p_qty         integer,
    p_movement_id integer,
    p_program_id  integer,
    p_pref_batches integer[] DEFAULT NULL,
    p_pref_qty     integer[] DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_left  integer := p_qty;
    v_take  integer;
    v_batch record;
    i       integer;
BEGIN
    IF p_pref_batches IS NOT NULL THEN
        FOR i IN 1 .. coalesce(array_length(p_pref_batches, 1), 0) LOOP
            EXIT WHEN v_left <= 0;
            SELECT * INTO v_batch FROM public.inventory_batches
             WHERE id = p_pref_batches[i] AND item_id = p_item_id FOR UPDATE;
            CONTINUE WHEN NOT FOUND;
            v_take := least(v_left, p_pref_qty[i], v_batch.quantity_remaining);
            CONTINUE WHEN v_take <= 0;
            UPDATE public.inventory_batches SET quantity_remaining = quantity_remaining - v_take
             WHERE id = v_batch.id;
            INSERT INTO public.inventory_batch_allocations
                (movement_id, batch_id, item_id, program_id, direction, quantity)
            VALUES (p_movement_id, v_batch.id, p_item_id, p_program_id, -1, v_take);
            v_left := v_left - v_take;
        END LOOP;
    END IF;

    FOR v_batch IN
        SELECT * FROM public.inventory_batches
         WHERE item_id = p_item_id AND quantity_remaining > 0
         ORDER BY expire_date NULLS LAST, received_date, id
         FOR UPDATE
    LOOP
        EXIT WHEN v_left <= 0;
        v_take := least(v_left, v_batch.quantity_remaining);
        UPDATE public.inventory_batches SET quantity_remaining = quantity_remaining - v_take
         WHERE id = v_batch.id;
        INSERT INTO public.inventory_batch_allocations
            (movement_id, batch_id, item_id, program_id, direction, quantity)
        VALUES (p_movement_id, v_batch.id, p_item_id, p_program_id, -1, v_take);
        v_left := v_left - v_take;
    END LOOP;

    IF v_left > 0 THEN
        -- Only possible if batches and current_stock disagree.
        RAISE EXCEPTION 'The batches of this item hold % fewer units than its stock count. Run the check at the bottom of 020_inventory_batches.sql.', v_left;
    END IF;
END;
$$;

-- Put p_qty back into the item's batches for one movement: into the
-- preferred batches first (up to the given amounts), the rest into the
-- newest batch, or a new OPENING batch if the item has none.
CREATE OR REPLACE FUNCTION public.inventory_batch_put(
    p_item_id     integer,
    p_qty         integer,
    p_movement_id integer,
    p_program_id  integer,
    p_pref_batches integer[] DEFAULT NULL,
    p_pref_qty     integer[] DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_left  integer := p_qty;
    v_put   integer;
    v_batch integer;
    i       integer;
BEGIN
    IF p_pref_batches IS NOT NULL THEN
        FOR i IN 1 .. coalesce(array_length(p_pref_batches, 1), 0) LOOP
            EXIT WHEN v_left <= 0;
            v_put := least(v_left, p_pref_qty[i]);
            CONTINUE WHEN v_put <= 0;
            UPDATE public.inventory_batches SET quantity_remaining = quantity_remaining + v_put
             WHERE id = p_pref_batches[i] AND item_id = p_item_id;
            CONTINUE WHEN NOT FOUND;
            INSERT INTO public.inventory_batch_allocations
                (movement_id, batch_id, item_id, program_id, direction, quantity)
            VALUES (p_movement_id, p_pref_batches[i], p_item_id, p_program_id, 1, v_put);
            v_left := v_left - v_put;
        END LOOP;
    END IF;

    IF v_left > 0 THEN
        SELECT id INTO v_batch FROM public.inventory_batches
         WHERE item_id = p_item_id ORDER BY received_date DESC, id DESC LIMIT 1 FOR UPDATE;
        IF v_batch IS NULL THEN
            INSERT INTO public.inventory_batches
                (item_id, batch_number, expire_date, unit_cost, quantity_received, quantity_remaining)
            SELECT id, 'OPENING', expire_date, unit_cost, 0, 0
              FROM public.inventory_items WHERE id = p_item_id
            RETURNING id INTO v_batch;
        END IF;
        UPDATE public.inventory_batches SET quantity_remaining = quantity_remaining + v_left
         WHERE id = v_batch;
        INSERT INTO public.inventory_batch_allocations
            (movement_id, batch_id, item_id, program_id, direction, quantity)
        VALUES (p_movement_id, v_batch, p_item_id, p_program_id, 1, v_left);
    END IF;
END;
$$;


-- ---------------------------------------------------------------------------
-- STEP 4. inventory_apply_movement(): 019's rules, plus batches
-- ---------------------------------------------------------------------------
-- One more optional parameter (p_batch_number), so 019's 8-argument version
-- is dropped first.
DROP FUNCTION IF EXISTS public.inventory_apply_movement(integer, integer, integer, text, date, text, numeric, date);

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
        -- Return: back into the batches this program took from, most recent first.
        SELECT array_agg(batch_id ORDER BY last_id DESC), array_agg(held ORDER BY last_id DESC)
          INTO v_pref_batches, v_pref_qty
          FROM (SELECT batch_id, sum(-direction * quantity) AS held, max(id) AS last_id
                  FROM public.inventory_batch_allocations
                 WHERE item_id = p_item_id AND program_id = p_program_id
                 GROUP BY batch_id) t
         WHERE held > 0;
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
-- STEP 5. inventory_reverse_movement(): 019's rules, plus batches and O3
-- ---------------------------------------------------------------------------
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
        CREATE OR REPLACE FUNCTION public.inventory_reverse_movement(
            p_transaction_id integer,
            p_reason         text
        )
        RETURNS jsonb
        LANGUAGE plpgsql
        AS $fn$
        DECLARE
            v_orig        public.inventory_transactions%%ROWTYPE;
            v_item        public.inventory_items%%ROWTYPE;
            v_batch       public.inventory_batches%%ROWTYPE;
            v_reason      text := nullif(trim(coalesce(p_reason, '')), '');
            v_type        text;
            v_held        integer;
            v_new_stock   integer;
            v_voided      integer := 0;
            v_row         jsonb;
            v_movement_id integer;
            v_batches     integer[];
            v_qty         integer[];
            v_price       numeric;
            v_restored    numeric;
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

            v_type := CASE v_orig.transaction_type
                          WHEN 'Restock' THEN 'Issue'
                          WHEN 'Issue'   THEN 'Return'
                          ELSE 'Issue' END;

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

            -- A Stock In comes back out of its own batch, so that batch must
            -- still hold it all.
            IF v_orig.transaction_type = 'Restock' THEN
                SELECT * INTO v_batch FROM public.inventory_batches
                 WHERE stock_in_id = p_transaction_id FOR UPDATE;
                IF FOUND AND v_batch.quantity_remaining < v_orig.quantity THEN
                    RAISE EXCEPTION 'Cannot reverse: batch %% has only %% of the %% received left, because some was already issued. Reverse those Stock Outs first, or record a stock adjustment.',
                        v_batch.batch_number, v_batch.quantity_remaining, v_orig.quantity;
                END IF;
            END IF;

            -- O3. Undoing the item's latest Stock In puts back the price the
            -- item had before it.
            IF v_orig.transaction_type = 'Restock' AND NOT EXISTS (
                SELECT 1 FROM public.inventory_transactions t
                 WHERE t.item_id = v_orig.item_id
                   AND t.transaction_type = 'Restock'
                   AND t.%1$I > p_transaction_id
                   AND NOT EXISTS (SELECT 1 FROM public.inventory_transactions r
                                    WHERE r.reverses_id = t.%1$I)
            ) THEN
                v_price := v_orig.previous_unit_cost;
                IF v_price IS NULL THEN
                    -- Stock In saved before 020: the price of the Stock In before it.
                    SELECT round(t.total_cost / t.quantity, 2) INTO v_price
                      FROM public.inventory_transactions t
                     WHERE t.item_id = v_orig.item_id
                       AND t.transaction_type = 'Restock'
                       AND t.%1$I < p_transaction_id
                       AND coalesce(t.total_cost, 0) > 0
                       AND NOT EXISTS (SELECT 1 FROM public.inventory_transactions r
                                        WHERE r.reverses_id = t.%1$I)
                     ORDER BY t.%1$I DESC
                     LIMIT 1;
                END IF;
                IF v_price IS NOT NULL AND v_price > 0 AND v_price IS DISTINCT FROM v_item.unit_cost THEN
                    v_restored := v_price;
                END IF;
            END IF;

            UPDATE public.inventory_items
               SET current_stock = v_new_stock,
                   unit_cost = coalesce(v_restored, unit_cost)
             WHERE id = v_orig.item_id;

            INSERT INTO public.inventory_transactions
                (item_id, program_id, quantity, transaction_type, transaction_date, notes,
                 total_cost, reverses_id)
            VALUES
                (v_orig.item_id, v_orig.program_id, v_orig.quantity, v_type,
                 (now() AT TIME ZONE 'Asia/Colombo')::date,
                 left('Reversal of movement #' || p_transaction_id || ': ' || v_reason, 500),
                 coalesce(v_orig.total_cost, 0), p_transaction_id)
            RETURNING to_jsonb(inventory_transactions.*) INTO v_row;
            v_movement_id := coalesce(v_row ->> 'id', v_row ->> 'transaction_id')::integer;

            -- Undo the batches exactly: the same batches, the other way.
            SELECT array_agg(batch_id ORDER BY id), array_agg(quantity ORDER BY id)
              INTO v_batches, v_qty
              FROM public.inventory_batch_allocations
             WHERE movement_id = p_transaction_id;

            IF v_type = 'Issue' THEN
                PERFORM public.inventory_batch_take(v_orig.item_id, v_orig.quantity, v_movement_id,
                                                    v_orig.program_id, v_batches, v_qty);
            ELSE
                PERFORM public.inventory_batch_put(v_orig.item_id, v_orig.quantity, v_movement_id,
                                                   v_orig.program_id, v_batches, v_qty);
            END IF;
            PERFORM public.inventory_refresh_expiry(v_orig.item_id);

            IF v_orig.transaction_type = 'Restock' THEN
                UPDATE public.financial_transactions
                   SET status = 'Voided'
                 WHERE inventory_transaction_id = p_transaction_id
                   AND status IS DISTINCT FROM 'Voided';
                GET DIAGNOSTICS v_voided = ROW_COUNT;
            END IF;

            RETURN v_row || jsonb_build_object(
                'stock_before',       coalesce(v_item.current_stock, 0),
                'stock_after',        v_new_stock,
                'ledger_voided',      v_voided,
                'unit_cost_restored', v_restored
            );
        END;
        $fn$
    $sql$, v_pk);
END $$;


-- ---------------------------------------------------------------------------
-- STEP 6. Who may run the functions (same as 019)
-- ---------------------------------------------------------------------------
REVOKE ALL ON FUNCTION public.inventory_apply_movement(integer, integer, integer, text, date, text, numeric, date, text)
    FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.inventory_apply_movement(integer, integer, integer, text, date, text, numeric, date, text)
    TO authenticated, service_role;
REVOKE ALL ON FUNCTION public.inventory_reverse_movement(integer, text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.inventory_reverse_movement(integer, text) TO authenticated, service_role;
REVOKE ALL ON FUNCTION public.inventory_refresh_expiry(integer) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.inventory_refresh_expiry(integer) TO authenticated, service_role;
REVOKE ALL ON FUNCTION public.inventory_batch_take(integer, integer, integer, integer, integer[], integer[]) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.inventory_batch_take(integer, integer, integer, integer, integer[], integer[]) TO authenticated, service_role;
REVOKE ALL ON FUNCTION public.inventory_batch_put(integer, integer, integer, integer, integer[], integer[]) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.inventory_batch_put(integer, integer, integer, integer, integer[], integer[]) TO authenticated, service_role;

NOTIFY pgrst, 'reload schema';


-- ---------------------------------------------------------------------------
-- AFTER RUNNING: check (screenshot each result)
-- ---------------------------------------------------------------------------
-- 1. Batches match stock for every item. Expect 0 rows:
--      SELECT i.id, i.item_name, i.current_stock,
--             coalesce(sum(b.quantity_remaining), 0) AS in_batches
--        FROM inventory_items i
--        LEFT JOIN inventory_batches b ON b.item_id = i.id
--       GROUP BY i.id, i.item_name, i.current_stock
--      HAVING coalesce(sum(b.quantity_remaining), 0) <> coalesce(i.current_stock, 0);
-- 2. One movement function with 9 arguments. Expect one row, 9:
--      SELECT proname, pronargs FROM pg_proc WHERE proname = 'inventory_apply_movement';
-- 3. The opening batches. Expect one row per item that has stock:
--      SELECT item_id, batch_number, expire_date, quantity_remaining
--        FROM inventory_batches ORDER BY item_id;
