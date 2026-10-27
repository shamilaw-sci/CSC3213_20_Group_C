"""
Probe every table's real exposure to the public anon key, via the live REST API.

This project has been bitten more than once by RLS policies that read correctly
in the Supabase editor but behaved differently at runtime. The only trustworthy
check is the one that asks PostgREST the same question an attacker would, with
the same key an attacker would have — the anon key is shipped to every browser
in NEXT_PUBLIC_SUPABASE_ANON_KEY, so it is public by construction.

Read probe
    Count rows as service_role, then as anon, and compare. Equal counts mean
    anon sees everything; zero means anon is shut out; anything between means a
    filtering policy (outbreak_zones is the intended example — anon sees only
    the active zones).

Write probe
    POSTs an empty object `{}`. Safe by construction rather than by judgement:
    the probe only runs against tables PostgREST reports as having at least one
    required field (a NOT NULL column with no default), so the insert is
    guaranteed to fail a not-null constraint even when the policy allows it.
    That list comes from the live OpenAPI spec, not from a hand-maintained
    table of column names that could drift from the database. The two failure
    modes are then diagnostic:

        42501   RLS refused the write   -> anon cannot insert
        23502   not-null violation      -> RLS ALLOWED the write and the
                                           constraint is what stopped it
                                           -> anon CAN insert

    A not-null error is the bad result. Nothing is written either way, which is
    what makes this safe to run against the live database. Tables with no
    required field are reported as unprobed rather than guessed at — writing a
    junk row to find out would be worse than not knowing.

Staff probe (--as-staff)
    Signs in as a real staff account and re-counts every table using that JWT,
    which is what role `authenticated` actually sees. This is the number that
    decides whether enabling RLS breaks the application: get_supabase() applies
    the caller's token to PostgREST, so every permission-gated staff endpoint
    runs as `authenticated`, not as service_role. A table that goes to zero
    here after a policy change is a broken feature.

Usage:
    python scripts/audit_rls.py              # read + write probes
    python scripts/audit_rls.py --read-only  # GETs only, issues no POST at all
    python scripts/audit_rls.py --as-staff EMAIL PASSWORD
"""

import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

URL = os.environ.get("SUPABASE_URL")
SERVICE_KEY = os.environ.get("SUPABASE_KEY")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

if not URL or not SERVICE_KEY or not ANON_KEY:
    sys.exit("SUPABASE_URL, SUPABASE_KEY and SUPABASE_ANON_KEY must all be set.")

# PostgREST surfaces the Postgres SQLSTATE in the JSON body.
RLS_DENIED = "42501"   # insufficient_privilege: the policy stopped the write
NOT_NULL = "23502"     # not_null_violation: the policy let it through


def _headers(apikey, extra=None, bearer=None):
    """
    Supabase authenticates on two headers that are NOT interchangeable.

    `apikey` must always be a project key (anon or service_role) — the API
    gateway validates it before the request reaches PostgREST. `Authorization`
    carries whatever identity the request should run as. For the anon and
    service_role probes those are the same string, which is why passing one
    value worked; for a user JWT they must differ, or the gateway rejects the
    JWT as an invalid project key and returns 401 before any policy is ever
    consulted. A 401 from that mistake looks exactly like a locked-down table,
    which is the kind of false negative this script exists to avoid.
    """
    if apikey not in (ANON_KEY, SERVICE_KEY):
        raise ValueError(
            "apikey must be the anon or service_role project key. Passing a "
            "user JWT here makes the gateway 401 every request, which this "
            "script would otherwise report as a table anon cannot read."
        )
    h = {"apikey": apikey, "Authorization": f"Bearer {bearer or apikey}"}
    if extra:
        h.update(extra)
    return h


def discover_tables():
    """
    Every table PostgREST exposes, mapped to its required (NOT NULL, no
    default) fields. Read from the live spec so a table added to the database
    tomorrow is audited without anyone remembering to edit this file.
    """
    req = urllib.request.Request(
        f"{URL}/rest/v1/",
        headers=_headers(SERVICE_KEY, {"Accept": "application/openapi+json"}),
    )
    spec = json.loads(urllib.request.urlopen(req).read())
    return {
        name: defn.get("required", [])
        for name, defn in spec.get("definitions", {}).items()
    }


