-- 025_payroll_eligibility_and_drift.sql
--
-- Two payroll defects found testing the Payroll page (2026-11-11).
--
-- 1. A draft paid everyone Active at the moment it was generated, whatever
--    their join date: someone joining on 1 December appeared on November's
--    payroll if HR had already added them. Who is paid for a month is now
--    one rule, payroll_eligible(): Active, and joined on or before the
--    month's last day (or with no join date recorded).
--
-- 2. A draft is a snapshot, and approval posted it as it stood. October's
--    draft (generated 29 Oct, 14 people) left out an employee added since,
--    and the Director's dialog offered it for approval without a word: she
--    would have gone unpaid and the ledger would have been 100,000 short.
--    payroll_draft_drift() lists how a draft differs from what generating
--    it now would produce; approve_payroll_run() refuses while it differs,
--    and GET /hr/payroll/run shows the differences.
--
-- Mid-month joiners and leavers are still paid the full month: pro-rating
-- comes with the payroll engine, as do EPF/ETF and deductions.
--
-- APPLY in the Supabase SQL editor after 007. Safe to re-run.

-- ---------------------------------------------------------------------------
-- 1. Who is paid for a month
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION payroll_eligible(p_month INTEGER, p_year INTEGER)
RETURNS TABLE (employee_id INTEGER, employee_name TEXT, base_salary NUMERIC)
LANGUAGE sql
STABLE
AS $$
    SELECT e.id,
           trim(coalesce(e.first_name, '') || ' ' || coalesce(e.last_name, '')),
           e.base_salary
    FROM employee_profile e
    WHERE e.status = 'Active'
      AND (e.date_joined IS NULL
           OR e.date_joined <= (make_date(p_year, p_month, 1) + INTERVAL '1 month - 1 day')::DATE);
$$;

-- ---------------------------------------------------------------------------
-- 2. How a draft differs from generating it now
-- ---------------------------------------------------------------------------
--
-- change: 'added'   eligible now, not on the draft
--         'removed' on the draft, no longer eligible (left, or deactivated)
--         'salary'  on both, with a different amount

CREATE OR REPLACE FUNCTION payroll_draft_drift(p_run_id INTEGER)
RETURNS TABLE (employee_id INTEGER, employee_name TEXT, change TEXT, draft_amount NUMERIC, current_amount NUMERIC)
LANGUAGE sql
STABLE
AS $$
    WITH run AS (
        SELECT payroll_month, payroll_year FROM payroll_runs WHERE id = p_run_id
    ),
    eligible AS (
        SELECT g.* FROM run, payroll_eligible(run.payroll_month, run.payroll_year) g
    ),
    lines AS (
        SELECT l.employee_id, l.net_payable FROM payroll_ledger l WHERE l.run_id = p_run_id
    )
    SELECT e.employee_id, e.employee_name, 'added', NULL::NUMERIC, e.base_salary
    FROM eligible e
    WHERE NOT EXISTS (SELECT 1 FROM lines l WHERE l.employee_id = e.employee_id)
    UNION ALL
    SELECT l.employee_id,
           coalesce(nullif(trim(coalesce(p.first_name, '') || ' ' || coalesce(p.last_name, '')), ''), 'Employee ' || l.employee_id),
           'removed', l.net_payable, NULL::NUMERIC
    FROM lines l
    LEFT JOIN employee_profile p ON p.id = l.employee_id
    WHERE NOT EXISTS (SELECT 1 FROM eligible e WHERE e.employee_id = l.employee_id)
    UNION ALL
    SELECT e.employee_id, e.employee_name, 'salary', l.net_payable, e.base_salary
    FROM eligible e
    JOIN lines l ON l.employee_id = e.employee_id
    WHERE l.net_payable <> e.base_salary;
$$;

-- ---------------------------------------------------------------------------
-- 3. generate_payroll_draft: as in 007, paying payroll_eligible()
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

    IF NOT EXISTS (SELECT 1 FROM payroll_eligible(p_month, p_year)) THEN
        RAISE EXCEPTION 'No active employees found for %/%.', p_month, p_year;
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
    SELECT g.employee_id, p_month, p_year, g.base_salary, v_run.id
    FROM payroll_eligible(p_month, p_year) g;

    UPDATE payroll_runs
    SET total = (SELECT COALESCE(SUM(net_payable), 0) FROM payroll_ledger WHERE run_id = v_run.id)
    WHERE id = v_run.id
    RETURNING * INTO v_run;

    RETURN v_run;
END;
$$;

-- ---------------------------------------------------------------------------
-- 4. approve_payroll_run: as in 007, refusing a draft that is out of date
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
    -- Checked inside the same transaction as the posting, so nothing can
    -- change between the check and the approval.
    IF EXISTS (SELECT 1 FROM payroll_draft_drift(v_run.id)) THEN
        RAISE EXCEPTION 'The payroll draft for %/% is out of date: employees or salaries have changed since it was generated. Regenerate it before approving.',
            v_run.payroll_month, v_run.payroll_year;
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

NOTIFY pgrst, 'reload schema';
