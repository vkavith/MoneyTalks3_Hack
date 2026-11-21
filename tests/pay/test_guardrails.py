"""One test per guardrail in pay(). Each one raises PaymentRefused."""

from __future__ import annotations

import httpx
import pytest

from ap.pay import PaymentRefused, pay, payment_idempotency_key
from ap.pay.prism import PrismClient, PrismConfig, configure_prism
from ap.shared import Invoice, PipelineContext, Vendor

from .conftest import matched


def refused(invoice: Invoice, ctx: PipelineContext) -> PaymentRefused:
    with pytest.raises(PaymentRefused) as info:
        pay(invoice, ctx)
    return info.value


def test_refuses_unless_approved(ctx: PipelineContext) -> None:
    assert refused(matched("INV-0001"), ctx).guardrail == "status"


def test_refuses_to_pay_twice(approved_small: Invoice, ctx: PipelineContext) -> None:
    paid = pay(approved_small, ctx)
    assert refused(paid, ctx).guardrail == "double_payment"


def test_refuses_without_an_active_vendor(approved_small: Invoice, ctx: PipelineContext) -> None:
    assert (
        refused(approved_small.model_copy(update={"vendor_id": "V-999"}), ctx).guardrail == "vendor"
    )
    assert refused(approved_small.model_copy(update={"vendor_id": None}), ctx).guardrail == "vendor"
    inactive = [v.model_copy(update={"active": False}) for v in ctx.vendors]
    from dataclasses import replace

    assert refused(approved_small, replace(ctx, vendors=inactive)).guardrail == "vendor"


def test_refuses_over_the_single_payment_limit(
    approved_small: Invoice, ctx: PipelineContext
) -> None:
    too_much = approved_small.model_copy(
        update={"total_cents": ctx.policy.max_single_payment_cents + 1}
    )
    assert refused(too_much, ctx).guardrail == "limit"


def test_refuses_a_non_positive_amount(approved_small: Invoice, ctx: PipelineContext) -> None:
    assert refused(approved_small.model_copy(update={"total_cents": 0}), ctx).guardrail == "amount"


def test_refuses_a_non_sandbox_base_url(
    approved_small: Invoice, ctx: PipelineContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PAYMENT_PROVIDER", "increase")
    monkeypatch.setenv("INCREASE_API_KEY", "test")
    monkeypatch.setenv("INCREASE_ACCOUNT_ID", "account_test")
    for bad in ("https://api.increase.com", "", "https://sandbox.increase.com.evil.example"):
        monkeypatch.setenv("INCREASE_BASE_URL", bad)
        assert refused(approved_small, ctx).guardrail == "sandbox"


def test_idempotency_key_is_ap_invoice_id(approved_small: Invoice, ctx: PipelineContext) -> None:
    assert payment_idempotency_key(approved_small) == "ap-INV-0001"
    paid = pay(approved_small, ctx)
    assert paid.payment is not None
    assert paid.payment.idempotency_key == "ap-INV-0001"
    assert paid.payment.amount_cents == approved_small.total_cents


def test_amount_and_payee_come_from_records_not_the_invoice(
    approved_small: Invoice, ctx: PipelineContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """remit_to on the invoice is a decoy; the request must carry the vendor master's bank."""
    decoy = approved_small.model_copy(
        update={"remit_to": {"routing_number": "999999999", "account_number": "000000001"}}
    )
    vendor: Vendor = next(v for v in ctx.vendors if v.id == decoy.vendor_id)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        import json

        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "ach_transfer_test",
                "status": "pending_submission",
                "amount": body["amount"],
                "created_at": "2026-11-21T12:00:00Z",
                "settlement": None,
            },
        )

    from ap.pay import increase

    monkeypatch.setenv("PAYMENT_PROVIDER", "increase")
    monkeypatch.setenv("INCREASE_API_KEY", "test")
    monkeypatch.setenv("INCREASE_ACCOUNT_ID", "account_test")
    monkeypatch.setenv("INCREASE_BASE_URL", "https://sandbox.increase.com")
    monkeypatch.setattr(
        increase.IncreaseClient,
        "from_env",
        classmethod(
            lambda cls, transport=None: cls(
                "test", "account_test", transport=httpx.MockTransport(handler)
            )
        ),
    )
    paid = pay(decoy, ctx)
    import json

    body = json.loads(seen[0].content)
    assert body["routing_number"] == vendor.bank.routing_number
    assert body["account_number"] == vendor.bank.account_number
    assert body["amount"] == decoy.total_cents
    assert seen[0].headers["Idempotency-Key"] == "ap-INV-0001"
    assert paid.payment is not None and paid.payment.provider == "increase"


def test_prism_block_refuses_and_is_honoured(approved_small: Invoice, ctx: PipelineContext) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        calls.append((request.url.path, body))
        if request.url.path == "/api/guardrails/evaluate":
            return httpx.Response(
                200,
                json={
                    "blocked": True,
                    "evaluated": True,
                    "rule_name": "No bank details in instructions",
                    "rule_type": "regex",
                    "matched_text": "routing",
                    "fallback_message": "Blocked by policy",
                },
            )
        return httpx.Response(200, json={"id": "t1", "cost_usd": 0})

    configure_prism(
        PrismClient(
            PrismConfig("https://prism.test", "proj", "pt-sk-test"),
            transport=httpx.MockTransport(handler),
        )
    )
    exc = refused(approved_small, ctx)
    assert exc.guardrail == "prism"
    paths = [p for p, _ in calls]
    assert paths == ["/api/guardrails/evaluate", "/api/traces"]
    evaluate_body, trace_body = calls[0][1], calls[1][1]
    assert evaluate_body["trace_id"] == trace_body["trace_id"], "same id so Prism can verify"
    assert trace_body["output_message"] == "", "a honoured block sends no output"
    assert trace_body["session_id"] == "INV-0001"
