"""Restricted (earmarked) fund accounting: balance maths, spend enforcement,
override authorization, and the audit row an override is required to produce.

The Supabase double and role harness are imported from test_rbac_matrix rather
than reimplemented. A second copy of that stub would drift, which is the exact
failure the note at the top of that module describes.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.audit import GENESIS, compute_hash
from app.core.permissions import ROLE_PERMISSIONS, has_permission
from app.core.security import get_current_user
from app.core.supabase import get_public_supabase, get_supabase
from app.main import app
from app.services.restricted_funds import compute_restricted_balance
from tests.test_rbac_matrix import (
    ALL_ROLES,
    USER_ID,
    _FakeResult,
    _request,
    acting_as,
    client,
)

PROGRAM_ID = 7


# --------------------------------------------------------------------------
# Supabase double that records inserts
# --------------------------------------------------------------------------

class _CapturingQuery:
    """Chainable stub that appends every inserted payload to a shared log.

    The shared _FakeQuery captures updates only; an override is proved by what
    it INSERTS into system_audit_logs, so that payload has to be observable.
    """

    def __init__(self, table, rows, inserts, fail_tables):
        self._table = table
        self._rows = rows if isinstance(rows, dict) else {"select": rows}
        self._inserts = inserts
        self._fail_tables = fail_tables
        self._op = "select"
        self._filters = []

    def select(self, *a, **k):
        self._op = "select"
        return self

    def eq(self, column, value):
        self._filters.append(("eq", column, value))
        return self

    def neq(self, column, value):
        self._filters.append(("neq", column, value))
        return self

    def insert(self, data=None, *a, **k):
        self._op = "insert"
        if self._table in self._fail_tables:
            raise RuntimeError(f"simulated write failure on {self._table}")
        self._inserts.append((self._table, data))
        return self

    def update(self, *a, **k):
        self._op = "update"
        return self

    def __getattr__(self, name):
        def _chain(*a, **k):
            return self
        return _chain

    def execute(self):
        rows = self._rows.get(self._op, [])
        if self._op != "select":
            return _FakeResult(rows)

        # Apply eq/neq. Without this, is_program_restricted's
        # .eq("is_restricted", True) probe would match any non-empty fixture
        # and always report the program as restricted, so the test asserting
        # that unrestricted programs are NOT gated would pass against a stub
        # rather than against the code.
        #
        # A filter on a column the fixture row omits is ignored rather than
        # treated as a non-match: fixtures declare only the columns under test.
        for op, column, value in self._filters:
            rows = [
                r for r in rows
                if column not in r
                or (r[column] == value if op == "eq" else r[column] != value)
            ]
        return _FakeResult(rows)


class _CapturingSupabase:
    def __init__(self, tables=None, fail_tables=()):
        self._tables = tables or {}
        self.inserts = []
        self._fail_tables = set(fail_tables)

    def table(self, name):
        return _CapturingQuery(
            name, self._tables.get(name, []), self.inserts, self._fail_tables
        )

    def rpc(self, name, params=None):
        return _CapturingQuery(name, self._tables.get(f"rpc:{name}", []), self.inserts, set())


def _tx(amount, tx_type, status="Cash", is_restricted=False):
    return {
        "amount": amount,
        "transaction_type": tx_type,
        "status": status,
        "is_restricted": is_restricted,
    }


def _created_row(amount, program_id=PROGRAM_ID):
    """A row shaped like the FinancialTransaction response model."""
    return {
        "id": 99,
        "transaction_date": "2026-01-15",
        "amount": amount,
        "transaction_type": "Expense",
        "status": "Cash",
        "program_id": program_id,
        "is_restricted": False,
    }


def _expense_payload(amount, program_id=PROGRAM_ID):
    return {
        "transaction_date": "2026-01-15",
        "amount": amount,
        "transaction_type": "Expense",
        "status": "Cash",
        "program_id": program_id,
    }


# Ledger for PROGRAM_ID: 1000 restricted cash raised, 400 already spent,
# so 600 remains. The extra rows exist to prove they are excluded.
LEDGER = [
    _tx(1000, "Income", "Cash", is_restricted=True),
    # Pledged but not received: must not authorize spending.
    _tx(5000, "Income", "Receivable", is_restricted=True),
    # Unrestricted general donation to the same program: not earmarked money.
    _tx(2500, "Income", "Cash", is_restricted=False),
    # Expense draws down restricted funds even though it is not flagged.
    _tx(400, "Expense", "Cash", is_restricted=False),
]


def _tables(ledger=None, audit_tail=None):
    return {
        "financial_transactions": {
            "select": LEDGER if ledger is None else ledger,
            "insert": [_created_row(100)],
        },
        "programs": {"select": [{"id": PROGRAM_ID}]},
        "system_audit_logs": {"select": audit_tail or [], "insert": [{"id": 1}]},
    }


ROLES_WITH_WRITE = [r for r in ALL_ROLES if has_permission(r, "finance:write")]
ROLES_WITH_OVERRIDE = [r for r in ALL_ROLES if has_permission(r, "finance:restricted:override")]


# --------------------------------------------------------------------------
# Balance maths
# --------------------------------------------------------------------------

def test_balance_counts_only_restricted_cash_income():
    supabase = _CapturingSupabase(_tables())
    balance = compute_restricted_balance(supabase, PROGRAM_ID)

    # 1000 restricted cash. The 5000 receivable and 2500 unrestricted are out.
    assert float(balance["raised"]) == 1000
    assert float(balance["spent"]) == 400
    assert float(balance["remaining"]) == 600


def test_balance_reports_negative_remaining_rather_than_clamping():
    ledger = [_tx(100, "Income", "Cash", is_restricted=True), _tx(450, "Expense")]
    balance = compute_restricted_balance(_CapturingSupabase(_tables(ledger)), PROGRAM_ID)

    # An already-overdrawn program must show as overdrawn, not as zero.
    assert float(balance["remaining"]) == -350


def test_balance_uses_decimal_not_float_accumulation():
    ledger = [_tx("0.10", "Income", "Cash", is_restricted=True) for _ in range(3)]
    balance = compute_restricted_balance(_CapturingSupabase(_tables(ledger)), PROGRAM_ID)

    # 0.1 * 3 in binary float is 0.30000000000000004, which would make an
    # exactly-0.30 expense look like an overspend.
    assert str(balance["raised"]) == "0.30"


# --------------------------------------------------------------------------
# Enforcement on expense creation
# --------------------------------------------------------------------------

@pytest.mark.parametrize("role", ROLES_WITH_WRITE)
def test_expense_within_restricted_balance_succeeds(role):
    with acting_as(role):
        app.dependency_overrides[get_supabase] = lambda: _CapturingSupabase(_tables())
        response = _request("POST", "/api/finance/transactions", json=_expense_payload(600))

    assert response.status_code == 200, response.text


@pytest.mark.parametrize("role", ROLES_WITH_WRITE)
def test_expense_exceeding_restricted_balance_is_blocked_without_override(role):
    with acting_as(role):
        app.dependency_overrides[get_supabase] = lambda: _CapturingSupabase(_tables())
        response = _request("POST", "/api/finance/transactions", json=_expense_payload(1000))

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    # The shortfall is 1000 - 600. A message that only says "insufficient
    # funds" does not tell the officer how much to cut.
    assert "400" in detail
    assert str(PROGRAM_ID) in detail


@pytest.mark.parametrize("role", ROLES_WITH_WRITE)
def test_override_flag_respects_permission(role):
    with acting_as(role):
        app.dependency_overrides[get_supabase] = lambda: _CapturingSupabase(_tables())
        response = _request(
            "POST",
            "/api/finance/transactions?override_restricted=true",
            json=_expense_payload(1000),
        )

    if has_permission(role, "finance:restricted:override"):
        assert response.status_code == 200, response.text
    else:
        assert response.status_code == 403, (
            f"{role} lacks finance:restricted:override but overspent anyway "
            f"({response.status_code})"
        )


def test_only_admin_holds_the_override_permission():
    # Guards the deliberate exclusions: Finance Officer creates the expenses and
    # must not clear its own shortfall; Director has no finance:write and so
    # could never reach this code path.
    assert ROLES_WITH_OVERRIDE == ["Admin"]
    assert not has_permission("Finance Officer", "finance:restricted:override")
    assert not has_permission("Director", "finance:write")


def test_unrestricted_program_is_not_gated():
    # No restricted income at all: is_program_restricted is False, so a large
    # expense must pass. Otherwise every ordinary program becomes unspendable.
    ledger = [_tx(50, "Income", "Cash", is_restricted=False)]
    with acting_as("Finance Officer"):
        app.dependency_overrides[get_supabase] = lambda: _CapturingSupabase(_tables(ledger))
        response = _request("POST", "/api/finance/transactions", json=_expense_payload(9999))

    assert response.status_code == 200, response.text


def test_expense_without_program_is_not_gated():
    payload = _expense_payload(9999)
    payload["program_id"] = None
    with acting_as("Finance Officer"):
        app.dependency_overrides[get_supabase] = lambda: _CapturingSupabase(_tables())
        response = _request("POST", "/api/finance/transactions", json=payload)

    assert response.status_code == 200, response.text


def test_restricted_income_requires_a_program():
    payload = {
        "transaction_date": "2026-01-15",
        "amount": 500,
        "transaction_type": "Income",
        "status": "Cash",
        "program_id": None,
        "is_restricted": True,
    }
    with acting_as("Finance Officer"):
        app.dependency_overrides[get_supabase] = lambda: _CapturingSupabase(_tables())
        response = _request("POST", "/api/finance/transactions", json=payload)

    assert response.status_code == 422, response.text


# --------------------------------------------------------------------------
# The override audit row
# --------------------------------------------------------------------------

def _override_and_capture(audit_tail=None):
    supabase = _CapturingSupabase(_tables(audit_tail=audit_tail))
    with acting_as("Admin"):
        app.dependency_overrides[get_supabase] = lambda: supabase
        response = _request(
            "POST",
            "/api/finance/transactions?override_restricted=true",
            json=_expense_payload(1000),
        )
    audit_rows = [d for t, d in supabase.inserts if t == "system_audit_logs"]
    return response, audit_rows


def test_override_writes_audit_row_with_program_shortfall_and_authorizer():
    response, audit_rows = _override_and_capture()
    assert response.status_code == 200, response.text

    overrides = [r for r in audit_rows if r["action_type"] == "FINANCE_RESTRICTED_OVERRIDE"]
    assert len(overrides) == 1, f"expected one override audit row, got {len(overrides)}"

    payload = overrides[0]["new_payload"]
    assert payload["program_id"] == PROGRAM_ID
    # Decimal strings, not floats — see
    # test_override_audit_row_survives_the_jsonb_number_roundtrip.
    assert payload["shortfall_amount"] == "400.00"
    assert payload["restricted_remaining"] == "600.00"
    assert payload["authorized_by"] == USER_ID
    assert overrides[0]["user_id"] == USER_ID


def test_override_audit_row_is_correctly_hash_chained():
    prior_hash = "a" * 64
    _, audit_rows = _override_and_capture(audit_tail=[{"hash": prior_hash}])

    row = next(r for r in audit_rows if r["action_type"] == "FINANCE_RESTRICTED_OVERRIDE")

    assert row["prev_hash"] == prior_hash
    # Recompute the digest from the stored fields. If the row's own contents
    # and its hash disagree, the chain is decorative.
    assert row["hash"] == compute_hash(
        row["prev_hash"],
        row["user_id"],
        row["action_type"],
        row["table_name"],
        row["old_payload"],
        row["new_payload"],
        row["timestamp"],
    )


def _jsonb_roundtrip(value):
    """Approximate what Postgres JSONB does to a payload on the way back out.

    The relevant behaviour: a whole-number float is returned without its
    fractional part, so 8000.0 comes back as 8000. Anything hashed as a float
    on insert therefore hashes differently on read.
    """
    if isinstance(value, dict):
        return {k: _jsonb_roundtrip(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonb_roundtrip(v) for v in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def test_override_audit_row_survives_the_jsonb_number_roundtrip():
    """Regression: the override row must still verify after a DB round trip.

    This was a live defect. The payload recorded money via float(), so the
    digest was computed over 8000.0 while the database returned 8000, and
    /audit-logs/verify reported the row as tampered forever after. Money is
    now recorded as a decimal string, which JSONB returns byte-identical.

    Asserting on the recomputed hash rather than on the field types is
    deliberate: it pins the property that actually matters, so any future
    payload change that reintroduces an unstable type fails here.
    """
    _, audit_rows = _override_and_capture()
    row = next(r for r in audit_rows if r["action_type"] == "FINANCE_RESTRICTED_OVERRIDE")

    assert row["hash"] == compute_hash(
        row["prev_hash"],
        row["user_id"],
        row["action_type"],
        row["table_name"],
        _jsonb_roundtrip(row["old_payload"]),
        _jsonb_roundtrip(row["new_payload"]),
        row["timestamp"],
    ), "override audit row does not verify after a JSONB number round trip"

    # The values are still readable as numbers by anyone auditing the log.
    assert row["new_payload"]["shortfall_amount"] == "400.00"
    assert row["new_payload"]["restricted_remaining"] == "600.00"


def test_override_audit_row_starts_a_chain_when_no_prior_row_exists():
    _, audit_rows = _override_and_capture(audit_tail=[])
    row = next(r for r in audit_rows if r["action_type"] == "FINANCE_RESTRICTED_OVERRIDE")
    assert row["prev_hash"] == GENESIS


def test_override_is_refused_when_the_audit_row_cannot_be_written():
    # log_audit_action is fail-soft everywhere else. Here the audit row IS the
    # authorization, so a dropped write must abort rather than leave an
    # unrecorded overspend in the ledger.
    supabase = _CapturingSupabase(_tables(), fail_tables={"system_audit_logs"})
    with acting_as("Admin"):
        app.dependency_overrides[get_supabase] = lambda: supabase
        response = _request(
            "POST",
            "/api/finance/transactions?override_restricted=true",
            json=_expense_payload(1000),
        )

    assert response.status_code == 503, response.text
    assert not [t for t, _ in supabase.inserts if t == "financial_transactions"], (
        "expense was written despite the override audit row failing"
    )


# --------------------------------------------------------------------------
# The restricted-balance endpoint
# --------------------------------------------------------------------------

@pytest.mark.parametrize("role", ALL_ROLES)
def test_restricted_balance_endpoint_requires_finance_read(role):
    with acting_as(role):
        app.dependency_overrides[get_supabase] = lambda: _CapturingSupabase(_tables())
        response = _request("GET", f"/api/finance/programs/{PROGRAM_ID}/restricted-balance")

    if has_permission(role, "finance:read"):
        assert response.status_code != 403
    else:
        # Staff hold programs:read but must not see the ledger.
        assert response.status_code == 403


def test_restricted_balance_endpoint_returns_raised_spent_remaining():
    with acting_as("Director"):
        app.dependency_overrides[get_supabase] = lambda: _CapturingSupabase(_tables())
        response = _request("GET", f"/api/finance/programs/{PROGRAM_ID}/restricted-balance")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "program_id": PROGRAM_ID,
        "raised": 1000.0,
        "spent": 400.0,
        "remaining": 600.0,
    }


def test_restricted_balance_endpoint_404s_for_unknown_program():
    tables = _tables()
    tables["programs"] = {"select": []}
    with acting_as("Director"):
        app.dependency_overrides[get_supabase] = lambda: _CapturingSupabase(tables)
        response = _request("GET", "/api/finance/programs/12345/restricted-balance")

    assert response.status_code == 404


def test_restricted_balance_endpoint_rejects_anonymous():
    response = client.request("GET", f"/api/finance/programs/{PROGRAM_ID}/restricted-balance")
    assert response.status_code == 401


# --------------------------------------------------------------------------
# Chatbot tool registration
# --------------------------------------------------------------------------

def test_restricted_fund_tool_is_gated_on_finance_read():
    from app.services.chat_tools import TOOLS

    tool = TOOLS["get_restricted_fund_balance"]
    assert tool["permission"] == "finance:read"
    assert tool["schema"]["function"]["parameters"]["required"] == ["program_id"]


def test_restricted_fund_tool_returns_json_serializable_values():
    import json

    from app.services.chat_tools import TOOLS

    result = TOOLS["get_restricted_fund_balance"]["impl"](
        _CapturingSupabase(_tables()), program_id=PROGRAM_ID
    )
    # Decimal would raise here, and the tool result is serialized into the
    # model's context.
    assert json.dumps(result)
    assert result["remaining"] == 600.0


# --------------------------------------------------------------------------
# Full scenario: donation -> spend -> block -> override -> verify the chain
# --------------------------------------------------------------------------

class _StatefulQuery:
    """Query double backed by a mutable ledger, honouring order() and limit().

    The shared stub ignores both, which is fine for single-shot tests but not
    here: log_audit_action finds the chain head with
    .order("id", desc=True).limit(1), so a double that ignores ordering would
    hand it the OLDEST row and every link would be chained to the wrong hash —
    the chain would appear to verify against a stub that built it wrong.
    """

    def __init__(self, store, table):
        self._store = store
        self._table = table
        self._op = "select"
        self._desc = False
        self._limit = None
        self._pending = None
        self._filters = []

    def select(self, *a, **k):
        self._op = "select"
        return self

    def insert(self, data=None, *a, **k):
        self._op = "insert"
        self._pending = data
        return self

    def order(self, column, desc=False, **k):
        self._desc = desc
        return self

    def limit(self, n):
        self._limit = n
        return self

    def eq(self, column, value):
        self._filters.append(("eq", column, value))
        return self

    def neq(self, column, value):
        self._filters.append(("neq", column, value))
        return self

    def __getattr__(self, name):
        def _chain(*a, **k):
            return self
        return _chain

    def execute(self):
        rows = self._store.setdefault(self._table, [])
        if self._op == "insert":
            row = dict(self._pending)
            row.setdefault("id", len(rows) + 1)
            rows.append(row)
            return _FakeResult([row])
        for op, column, value in self._filters:
            rows = [
                r for r in rows
                if column not in r
                or (r[column] == value if op == "eq" else r[column] != value)
            ]
        ordered = sorted(rows, key=lambda r: r.get("id", 0), reverse=self._desc)
        if self._limit is not None:
            ordered = ordered[: self._limit]
        return _FakeResult(ordered)


class _StatefulSupabase:
    def __init__(self, store):
        self._store = store

    def table(self, name):
        return _StatefulQuery(self._store, name)

    def rpc(self, name, params=None):
        return _StatefulQuery(self._store, f"rpc:{name}")


def test_end_to_end_restricted_lifecycle_leaves_a_verifiable_chain():
    """Donation, in-budget spend, refused overspend, authorized override.

    Then the accumulated audit log is walked by the real verification endpoint
    rather than by a recomputation written for this test — proving the override
    row is chained the way the auditor's own tool expects.
    """
    # Starts empty: every row below is written by the endpoints under test, so
    # the balance each step sees is the product of the preceding steps rather
    # than of a fixture.
    store = {
        "system_audit_logs": [],
        "financial_transactions": [],
        "programs": [{"id": PROGRAM_ID}],
    }
    supabase = _StatefulSupabase(store)

    def as_admin(method, path, json=None):
        with acting_as("Admin"):
            app.dependency_overrides[get_supabase] = lambda: supabase
            return _request(method, path, json=json)

    # 1. A restricted donation is recorded.
    donation = as_admin("POST", "/api/finance/transactions", json={
        "transaction_date": "2026-01-01",
        "amount": 1000,
        "transaction_type": "Income",
        "status": "Cash",
        "program_id": PROGRAM_ID,
        "is_restricted": True,
    })
    assert donation.status_code == 200, donation.text

    # 2. An expense inside the 1000 raised is accepted with no override.
    within = as_admin("POST", "/api/finance/transactions", json=_expense_payload(600))
    assert within.status_code == 200, within.text

    # 3. 400 now remains, so a further 1000 is refused and names the 600 gap.
    exceeds = as_admin("POST", "/api/finance/transactions", json=_expense_payload(1000))
    assert exceeds.status_code == 409, exceeds.text
    assert "600" in exceeds.json()["detail"]

    # 4. The same expense with an explicit override is accepted.
    override = as_admin(
        "POST", "/api/finance/transactions?override_restricted=true",
        json=_expense_payload(1000),
    )
    assert override.status_code == 200, override.text

    actions = [r["action_type"] for r in store["system_audit_logs"]]
    assert actions.count("FINANCE_RESTRICTED_OVERRIDE") == 1, actions
    # The refused attempt must not have logged an override.
    assert len(actions) == 4, actions

    # 5. The auditor's own endpoint walks the chain.
    with acting_as("Admin"):
        app.dependency_overrides[get_supabase] = lambda: supabase
        verify = _request("GET", "/api/admin/audit-logs/verify")

    assert verify.status_code == 200, verify.text
    body = verify.json()
    assert body["valid"] is True, body
    assert body["unchained_legacy_rows"] == 0


def test_tampering_with_a_logged_override_breaks_the_chain():
    """The override's recorded shortfall must not be silently editable."""
    store = {
        "system_audit_logs": [],
        "financial_transactions": LEDGER,
        "programs": [{"id": PROGRAM_ID}],
    }
    supabase = _StatefulSupabase(store)

    with acting_as("Admin"):
        app.dependency_overrides[get_supabase] = lambda: supabase
        assert _request(
            "POST", "/api/finance/transactions?override_restricted=true",
            json=_expense_payload(1000),
        ).status_code == 200

    row = next(
        r for r in store["system_audit_logs"]
        if r["action_type"] == "FINANCE_RESTRICTED_OVERRIDE"
    )
    # Understate the overspend, as someone covering it up would.
    row["new_payload"]["shortfall_amount"] = 0

    with acting_as("Admin"):
        app.dependency_overrides[get_supabase] = lambda: supabase
        body = _request("GET", "/api/admin/audit-logs/verify").json()

    assert body["valid"] is False
    assert body["tampered_row_id"] == row["id"]


