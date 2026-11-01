"""
Logging in must never change the client the public routes use.

supabase-py (2.28+) switches a client's Authorization header to the user's
JWT on sign-in. get_supabase used to hand login/register the shared client, so after
anyone logged in, public routes (volunteer applications, rescue reports) ran
as that user and broke once the JWT expired. These tests need no network:
they fire the same auth event supabase-py fires on a real sign-in.
"""
from types import SimpleNamespace

from starlette.requests import Request

from app.core import supabase as sb


def _request(headers=None):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "headers": raw})


def test_no_token_request_gets_its_own_client():
    client = sb.get_supabase(_request())
    assert client is not sb.get_public_supabase()


def test_sign_in_on_login_client_leaves_public_client_untouched():
    public = sb.get_public_supabase()
    before = public.options.headers.get("Authorization")

    login_client = sb.get_supabase(_request())
    login_client._listen_to_auth_events(
        "SIGNED_IN", SimpleNamespace(access_token="user-jwt")
    )

    # Only the public client is asserted on: whether the login client's own
    # header changes depends on the supabase-py version (2.28 does, 2.3 does
    # not), but in neither may the shared client change.
    assert public.options.headers.get("Authorization") == before
