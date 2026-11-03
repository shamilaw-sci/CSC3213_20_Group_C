"""Donations: PayHere signing, the public routes, and the analytics.

The money rule under test: a donation reaches the ledger only through
record_donation_payment(), and only after PayHere confirms it. These tests
check the API never calls that function on the browser's word alone.
"""

import hashlib
from decimal import Decimal

import pytest

from app.api import donations as donations_api
from app.core import config
from app.core.supabase import get_public_supabase, get_supabase
from app.main import app
from app.schemas.donations import DonationCheckoutCreate
from app.services import payhere
from tests.test_rbac_matrix import _FakeQuery, _FakeResult, _FakeSupabase, acting_as, client

MERCHANT_ID = "1211149"
MERCHANT_SECRET = "test-secret"


def _md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest().upper()


@pytest.fixture
def payhere_keys(monkeypatch):
    monkeypatch.setattr(config, "PAYHERE_MERCHANT_ID", MERCHANT_ID)
    monkeypatch.setattr(config, "PAYHERE_MERCHANT_SECRET", MERCHANT_SECRET)
    monkeypatch.setattr(config, "PAYHERE_APP_ID", None)
    monkeypatch.setattr(config, "PAYHERE_APP_SECRET", None)


class _RecordingSupabase(_FakeSupabase):
    """Fake client that records rpc calls and inserts."""

    def __init__(self, tables=None):
        super().__init__(tables)
        self.rpc_calls = []
        self.inserts = []

    def table(self, name):
        query = super().table(name)
        original_insert = query.insert
        recorder = self

        def insert(data=None, *a, **k):
            recorder.inserts.append((name, data))
            return original_insert(data, *a, **k)

        query.insert = insert
        return query

    def rpc(self, name, params=None):
        self.rpc_calls.append((name, params))
        return super().rpc(name, params)


@pytest.fixture
def public_db():
    holder = {}

    def use(tables):
        fake = _RecordingSupabase(tables)
        holder["db"] = fake
        app.dependency_overrides[get_public_supabase] = lambda: fake
        return fake

    try:
        yield use
    finally:
        app.dependency_overrides.clear()


def _donation_row(**over):
    row = {
        "id": 7, "amount": "5000.00", "currency": "LKR", "purpose": "general",
        "program_id": None, "is_anonymous": False, "donor_name": "Nimal Perera",
        "donor_email": "nimal@example.com", "donor_phone": None, "message": None,
        "status": "pending", "gateway": "payhere", "gateway_ref": "VFF-ABC123",
        "finance_transaction_id": None, "thank_you_sent_at": None,
        "created_at": "2026-11-03T10:00:00+00:00", "paid_at": None, "programs": None,
    }
    row.update(over)
    return row


# --------------------------------------------------------------------------
# PayHere signing
# --------------------------------------------------------------------------

def test_checkout_hash_matches_payhere_formula():
    expected = _md5(f"{MERCHANT_ID}ORDER1" + "1000.00" + "LKR" + _md5(MERCHANT_SECRET))
    got = payhere.checkout_hash("ORDER1", Decimal("1000"), "LKR",
                                merchant_id=MERCHANT_ID, merchant_secret=MERCHANT_SECRET)
    assert got == expected


def _signed_notification(status_code="2", amount="5000.00", order_id="VFF-ABC123"):
    form = {
        "merchant_id": MERCHANT_ID, "order_id": order_id, "payment_id": "320025071278",
        "payhere_amount": amount, "payhere_currency": "LKR", "status_code": status_code,
    }
    form["md5sig"] = _md5(
        f"{MERCHANT_ID}{order_id}{amount}LKR{status_code}{_md5(MERCHANT_SECRET)}"
    )
    return form


def test_genuine_notification_is_accepted():
    assert payhere.notification_is_genuine(
        _signed_notification(), merchant_secret=MERCHANT_SECRET, merchant_id=MERCHANT_ID)


def test_tampered_notification_is_rejected():
    form = _signed_notification()
    form["payhere_amount"] = "50000.00"  # amount changed after signing
    assert not payhere.notification_is_genuine(
        form, merchant_secret=MERCHANT_SECRET, merchant_id=MERCHANT_ID)


def test_notification_for_another_merchant_is_rejected():
    form = _signed_notification()
    assert not payhere.notification_is_genuine(
        form, merchant_secret=MERCHANT_SECRET, merchant_id="999")


def _search_body(status="RECEIVED", amount=1000):
    return {"status": 1, "data": [{
        "order_id": "VFF-ABC123", "status": status, "currency": "LKR",
        "amount": amount, "amount_detail": {"gross": amount},
    }]}


