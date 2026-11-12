-- 026_payroll_engine.sql
--
-- The payroll engine, v1 (policy confirmed 2026-11-12):
--
--   * pay per employee is worked out in Python (app/services/payroll_engine.py):
--     base / 30 a day, part months pro-rated for joiners and leavers, approved
--     no-pay leave deducted, EPF 8% from the employee, EPF 12% + ETF 3% from
--     the employer;
--   * this file stores the breakdown and writes a run atomically;
--   * approval posts three payables: net salaries, EPF (20%) and ETF (3%).
--
-- Replaces 025's payroll_eligible() and payroll_draft_drift(): who is paid
-- and whether a draft is out of date are now decided by the engine, in one
-- place, and an out-of-date draft is refused before approve_payroll_run is
-- called (which itself refuses a draft regenerated since it was checked).
--
-- APPLY in the Supabase SQL editor after 025. Safe to re-run.

-- ---------------------------------------------------------------------------
-- 1. Columns
-- ---------------------------------------------------------------------------

-- A leaver's last day: their final month is pro-rated to it.
ALTER TABLE employee_profile ADD COLUMN IF NOT EXISTS date_left DATE;
-- Shown on payslips.
ALTER TABLE employee_profile ADD COLUMN IF NOT EXISTS epf_number VARCHAR(20);

-- A line's breakdown. NULL on lines from before the engine, which were net
-- only (the base salary).
ALTER TABLE payroll_ledger
    ADD COLUMN IF NOT EXISTS days_in_month INTEGER,
    ADD COLUMN IF NOT EXISTS paid_days INTEGER,
    ADD COLUMN IF NOT EXISTS basic NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS nopay_days NUMERIC(5, 1),
    ADD COLUMN IF NOT EXISTS nopay_deduction NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS gross NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS epf_employee NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS epf_employer NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS etf NUMERIC(12, 2);

