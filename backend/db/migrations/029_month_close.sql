-- 029_month_close.sql
--
-- Month close (attendance rework, step 5; policy confirmed 2026-11-12).
--
--   * HR closes a past month once nothing is loose (no missing clock-out,
--     no correction waiting). The close records each employee's payable
--     absences: ABSENT days, half a day where half-day leave left the other
--     half unworked.
--   * A closed month is frozen whole, like an approved payroll's days.
--   * Its absences are deducted IN ARREARS by the next payroll generated
--     after closing, at base / 30 (app/services/payroll_engine.py), as their
--     own line. Approving that payroll records which closes it took.
--   * HR may reopen a month until a payroll that took its absences is
--     approved. Reopening one taken by a draft makes the draft out of date.
--
-- APPLY in the Supabase SQL editor after 026. Safe to re-run.

-- ---------------------------------------------------------------------------
-- 1. Closes and their lines
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS attendance_month_closes (
    id                 SERIAL PRIMARY KEY,
    close_month        INTEGER NOT NULL CHECK (close_month BETWEEN 1 AND 12),
    close_year         INTEGER NOT NULL CHECK (close_year BETWEEN 2000 AND 2100),
    status             VARCHAR(20) NOT NULL DEFAULT 'Closed' CHECK (status IN ('Closed', 'Reopened')),
    closed_by          UUID REFERENCES users(id) ON DELETE SET NULL,
    closed_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    reopened_by        UUID REFERENCES users(id) ON DELETE SET NULL,
    reopened_at        TIMESTAMP WITH TIME ZONE,
    -- The approved payroll that deducted these absences; set on approval.
    deducted_in_run_id INTEGER REFERENCES payroll_runs(id) ON DELETE SET NULL,
    -- One row per month: reopening and closing again reuses it.
    UNIQUE (close_month, close_year)
);

CREATE TABLE IF NOT EXISTS attendance_close_lines (
    id           SERIAL PRIMARY KEY,
    close_id     INTEGER NOT NULL REFERENCES attendance_month_closes(id) ON DELETE CASCADE,
    employee_id  INTEGER NOT NULL REFERENCES employee_profile(id) ON DELETE CASCADE,
    absent_days  NUMERIC(4, 1) NOT NULL CHECK (absent_days > 0),
    absent_dates JSONB NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE (close_id, employee_id)
);

ALTER TABLE public.attendance_month_closes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS attendance_month_closes_authenticated_all ON public.attendance_month_closes;
CREATE POLICY attendance_month_closes_authenticated_all ON public.attendance_month_closes
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

ALTER TABLE public.attendance_close_lines ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS attendance_close_lines_authenticated_all ON public.attendance_close_lines;
CREATE POLICY attendance_close_lines_authenticated_all ON public.attendance_close_lines
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ---------------------------------------------------------------------------
-- 2. Payroll: absences on the line, and which months they came from
-- ---------------------------------------------------------------------------

ALTER TABLE payroll_ledger
    ADD COLUMN IF NOT EXISTS absent_days NUMERIC(5, 1),
    ADD COLUMN IF NOT EXISTS absence_deduction NUMERIC(12, 2);

-- e.g. "October 2026": the closed months whose absences this run deducts.
ALTER TABLE payroll_runs ADD COLUMN IF NOT EXISTS absence_months TEXT;

-- ---------------------------------------------------------------------------
-- 3. close_attendance_month: the close and its lines in one transaction
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION close_attendance_month(p_month INTEGER, p_year INTEGER, p_user UUID, p_lines JSONB)
RETURNS attendance_month_closes
LANGUAGE plpgsql
AS $$
DECLARE
    v_close attendance_month_closes;
