"""Every route requires a signed-in user unless it is on PUBLIC_ROUTES.

A route with no auth dependency does not fail closed here — it runs as
service_role. get_supabase() falls back to the service_role client when no
token is sent, so RLS never applies. That is how GET /api/auth/users served
every user's email and role to anonymous callers. The RBAC matrix did list it,
but as a known-gap xfail, and an allowlist that has to be updated by hand is
what let that state persist.

So this file enumerates the app's registered routes instead of a hand-written
list, and checks behaviour, not just declarations:

  * every non-allowlisted route has get_current_user in its dependency tree;
  * every non-allowlisted route answers an anonymous request with 401;
  * every allowlisted route still exists and is still public, so the
    allowlist cannot quietly go stale.

Adding a public route means adding it to PUBLIC_ROUTES with a reason.
"""

import re

import pytest
from fastapi.routing import APIRoute

from app.core.security import get_current_user
from app.core.supabase import get_public_supabase, get_supabase
from app.main import app
from tests.test_rbac_matrix import _FakeSupabase, client

PUBLIC_ROUTES = {
    ("GET", "/"): "health check; returns a status message, no data",
    ("POST", "/api/auth/login"): "how a token is obtained",
    ("POST", "/api/auth/register"): "self-service signup; always assigned General Staff",
    ("POST", "/api/rescue_cases/cases"): "public rescue report form",
    ("POST", "/api/rescue_cases/upload-photo"): "photo upload step of the public report form",
    ("GET", "/api/rescue_cases/geo"): "public outbreak map; coordinates rounded to 3 dp, no case details",
    ("GET", "/api/rescue_cases/outbreak-zones"): "public outbreak map; active zones only",
    ("GET", "/api/rescue_cases/impact"):
        "public site impact numbers; this year's totals only, no case details",
    ("POST", "/api/volunteers/apply"): "public volunteer application form",
    ("GET", "/api/volunteers/my-assignments/{token}"):
        "volunteers have no login; the link token is the credential",
    ("POST", "/api/volunteers/my-assignments/{token}/{assignment_id}/respond"):
        "volunteers have no login; the link token is the credential",
    ("GET", "/api/donations/programs"):
        "public donate page; Upcoming and Active program names and dates only",
    ("GET", "/api/programs/public"):
        "public clinics page; published Upcoming and Active programs, no costs or team",
    ("POST", "/api/donations/checkout"):
        "public donate form; saves a pending donation, never touches the ledger",
    ("POST", "/api/donations/payhere/notify"):
        "PayHere server callback; every request is checked against md5sig",
    ("POST", "/api/donations/confirm/{order_id}"):
        "donors have no login; records only what PayHere confirms, returns no donor details",
    ("POST", "/api/donations/cancel/{order_id}"):
        "donors have no login; only moves a pending donation to cancelled",
}


def _requires_user(dependant):
    return any(d.call is get_current_user or _requires_user(d) for d in dependant.dependencies)


def _routes():
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in sorted(route.methods):
                yield method, route.path, route


ROUTES = list(_routes())
PROTECTED = [(m, p) for m, p, r in ROUTES if (m, p) not in PUBLIC_ROUTES]


def test_every_non_public_route_requires_a_signed_in_user():
    unguarded = sorted(
        f"{m} {p}" for m, p, r in ROUTES
        if (m, p) not in PUBLIC_ROUTES and not _requires_user(r.dependant)
    )
    assert unguarded == [], (
        "these routes run as service_role for anonymous callers; add an auth "
        f"dependency, or add them to PUBLIC_ROUTES with a reason: {unguarded}"
    )


def test_public_routes_allowlist_is_not_stale():
    registered = {(m, p): r for m, p, r in ROUTES}
    missing = sorted(f"{m} {p}" for m, p in PUBLIC_ROUTES if (m, p) not in registered)
    guarded = sorted(
        f"{m} {p}" for (m, p), r in registered.items()
        if (m, p) in PUBLIC_ROUTES and _requires_user(r.dependant)
    )
    assert missing == [], f"allowlisted but not registered: {missing}"
    assert guarded == [], f"allowlisted but requires auth — remove from PUBLIC_ROUTES: {guarded}"


@pytest.fixture
def no_live_db():
    # This test exists for the case where a route is NOT guarded — and then
    # its handler runs. Without this it would run as service_role against the
    # live database, and some of these routes are DELETEs.
    fake = lambda: _FakeSupabase()
    app.dependency_overrides[get_supabase] = fake
    app.dependency_overrides[get_public_supabase] = fake
    try:
        yield
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("method, path", PROTECTED, ids=[f"{m} {p}" for m, p in PROTECTED])
def test_anonymous_request_gets_401(method, path, no_live_db):
    # The auth dependency is resolved before path, query and body validation,
    # so placeholder path values and an empty body never reach a handler.
    url = re.sub(r"\{[^}]+\}", "1", path)
    response = client.request(method, url, json={})
    assert response.status_code == 401, f"{method} {path} -> {response.status_code}"
    assert response.headers.get("www-authenticate") == "Bearer"
