import pytest

from app.services import board_events


@pytest.fixture(autouse=True)
def _no_live_board_broadcast(monkeypatch):
    """Keep every suite off the live Realtime API.

    The case routes ping the board after each mutation, and SUPABASE_URL /
    SUPABASE_KEY come from the real backend/.env — without this, any test that
    drives create_case or update_case_status to a 200 (the RBAC matrix does,
    dozens of times) would broadcast to the live project. Records the bodies
    instead, so tests that care can assert on them via `board_pings`.
    """
    sent = []

    async def _record(body):
        sent.append(body)

    monkeypatch.setattr(board_events, "_post", _record)
    return sent


@pytest.fixture
def board_pings(_no_live_board_broadcast):
    return _no_live_board_broadcast
