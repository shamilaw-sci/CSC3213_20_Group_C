-- 007_payroll_runs.sql
--
-- Gives payroll a real approval step.
--
-- BEFORE. generate_monthly_payroll (db/init.sql) did three things in one
-- call: wrote a payroll_ledger row per Active employee, and immediately
-- inserted the month's total into financial_transactions as a settled
-- expense. The "Approve & Finalize" button on the payroll page only showed a
-- toast. So salaries hit the books the moment anyone pressed Generate, nobody
-- ever approved anything, and a mistake could only be fixed by hand in the
-- ledger.
--
-- AFTER. A payroll run is a row in payroll_runs with a status:
--
--   Draft     generate_payroll_draft() writes the lines. Regenerating a Draft
--             replaces its lines (e.g. after a salary correction). Nothing
--             touches financial_transactions.
--   Approved  approve_payroll_run() freezes the run and posts ONE expense
--             for its total, dated the last day of the payroll month, as a
--             payable (status 'Receivable'): approved salaries are owed until
--             Finance marks them paid in the Ledger.
--
-- Policy confirmed with the project owner on 2026-10-29: HR generates
-- (payroll:generate), Director approves (payroll:approve). The two-person
-- rule is enforced here, not only in the UI: the approver may not be the
-- user who last generated the run. Admin holds both permissions, and without
-- this check could approve their own draft.
--
-- Pay itself is unchanged in this migration: each line is the employee's
-- base_salary (fixed monthly salary, the confirmed basis). Deductions,
-- allowances and EPF/ETF come with the payroll engine, a later migration.
--
-- Both functions run as one transaction each, which is why they are SQL and
-- not Python: the backend's Supabase client cannot span several writes in a
-- transaction, and a half-written run or an approval without its expense
-- would put payroll and the ledger out of step.
--
-- APPLY in the Supabase SQL editor. Safe to re-run.

-- ---------------------------------------------------------------------------
-- 1. payroll_runs
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS payroll_runs (
    id SERIAL PRIMARY KEY,
    payroll_month INTEGER NOT NULL CHECK (payroll_month BETWEEN 1 AND 12),
    payroll_year INTEGER NOT NULL CHECK (payroll_year BETWEEN 2000 AND 2100),
    status VARCHAR(20) NOT NULL DEFAULT 'Draft' CHECK (status IN ('Draft', 'Approved')),
    total NUMERIC(14, 2) NOT NULL DEFAULT 0,
    generated_by UUID REFERENCES users(id) ON DELETE SET NULL,
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    approved_by UUID REFERENCES users(id) ON DELETE SET NULL,
    approved_at TIMESTAMP WITH TIME ZONE,
    finance_transaction_id INTEGER REFERENCES financial_transactions(id) ON DELETE SET NULL,
    -- One run per month: a second Generate updates the Draft instead of
    -- creating a parallel one.
    UNIQUE (payroll_month, payroll_year)
);

