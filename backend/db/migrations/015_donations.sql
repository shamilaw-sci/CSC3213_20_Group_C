-- 015_donations.sql
--
-- Public donations: one row per donation attempt, and the atomic step that
-- posts a paid donation to the finance ledger.
--
-- Additive only:
--   * One new table, donations.
--   * One new function, record_donation_payment(), which the API calls once
--     the payment gateway has confirmed the payment.
--   * No existing table, column, trigger, function or policy is changed.
--     financial_transactions already allows source_type 'donation' (013).
--
-- Ledger rules, following 002_restricted_funds.sql:
--   * Every paid donation becomes ONE Income row, status Cash,
--     source_type 'donation', dated the day the payment was confirmed.
--   * Program donation: program_id set and is_restricted = TRUE, so the money
--     counts towards that program's restricted (earmarked) funds and can only
--     be spent on that program.
--   * General donation: program_id NULL, is_restricted = FALSE.
--   * A donation is posted only once. Calling the function again for the same
--     donation does nothing and returns the existing ledger row.
--
-- Anonymous donations store no name, email or phone at all.
--
-- APPLY in the Supabase SQL editor: paste the whole file and press Run once.
-- Safe to re-run.

-- ---------------------------------------------------------------------------
-- STEP 1. The donations table
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.donations (
    id                       BIGSERIAL PRIMARY KEY,
    amount                   NUMERIC(15, 2) NOT NULL CHECK (amount >= 100 AND amount <= 999999.99),
    currency                 VARCHAR(3) NOT NULL DEFAULT 'LKR',
    -- 'program' = given for one program (restricted), 'general' = any purpose.
    purpose                  VARCHAR(10) NOT NULL CHECK (purpose IN ('program', 'general')),
    program_id               INTEGER REFERENCES public.programs(id) ON DELETE RESTRICT,
    is_anonymous             BOOLEAN NOT NULL DEFAULT FALSE,
    donor_name               VARCHAR(150),
    donor_email              VARCHAR(255),
    donor_phone              VARCHAR(30),
    message                  VARCHAR(500),
    -- pending: sent to the gateway, not paid yet. paid: confirmed and posted
    -- to the ledger. failed / cancelled: never paid, never posted.
    status                   VARCHAR(10) NOT NULL DEFAULT 'pending'
                             CHECK (status IN ('pending', 'paid', 'failed', 'cancelled')),
    gateway                  VARCHAR(20) NOT NULL DEFAULT 'payhere',
    -- The gateway's own id for this payment (the PayHere order_id we send
    -- to checkout). Unique so one payment can never be recorded twice.
    gateway_ref              VARCHAR(255) UNIQUE,
    finance_transaction_id   INTEGER REFERENCES public.financial_transactions(id) ON DELETE RESTRICT,
    thank_you_sent_at        TIMESTAMPTZ,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    paid_at                  TIMESTAMPTZ,

    -- A program donation names its program; a general one names none.
    CONSTRAINT donations_purpose_program CHECK (
        (purpose = 'program' AND program_id IS NOT NULL)
        OR (purpose = 'general' AND program_id IS NULL)
    ),
    -- Anonymous means nothing about the donor is stored.
    CONSTRAINT donations_anonymous_no_details CHECK (
        is_anonymous = FALSE
        OR (donor_name IS NULL AND donor_email IS NULL AND donor_phone IS NULL)
    ),
    -- A named donor gives at least a name and an email.
    CONSTRAINT donations_named_has_details CHECK (
        is_anonymous = TRUE
        OR (donor_name IS NOT NULL AND donor_email IS NOT NULL)
    ),
    -- Paid and posted to the ledger always go together.
    CONSTRAINT donations_paid_is_posted CHECK (
        (status = 'paid') = (finance_transaction_id IS NOT NULL AND paid_at IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_donations_status_created ON public.donations (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_donations_program ON public.donations (program_id);
CREATE INDEX IF NOT EXISTS idx_donations_email ON public.donations (lower(donor_email));

COMMENT ON TABLE public.donations IS
    'Public donations. Only status=paid rows are real money; each has exactly one Income row in financial_transactions (source_type donation).';

-- ---------------------------------------------------------------------------
-- STEP 2. Mark a donation paid and post it to the ledger, in one transaction
-- ---------------------------------------------------------------------------
-- Called by the API only after the gateway has confirmed the payment.
-- Locks the donation row first, so two confirmations arriving at once (the
-- donor's return page and the gateway's callback) cannot post it twice.
CREATE OR REPLACE FUNCTION public.record_donation_payment(
    p_donation_id BIGINT,
    p_amount      NUMERIC
)
RETURNS public.donations
LANGUAGE plpgsql
AS $$
DECLARE
    d     public.donations;
    tx_id INTEGER;
BEGIN
    SELECT * INTO d FROM public.donations WHERE id = p_donation_id FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Donation % not found', p_donation_id;
    END IF;

    -- Already posted: nothing to do.
    IF d.status = 'paid' THEN
        RETURN d;
    END IF;

    -- The gateway must confirm exactly the amount the donor pledged.
    IF p_amount IS DISTINCT FROM d.amount THEN
        RAISE EXCEPTION 'Donation % paid amount % does not match %', p_donation_id, p_amount, d.amount;
    END IF;

    INSERT INTO public.financial_transactions
        (transaction_date, amount, transaction_type, status, program_id, is_restricted, source_type)
    VALUES
        (CURRENT_DATE, d.amount, 'Income', 'Cash', d.program_id, d.purpose = 'program', 'donation')
    RETURNING id INTO tx_id;

    UPDATE public.donations
       SET status = 'paid', paid_at = now(), finance_transaction_id = tx_id
     WHERE id = p_donation_id
    RETURNING * INTO d;

    RETURN d;
END;
$$;

-- ---------------------------------------------------------------------------
-- STEP 3. RLS, same pattern as 003 and 004
-- ---------------------------------------------------------------------------
-- No anon policy: the public donate form goes through FastAPI on the
-- service_role client. Staff read through FastAPI with require_permission().
ALTER TABLE public.donations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS donations_authenticated_all ON public.donations;
CREATE POLICY donations_authenticated_all ON public.donations
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ---------------------------------------------------------------------------
-- STEP 4. Make the API see the new table now
-- ---------------------------------------------------------------------------
NOTIFY pgrst, 'reload schema';

-- ---------------------------------------------------------------------------
-- AFTER RUNNING: check with these (screenshot the results)
-- ---------------------------------------------------------------------------
--   1. The table exists with its columns:
--      SELECT column_name, data_type, is_nullable
--        FROM information_schema.columns
--       WHERE table_name = 'donations' ORDER BY ordinal_position;
--   2. The function exists:
--      SELECT proname FROM pg_proc WHERE proname = 'record_donation_payment';
--   3. RLS is on:
--      SELECT relrowsecurity FROM pg_class WHERE relname = 'donations';

-- ---------------------------------------------------------------------------
-- IF YOU RAN AN EARLIER COPY OF THIS FILE (Stripe version: minimum LKR 200,
-- gateway default 'stripe'), run this once to match the PayHere version:
-- ---------------------------------------------------------------------------
--   ALTER TABLE public.donations ALTER COLUMN gateway SET DEFAULT 'payhere';
--   ALTER TABLE public.donations DROP CONSTRAINT IF EXISTS donations_amount_check;
--   ALTER TABLE public.donations ADD CONSTRAINT donations_amount_check
--       CHECK (amount >= 100 AND amount <= 999999.99);
--   NOTIFY pgrst, 'reload schema';
