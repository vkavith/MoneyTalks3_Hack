"""pay(), reconcile() and the return path against the fake Increase sandbox."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from ap.pay import PaymentRefused, pay, reconcile
from ap.pay import increase as increase_module
from ap.pay.increase import IncreaseClient, SandboxRequired, payment_status
from ap.shared import Invoice, PipelineContext

from .fake_increase import FakeIncrease


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeIncrease]:
    server = FakeIncrease()
    monkeypatch.setenv("PAYMENT_PROVIDER", "increase")
    monkeypatch.setenv("INCREASE_API_KEY", "test-sandbox-key")
    monkeypatch.setenv("INCREASE_ACCOUNT_ID", "account_test")
    monkeypatch.setenv("INCREASE_BASE_URL", "https://sandbox.increase.com")

    def from_env(
        cls: type[IncreaseClient], transport: httpx.BaseTransport | None = None
    ) -> IncreaseClient:
        return cls("test-sandbox-key", "account_test", transport=server.transport)

    monkeypatch.setattr(increase_module.IncreaseClient, "from_env", classmethod(from_env))
    yield server


def test_pay_sends_one_ach_credit(
    fake: FakeIncrease, approved_small: Invoice, ctx: PipelineContext
) -> None:
    paid = pay(approved_small, ctx)
    assert paid.status == "paid"
    assert paid.payment is not None
    assert paid.payment.provider == "increase"
    assert paid.payment.status == "pending"
    assert paid.payment.idempotency_key == "ap-INV-0001"
    assert len(fake.transfers) == 1
    (transfer,) = fake.transfers.values()
    vendor = next(v for v in ctx.vendors if v.id == approved_small.vendor_id)
    assert transfer["amount"] == approved_small.total_cents
    assert transfer["routing_number"] == vendor.bank.routing_number
    assert transfer["account_number"] == vendor.bank.account_number
    create = next(r for r in fake.requests if r.url.path == "/ach_transfers")
    assert create.headers["Idempotency-Key"] == "ap-INV-0001"


def test_retrying_with_the_same_key_makes_one_transfer(
    fake: FakeIncrease, approved_small: Invoice, ctx: PipelineContext
) -> None:
    """Our own double-payment guardrail fires first; but even the raw provider call replays."""
    paid = pay(approved_small, ctx)
    with pytest.raises(PaymentRefused):
        pay(paid, ctx)
    client = IncreaseClient("test-sandbox-key", "account_test", transport=fake.transport)
    vendor = next(v for v in ctx.vendors if v.id == approved_small.vendor_id)
    again = client.create_ach_credit(
        amount_cents=approved_small.total_cents,
        routing_number=vendor.bank.routing_number,
        account_number=vendor.bank.account_number,
        payee_name=vendor.name,
        idempotency_key="ap-INV-0001",
        entry_description=approved_small.invoice_number,
    )
    assert paid.payment is not None and again["id"] == paid.payment.transfer_id
    assert len(fake.transfers) == 1


def test_reconcile_settles_in_sandbox_and_matches_the_transaction(
    fake: FakeIncrease, approved_small: Invoice, ctx: PipelineContext
) -> None:
    paid = pay(approved_small, ctx)
    done = reconcile(paid, ctx)
    assert done.status == "reconciled"
    assert done.payment is not None and done.payment.status == "settled"
    assert done.reconciliation is not None
    assert done.reconciliation.bank_txn_id in {t["id"] for t in fake.transactions}
    (transfer,) = fake.transfers.values()
    assert transfer["status"] == "submitted" and transfer["settlement"] is not None


def test_returned_transfer_goes_back_to_approved_and_pays_again(
    fake: FakeIncrease, approved_small: Invoice, ctx: PipelineContext
) -> None:
    paid = pay(approved_small, ctx)
    assert paid.payment is not None
    client = IncreaseClient("test-sandbox-key", "account_test", transport=fake.transport)
    client.settle_in_sandbox(paid.payment.transfer_id)
    client.simulate_return(paid.payment.transfer_id, reason="account_closed")

    back = reconcile(paid, ctx)
    assert back.status == "approved"
    assert back.payment is not None and back.payment.status == "returned"
    assert back.history[-1].from_status == "paid" and back.history[-1].to_status == "approved"

    repaid = pay(back, ctx)
    assert repaid.payment is not None
    assert repaid.payment.idempotency_key == "ap-INV-0001-2"
    assert repaid.payment.transfer_id != paid.payment.transfer_id
    assert len(fake.transfers) == 2

    done = reconcile(repaid, ctx)
    assert done.status == "reconciled"
    assert done.payment is not None and done.payment.idempotency_key == "ap-INV-0001-2"


def test_large_invoice_pays_after_human_approval(
    fake: FakeIncrease, approved_large: Invoice, ctx: PipelineContext
) -> None:
    done = reconcile(pay(approved_large, ctx), ctx)
    assert done.status == "reconciled"
    assert done.payment is not None and done.payment.amount_cents == 4_800_000


def test_client_refuses_non_sandbox_hosts() -> None:
    with pytest.raises(SandboxRequired):
        IncreaseClient("k", "a", base_url="https://api.increase.com")
    with pytest.raises(SandboxRequired):
        IncreaseClient("k", "a", base_url="https://sandbox.increase.com.attacker.example")


def test_payment_status_mapping() -> None:
    assert payment_status({"status": "pending_submission"}) == "pending"
    assert payment_status({"status": "submitted", "settlement": None}) == "submitted"
    assert payment_status({"status": "submitted", "settlement": {"settled_at": "x"}}) == "settled"
    assert payment_status({"status": "returned"}) == "returned"
    with pytest.raises(increase_module.IncreaseError):
        payment_status({"status": "rejected", "id": "t"})


def test_bank_txns_carry_the_idempotency_key(
    fake: FakeIncrease, approved_small: Invoice, ctx: PipelineContext
) -> None:
    paid = pay(approved_small, ctx)
    assert paid.payment is not None
    client = IncreaseClient("test-sandbox-key", "account_test", transport=fake.transport)
    client.settle_in_sandbox(paid.payment.transfer_id)
    (line,) = client.bank_txns()
    assert line.reference == "ap-INV-0001"
    assert line.amount_cents == -approved_small.total_cents


def test_setup_sandbox_creates_and_funds_an_account(fake: FakeIncrease) -> None:
    client = IncreaseClient("test-sandbox-key", "", transport=fake.transport)
    ids = client.setup_sandbox(funding_cents=5_000)
    assert ids["INCREASE_ACCOUNT_ID"] == "account_new"
    paths = [r.url.path for r in fake.requests]
    assert paths == [
        "/programs",
        "/entities",
        "/entities",
        "/accounts",
        "/account_numbers",
        "/simulations/inbound_wire_transfers",
    ]
