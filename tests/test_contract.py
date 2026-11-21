"""Lane 4. Guards the contract and the end-to-end skeleton.

Each lane adds its own tests under tests/intake/, tests/match/ or tests/pay/.
"""

from __future__ import annotations

import pytest

from ap.orchestrator.run import compare, run_pipeline
from ap.shared import IllegalTransition, Invoice, transition
from ap.shared.load import list_inbox, load_captured_fixture


def test_fixtures_round_trip() -> None:
    for file in list_inbox():
        inv = load_captured_fixture(file)
        assert Invoice.model_validate_json(inv.model_dump_json()) == inv


def test_transition_records_history() -> None:
    inv = load_captured_fixture("INV-0001.pdf")
    moved = transition(inv, "matched", "test", "note")
    assert moved.status == "matched"
    assert moved.history[-1].from_status == "captured"
    assert moved.history[-1].to_status == "matched"
    assert inv.status == "captured", "the original must not change"


def test_illegal_transition_is_rejected() -> None:
    inv = load_captured_fixture("INV-0001.pdf")
    with pytest.raises(IllegalTransition):
        transition(inv, "paid", "test")


def test_pipeline_matches_expected_outcomes() -> None:
    rows = compare(run_pipeline())
    assert [r["invoice"] for r in rows if r["ok"] != "yes"] == []


def test_human_approval_lets_the_large_invoice_through() -> None:
    results = {inv.id: inv for inv in run_pipeline(["INV-0003"])}
    assert results["INV-0003"].status == "reconciled"
