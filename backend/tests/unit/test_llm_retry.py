# backend/tests/unit/test_llm_retry.py
#
# complete()'s single-retry rules and the classifier's hard budget. No network:
# _post is replaced with a scripted sequence of responses and failures, and
# backoff sleeps are recorded instead of waited.

import asyncio
import json
import time

import httpx
import pytest

from app.services import case_classifier, llm

MSGS = [{"role": "user", "content": "x"}]
OK = {"choices": [{"message": {"content": json.dumps({"urgency": "High", "reason": "r"})}}]}


def status_error(code, headers=None, body=None):
    request = httpx.Request("POST", "https://llm.test/chat/completions")
    response = httpx.Response(code, request=request, headers=headers, json=body)
    return httpx.HTTPStatusError(str(code), request=request, response=response)


def gemini_429(retry_delay):
    # Shape of Gemini's OpenAI-compatible quota error, as returned live.
    return status_error(429, body=[{"error": {"code": 429, "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": []},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry_delay},
    ]}}])


@pytest.fixture
def scripted(monkeypatch):
    """Script _post's outcomes; returns (calls, sleeps) for assertions."""
    calls, sleeps = [], []

    def install(*outcomes):
        queue = list(outcomes)

        async def fake_post(payload, timeout):
            calls.append(payload)
            outcome = queue.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr(llm, "_post", fake_post)
        monkeypatch.setattr(llm, "_sleep", fake_sleep)
        return calls, sleeps

    return install


def run(coro):
    return asyncio.run(coro)


# ---------- retried once ----------

@pytest.mark.parametrize("first, backoff", [
    (status_error(503), 1.0),
    (httpx.ConnectError("refused"), 0.5),
    (httpx.ConnectTimeout("slow connect"), 0.5),
])
def test_transient_failure_is_retried_once(scripted, first, backoff):
    calls, sleeps = scripted(first, OK)
    assert run(llm.complete(MSGS, retry=True)) == OK
    assert len(calls) == 2
    assert sleeps == [backoff]


def test_second_failure_is_not_retried_again(scripted):
    calls, _ = scripted(status_error(503), status_error(503))
    with pytest.raises(httpx.HTTPStatusError):
        run(llm.complete(MSGS, retry=True))
    assert len(calls) == 2


# ---------- never retried ----------

@pytest.mark.parametrize("failure", [
    pytest.param(httpx.ReadTimeout(""), id="read-timeout"),
    pytest.param(status_error(500), id="500"),
    pytest.param(status_error(400), id="400"),
    pytest.param(status_error(429), id="429-no-retry-info"),
])
def test_non_retryable_failure_raises_after_one_attempt(scripted, failure):
    calls, sleeps = scripted(failure)
    with pytest.raises(type(failure)):
        run(llm.complete(MSGS, retry=True))
    assert len(calls) == 1
    assert sleeps == []


def test_retry_is_off_by_default(scripted):
    # The chatbot path calls complete() without retry=True until it opts in.
    calls, _ = scripted(status_error(503))
    with pytest.raises(httpx.HTTPStatusError):
        run(llm.complete(MSGS))
    assert len(calls) == 1


# ---------- 429: only when the requested wait fits ----------

def test_429_retried_when_requested_wait_fits_deadline(scripted):
    calls, sleeps = scripted(gemini_429("1s"), OK)
    run(llm.complete(MSGS, retry=True, deadline=time.monotonic() + 10))
    assert len(calls) == 2
    assert sleeps == [1.0]


def test_429_retry_after_header_is_honoured(scripted):
    calls, sleeps = scripted(status_error(429, headers={"Retry-After": "2"}), OK)
    run(llm.complete(MSGS, retry=True, deadline=time.monotonic() + 10))
    assert sleeps == [2.0]


def test_429_daily_quota_wait_is_not_retried_within_deadline(scripted):
    # The live free-tier response: retryDelay 53316s (~15 h).
    calls, sleeps = scripted(gemini_429("53316s"))
    with pytest.raises(httpx.HTTPStatusError):
        run(llm.complete(MSGS, retry=True, deadline=time.monotonic() + 6))
    assert len(calls) == 1 and sleeps == []


def test_429_daily_quota_wait_is_not_retried_without_deadline(scripted):
    calls, sleeps = scripted(gemini_429("53316s"))
    with pytest.raises(httpx.HTTPStatusError):
        run(llm.complete(MSGS, retry=True))
    assert len(calls) == 1 and sleeps == []


# ---------- deadline ----------

def test_retry_skipped_when_too_little_deadline_remains(scripted):
    # 503 backoff 1.0 s + MIN_ATTEMPT_S 2.0 s > 2.5 s left: a retry would be cut
    # off by the caller's cap, and would still spend a request of quota.
    calls, sleeps = scripted(status_error(503))
    with pytest.raises(httpx.HTTPStatusError):
        run(llm.complete(MSGS, retry=True, deadline=time.monotonic() + 2.5))
    assert len(calls) == 1 and sleeps == []


# ---------- payload ----------

def test_reasoning_effort_sent_only_when_given(scripted):
    calls, _ = scripted(OK, OK)
    run(llm.complete(MSGS))
    run(llm.complete(MSGS, reasoning_effort="none"))
    assert "reasoning_effort" not in calls[0]
    assert calls[1]["reasoning_effort"] == "none"


# ---------- classifier ----------

def test_classifier_uses_budget_retry_and_low_reasoning(monkeypatch):
    seen = {}

    async def fake_complete(messages, **kwargs):
        seen.update(kwargs)
        return OK

    monkeypatch.setattr(case_classifier, "complete", fake_complete)
    before = time.monotonic()
    result = run(case_classifier.classify_case_urgency("Dog", "hit by car"))

    assert result["source"] == "ai"
    assert seen["retry"] is True
    assert seen["reasoning_effort"] == "low"
    assert seen["timeout"] is case_classifier.CLASSIFY_TIMEOUT
    assert before < seen["deadline"] <= time.monotonic() + case_classifier.CLASSIFY_BUDGET_S


def test_classifier_budget_is_a_hard_cap(monkeypatch):
    # A provider that never answers must not hold the public report past the
    # budget — the default lands instead.
    monkeypatch.setattr(case_classifier, "CLASSIFY_BUDGET_S", 0.2)

    async def hangs(*_a, **_k):
        await asyncio.sleep(30)

    monkeypatch.setattr(case_classifier, "complete", hangs)
    t0 = time.monotonic()
    result = run(case_classifier.classify_case_urgency("Dog", "hit by car"))

    assert time.monotonic() - t0 < 1.0
    assert result == {
        "urgency": "Medium",
        "reason": "Automatic classification unavailable.",
        "source": "default_classifier_error",
    }


def test_budget_leaves_headroom_under_assumed_function_limit():
    # Guard on the ASSUMED 10 s Vercel limit: classification must leave room
    # for cold start, the insert and the audit write. Revisit both together.
    assert case_classifier.CLASSIFY_BUDGET_S <= 6.0
    assert case_classifier.CLASSIFY_TIMEOUT.read <= case_classifier.CLASSIFY_BUDGET_S


def test_default_model_is_not_the_withdrawn_one(monkeypatch):
    # The default only applies when LLM_MODEL is unset. Reloading config would
    # re-run load_dotenv and quietly restore it from .env, making this pass
    # whatever the default is — so .env loading is disabled for the reload.
    import importlib
    import dotenv
    from app.core import config

    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    try:
        assert importlib.reload(config).LLM_MODEL == "gemini-3.5-flash-lite"
    finally:
        monkeypatch.undo()
        importlib.reload(config)