def count_rows(table, key, bearer=None):
    """
    Exact row count as seen by `bearer` (defaulting to `key`), or an error.

    `key` is the project key sent as `apikey`; `bearer` is the identity to run
    as. Pass a user JWT as `bearer` with ANON_KEY as `key` — never as `key`.
    """
    req = urllib.request.Request(
        f"{URL}/rest/v1/{table}?select=*",
        headers=_headers(key, {"Prefer": "count=exact", "Range": "0-0"}, bearer),
    )
    try:
        resp = urllib.request.urlopen(req)
        # Content-Range looks like "0-0/57"; the total is what we want, and
        # "*/0" is how PostgREST reports an empty result.
        return int(resp.headers.get("Content-Range", "*/0").split("/")[-1])
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}"


def _post_empty(table, key):
    """POST a literal `{}` as `key`. Returns the SQLSTATE, or None on success."""
    req = urllib.request.Request(
        f"{URL}/rest/v1/{table}",
        headers=_headers(key, {"Content-Type": "application/json",
                               "Prefer": "return=minimal"}),
        data=b"{}",
        method="POST",
    )
    try:
        urllib.request.urlopen(req)
        return None
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()).get("code", "") or f"HTTP {e.code}"
        except Exception:
            return f"HTTP {e.code}"


def can_anon_insert(table, required):
    """
    'WRITABLE' / 'blocked' / 'not probed'.

    The probe body is a literal `{}` — this module never constructs a payload
    containing column values, so there is no code path that can write a
    meaningful row. What stops it writing an all-defaults row is a NOT NULL
    constraint, and rather than trusting the OpenAPI spec's `required` list to
    predict that, we prove it: fire the same empty insert as service_role
    first. service_role bypasses RLS, so a not-null failure there is the
    constraint firing with policy enforcement out of the picture. Only once
    that is observed do we repeat it as anon, where the result can then only be

        23502  the same constraint  -> RLS let anon through -> WRITABLE
        42501  policy refusal       -> RLS stopped anon     -> blocked

    If the service_role pre-flight does anything else, we skip the anon probe
    and report why. That costs a table's worth of coverage and risks nothing.
    """
    if not required:
        return "not probed (no NOT NULL column to fail on)"

    preflight = _post_empty(table, SERVICE_KEY)
    if preflight is None:
        return ("NOT PROBED - service_role wrote an all-defaults row; "
                "spec claims NOT NULL but the database disagrees. DELETE IT.")
    if preflight != NOT_NULL:
        return f"not probed (pre-flight gave {preflight}, expected {NOT_NULL})"

    # The constraint is now known to fire for this exact request, so the anon
    # attempt cannot write regardless of what the policy decides.
    code = _post_empty(table, ANON_KEY)
    if code == RLS_DENIED:
        return "blocked"
    if code == NOT_NULL:
        return "WRITABLE"
    return f"inconclusive (SQLSTATE {code})"


def password_hash_exposure():
    """
    How many users rows carry a non-null password_hash, and how many of those
    anon can read.

    db/init.sql calls this column "Not used for Supabase Auth, but kept for ER
    diagram compliance". If that is true the column is dead weight and the
    users exposure is emails and roles. If it is false, the public anon key
    reads credential material, which is a different severity of problem. Worth
    one query rather than an assumption either way.
    """
    out = {}
    for label, key in (("service", SERVICE_KEY), ("anon", ANON_KEY)):
        req = urllib.request.Request(
            f"{URL}/rest/v1/users?select=id&password_hash=not.is.null",
            headers=_headers(key, {"Prefer": "count=exact", "Range": "0-0"}),
        )
        try:
            resp = urllib.request.urlopen(req)
            out[label] = int(resp.headers.get("Content-Range", "*/0").split("/")[-1])
        except urllib.error.HTTPError as e:
            out[label] = f"HTTP {e.code}"
    return out


def staff_token(email, password):
    """A real staff JWT, obtained the same way the login page obtains one."""
    req = urllib.request.Request(
        f"{URL}/auth/v1/token?grant_type=password",
        headers={"apikey": ANON_KEY, "Content-Type": "application/json"},
        data=json.dumps({"email": email, "password": password}).encode(),
        method="POST",
    )
    try:
        return json.loads(urllib.request.urlopen(req).read())["access_token"]
    except urllib.error.HTTPError as e:
        sys.exit(f"Login failed for {email}: HTTP {e.code} {e.read()[:200]!r}")


