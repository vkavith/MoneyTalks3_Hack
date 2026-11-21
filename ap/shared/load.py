"""Helpers for reading /data. Every file is validated against the contract."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TypeVar

from pydantic import TypeAdapter

from .schema import (
    BankTxn,
    ExpectedOutcome,
    GoodsReceipt,
    Invoice,
    Policy,
    PurchaseOrder,
    Vendor,
)
from .stages import PipelineContext

T = TypeVar("T")

DATA_DIR = Path(os.environ.get("AP_DATA_DIR") or Path(__file__).resolve().parents[2] / "data")


def _read(kind: type[T], *path: str) -> T:
    return TypeAdapter(kind).validate_json(DATA_DIR.joinpath(*path).read_bytes())


def load_context() -> PipelineContext:
    return PipelineContext(
        vendors=_read(list[Vendor], "vendors.json"),
        purchase_orders=_read(list[PurchaseOrder], "purchase_orders.json"),
        receipts=_read(list[GoodsReceipt], "goods_receipts.json"),
        policy=_read(Policy, "policy.json"),
        bank_txns=_read(list[BankTxn], "bank_statement.json"),
    )


def list_inbox() -> list[str]:
    """PDF file names in data/inbox, in arrival order."""
    return sorted(p.name for p in (DATA_DIR / "inbox").glob("*.pdf"))


def load_captured_fixture(source_file: str) -> Invoice:
    """Ground truth for what capture should produce from an inbox file."""
    return _read(Invoice, "expected", "captured", Path(source_file).stem + ".json")


def load_expected_outcomes() -> list[ExpectedOutcome]:
    return _read(list[ExpectedOutcome], "expected", "outcomes.json")
