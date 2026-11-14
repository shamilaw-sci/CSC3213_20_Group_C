# backend/tests/unit/test_board_events.py
#
# The board ping: what it sends, that it fails soft, and which requests send
# it. No network — conftest.py replaces board_events._post for every test, and
# the one test of the real _post runs it over an httpx.MockTransport.

import asyncio
import logging

import httpx
import pytest

from app.api import rescue_cases
from app.services import board_events
from tests.test_rbac_matrix import CASE_ID, OTHER_USER_ID, USER_ID, _case_row, acting_as, client

# Captured at import, before the autouse fixture swaps it out.
REAL_POST = board_events._post

CREATE_PAYLOAD = {"animal_type": "Dog", "description": "Limping", "lat": 6.9, "lng": 79.8}

FAILURES = [
    httpx.ReadTimeout(""),
    httpx.ConnectError("refused"),
    httpx.HTTPStatusError(
        "503",
        request=httpx.Request("POST", "https://x.test"),
        response=httpx.Response(503, request=httpx.Request("POST", "https://x.test")),
    ),
    RuntimeError("anything else"),
]


@pytest.fixture
def no_classifier(monkeypatch):
    async def _fixed(animal_type, description):
        return {"urgency": "Medium", "reason": None, "source": "ai"}
    monkeypatch.setattr(rescue_cases, "classify_case_urgency", _fixed)


@pytest.fixture
def failing_post(monkeypatch):
    def install(exc):
        async def _raise(body):
            raise exc
        monkeypatch.setattr(board_events, "_post", _raise)
    return install


# --------------------------------------------------------------------------
# The message itself
# --------------------------------------------------------------------------

def test_ping_is_private_and_carries_no_data(board_pings):
    asyncio.run(board_events.notify_board_changed())

    assert board_pings == [{"messages": [{
        "topic": "rescue-board",
        "event": "cases_changed",
        "payload": {},
        "private": True,
    }]}]


def test_real_post_uses_rest_broadcast_with_service_key(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(202)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        board_events.httpx, "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    asyncio.run(REAL_POST({"messages": []}))

    (request,) = seen
    assert request.method == "POST"
    assert str(request.url) == f"{board_events.SUPABASE_URL}/realtime/v1/api/broadcast"
    assert request.headers["apikey"] == board_events.SERVICE_KEY
    assert request.headers["authorization"] == f"Bearer {board_events.SERVICE_KEY}"


def test_real_post_raises_on_error_status_so_it_is_logged(monkeypatch):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        board_events.httpx, "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(lambda r: httpx.Response(401)), **kw),
    )
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(REAL_POST({"messages": []}))


# --------------------------------------------------------------------------
# Fail soft
# --------------------------------------------------------------------------

@pytest.mark.parametrize("exc", FAILURES, ids=lambda e: type(e).__name__)
def test_notify_never_raises_and_logs_the_type(exc, failing_post, caplog):
    failing_post(exc)
    with caplog.at_level(logging.WARNING, logger="app.services.board_events"):
        asyncio.run(board_events.notify_board_changed())

    (record,) = caplog.records
    assert record.levelno == logging.WARNING
    assert type(exc).__name__ in record.getMessage()


@pytest.mark.parametrize("exc", FAILURES, ids=lambda e: type(e).__name__)
def test_public_report_succeeds_when_broadcast_fails(exc, failing_post, no_classifier):
    failing_post(exc)
    with acting_as("Admin", tables={"rescue_cases": {"insert": [_case_row()]}}):
        response = client.post("/api/rescue_cases/cases", json=CREATE_PAYLOAD)
    assert response.status_code == 200, response.text
    assert response.json()["id"] == CASE_ID


@pytest.mark.parametrize("exc", FAILURES, ids=lambda e: type(e).__name__)
def test_status_update_succeeds_when_broadcast_fails(exc, failing_post):
    failing_post(exc)
    tables = {"rescue_cases": {
        "select": [{"status": "In Treatment", "assigned_to": USER_ID}],
        "update": [_case_row(status="Resolved", assigned_to=USER_ID)],
    }}
    with acting_as("Admin", tables=tables):
        response = client.patch(f"/api/rescue_cases/cases/{CASE_ID}/status", json={"new_status": "Resolved", "outcome": "Released"})
    assert response.status_code == 200, response.text


# --------------------------------------------------------------------------
# Which requests ping
# --------------------------------------------------------------------------

def test_case_create_pings(board_pings, no_classifier):
    with acting_as("Admin", tables={"rescue_cases": {"insert": [_case_row()]}}):
        assert client.post("/api/rescue_cases/cases", json=CREATE_PAYLOAD).status_code == 200
    assert len(board_pings) == 1


def test_failed_case_create_does_not_ping(board_pings, no_classifier):
    with acting_as("Admin", tables={"rescue_cases": {"insert": []}}):
        assert client.post("/api/rescue_cases/cases", json=CREATE_PAYLOAD).status_code == 500
    assert board_pings == []


@pytest.mark.parametrize("before, after, payload", [
    (("In Treatment", USER_ID), ("Resolved", USER_ID), {"new_status": "Resolved", "outcome": "Released"}),
    (("Reported", None), ("In Treatment", USER_ID), {"new_status": "In Treatment", "assigned_to": USER_ID}),
    (("In Treatment", USER_ID), ("In Treatment", OTHER_USER_ID),
     {"new_status": "In Treatment", "assigned_to": OTHER_USER_ID}),
], ids=["status-only", "claim", "reassign-only"])
def test_status_or_assignment_change_pings_once(board_pings, before, after, payload):
    tables = {"rescue_cases": {
        "select": [{"status": before[0], "assigned_to": before[1]}],
        "update": [_case_row(status=after[0], assigned_to=after[1])],
    }}
    with acting_as("Admin", tables=tables):
        response = client.patch(f"/api/rescue_cases/cases/{CASE_ID}/status", json=payload)
    assert response.status_code == 200, response.text
    assert len(board_pings) == 1


def test_noop_status_update_does_not_ping(board_pings):
    tables = {"rescue_cases": {
        "select": [{"status": "Reported", "assigned_to": None}],
        "update": [_case_row(status="Reported", assigned_to=None)],
    }}
    with acting_as("Admin", tables=tables):
        response = client.patch(f"/api/rescue_cases/cases/{CASE_ID}/status", json={"new_status": "Reported"})
    assert response.status_code == 200
    assert board_pings == []


@pytest.mark.parametrize("role, select, payload, status", [
    ("Finance Officer", [{"status": "Reported", "assigned_to": None}], {"new_status": "Reported"}, 403),
    ("Director", [{"status": "In Treatment", "assigned_to": USER_ID}], {"new_status": "Resolved"}, 403),
    ("Admin", [], {"new_status": "Resolved"}, 404),
    ("Admin", [{"status": "Reported", "assigned_to": None}], {"new_status": "In Treatment"}, 400),
], ids=["no-rescue-read", "no-rescue-manage", "missing", "no-assignee"])
def test_rejected_status_update_does_not_ping(board_pings, role, select, payload, status):
    tables = {"rescue_cases": {"select": select, "update": [_case_row(status="Resolved")]}}
    with acting_as(role, tables=tables):
        response = client.patch(f"/api/rescue_cases/cases/{CASE_ID}/status", json=payload)
    assert response.status_code == status
    assert board_pings == []