def run_as_staff(email, password):
    """
    Counts as role `authenticated`, plus the get_current_user path explicitly.

    That path is checked on its own because it is the one that takes the whole
    app down if it breaks: security.py resolves every request's user by reading
    users joined to roles with the caller's own token. If either table gets RLS
    without an authenticated policy, this query returns nothing, get_current_user
    raises 403, and no authenticated endpoint in the application works.
    """
    token = staff_token(email, password)

    # Confirm the token is actually being accepted before reporting any counts.
    # Without this, a header mistake yields a column of zeros and 401s that
    # reads like a perfectly locked-down database.
    probe = urllib.request.Request(
        f"{URL}/auth/v1/user", headers=_headers(ANON_KEY, bearer=token)
    )
    try:
        who = json.loads(urllib.request.urlopen(probe).read())
    except urllib.error.HTTPError as e:
        sys.exit(f"Token rejected by /auth/v1/user: HTTP {e.code} {e.read()[:200]!r}")

    tables = discover_tables()

    print(f"Signed in as {email} (sub={who.get('id')}, role={who.get('role')}). "
          f"Counts as role `authenticated`:\n")
    print(f"{'table':<24} {'service':>8} {'authenticated':>14}")
    print("-" * 50)
    for table in sorted(tables):
        print(f"{table:<24} {str(count_rows(table, SERVICE_KEY)):>8} "
              f"{str(count_rows(table, ANON_KEY, bearer=token)):>14}")

    # Filtered to the caller's own sub, exactly as security.py does. An
    # unfiltered limit=1 would report on whichever row PostgREST happened to
    # return first — which can succeed while the real, filtered query fails,
    # and prints a role name belonging to somebody else.
    sub = who.get("id")
    req = urllib.request.Request(
        f"{URL}/rest/v1/users?select=*,roles(role_name)&id=eq.{sub}",
        headers=_headers(ANON_KEY, bearer=token),
    )
    try:
        rows = json.loads(urllib.request.urlopen(req).read())
        if not rows:
            print(f"\nget_current_user join for sub={sub}: RETURNED NOTHING "
                  f"- login would break")
        elif rows[0].get("roles") is None:
            print(f"\nget_current_user join for sub={sub}: user row OK but the "
                  f"embedded roles() is NULL - require_permission would deny "
                  f"everything")
        else:
            print(f"\nget_current_user join for sub={sub}: OK - "
                  f"{rows[0]['roles']}")
    except urllib.error.HTTPError as e:
        print(f"\nget_current_user join for sub={sub} FAILED: HTTP {e.code} "
              f"{e.read()[:200]!r} - login would break")


def main():
    if "--as-staff" in sys.argv:
        i = sys.argv.index("--as-staff")
        try:
            return run_as_staff(sys.argv[i + 1], sys.argv[i + 2])
        except IndexError:
            sys.exit("Usage: audit_rls.py --as-staff EMAIL PASSWORD")

    read_only = "--read-only" in sys.argv
    tables = discover_tables()

    print(f"{'table':<24} {'service':>8} {'anon':>8}  {'anon read':<12} {'anon insert'}")
    print("-" * 78)

    for table in sorted(tables):
        service_n = count_rows(table, SERVICE_KEY)
        anon_n = count_rows(table, ANON_KEY)

        if isinstance(anon_n, str):
            verdict = anon_n
        elif service_n == 0:
            # An empty table tells us nothing: anon reading 0 of 0 rows looks
            # identical whether the policy is airtight or absent. Say so rather
            # than letting `anon == service` report a wide-open table as
            # "FULL READ" or a locked one as "blocked" — a verdict that depends
            # on whether someone happened to have inserted a row yet is worse
            # than no verdict.
            verdict = "empty (n/a)"
        elif anon_n == 0:
            verdict = "blocked"
        elif anon_n == service_n:
            verdict = "FULL READ"
        else:
            verdict = "filtered"

        write = "skipped" if read_only else can_anon_insert(table, tables[table])

        print(f"{table:<24} {str(service_n):>8} {str(anon_n):>8}  "
              f"{verdict:<12} {write}")

    pw = password_hash_exposure()
    print(f"\nusers.password_hash non-null: {pw['service']} of "
          f"{count_rows('users', SERVICE_KEY)} rows "
          f"({pw['anon']} of them readable by anon)")


if __name__ == "__main__":
    main()