def test_received_payment_counts_as_paid():
    assert payhere.paid_in_full(_search_body("RECEIVED"), "VFF-ABC123", Decimal("1000"))


def test_sandbox_authorized_payment_counts_as_paid(monkeypatch):
    # The PayHere sandbox shows successful test payments as "Authorized".
    monkeypatch.setattr(config, "PAYHERE_SANDBOX", True)
    assert payhere.paid_in_full(_search_body("AUTHORIZED"), "VFF-ABC123", Decimal("1000"))


def test_live_authorized_payment_does_not_count(monkeypatch):
    monkeypatch.setattr(config, "PAYHERE_SANDBOX", False)
    assert not payhere.paid_in_full(_search_body("AUTHORIZED"), "VFF-ABC123", Decimal("1000"))


def test_partial_or_other_order_payment_does_not_count():
    assert not payhere.paid_in_full(_search_body(amount=500), "VFF-ABC123", Decimal("1000"))
    assert not payhere.paid_in_full(_search_body(), "VFF-OTHER", Decimal("1000"))
    assert not payhere.paid_in_full({"status": -1, "data": []}, "VFF-ABC123", Decimal("1000"))


# --------------------------------------------------------------------------
# The form
# --------------------------------------------------------------------------

def test_anonymous_donation_drops_every_detail():
    d = DonationCheckoutCreate(
        amount=Decimal("1000"), purpose="general", is_anonymous=True,
        donor_name="Typed before toggling", donor_email="a@b.com", donor_phone="077",
    )
    assert (d.donor_name, d.donor_email, d.donor_phone) == (None, None, None)


def test_named_donation_needs_name_and_email():
    with pytest.raises(ValueError):
        DonationCheckoutCreate(amount=Decimal("1000"), purpose="general", donor_name="Nimal")
    with pytest.raises(ValueError):
        DonationCheckoutCreate(amount=Decimal("1000"), purpose="general", donor_email="n@x.com")


def test_program_donation_needs_a_program():
    with pytest.raises(ValueError):
        DonationCheckoutCreate(amount=Decimal("1000"), purpose="program", is_anonymous=True)


def test_general_donation_never_carries_a_program():
    d = DonationCheckoutCreate(amount=Decimal("1000"), purpose="general",
                               program_id=3, is_anonymous=True)
    assert d.program_id is None


@pytest.mark.parametrize("amount", ["99.99", "0", "-5", "1000000"])
def test_amount_out_of_range_is_rejected(amount):
    with pytest.raises(ValueError):
        DonationCheckoutCreate(amount=Decimal(amount), purpose="general", is_anonymous=True)


# --------------------------------------------------------------------------
# Public routes
# --------------------------------------------------------------------------

def test_programs_list_hides_completed(public_db):
    public_db({"programs": [
        {"id": 1, "program_name": "Clinic", "status": "Active"},
        {"id": 2, "program_name": "Old", "status": "Completed"},
        {"id": 3, "program_name": "Soon", "status": "Upcoming"},
    ]})
    r = client.get("/api/donations/programs")
    assert r.status_code == 200
    assert [p["id"] for p in r.json()] == [1, 3]


def test_checkout_without_payhere_keys_is_503(public_db, monkeypatch):
    monkeypatch.setattr(config, "PAYHERE_MERCHANT_ID", None)
    public_db({})
    r = client.post("/api/donations/checkout",
                    json={"amount": 1000, "purpose": "general", "is_anonymous": True})
    assert r.status_code == 503


