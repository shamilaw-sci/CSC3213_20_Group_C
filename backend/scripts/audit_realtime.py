"""
Probe who can receive on, and who can send to, the private `rescue-board`
Realtime channel — against the live Realtime API, the way audit_rls.py probes
PostgREST. Reading migration 006 says what the policy means; this says what
Realtime actually does with it.

Checks
    1. anon cannot subscribe       anon key as the JWT, private join -> refused
    2. nobody but the backend can send (the spoofing case — the one that matters)
                                   every client route below is attempted, and a
                                   staff listener must receive none of them
    3. staff can subscribe and receive a server ping
                                   private join with a staff JWT -> accepted, and
                                   the real notify_board_changed() is delivered

Why check 2 needs a listener. A send can be refused loudly (HTTP error, error
reply) or accepted at the door and dropped by the authorizer, and those look
different per route. The only answer that does not depend on reading Realtime's
status codes correctly is whether a legitimate subscriber actually received
it. So check 2 is decided by delivery, not by response codes; the codes are
printed as diagnostics only.

Positive controls, before AND after the spoof attempts. A listener that never
receives anything would pass check 2 trivially. The first control proves it
can receive; the second proves it was still connected while the spoofs ran.
Both send through the real app.services.board_events, so they also verify the
production send path. Open boards will refetch twice — harmless, and the point.

Spoof routes attempted (each carries a distinct marker in its payload):
    anon-ws-private     anon joins the private topic over the socket and sends
                        (only reached if check 1 failed)
    anon-rest-private   anon key, REST broadcast, private: true
    anon-rest-public    anon key, REST broadcast, private: false, same topic
    anon-ws-public      anon joins the PUBLIC topic of the same name and sends
    staff-rest-private  staff JWT, REST broadcast, private: true
    staff-ws-private    staff JWT joins the private topic (allowed — SELECT
                        policy) and sends from it (must not be — no INSERT)
The staff routes matter as much as the anon ones: General Staff is the default
role for self-registration, so a staff JWT is one signup away for anyone.

Usage:
    python scripts/audit_realtime.py --as-staff EMAIL PASSWORD   # all checks
    python scripts/audit_realtime.py                             # check 1 only

Run it before applying migration 006 as well as after: before, the staff join
should be refused too (no SELECT policy yet), which shows the probe can tell
the two states apart.
"""

import asyncio
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))

import websockets

from audit_rls import ANON_KEY, SERVICE_KEY, URL, _headers, staff_token
from app.services import board_events

TOPIC = board_events.BOARD_TOPIC
EVENT = board_events.BOARD_EVENT
WS_URL = URL.replace("https://", "wss://").replace("http://", "ws://") + "/realtime/v1/websocket"

# Long enough for Realtime to fan a message out; measured deliveries are well
# under a second.
SETTLE = 3.0

JOINED, REFUSED, UNKNOWN = "joined", "refused", "unknown"


class Socket:
    """A bare Phoenix-protocol Realtime client, so nothing hides a refusal."""

    def __init__(self, label):
        self.label = label
        self.ws = None
        self.messages = []
        self._ref = 0
        self._reader = None

    async def open(self):
        self.ws = await websockets.connect(f"{WS_URL}?apikey={ANON_KEY}&vsn=1.0.0")
        self._reader = asyncio.create_task(self._read())

    async def _read(self):
        try:
            async for raw in self.ws:
                self.messages.append(json.loads(raw))
        except websockets.ConnectionClosed:
            pass

    def _next_ref(self):
        self._ref += 1
        return str(self._ref)

    async def _reply(self, ref, timeout=10.0):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            for m in self.messages:
                if m.get("ref") == ref and m.get("event") == "phx_reply":
                    return m["payload"]
            await asyncio.sleep(0.05)
        return None

    def _refused_after_join(self, topic):
        # Realtime can accept the join and then close the channel with a
        # system error once authorization runs. Either way it is a refusal.
        for m in self.messages:
            if m.get("topic") != topic:
                continue
            if m.get("event") in ("phx_close", "phx_error"):
                return m.get("event")
            if m.get("event") == "system" and m.get("payload", {}).get("status") == "error":
                return m["payload"].get("message", "system error")
        return None

    async def join(self, private, access_token):
        """Returns (outcome, detail): outcome is JOINED, REFUSED or UNKNOWN.

        UNKNOWN (no reply) is kept apart from REFUSED on purpose. A first run
        of this script timed out on a cold connection and scored the silence
        as "anon cannot subscribe" — a pass produced by a broken probe.
        """
        topic = f"realtime:{TOPIC}"
        ref = self._next_ref()
        self.join_ref = ref
        await self.ws.send(json.dumps({
            "topic": topic, "event": "phx_join", "ref": ref, "join_ref": ref,
            "payload": {
                "config": {
                    "broadcast": {"ack": True, "self": False},
                    "presence": {"key": ""},
                    "postgres_changes": [],
                    "private": private,
                },
                "access_token": access_token,
            },
        }))
        reply = await self._reply(ref)
        if reply is None:
            return UNKNOWN, "no reply - inconclusive, not a refusal"
        if reply.get("status") != "ok":
            return REFUSED, json.dumps(reply.get("response"))[:160]
        await asyncio.sleep(1.0)
        late = self._refused_after_join(topic)
        if late:
            return REFUSED, f"accepted, then {late}"
        return JOINED, "ok"

    async def send(self, marker):
        ref = self._next_ref()
        await self.ws.send(json.dumps({
            "topic": f"realtime:{TOPIC}", "event": "broadcast", "ref": ref, "join_ref": self.join_ref,
            "payload": {"type": "broadcast", "event": EVENT, "payload": {"probe": marker}},
        }))
        reply = await self._reply(ref, timeout=2.0)
        return reply.get("status") if reply else "no reply"

    def received(self):
        return [
            m["payload"].get("payload")
            for m in self.messages
            if m.get("event") == "broadcast" and m.get("payload", {}).get("event") == EVENT
        ]

    async def close(self):
        if self.ws:
            await self.ws.close()
        if self._reader:
            await self._reader


