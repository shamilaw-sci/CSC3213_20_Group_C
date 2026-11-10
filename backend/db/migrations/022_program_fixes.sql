-- 022_program_fixes.sql
--
-- Program fixes from the audit. Apply after 021_inventory_batch_costing.sql.
--
-- What this does:
--   Cost  A program's Total Cost now takes Returns back off. Before, only
--         Stock Outs were added up, so returned stock (and a reversed Stock
--         Out, which is saved as a Return) still counted as a cost and made
--         cost per animal too high. recalculate_program_total_cost() and
--         get_cost_per_animal() both change, and every program's Total Cost
--         is worked out again once. Payroll and Stock Outs with no program
--         are still left out, as before.
--   P5    A program can be Cancelled while it is Upcoming (created by
--         mistake, or called off before it began). Nothing else changes in
--         the Upcoming -> Active -> Completed order.
--   P2    Each volunteer shift gets a program_id, so it belongs to a program
--         by id and not by its title. Existing shifts are linked when their
--         title matches exactly one program's name; the rest stay unlinked
--         and keep the old title rule.
--
-- Access is unchanged: no policies or grants are touched. The new column is
-- covered by volunteer_shifts' existing rules.
--
-- APPLY in the Supabase SQL editor: paste the whole file and press Run once.
-- Safe to re-run. Run the checks at the bottom afterwards.


-- ---------------------------------------------------------------------------
-- STEP 1. Total Cost = Stock Outs - Returns + program expenses
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.recalculate_program_total_cost(p_program_id integer)
RETURNS void
LANGUAGE plpgsql
AS $function$
DECLARE
    v_inventory_cost DECIMAL(15,2);
    v_other_cost     DECIMAL(15,2);
BEGIN
    IF p_program_id IS NULL THEN
        RETURN;
    END IF;

    -- Stock Outs add, Returns (and reversed Stock Outs) take back off.
    SELECT greatest(coalesce(sum(CASE transaction_type
                                     WHEN 'Issue'  THEN total_cost
                                     WHEN 'Return' THEN -total_cost
                                     ELSE 0 END), 0), 0)
      INTO v_inventory_cost
      FROM inventory_transactions
     WHERE program_id = p_program_id;

    -- Program expenses in Finance, except voided ones.
    SELECT coalesce(sum(amount), 0)
      INTO v_other_cost
      FROM financial_transactions
     WHERE program_id = p_program_id
       AND transaction_type = 'Expense'
       AND status IS DISTINCT FROM 'Voided';

    UPDATE programs
       SET total_cost = v_inventory_cost + v_other_cost
     WHERE id = p_program_id;
END;
$function$;

CREATE OR REPLACE FUNCTION public.get_cost_per_animal(p_program_id integer)
RETURNS TABLE(program_id integer, program_name character varying, inventory_cost numeric,
              other_cost numeric, total_cost numeric, animals_treated integer,
              cost_per_animal numeric)
LANGUAGE plpgsql
AS $function$
DECLARE
    v_inventory_cost DECIMAL(15,2);
    v_other_cost     DECIMAL(15,2);
    v_animals        INT;
    v_name           VARCHAR;
BEGIN
    SELECT p.program_name, p.total_animals_treated INTO v_name, v_animals
      FROM programs p
     WHERE p.id = p_program_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Program % not found', p_program_id;
    END IF;

    SELECT greatest(coalesce(sum(CASE it.transaction_type
                                     WHEN 'Issue'  THEN it.total_cost
                                     WHEN 'Return' THEN -it.total_cost
                                     ELSE 0 END), 0), 0)
      INTO v_inventory_cost
      FROM inventory_transactions it
     WHERE it.program_id = p_program_id;

    SELECT coalesce(sum(ft.amount), 0) INTO v_other_cost
      FROM financial_transactions ft
     WHERE ft.program_id = p_program_id
       AND ft.transaction_type = 'Expense'
       AND ft.status IS DISTINCT FROM 'Voided';

    RETURN QUERY
    SELECT p_program_id, v_name, v_inventory_cost, v_other_cost,
           v_inventory_cost + v_other_cost, v_animals,
           CASE WHEN v_animals > 0
                THEN round((v_inventory_cost + v_other_cost) / v_animals, 2)
                ELSE 0 END;
END;
$function$;

-- Work every program's Total Cost out again with the new rule.
DO $$
DECLARE
    v_id integer;
BEGIN
    FOR v_id IN SELECT id FROM programs LOOP
        PERFORM public.recalculate_program_total_cost(v_id);
    END LOOP;
END $$;


-- ---------------------------------------------------------------------------
-- STEP 2. Cancelled programs
-- ---------------------------------------------------------------------------
ALTER TABLE programs DROP CONSTRAINT IF EXISTS programs_status_lifecycle;
ALTER TABLE programs ADD CONSTRAINT programs_status_lifecycle
    CHECK (status IN ('Upcoming', 'Active', 'Completed', 'Cancelled'));

CREATE OR REPLACE FUNCTION enforce_program_status_transition()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status
       AND NOT (
            (OLD.status = 'Upcoming' AND NEW.status = 'Active')
         OR (OLD.status = 'Active'   AND NEW.status = 'Completed')
         OR (OLD.status = 'Upcoming' AND NEW.status = 'Cancelled')
       )
    THEN
        RAISE EXCEPTION
            'Program % cannot move from % to %: programs only move Upcoming -> Active -> Completed, or Upcoming -> Cancelled',
            OLD.id, OLD.status, NEW.status
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

COMMENT ON COLUMN programs.status IS
    'Lifecycle: Upcoming -> Active -> Completed, or Upcoming -> Cancelled (trigger programs_status_transition). New programs default to Upcoming.';


-- ---------------------------------------------------------------------------
-- STEP 3. Shifts belong to a program by id
-- ---------------------------------------------------------------------------
ALTER TABLE volunteer_shifts
    ADD COLUMN IF NOT EXISTS program_id integer REFERENCES programs(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_volunteer_shifts_program ON volunteer_shifts (program_id);
COMMENT ON COLUMN volunteer_shifts.program_id IS
    'The program this shift is for. NULL on older shifts that could not be linked by name.';

-- Link existing shifts whose title is exactly one program's name (ignoring
-- case and extra spaces, the rule the app used until now).
WITH names AS (
    SELECT lower(regexp_replace(trim(program_name), '\s+', ' ', 'g')) AS name,
           min(id) AS program_id,
           count(*) AS n
      FROM programs
     GROUP BY 1
)
UPDATE volunteer_shifts s
   SET program_id = names.program_id
  FROM names
 WHERE s.program_id IS NULL
   AND names.n = 1
   AND lower(regexp_replace(trim(s.title), '\s+', ' ', 'g')) = names.name;

NOTIFY pgrst, 'reload schema';


-- ---------------------------------------------------------------------------
-- AFTER RUNNING: check (screenshot each result)
-- ---------------------------------------------------------------------------
-- 1. Every program's Total Cost, now with Returns taken off:
--      SELECT id, program_name, status, total_cost, total_animals_treated
--        FROM programs ORDER BY id;
-- 2. The four statuses are allowed. Expect one row that includes 'Cancelled':
--      SELECT pg_get_constraintdef(oid) FROM pg_constraint
--       WHERE conname = 'programs_status_lifecycle';
-- 3. How many shifts were linked to a program. not_linked shifts keep the
--    old title rule:
--      SELECT count(*) FILTER (WHERE program_id IS NOT NULL) AS linked,
--             count(*) FILTER (WHERE program_id IS NULL)     AS not_linked
--        FROM volunteer_shifts;
