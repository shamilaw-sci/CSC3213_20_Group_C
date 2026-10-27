-- 006_realtime_board_channel.sql
--
-- Lets signed-in staff RECEIVE on the private Realtime Broadcast topic
-- `rescue-board`, and lets nobody but the backend SEND on it.
--
-- WHAT THE CHANNEL IS FOR. After a case is created, moved or reassigned, the
-- backend (app/services/board_events.py) broadcasts an empty ping, and open
-- case-triage boards refetch GET /rescue_cases/cases. The ping carries no case
-- data and no case id; rescue:read is still enforced by FastAPI on the refetch.
-- postgres_changes on rescue_cases was rejected because that table's RLS is
-- permissive for every authenticated user, so subscribing to it would push full
-- case rows to accounts holding no rescue permission.
--
--
-- WHY PRIVATE, given the ping has no data. Two reasons, the first decisive:
--
--   1. Spoofing. On a public channel, anyone holding the anon key can SEND.
--      That key ships in every browser bundle, including the public /report
--      page, so anyone could make every open staff board refetch on demand.
--   2. Activity timing. Anyone could subscribe anonymously and learn when
--      reports arrive and cases move.
--
-- On a private channel, Realtime authorizes each join and each client send
-- against RLS on realtime.messages, using the JWT the client presents:
--
--   join (receive)   needs a SELECT policy matching the topic
--   client send      needs an INSERT policy matching the topic
--
-- This migration creates the first and deliberately NOT the second, for any
-- role. "No client can send" therefore holds by RLS's default deny rather than
-- by a policy someone could later loosen. The backend sends over the REST
-- broadcast endpoint with the service_role key, which bypasses RLS (BYPASSRLS),
-- so it needs no policy here.
--
-- Withholding INSERT from `authenticated` matters as much as from anon:
-- General Staff is the default role for self-registration, so `authenticated`
-- is effectively "anyone who signs up". Granting it INSERT would reopen the
-- spoofing hole one signup away.
--
--
-- WHY `authenticated` RATHER THAN THE rescue:read ROLES. Encoding the role
-- list in SQL would make a third copy of the permission matrix, after
-- app/core/permissions.py and frontend/src/lib/permissions.ts — and those two
-- have already drifted from reality once. The only signed-in roles without
-- rescue:read are Finance Officer and System Administrator; an empty ping tells
-- them nothing, and the refetch it triggers is refused by FastAPI.
--
--
-- SCOPE. realtime.messages already has RLS enabled by Supabase; this migration
-- does not ALTER the table. The policy is scoped to this one topic and to the
-- broadcast extension, so it grants nothing on any other channel and nothing
-- for presence. Any pre-existing policy on realtime.messages is untouched —
-- the before/after pg_policies query is how to confirm there is none that
-- widens this (in particular, no INSERT policy for anon or authenticated).
--
-- Verified against the live Realtime API, not by reading this file:
-- backend/scripts/audit_realtime.py.

DROP POLICY IF EXISTS rescue_board_authenticated_receive ON realtime.messages;
CREATE POLICY rescue_board_authenticated_receive
    ON realtime.messages
    FOR SELECT TO authenticated
    USING (
        (SELECT realtime.topic()) = 'rescue-board'
        AND realtime.messages.extension = 'broadcast'
    );
