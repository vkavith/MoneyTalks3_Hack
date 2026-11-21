from __future__ import annotations

import pytest

from ap.pay import approve
from ap.shared import HumanDecision, PipelineContext

from .conftest import matched


def test_under_limit_is_auto_approved(ctx: PipelineContext) -> None:
    inv = approve(matched("INV-0001"), ctx)
    assert inv.status == "approved"
    assert inv.approval is not None and inv.approval.decision == "auto_approved"
    assert inv.history[-1].actor == "approve"


def test_over_limit_waits_on_the_right_tier(ctx: PipelineContext) -> None:
    inv = approve(matched("INV-0003"), ctx)  # $48,000: tier 1 (<= $50,000) is finance_manager
    assert inv.status == "matched"
    assert inv.approval is not None
    assert inv.approval.decision == "pending"
    assert inv.approval.approver == "finance_manager"
    assert inv.approval.decided_at is None


def test_human_approval_moves_it_on(ctx: PipelineContext) -> None:
    pending = approve(matched("INV-0003"), ctx)
    human = HumanDecision(approver="Jane Doe", decision="approved", reason="Budgeted")
    inv = approve(pending, ctx, human)
    assert inv.status == "approved"
    assert inv.approval is not None and inv.approval.approver == "Jane Doe"
    assert inv.history[-1].actor == "human:Jane Doe"
    assert inv.history[-1].note == "Budgeted"


def test_human_rejection_is_terminal(ctx: PipelineContext) -> None:
    pending = approve(matched("INV-0003"), ctx)
    human = HumanDecision(approver="Jane Doe", decision="rejected", reason="Not ordered")
    inv = approve(pending, ctx, human)
    assert inv.status == "rejected"


def test_only_matched_invoices_can_be_approved(ctx: PipelineContext) -> None:
    captured = matched("INV-0001").history[0]  # sanity: fixture starts captured
    assert captured.to_status == "captured"
    with pytest.raises(ValueError):
        approve(approve(matched("INV-0001"), ctx), ctx)
