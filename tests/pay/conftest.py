"""Lane 3 fixtures. No network: Prism is off and the provider is the mock unless a test says so."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from ap.pay import approve
from ap.pay.prism import configure_prism, reset_prism
from ap.shared import HumanDecision, Invoice, PipelineContext, transition
from ap.shared.load import load_captured_fixture, load_context


@pytest.fixture(autouse=True)
def quiet_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv("PAYMENT_PROVIDER", raising=False)
    monkeypatch.delenv("PRISMTRACE_API_KEY", raising=False)
    monkeypatch.delenv("PRISMTRACE_PROJECT_ID", raising=False)
    configure_prism(None)
    yield
    reset_prism()


@pytest.fixture
def ctx() -> PipelineContext:
    return load_context()


def matched(invoice_id: str) -> Invoice:
    inv = load_captured_fixture(f"{invoice_id}.pdf")
    return transition(inv, "matched", "test")


def approved(invoice_id: str, ctx: PipelineContext) -> Invoice:
    inv = approve(matched(invoice_id), ctx)
    if inv.status != "approved":
        human = HumanDecision(approver="Test Approver", decision="approved", reason="test")
        inv = approve(inv, ctx, human)
    assert inv.status == "approved"
    return inv


@pytest.fixture
def approved_small(ctx: PipelineContext) -> Invoice:
    """INV-0001: $1,300, auto-approved."""
    return approved("INV-0001", ctx)


@pytest.fixture
def approved_large(ctx: PipelineContext) -> Invoice:
    """INV-0003: $48,000, needs a human."""
    return approved("INV-0003", ctx)
