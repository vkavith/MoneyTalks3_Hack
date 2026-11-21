"""Prism wiring: traces per decision, fail-open, and no bank details in anything we send."""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx
import pytest

from ap.pay import approve, pay, reconcile
from ap.pay.prism import PrismClient, PrismConfig, Verdict, configure_prism, prism_client
from ap.shared import Invoice, PipelineContext

from .conftest import matched


class FakePrism:
    def __init__(self, evaluate: dict[str, object] | None = None, status: int = 200) -> None:
        self.evaluate = evaluate or {"blocked": False, "evaluated": True}
        self.status = status
        self.calls: list[tuple[str, dict[str, object]]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["X-PRISMtrace-Key"] == "pt-sk-test"
        assert "Authorization" not in request.headers
        body = json.loads(request.content)
        self.calls.append((request.url.path, body))
        if self.status != 200:
            return httpx.Response(self.status, json={"detail": "boom"})
        if request.url.path == "/api/guardrails/evaluate":
            return httpx.Response(200, json=self.evaluate)
        return httpx.Response(200, json={"id": "trace-1", "cost_usd": 0})

    def client(self) -> PrismClient:
        return PrismClient(
            PrismConfig("https://prism.test", "proj-1", "pt-sk-test"),
            transport=httpx.MockTransport(self.handle),
        )

    def traces(self) -> list[dict[str, object]]:
        return [b for p, b in self.calls if p == "/api/traces"]


@pytest.fixture
def prism() -> Iterator[FakePrism]:
    fake = FakePrism()
    configure_prism(fake.client())
    yield fake


def test_every_stage_records_a_trace_in_the_invoice_session(
    prism: FakePrism, ctx: PipelineContext
) -> None:
    inv = approve(matched("INV-0001"), ctx)
    inv = pay(inv, ctx)
    inv = reconcile(inv, ctx)
    assert inv.status == "reconciled"
    stages = [t["metadata"]["stage"] for t in prism.traces()]  # type: ignore[index]
    assert stages == ["approve", "pay", "reconcile"]
    for trace in prism.traces():
        assert trace["session_id"] == "INV-0001"
        assert trace["agent_id"] == "ap-pay"
        assert trace["project_id"] == "proj-1"
        assert isinstance(trace["latency_ms"], int)
    paths = [p for p, _ in prism.calls]
    assert paths.count("/api/guardrails/evaluate") == 1, "pay asks the guardrails exactly once"


def test_nothing_we_send_contains_bank_details(prism: FakePrism, ctx: PipelineContext) -> None:
    inv = reconcile(pay(approve(matched("INV-0001"), ctx), ctx), ctx)
    assert inv.status == "reconciled"
    vendor = next(v for v in ctx.vendors if v.id == inv.vendor_id)
    fixture = matched("INV-0001")
    assert fixture.remit_to is not None
    secrets = {
        vendor.bank.account_number,
        vendor.bank.routing_number,
        fixture.remit_to.account_number,
        fixture.remit_to.routing_number,
    }
    everything = json.dumps([b for _, b in prism.calls])
    for secret in secrets:
        assert secret not in everything


def test_refusals_are_recorded(prism: FakePrism, ctx: PipelineContext) -> None:
    from ap.pay import PaymentRefused

    with pytest.raises(PaymentRefused):
        pay(matched("INV-0001"), ctx)
    (trace,) = prism.traces()
    assert trace["metadata"]["outcome"] == "refused"  # type: ignore[index]
    assert trace["metadata"]["guardrail"] == "status"  # type: ignore[index]
    assert str(trace["output_message"]).startswith("REFUSED")


def test_pending_approval_is_recorded(prism: FakePrism, ctx: PipelineContext) -> None:
    approve(matched("INV-0003"), ctx)
    (trace,) = prism.traces()
    assert trace["metadata"]["outcome"] == "pending"  # type: ignore[index]
    assert trace["metadata"]["approver_role"] == "finance_manager"  # type: ignore[index]


def test_prism_outage_fails_open(approved_small: Invoice, ctx: PipelineContext) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    client = PrismClient(
        PrismConfig("https://prism.test", "proj-1", "pt-sk-test"),
        transport=httpx.MockTransport(down),
    )
    configure_prism(client)
    assert client.evaluate("t", [{"role": "user", "content": "x"}]) == Verdict.skipped(
        "unreachable"
    )
    paid = pay(approved_small, ctx)
    assert paid.status == "paid"


def test_prism_server_error_fails_open(approved_small: Invoice, ctx: PipelineContext) -> None:
    fake = FakePrism(status=500)
    configure_prism(fake.client())
    assert pay(approved_small, ctx).status == "paid"


def test_plan_not_entitled_is_not_a_block(approved_small: Invoice, ctx: PipelineContext) -> None:
    fake = FakePrism(evaluate={"blocked": False, "evaluated": False, "reason": "plan_not_entitled"})
    configure_prism(fake.client())
    assert pay(approved_small, ctx).status == "paid"


def test_disabled_without_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    from ap.pay.prism import reset_prism

    reset_prism()
    monkeypatch.delenv("PRISMTRACE_API_KEY", raising=False)
    monkeypatch.delenv("PRISMTRACE_PROJECT_ID", raising=False)
    assert prism_client() is None
    monkeypatch.setenv("PRISMTRACE_API_KEY", "pt-sk-x")
    monkeypatch.setenv("PRISMTRACE_PROJECT_ID", "p")
    client = prism_client()
    assert client is not None and client.config.host == "https://api.prism.blockconvey.com"
    client.close()