def _frontend_permission_map():
    """Parse ROLE_PERMISSIONS out of frontend/src/lib/permissions.ts."""
    import re

    ts_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "frontend", "src", "lib", "permissions.ts"
    )
    with open(ts_path, encoding="utf-8") as fh:
        ts = fh.read()

    body = re.search(
        r"ROLE_PERMISSIONS:\s*Record<UserRole,\s*Permission\[\]>\s*=\s*\{(.*?)\n\};",
        ts,
        re.S,
    ).group(1)

    # Role keys are quoted only when they contain a space ('HR Officer'), so
    # both forms have to be accepted.
    return {
        (quoted or bare): set(re.findall(r"'([^']+)'", perms))
        for quoted, bare, perms in re.findall(
            r"(?:'([^']+)'|(\w+))\s*:\s*\[(.*?)\]", body, re.S
        )
    }


@pytest.mark.parametrize("role", ALL_ROLES)
def test_permission_map_stays_in_sync_with_frontend(role):
    """Both maps carry a 'must stay in sync' comment and nothing enforced it.

    Previously this only checked Admin, which is precisely how a real drift
    survived: Finance Officer was missing programs:read on the backend, so the
    program picker rendered bare numeric ids for the one role that books
    program-linked expenses. Every role is checked now.
    """
    frontend = _frontend_permission_map()

    assert role in frontend, f"{role} is missing from the frontend permission map"
    assert frontend[role] == set(ROLE_PERMISSIONS[role]), (
        f"{role} differs between backend and frontend.\n"
        f"  backend only:  {sorted(set(ROLE_PERMISSIONS[role]) - frontend[role])}\n"
        f"  frontend only: {sorted(frontend[role] - set(ROLE_PERMISSIONS[role]))}"
    )


def test_frontend_declares_every_backend_permission_in_its_union():
    """A permission missing from the TS union is a compile error waiting to happen."""
    import re

    ts_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "frontend", "src", "lib", "permissions.ts"
    )
    with open(ts_path, encoding="utf-8") as fh:
        ts = fh.read()

    union = re.search(r"export type Permission\s*=(.*?);", ts, re.S).group(1)
    declared = set(re.findall(r"'([^']+)'", union))
    granted = {p for perms in ROLE_PERMISSIONS.values() for p in perms}

    assert not (granted - declared), (
        f"permissions used by the backend but absent from the frontend "
        f"Permission union: {sorted(granted - declared)}"
    )
