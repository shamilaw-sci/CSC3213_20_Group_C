import os
from supabase import create_client, Client
from dotenv import load_dotenv
from fastapi import Request

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise ValueError("SUPABASE_URL or SUPABASE_KEY not found in environment variables")

# Shared client used as fallback (no token) and for internal auth lookups.
_supabase: Client = create_client(url, key)


def get_supabase(request: Request) -> Client:
    """Return a Supabase client scoped to the caller's JWT.

    Reads the Authorization header directly from the Request object —
    no separate Security() dependency — so there is no conflict with the
    HTTPBearer instance already declared in security.py.

    If a Bearer token is present, we apply it to the PostgREST layer via
    client.postgrest.auth(token).  Supabase RLS then sees the authenticated
    user instead of 'anon', fixing the 401 on INSERT/UPDATE/DELETE.

    If there is no token (health-check routes, login, register) we return a
    FRESH client, never the shared one. Login and register call
    auth.sign_in_with_password / auth.sign_up on whatever client they get, and
    supabase-py (2.28+; 2.3 does not) then switches that client's Authorization header to the
    signed-in user's JWT. On the shared client that silently turned every
    public route (volunteer applications, rescue reports) into requests made
    as the last person who logged in, and once that JWT expired an hour later
    they all failed — the volunteer form returned "Could not submit your
    application" and nothing reached the Pending list.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):]
        client = create_client(url, key)
        client.postgrest.auth(token)
        return client

    return create_client(url, key)

def get_public_supabase() -> Client:
    """Client for routes that must work regardless of caller auth state.

    Always uses the shared anon-key client, ignoring any Authorization
    header entirely — so a stale/expired token sitting in the caller's
    browser can never break a route that was never supposed to require
    login in the first place.
    """
    return _supabase