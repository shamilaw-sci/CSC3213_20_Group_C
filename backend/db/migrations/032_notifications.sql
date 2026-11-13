-- 032_notifications.sql
--
-- Personal updates (policy confirmed 2026-11-13): a message to one person
-- when something about them is decided. In-app only, no email.
--
--   leave_decided       your leave request was approved, or rejected (reason)
--   correction_decided  your attendance correction was approved or rejected
--   case_assigned       someone else assigned you a rescue case
--   payslip_ready       a month's payroll was approved: your payslip is there
--
-- Written by the API at each decision (app/services/notifications.py),
-- fail-soft: a notification that cannot be written never fails the decision.
-- Nobody is notified of their own action.
--
-- The bell's "Needs your action" is worked out live (app/api/inbox.py); these
-- are the stored half, with read state. Kept, not deleted: Settings shows the
-- history. read_at NULL = unread.
--
-- RLS: unlike the permissive tables, a person reads and updates only their
-- own rows, so another user's updates (leave reasons, payslip months) can't be
-- read through the REST API with a staff JWT. Anyone signed in may insert, as
-- the person deciding writes the other person's notification. No delete.
--
-- APPLY in the Supabase SQL editor. Safe to re-run.

CREATE TABLE IF NOT EXISTS public.notifications (
    id         BIGSERIAL PRIMARY KEY,
    user_id    UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    kind       VARCHAR(30) NOT NULL
               CHECK (kind IN ('leave_decided', 'correction_decided', 'case_assigned', 'payslip_ready')),
    title      VARCHAR(200) NOT NULL,
    body       VARCHAR(600),
    href       VARCHAR(200),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    read_at    TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_notifications_user
    ON public.notifications (user_id, created_at DESC);

ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS notifications_own_select ON public.notifications;
CREATE POLICY notifications_own_select ON public.notifications
    FOR SELECT TO authenticated USING (user_id = auth.uid());
DROP POLICY IF EXISTS notifications_own_update ON public.notifications;
CREATE POLICY notifications_own_update ON public.notifications
    FOR UPDATE TO authenticated USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
DROP POLICY IF EXISTS notifications_authenticated_insert ON public.notifications;
CREATE POLICY notifications_authenticated_insert ON public.notifications
    FOR INSERT TO authenticated WITH CHECK (true);

NOTIFY pgrst, 'reload schema';