def test_checkout_saves_pending_and_signs_form(public_db, payhere_keys):
    db = public_db({"donations": {"insert": [_donation_row()]}})
    r = client.post("/api/donations/checkout", json={
        "amount": 5000, "purpose": "general",
        "donor_name": "Nimal Perera", "donor_email": "nimal@example.com",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    fields = body["fields"]
    assert fields["amount"] == "5000.00"
    assert fields["hash"] == payhere.checkout_hash(body["order_id"], Decimal("5000"))
    assert fields["first_name"] == "Nimal" and fields["last_name"] == "Perera"

    (table, saved), = db.inserts
    assert table == "donations"
    assert saved["status"] == "pending"
    assert saved["gateway_ref"] == body["order_id"]
    # Starting a checkout never touches the ledger.
    assert db.rpc_calls == []


def test_checkout_refuses_completed_program(public_db, payhere_keys):
    public_db({"programs": [{"id": 2, "program_name": "Old", "status": "Completed"}]})
    r = client.post("/api/donations/checkout", json={
        "amount": 1000, "purpose": "program", "program_id": 2, "is_anonymous": True,
    })
    assert r.status_code == 400


def test_anonymous_checkout_sends_org_details_and_stores_none(public_db, payhere_keys):
    db = public_db({"donations": {"insert": [_donation_row(is_anonymous=True)]}})
    r = client.post("/api/donations/checkout", json={
        "amount": 1000, "purpose": "general", "is_anonymous": True,
        "donor_name": "Should vanish", "donor_email": "gone@example.com",
    })
    assert r.status_code == 200, r.text
    assert r.json()["fields"]["first_name"] == "Anonymous"
    (_, saved), = db.inserts
    assert "donor_name" not in saved and "donor_email" not in saved


def test_confirm_without_payhere_confirmation_records_nothing(public_db, payhere_keys, monkeypatch):
    async def not_paid(*a, **k):
        return False
    monkeypatch.setattr(payhere, "order_is_paid", not_paid)
    db = public_db({"donations": [_donation_row()]})
    r = client.post("/api/donations/confirm/VFF-ABC123")
    assert r.status_code == 200
    assert r.json()["status"] == "pending"
    assert db.rpc_calls == []


def test_confirm_records_when_payhere_says_paid(public_db, payhere_keys, monkeypatch):
    async def paid(*a, **k):
        return True
    monkeypatch.setattr(payhere, "order_is_paid", paid)
    db = public_db({"donations": [_donation_row()]})
    client.post("/api/donations/confirm/VFF-ABC123")
    assert db.rpc_calls == [
        ("record_donation_payment", {"p_donation_id": 7, "p_amount": "5000.00"})
    ]


def test_forged_notification_records_nothing(public_db, payhere_keys):
    db = public_db({"donations": [_donation_row()]})
    form = _signed_notification()
    form["md5sig"] = "0" * 32
    r = client.post("/api/donations/payhere/notify", data=form)
    assert r.status_code == 200
    assert db.rpc_calls == []


def test_notification_with_wrong_amount_records_nothing(public_db, payhere_keys):
    db = public_db({"donations": [_donation_row()]})
    r = client.post("/api/donations/payhere/notify",
                    data=_signed_notification(amount="100.00"))
    assert r.status_code == 200
    assert db.rpc_calls == []


def test_genuine_notification_records_payment(public_db, payhere_keys):
    db = public_db({"donations": [_donation_row()]})
    r = client.post("/api/donations/payhere/notify", data=_signed_notification())
    assert r.status_code == 200
    assert db.rpc_calls == [
        ("record_donation_payment", {"p_donation_id": 7, "p_amount": "5000.00"})
    ]


# --------------------------------------------------------------------------
# Staff routes and analytics
# --------------------------------------------------------------------------

def test_summary_needs_finance_read():
    with acting_as("General Staff"):
        assert client.get("/api/donations/summary").status_code == 403
    with acting_as("Finance Officer", tables={"donations": []}):
        assert client.get("/api/donations/summary").status_code == 200


def test_summary_counts_paid_only_and_groups_donors_by_email():
    rows = [
        _donation_row(id=1, amount="1000", status="paid", donor_email="Nimal@example.com",
                      paid_at="2026-10-01T00:00:00+00:00"),
        _donation_row(id=2, amount="2500", status="paid", donor_email="nimal@example.com",
                      donor_name="Nimal P.", paid_at="2026-11-01T00:00:00+00:00"),
        _donation_row(id=3, amount="4000", status="paid", is_anonymous=True,
                      donor_name=None, donor_email=None, purpose="program", program_id=5,
                      programs={"program_name": "Clinic"}, paid_at="2026-11-02T00:00:00+00:00"),
        _donation_row(id=4, amount="9999", status="pending"),
        _donation_row(id=5, amount="9999", status="cancelled"),
    ]
    s = donations_api.build_summary(rows)
    assert s["total_raised"] == Decimal("7500.00")
    assert s["donation_count"] == 3
    assert s["anonymous_total"] == Decimal("4000.00")
    assert s["unique_donors"] == 1
    assert s["donors"][0]["total"] == Decimal("3500.00")
    assert s["donors"][0]["count"] == 2
    assert s["donors"][0]["donor_name"] == "Nimal P."  # latest name wins
    assert s["program_total"] == Decimal("4000.00")
    assert s["general_total"] == Decimal("3500.00")
    assert s["by_program"][0]["program_name"] == "Clinic"
    assert s["pending_count"] == 1
    assert [m["month"] for m in s["monthly"]] == ["2026-10", "2026-11"]
