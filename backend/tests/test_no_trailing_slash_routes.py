"""No API route may need a trailing slash.

Next's /api proxy (rewrites() in frontend/next.config.ts) strips a trailing
slash before forwarding. A route declared as "/" under a router prefix then
only exists at the slashed URL, so FastAPI answers the proxied request with a
307 to http://localhost:8000/api/...; that is cross-origin to the page, the
browser drops the Authorization header on the redirected request, and the
route fails as "Not authenticated". Declare such routes as "" instead.
"""

from fastapi.routing import APIRoute

from app.main import app
from tests.test_rbac_matrix import _volunteer_row, acting_as, client


def test_volunteer_list_answers_without_trailing_slash():
    # follow_redirects=False is the whole test: TestClient follows the 307 by
    # default, which hides the bug — it keeps the header, the browser doesn't.
    with acting_as("Admin", tables={"volunteers": {"select": [_volunteer_row(status="pending")]}}):
        response = client.get("/api/volunteers?status=pending", follow_redirects=False)

    assert response.status_code == 200, (
        f"got {response.status_code} {response.headers.get('location', '')}"
    )
    assert [v["status"] for v in response.json()] == ["pending"]


def test_no_api_route_is_declared_with_a_trailing_slash():
    slashed = sorted(
        f"{sorted(r.methods)} {r.path}"
        for r in app.routes
        if isinstance(r, APIRoute) and r.path.startswith("/api/") and r.path.endswith("/")
    )
    assert slashed == [], f"declare these as \"\" not \"/\": {slashed}"