def rest_send(apikey, marker, private, bearer=None):
    req = urllib.request.Request(
        f"{URL}/realtime/v1/api/broadcast",
        headers=_headers(apikey, {"Content-Type": "application/json"}, bearer=bearer),
        data=json.dumps({"messages": [{
            "topic": TOPIC, "event": EVENT, "payload": {"probe": marker}, "private": private,
        }]}).encode(),
        method="POST",
    )
    try:
        return urllib.request.urlopen(req).status
    except urllib.error.HTTPError as e:
        return e.code


results = []


def check(name, passed, detail=""):
    results.append(passed)
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


async def anon_cannot_subscribe():
    anon = Socket("anon")
    await anon.open()
    outcome, detail = await anon.join(private=True, access_token=ANON_KEY)
    check("1. anon cannot subscribe to the private topic", outcome == REFUSED, detail)
    return anon, outcome


async def server_ping_delivered(listener, label):
    before = len(listener.received())
    await board_events.notify_board_changed()
    await asyncio.sleep(SETTLE)
    got = listener.received()[before:]
    delivered = {} in got
    check(f"3b. listener received the server ping ({label})", delivered,
          f"got {got}" if not delivered else "")
    return delivered


async def run_full(email, password):
    token = staff_token(email, password)

    print("Subscriber")
    listener = Socket("staff-listener")
    await listener.open()
    outcome, detail = await listener.join(private=True, access_token=token)
    check("3a. staff can subscribe to the private topic", outcome == JOINED, detail)
    if outcome != JOINED:
        print("\nNo staff subscription, so nothing below can be judged by delivery. Stopping.")
        return

    print("\nPositive control (before)")
    if not await server_ping_delivered(listener, "before spoofs"):
        print("\nListener cannot receive, so a clean spoof result would mean nothing. Stopping.")
        return

    print("\nAnon")
    anon, anon_outcome = await anon_cannot_subscribe()
    codes = {}
    if anon_outcome != REFUSED:
        codes["anon-ws-private"] = await anon.send("anon-ws-private")
    await anon.close()

    codes["anon-rest-private"] = rest_send(ANON_KEY, "anon-rest-private", private=True)
    codes["anon-rest-public"] = rest_send(ANON_KEY, "anon-rest-public", private=False)

    anon_public = Socket("anon-public")
    await anon_public.open()
    pub_outcome, pub_detail = await anon_public.join(private=False, access_token=ANON_KEY)
    codes["anon-ws-public"] = (await anon_public.send("anon-ws-public")) if pub_outcome == JOINED else f"join {pub_outcome}: {pub_detail}"
    await anon_public.close()

    print("\nStaff (sending)")
    codes["staff-rest-private"] = rest_send(ANON_KEY, "staff-rest-private", private=True, bearer=token)
    staff_sender = Socket("staff-sender")
    await staff_sender.open()
    s_outcome, s_detail = await staff_sender.join(private=True, access_token=token)
    codes["staff-ws-private"] = (await staff_sender.send("staff-ws-private")) if s_outcome == JOINED else f"join {s_outcome}: {s_detail}"
    await staff_sender.close()

    await asyncio.sleep(SETTLE)

    print("\nSpoofing — decided by what the staff listener received")
    leaked = {p.get("probe") for p in listener.received() if isinstance(p, dict) and p.get("probe")}
    for marker, code in codes.items():
        check(f"2. {marker} was not delivered", marker not in leaked, f"response: {code}")

    print("\nPositive control (after)")
    await server_ping_delivered(listener, "after spoofs")
    await listener.close()


async def run_anon_only():
    print("Anon (no staff credentials given: spoofing and staff checks are NOT run)")
    anon, _ = await anon_cannot_subscribe()
    await anon.close()


def main():
    if "--as-staff" in sys.argv:
        i = sys.argv.index("--as-staff")
        if len(sys.argv) < i + 3:
            sys.exit("usage: audit_realtime.py --as-staff EMAIL PASSWORD")
        asyncio.run(run_full(sys.argv[i + 1], sys.argv[i + 2]))
    else:
        asyncio.run(run_anon_only())

    failed = results.count(False)
    print(f"\n{len(results) - failed} passed, {failed} failed")
    sys.exit(1 if failed or not results else 0)


if __name__ == "__main__":
    main()
