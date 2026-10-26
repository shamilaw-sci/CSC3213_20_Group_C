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