BEGIN
    SELECT * INTO v_close FROM attendance_month_closes
    WHERE close_month = p_month AND close_year = p_year
    FOR UPDATE;

    IF FOUND AND v_close.status = 'Closed' THEN
        RAISE EXCEPTION '%/% is already closed.', p_month, p_year;
    END IF;

    IF FOUND THEN
        DELETE FROM attendance_close_lines WHERE close_id = v_close.id;
        UPDATE attendance_month_closes
        SET status = 'Closed', closed_by = p_user, closed_at = now(),
            reopened_by = NULL, reopened_at = NULL, deducted_in_run_id = NULL
        WHERE id = v_close.id
        RETURNING * INTO v_close;
    ELSE
        INSERT INTO attendance_month_closes (close_month, close_year, closed_by)
        VALUES (p_month, p_year, p_user)
        RETURNING * INTO v_close;
    END IF;

    INSERT INTO attendance_close_lines (close_id, employee_id, absent_days, absent_dates)
    SELECT v_close.id, l.employee_id, l.absent_days, COALESCE(l.absent_dates, '[]'::jsonb)
    FROM jsonb_to_recordset(COALESCE(p_lines, '[]'::jsonb))
         AS l(employee_id INTEGER, absent_days NUMERIC, absent_dates JSONB)
    WHERE l.absent_days > 0;

    RETURN v_close;
END;
$$;

-- ---------------------------------------------------------------------------
-- 4. generate_payroll_draft: as in 026, with absences and their months
-- ---------------------------------------------------------------------------

DROP FUNCTION IF EXISTS generate_payroll_draft(INTEGER, INTEGER, UUID, JSONB);

CREATE OR REPLACE FUNCTION generate_payroll_draft(p_month INTEGER, p_year INTEGER, p_user UUID, p_lines JSONB,
                                                  p_absence_months TEXT)
RETURNS payroll_runs
LANGUAGE plpgsql
AS $$
DECLARE
    v_run payroll_runs;
    v_exists BOOLEAN;
BEGIN
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
        UPDATE payroll_runs SET generated_by = p_user, generated_at = now(), absence_months = p_absence_months
        WHERE id = v_run.id;
    ELSE
        INSERT INTO payroll_runs (payroll_month, payroll_year, generated_by, absence_months)
        VALUES (p_month, p_year, p_user, p_absence_months)
        RETURNING * INTO v_run;
    END IF;

    INSERT INTO payroll_ledger (
        employee_id, payroll_month, payroll_year, run_id,
        days_in_month, paid_days, basic, nopay_days, nopay_deduction, absent_days, absence_deduction,
        gross, epf_employee, epf_employer, etf, net_payable
    )
    SELECT l.employee_id, p_month, p_year, v_run.id,
           l.days_in_month, l.paid_days, l.basic, l.nopay_days, l.nopay_deduction, l.absent_days, l.absence_deduction,
           l.gross, l.epf_employee, l.epf_employer, l.etf, l.net_payable
    FROM jsonb_to_recordset(p_lines) AS l(
        employee_id INTEGER, days_in_month INTEGER, paid_days INTEGER,
        basic NUMERIC, nopay_days NUMERIC, nopay_deduction NUMERIC, absent_days NUMERIC, absence_deduction NUMERIC,
        gross NUMERIC, epf_employee NUMERIC, epf_employer NUMERIC, etf NUMERIC, net_payable NUMERIC
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
-- 5. approve_payroll_run: as in 026, and records the closes it deducts
-- ---------------------------------------------------------------------------

DROP FUNCTION IF EXISTS approve_payroll_run(INTEGER, UUID, TIMESTAMPTZ);

CREATE OR REPLACE FUNCTION approve_payroll_run(p_run_id INTEGER, p_user UUID, p_generated_at TIMESTAMPTZ,
                                               p_close_ids INTEGER[])
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
    v_marked INTEGER;
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

    -- The closed months whose absences this run deducts. Each is taken once:
    -- one already taken, or reopened since the check, makes the draft out
    -- of date.
    IF COALESCE(array_length(p_close_ids, 1), 0) > 0 THEN
        UPDATE attendance_month_closes
        SET deducted_in_run_id = v_run.id
        WHERE id = ANY(p_close_ids) AND status = 'Closed' AND deducted_in_run_id IS NULL;
        GET DIAGNOSTICS v_marked = ROW_COUNT;
        IF v_marked <> array_length(p_close_ids, 1) THEN
            RAISE EXCEPTION 'The payroll draft for %/% is out of date: a month it deducts absences for was reopened or already deducted. Regenerate it before approving.',
                v_run.payroll_month, v_run.payroll_year;
        END IF;
    END IF;

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