-- Run totals. `total` becomes the employer cost (gross + EPF 12% + ETF 3%),
-- what the organisation spends; net_total is what staff are paid.
ALTER TABLE payroll_runs
    ADD COLUMN IF NOT EXISTS gross_total NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS epf_employee_total NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS epf_employer_total NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS etf_total NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS net_total NUMERIC(14, 2),
    -- finance_transaction_id (007) stays: the net salaries payable.
    ADD COLUMN IF NOT EXISTS epf_transaction_id INTEGER REFERENCES financial_transactions(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS etf_transaction_id INTEGER REFERENCES financial_transactions(id) ON DELETE SET NULL;

-- A short label the ledger shows after the source, so the three payroll
-- payables read "Payroll-November 2026 net salaries" and so on rather than
-- three identical "Payroll-General" rows.
ALTER TABLE financial_transactions ADD COLUMN IF NOT EXISTS memo VARCHAR(120);

-- ---------------------------------------------------------------------------
-- 2. Retire 025's functions and the old signatures
-- ---------------------------------------------------------------------------

DROP FUNCTION IF EXISTS approve_payroll_run(INTEGER, UUID);
DROP FUNCTION IF EXISTS generate_payroll_draft(INTEGER, INTEGER, UUID);
DROP FUNCTION IF EXISTS payroll_draft_drift(INTEGER);
DROP FUNCTION IF EXISTS payroll_eligible(INTEGER, INTEGER);

-- ---------------------------------------------------------------------------
-- 3. generate_payroll_draft: store the engine's lines as the month's Draft
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION generate_payroll_draft(p_month INTEGER, p_year INTEGER, p_user UUID, p_lines JSONB)
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

    IF p_lines IS NULL OR jsonb_array_length(p_lines) = 0 THEN
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

    INSERT INTO payroll_ledger (
        employee_id, payroll_month, payroll_year, run_id,
        days_in_month, paid_days, basic, nopay_days, nopay_deduction,
        gross, epf_employee, epf_employer, etf, net_payable
    )
    SELECT l.employee_id, p_month, p_year, v_run.id,
           l.days_in_month, l.paid_days, l.basic, l.nopay_days, l.nopay_deduction,
           l.gross, l.epf_employee, l.epf_employer, l.etf, l.net_payable
    FROM jsonb_to_recordset(p_lines) AS l(
        employee_id INTEGER, days_in_month INTEGER, paid_days INTEGER,
        basic NUMERIC, nopay_days NUMERIC, nopay_deduction NUMERIC, gross NUMERIC,
        epf_employee NUMERIC, epf_employer NUMERIC, etf NUMERIC, net_payable NUMERIC
    );

    UPDATE payroll_runs r
    SET gross_total = t.gross, epf_employee_total = t.epf_employee, epf_employer_total = t.epf_employer,
        etf_total = t.etf, net_total = t.net, total = t.gross + t.epf_employer + t.etf
    FROM (
        SELECT COALESCE(SUM(gross), 0) AS gross, COALESCE(SUM(epf_employee), 0) AS epf_employee,
               COALESCE(SUM(epf_employer), 0) AS epf_employer, COALESCE(SUM(etf), 0) AS etf,
               COALESCE(SUM(net_payable), 0) AS net
        FROM payroll_ledger WHERE run_id = v_run.id
    ) t
    WHERE r.id = v_run.id
    RETURNING r.* INTO v_run;

    RETURN v_run;
END;
$$;

-- ---------------------------------------------------------------------------
-- 4. approve_payroll_run: freeze the Draft and post three payables
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION approve_payroll_run(p_run_id INTEGER, p_user UUID, p_generated_at TIMESTAMPTZ)
RETURNS payroll_runs
LANGUAGE plpgsql
AS $$
DECLARE
    v_run payroll_runs;
    v_month_end DATE;
    v_label TEXT;
    v_net_tx INTEGER;
    v_epf_tx INTEGER;
    v_etf_tx INTEGER;
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
    -- The API checked this draft against a fresh run just before calling;
    -- a regeneration since then would approve figures nobody checked.
    IF p_generated_at IS NULL OR v_run.generated_at IS DISTINCT FROM p_generated_at THEN
        RAISE EXCEPTION 'The payroll draft for %/% is out of date: it was regenerated while being reviewed. Reload it before approving.',
            v_run.payroll_month, v_run.payroll_year;
    END IF;
    IF v_run.net_total IS NULL THEN
        RAISE EXCEPTION 'The payroll draft for %/% is out of date: it was generated before the payroll engine. Regenerate it before approving.',
            v_run.payroll_month, v_run.payroll_year;
    END IF;
    IF v_run.total <= 0 THEN
        RAISE EXCEPTION 'Payroll for %/% has nothing to pay.', v_run.payroll_month, v_run.payroll_year;
    END IF;

    -- The expense belongs to the month it pays for, not the day it was
    -- approved.
    v_month_end := (make_date(v_run.payroll_year, v_run.payroll_month, 1) + INTERVAL '1 month - 1 day')::DATE;
    v_label := trim(to_char(make_date(v_run.payroll_year, v_run.payroll_month, 1), 'FMMonth YYYY'));

    INSERT INTO financial_transactions (transaction_date, amount, transaction_type, status, source_type, memo)
    VALUES (v_month_end, v_run.net_total, 'Expense', 'Receivable', 'payroll', v_label || ' net salaries')
    RETURNING id INTO v_net_tx;

    IF v_run.epf_employee_total + v_run.epf_employer_total > 0 THEN
        INSERT INTO financial_transactions (transaction_date, amount, transaction_type, status, source_type, memo)
        VALUES (v_month_end, v_run.epf_employee_total + v_run.epf_employer_total, 'Expense', 'Receivable',
                'payroll', v_label || ' EPF (8% + 12%)')
        RETURNING id INTO v_epf_tx;
    END IF;

    IF v_run.etf_total > 0 THEN
        INSERT INTO financial_transactions (transaction_date, amount, transaction_type, status, source_type, memo)
        VALUES (v_month_end, v_run.etf_total, 'Expense', 'Receivable', 'payroll', v_label || ' ETF (3%)')
        RETURNING id INTO v_etf_tx;
    END IF;

    UPDATE payroll_runs
    SET status = 'Approved', approved_by = p_user, approved_at = now(),
        finance_transaction_id = v_net_tx, epf_transaction_id = v_epf_tx, etf_transaction_id = v_etf_tx
    WHERE id = v_run.id
    RETURNING * INTO v_run;

    RETURN v_run;
END;
$$;

NOTIFY pgrst, 'reload schema';
