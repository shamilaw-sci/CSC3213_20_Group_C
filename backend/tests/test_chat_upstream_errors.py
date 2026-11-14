"""POST /api/chat when the LLM provider fails.

A Gemini 503 used to escape complete() unhandled and crash the request with a
500 and a traceback. Every upstream failure must instead come back as a clean
503 carrying the message the chat widget shows.

Harness imported from test_rbac_matrix rather than reimplemented, for the
reason given at the top of test_restricted_funds.
"""

import logging
import os
import sys
from unittest.mock import patch

import httpx
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api.chat import UNAVAILABLE_MESSAGE
from tests.test_rbac_matrix import _request, acting_as

# Any role with at least one chat tool; with none, /chat 403s before the LLM.
ROLE = "Admin"


def _status_error(code):
    request = httpx.Request("POST", "https://llm.test/chat/completions")
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError(f"{code}", request=request, response=response)


def _raises(exc):
    async def _complete(*_a, **_k):
        raise exc
    return _complete


def _returns(data):
    async def _complete(*_a, **_k):
        return data
    return _complete


UPSTREAM_FAILURES = [
    pytest.param(_status_error(503), id="503"),
    pytest.param(_status_error(429), id="429"),
    pytest.param(_status_error(500), id="500"),
    pytest.param(httpx.ReadTimeout(""), id="read-timeout"),
    pytest.param(httpx.ConnectError("refused"), id="connect-error"),
]


@pytest.mark.parametrize("exc", UPSTREAM_FAILURES)
def test_upstream_failure_returns_clean_503(exc):
    with acting_as(ROLE), patch("app.api.chat.complete", _raises(exc)):
        r = _request("POST", "/api/chat", json={"message": "what's urgent?"})

    assert r.status_code == 503
    assert r.json() == {"detail": UNAVAILABLE_MESSAGE}


@pytest.mark.parametrize("data", [
    pytest.param({}, id="no-choices"),
    pytest.param({"choices": []}, id="empty-choices"),
    pytest.param({"choices": [None]}, id="null-choice"),
])
def test_malformed_response_returns_clean_503(data):
    with acting_as(ROLE), patch("app.api.chat.complete", _returns(data)):
        r = _request("POST", "/api/chat", json={"message": "what's urgent?"})

    assert r.status_code == 503
    assert r.json() == {"detail": UNAVAILABLE_MESSAGE}


def test_status_error_log_names_code_and_type_without_traceback(caplog):
    with caplog.at_level(logging.WARNING, logger="app.api.chat"), \
            acting_as(ROLE), patch("app.api.chat.complete", _raises(_status_error(503))):
        _request("POST", "/api/chat", json={"message": "hi"})

    [record] = [r for r in caplog.records if r.name == "app.api.chat"]
    assert "503" in record.getMessage()
    assert "HTTPStatusError" in record.getMessage()
    assert record.exc_info is None


def test_timeout_log_is_not_empty(caplog):
    # str(httpx.ReadTimeout("")) is "", which is how this class of failure
    # previously logged with no indication of what went wrong.
    with caplog.at_level(logging.WARNING, logger="app.api.chat"), \
            acting_as(ROLE), patch("app.api.chat.complete", _raises(httpx.ReadTimeout(""))):
        _request("POST", "/api/chat", json={"message": "hi"})

    [record] = [r for r in caplog.records if r.name == "app.api.chat"]
    assert "ReadTimeout" in record.getMessage()
    assert record.exc_info is None


def test_successful_reply_is_unchanged():
    data = {"choices": [{"message": {"role": "assistant", "content": "All clear."}}]}
    with acting_as(ROLE), patch("app.api.chat.complete", _returns(data)):
        r = _request("POST", "/api/chat", json={"message": "hi"})

    assert r.status_code == 200
    assert r.json()["reply"] == "All clear."


# --------------------------------------------------------------------------
# Retry opt-in. These patch llm._post (the HTTP call) rather than complete(),
# so the real retry logic in complete() runs between /chat and the provider.
# --------------------------------------------------------------------------

def _scripted_post(monkeypatch, *outcomes):
    from app.services import llm
    calls, queue = [], list(outcomes)

    async def fake_post(payload, timeout):
        calls.append(timeout)
        outcome = queue.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def no_sleep(_s):
        pass

    monkeypatch.setattr(llm, "_post", fake_post)
    monkeypatch.setattr(llm, "_sleep", no_sleep)
    return calls


REPLY = {"choices": [{"message": {"role": "assistant", "content": "All clear."}}]}


def test_transient_503_is_retried_and_the_reply_returned(monkeypatch):
    calls = _scripted_post(monkeypatch, _status_error(503), REPLY)
    with acting_as(ROLE):
        r = _request("POST", "/api/chat", json={"message": "hi"})

    assert r.status_code == 200
    assert r.json()["reply"] == "All clear."
    assert len(calls) == 2


def test_persistent_503_still_ends_in_the_clean_message(monkeypatch):
    calls = _scripted_post(monkeypatch, _status_error(503), _status_error(503))
    with acting_as(ROLE):
        r = _request("POST", "/api/chat", json={"message": "hi"})

    assert r.status_code == 503
    assert r.json() == {"detail": UNAVAILABLE_MESSAGE}
    assert len(calls) == 2


def test_read_timeout_is_not_retried(monkeypatch):
    calls = _scripted_post(monkeypatch, httpx.ReadTimeout(""))
    with acting_as(ROLE):
        r = _request("POST", "/api/chat", json={"message": "hi"})

    assert r.status_code == 503
    assert len(calls) == 1


def test_chat_uses_its_own_shorter_timeout(monkeypatch):
    from app.api.chat import CHAT_TIMEOUT
    calls = _scripted_post(monkeypatch, REPLY)
    with acting_as(ROLE):
        _request("POST", "/api/chat", json={"message": "hi"})

    assert calls == [CHAT_TIMEOUT]
    assert CHAT_TIMEOUT.read == 30.0


# Overall budget. Next.js cuts a proxied request off at 30 s with a bare 500,
# so the whole chat request has to give up, cleanly, before that.

def test_a_hung_provider_ends_in_the_clean_message_within_the_budget(monkeypatch):
    import asyncio
    import app.api.chat as chat

    monkeypatch.setattr(chat, "CHAT_BUDGET_S", 0.3)
    monkeypatch.setattr(chat, "MIN_CALL_S", 0.0)

    async def _hangs(*_a, **_k):
        await asyncio.sleep(5)

    with acting_as(ROLE), patch("app.api.chat.complete", _hangs):
        r = _request("POST", "/api/chat", json={"message": "hi"})

    assert r.status_code == 503
    assert r.json()["detail"] == UNAVAILABLE_MESSAGE


def test_chat_passes_its_deadline_so_a_doomed_retry_is_skipped():
    import time
    from app.api.chat import CHAT_BUDGET_S

    seen = {}

    async def _complete(*_a, **k):
        seen.update(k)
        return REPLY

    started = time.monotonic()
    with acting_as(ROLE), patch("app.api.chat.complete", _complete):
        _request("POST", "/api/chat", json={"message": "hi"})

    assert seen["retry"] is True
    assert started < seen["deadline"] <= started + CHAT_BUDGET_S + 1
    assert CHAT_BUDGET_S < 30