ALTER TABLE payroll_ledger
    ADD COLUMN IF NOT EXISTS run_id INTEGER REFERENCES payroll_runs(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_payroll_ledger_run ON payroll_ledger (run_id);

-- Same shape as the other tables in 003_rls_lockdown.sql: signed-in staff
-- requests run as `authenticated` and need a policy, or every HR request
-- against this table is refused. Permission checks live in FastAPI.
ALTER TABLE public.payroll_runs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS payroll_runs_authenticated_all ON public.payroll_runs;
CREATE POLICY payroll_runs_authenticated_all ON public.payroll_runs
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ---------------------------------------------------------------------------
-- 2. Backfill: payroll generated under the old function
-- ---------------------------------------------------------------------------
--
-- Those months were already posted to financial_transactions by the old
-- function. They become Approved runs so they cannot be approved again, which
-- would post their salaries a second time. approved_by and
-- finance_transaction_id stay NULL: nobody approved them, and the old
-- function did not record which ledger row it wrote.

INSERT INTO payroll_runs (payroll_month, payroll_year, status, total, generated_at, approved_at)
SELECT payroll_month, payroll_year, 'Approved', SUM(net_payable), now(), now()
FROM payroll_ledger
WHERE run_id IS NULL
GROUP BY payroll_month, payroll_year
ON CONFLICT (payroll_month, payroll_year) DO NOTHING;

UPDATE payroll_ledger l
SET run_id = r.id
FROM payroll_runs r
WHERE l.run_id IS NULL
  AND r.payroll_month = l.payroll_month
  AND r.payroll_year = l.payroll_year;

-- ---------------------------------------------------------------------------
-- 3. Retire the old one-step function
-- ---------------------------------------------------------------------------
--
-- Dropped rather than left beside the new ones: anything still calling it
-- would quietly post unapproved salaries to the ledger.

DROP FUNCTION IF EXISTS generate_monthly_payroll(INTEGER, INTEGER);

-- ---------------------------------------------------------------------------
-- 4. generate_payroll_draft
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION generate_payroll_draft(p_month INTEGER, p_year INTEGER, p_user UUID)
RETURNS payroll_runs
LANGUAGE plpgsql
AS $$
DECLARE
    v_run payroll_runs;
    v_exists BOOLEAN;
BEGIN
    -- Lock the month's run, if any, so two Generates cannot interleave.
    SELECT * INTO v_run FROM payroll_runs
    WHERE payroll_month = p_month AND payroll_year = p_year
    FOR UPDATE;
    v_exists := FOUND;

    IF v_exists AND v_run.status <> 'Draft' THEN
        RAISE EXCEPTION 'Payroll for %/% is already approved and cannot be regenerated.', p_month, p_year;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM employee_profile WHERE status = 'Active') THEN
        RAISE EXCEPTION 'No active employees found.';
    END IF;

    IF v_exists THEN
        DELETE FROM payroll_ledger WHERE run_id = v_run.id;
        UPDATE payroll_runs SET generated_by = p_user, generated_at = now()
        WHERE id = v_run.id;
    ELSE
        INSERT INTO payroll_runs (payroll_month, payroll_year, generated_by)
        VALUES (p_month, p_year, p_user)
        RETURNING * INTO v_run;
    END IF;

    INSERT INTO payroll_ledger (employee_id, payroll_month, payroll_year, net_payable, run_id)
    SELECT id, p_month, p_year, base_salary, v_run.id
    FROM employee_profile
    WHERE status = 'Active';

    UPDATE payroll_runs
    SET total = (SELECT COALESCE(SUM(net_payable), 0) FROM payroll_ledger WHERE run_id = v_run.id)
    WHERE id = v_run.id
    RETURNING * INTO v_run;

    RETURN v_run;
END;
$$;

-- ---------------------------------------------------------------------------
-- 5. approve_payroll_run
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION approve_payroll_run(p_run_id INTEGER, p_user UUID)
RETURNS payroll_runs
LANGUAGE plpgsql
AS $$
DECLARE
    v_run payroll_runs;
    v_tx_id INTEGER;
    v_month_end DATE;
BEGIN
    SELECT * INTO v_run FROM payroll_runs WHERE id = p_run_id FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Payroll run % not found.', p_run_id;
    END IF;
    IF v_run.status <> 'Draft' THEN
        RAISE EXCEPTION 'Payroll for %/% is already approved.', v_run.payroll_month, v_run.payroll_year;
    END IF;
    IF v_run.generated_by IS NOT NULL AND v_run.generated_by = p_user THEN
        RAISE EXCEPTION 'Payroll must be approved by someone other than the person who generated it.';
    END IF;
    IF v_run.total <= 0 THEN
        RAISE EXCEPTION 'Payroll for %/% has nothing to pay.', v_run.payroll_month, v_run.payroll_year;
    END IF;

    -- The expense belongs to the month it pays for, not the day it was
    -- approved.
    v_month_end := (make_date(v_run.payroll_year, v_run.payroll_month, 1) + INTERVAL '1 month - 1 day')::DATE;

    INSERT INTO financial_transactions (transaction_date, amount, transaction_type, status)
    VALUES (v_month_end, v_run.total, 'Expense', 'Receivable')
    RETURNING id INTO v_tx_id;

    UPDATE payroll_runs
    SET status = 'Approved', approved_by = p_user, approved_at = now(), finance_transaction_id = v_tx_id
    WHERE id = v_run.id
    RETURNING * INTO v_run;

    RETURN v_run;
END;
$$;

-- ---------------------------------------------------------------------------
-- 6. Make the API see the new table and functions now
-- ---------------------------------------------------------------------------
--
-- PostgREST caches the schema. Without this, the backend keeps getting
-- PGRST205 "Could not find the table 'public.payroll_runs'" until the cache
-- happens to refresh.

NOTIFY pgrst, 'reload schema';
