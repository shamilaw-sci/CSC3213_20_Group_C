# backend/tests/unit/test_list_urgent_cases.py
#
# The chatbot's list_urgent_cases tool. The failure these guard against: a
# case whose classification failed is stored as "Medium", ranked with genuine
# Mediums, falls outside the top 10, and the model then answers "no" to "are
# there any cases that couldn't be assessed?" from a list it doesn't know was
# cut short.
#
# The shared double in test_rbac_matrix ignores filters, which would let a
# query that forgot `.like(...)` or `.neq(...)` pass. This one applies them.

import pytest

from app.services.chat_tools import URGENT_CASES_LIMIT, list_urgent_cases


class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _FilteringQuery:
    def __init__(self, rows, max_rows):
        self._rows = rows
        self._max_rows = max_rows
        self._count = None

    def select(self, *_cols, count=None):
        self._count = count
        return self

    def neq(self, col, val):
        self._rows = [r for r in self._rows if r.get(col) != val]
        return self

    def like(self, col, pattern):
        # Only the trailing-% prefix form the tool uses.
        assert pattern.endswith("%") and "%" not in pattern[:-1]
        prefix = pattern[:-1]
        self._rows = [r for r in self._rows if (r.get(col) or "").startswith(prefix)]
        return self

    def order(self, col, desc=False):
        self._rows = sorted(self._rows, key=lambda r: r[col], reverse=desc)
        return self

    def execute(self):
        # Mimics PostgREST: data is capped at max-rows, count is not.
        count = len(self._rows) if self._count == "exact" else None
        return _Result([dict(r) for r in self._rows[: self._max_rows]], count)


class _FakeSupabase:
    def __init__(self, rows, max_rows=1000):
        self._rows = rows
        self._max_rows = max_rows

    def table(self, name):
        assert name == "rescue_cases"
        return _FilteringQuery(self._rows, self._max_rows)


def _case(n, urgency, source="ai", status="Reported"):
    return {
        "id": f"case-{n:02d}",
        "animal_type": "Dog",
        "urgency": urgency,
        "urgency_reason": None if source is None else f"reason {n}",
        "urgency_source": source,
        "status": status,
        "description": f"case {n}",
        "reported_at": f"2026-10-{n:02d}T00:00:00+00:00",
    }


def _busy_board():
    """12 classified unresolved cases — already more than the limit — plus one
    severe report whose classification failed, sitting among the Mediums."""
    rows = (
        [_case(i, "Critical") for i in range(1, 4)]
        + [_case(i, "High") for i in range(4, 8)]
        + [_case(i, "Medium") for i in range(8, 13)]
    )
    rows.append(_case(13, "Medium", source="default_classifier_error"))
    return rows


def test_default_case_is_returned_even_when_ranking_would_cut_it():
    rows = _busy_board()
    assert len([r for r in rows if r["status"] != "Resolved"]) > URGENT_CASES_LIMIT

    out = list_urgent_cases(_FakeSupabase(rows))

    review_ids = [c["id"] for c in out["needs_manual_review"]]
    assert review_ids == ["case-13"]
    assert out["needs_manual_review"][0]["needs_manual_review"] is True
    assert out["needs_manual_review_count"] == 1


def test_default_case_is_not_also_ranked_as_medium():
    out = list_urgent_cases(_FakeSupabase(_busy_board()))
    assert "case-13" not in [c["id"] for c in out["ranked_cases"]]


def test_output_states_totals_and_truncation():
    out = list_urgent_cases(_FakeSupabase(_busy_board()))

    assert out["total_unresolved"] == 13
    assert out["ranked_cases_total"] == 12
    assert out["ranked_cases_shown"] == URGENT_CASES_LIMIT
    assert out["truncated"] is True
    assert [c["urgency"] for c in out["ranked_cases"][:3]] == ["Critical"] * 3


@pytest.mark.parametrize("source", [
    "default_no_description", "default_classifier_error", "default_invalid_label",
])
def test_every_default_source_needs_review(source):
    rows = _busy_board()
    rows[-1]["urgency_source"] = source
    out = list_urgent_cases(_FakeSupabase(rows))
    assert [c["id"] for c in out["needs_manual_review"]] == ["case-13"]


def test_resolved_default_cases_are_excluded():
    rows = _busy_board() + [_case(14, "Medium", source="default_classifier_error", status="Resolved")]
    out = list_urgent_cases(_FakeSupabase(rows))
    assert "case-14" not in [c["id"] for c in out["needs_manual_review"]]
    assert out["total_unresolved"] == 13


def test_legacy_null_source_is_ranked_not_flagged():
    rows = [_case(1, "High", source=None), _case(2, "Low")]
    out = list_urgent_cases(_FakeSupabase(rows))

    assert out["needs_manual_review"] == []
    assert [c["id"] for c in out["ranked_cases"]] == ["case-01", "case-02"]
    assert out["truncated"] is False
    assert out["total_unresolved"] == 2


def test_total_comes_from_exact_count_not_the_capped_page():
    # A server row cap must not make a partial page look like the whole set.
    out = list_urgent_cases(_FakeSupabase(_busy_board(), max_rows=5))

    assert out["total_unresolved"] == 13
    assert out["truncated"] is True
    assert [c["id"] for c in out["needs_manual_review"]] == ["case-13"]
