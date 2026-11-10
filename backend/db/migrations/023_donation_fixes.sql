-- 023_donation_fixes.sql
--
-- Donation fixes from the audit. Only the donations table and its own
-- function change, plus one trigger on financial_transactions that reacts
-- to donation rows only.
--
--   D3  A donation can be 'refunded'. When finance staff void a donation's
--       ledger row, the donation becomes refunded by itself, so the Donation
--       details page and the ledger agree. gateway_note records what PayHere
--       reported that needs a person (a chargeback, a wrong amount).
--   D5  record_donation_payment() dates the ledger row with Sri Lanka's date,
--       not the database's UTC date. It still keeps its existing permissions.
--   D2  Logged-in users can no longer read the donations table straight from
--       Supabase. The backend reads it with its service key, and only after
--       checking finance:read. Only this table changes.
--
-- APPLY in the Supabase SQL editor: paste the whole file and press Run once.
-- Safe to re-run.

-- ---------------------------------------------------------------------------
-- STEP 1. Refunded status and the note column (D3)
-- ---------------------------------------------------------------------------
ALTER TABLE public.donations ADD COLUMN IF NOT EXISTS refunded_at  TIMESTAMPTZ;
ALTER TABLE public.donations ADD COLUMN IF NOT EXISTS gateway_note VARCHAR(300);

ALTER TABLE public.donations DROP CONSTRAINT IF EXISTS donations_status_check;
ALTER TABLE public.donations ADD CONSTRAINT donations_status_check
    CHECK (status IN ('pending', 'paid', 'failed', 'cancelled', 'refunded'));

-- A refunded donation was paid and posted once, so it keeps its ledger link.
ALTER TABLE public.donations DROP CONSTRAINT IF EXISTS donations_paid_is_posted;
ALTER TABLE public.donations ADD CONSTRAINT donations_paid_is_posted CHECK (
    (status IN ('paid', 'refunded')) = (finance_transaction_id IS NOT NULL AND paid_at IS NOT NULL)
);

-- ---------------------------------------------------------------------------
-- STEP 2. Voiding a donation's ledger row marks the donation refunded (D3)
-- ---------------------------------------------------------------------------
-- SECURITY DEFINER so it works whoever voids the row, even if the donations
-- table is later closed to direct access. It only ever touches the donation
-- linked to the voided row.
CREATE OR REPLACE FUNCTION public.donation_refund_on_void()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF NEW.status = 'Voided' AND OLD.status IS DISTINCT FROM 'Voided'
       AND NEW.source_type = 'donation' THEN
        UPDATE public.donations
           SET status = 'refunded', refunded_at = now()
         WHERE finance_transaction_id = NEW.id
           AND status = 'paid';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.donation_refund_on_void() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS donation_refund_on_void ON public.financial_transactions;
CREATE TRIGGER donation_refund_on_void
    AFTER UPDATE OF status ON public.financial_transactions
    FOR EACH ROW EXECUTE FUNCTION public.donation_refund_on_void();

-- Donations whose ledger row was voided before this file ran.
UPDATE public.donations d
   SET status = 'refunded', refunded_at = coalesce(d.refunded_at, now())
  FROM public.financial_transactions t
 WHERE t.id = d.finance_transaction_id
   AND t.status = 'Voided'
   AND d.status = 'paid';

-- ---------------------------------------------------------------------------
-- STEP 3. Sri Lanka date on the ledger row (D5)
-- ---------------------------------------------------------------------------
-- Same name and arguments as 015, so its permissions stay exactly as they
-- are. Changes: the date, and a refunded donation is never posted again.
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

    -- Already posted (and maybe refunded since): nothing to do.
    IF d.status IN ('paid', 'refunded') THEN
        RETURN d;
    END IF;

    -- The gateway must confirm exactly the amount the donor pledged.
    IF p_amount IS DISTINCT FROM d.amount THEN
        RAISE EXCEPTION 'Donation % paid amount % does not match %', p_donation_id, p_amount, d.amount;
    END IF;

    INSERT INTO public.financial_transactions
        (transaction_date, amount, transaction_type, status, program_id, is_restricted, source_type)
    VALUES
        ((now() AT TIME ZONE 'Asia/Colombo')::date, d.amount, 'Income', 'Cash',
         d.program_id, d.purpose = 'program', 'donation')
    RETURNING id INTO tx_id;

    UPDATE public.donations
       SET status = 'paid', paid_at = now(), finance_transaction_id = tx_id
     WHERE id = p_donation_id
    RETURNING * INTO d;

    RETURN d;
END;
$$;

-- ---------------------------------------------------------------------------
-- STEP 4. Close the donations table to direct access (D2)
-- ---------------------------------------------------------------------------
-- RLS stays on, and with no policy left, a logged-in user's key reads
-- nothing. The backend's service key ignores RLS, so the donate page, PayHere
-- and the staff page keep working.
DROP POLICY IF EXISTS donations_authenticated_all ON public.donations;

NOTIFY pgrst, 'reload schema';

-- ---------------------------------------------------------------------------
-- AFTER RUNNING: check with these, one at a time (screenshot each result)
-- ---------------------------------------------------------------------------
-- 1. The status rule includes 'refunded':
--      SELECT pg_get_constraintdef(oid) FROM pg_constraint
--       WHERE conname = 'donations_status_check';
-- 2. The trigger exists:
--      SELECT tgname FROM pg_trigger WHERE tgname = 'donation_refund_on_void';
-- 3. Donations by status (voided ones now show as refunded):
--      SELECT status, count(*) FROM donations GROUP BY status ORDER BY status;
-- 4. No policy is left on donations (expect no rows):
--      SELECT policyname FROM pg_policies WHERE tablename = 'donations';
