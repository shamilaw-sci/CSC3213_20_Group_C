"""Malformed ids and unknown roles are client errors, not server errors.

A path id that is not a uuid used to reach PostgREST, which rejects it with
400, and came back as a 500 (or as the raw database error). An unknown role id
came back as a 400 carrying the foreign-key violation verbatim.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.test_rbac_matrix import _request, acting_as

BAD = "not-a-uuid"
USER = "11111111-1111-1111-1111-111111111111"


@pytest.mark.parametrize("method,path,body", [
    ("PATCH", f"/api/rescue_cases/cases/{BAD}/status", {"new_status": "In Treatment"}),
    ("POST", f"/api/rescue_cases/cases/{BAD}/notes", {"body": "x"}),
    ("POST", f"/api/rescue_cases/cases/{BAD}/outcome", {"outcome": "Released"}),
    ("GET", f"/api/rescue_cases/cases/{BAD}/timeline", None),
    ("PATCH", f"/api/rescue_cases/outbreak-zones/{BAD}/resolve", None),
    ("PATCH", f"/api/volunteers/{BAD}/review", {"status": "approved"}),
    ("POST", f"/api/volunteers/{BAD}/link-shared", None),
    ("POST", f"/api/volunteers/{BAD}/reset-link", None),
    ("PATCH", f"/api/volunteers/shifts/{BAD}", {"title": "x"}),
    ("DELETE", f"/api/volunteers/assignments/{BAD}", None),
    ("PUT", f"/api/auth/users/{BAD}/role", {"role_id": 6}),
    ("DELETE", f"/api/auth/users/{BAD}", None),
])
def test_a_malformed_id_is_a_422(method, path, body):
    with acting_as("Admin"):
        response = _request(method, path, json=body)
    assert response.status_code == 422, response.text


def test_an_unknown_role_is_a_plain_422():
    tables = {
        "users": {"select": [{"id": USER, "email": "a@vff.test", "role_id": 6}]},
        "roles": {"select": []},
    }
    with acting_as("Admin", tables=tables):
        response = _request("PUT", f"/api/auth/users/{USER}/role", json={"role_id": 99})
    assert response.status_code == 422
    assert response.json()["detail"] == "Unknown role"
