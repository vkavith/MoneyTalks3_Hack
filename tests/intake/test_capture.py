from json import dumps
from pathlib import Path

import httpx
import pytest
from reportlab.pdfgen.canvas import Canvas

import ap.intake as intake
from ap.intake import capture
from ap.intake.extraction import CaptureError
from ap.shared import Invoice
from ap.shared.load import list_inbox, load_captured_fixture


@pytest.mark.parametrize("source_file", list_inbox())
def test_capture_matches_seed_invoice(source_file: str) -> None:
    captured = Invoice.model_validate(capture(source_file).model_dump())
    expected = load_captured_fixture(source_file)
    assert captured.model_dump(exclude={"history"}) == expected.model_dump(exclude={"history"})
    assert [(event.from_status, event.to_status) for event in captured.history] == [
        (None, "received"),
        ("received", "captured"),
    ]
    assert captured.history[-1].actor == "capture"


@pytest.fixture
def inbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "inbox"
    path.mkdir()
    monkeypatch.setattr(intake, "DATA_DIR", tmp_path)
    return path


def _pdf(path: Path, lines: list[str]) -> None:
    canvas = Canvas(str(path))
    for index, line in enumerate(lines):
        canvas.drawString(45, 750 - 18 * index, line)
    canvas.save()


def test_pdf_values_come_from_document(inbox: Path) -> None:
    _pdf(
        inbox / "test.pdf",
        [
            "New Vendor",
            "INVOICE",
            "Invoice number: DEMO-01",
            "Invoice date: 2026-10-15",
            "Due date: 2026-11-14",
            "Description                Qty           Unit price        Amount",
            "Demo item                  2             $10.00           $25.00",
            "Subtotal: $25.00",
            "Tax: $0.00",
            "Total due: $25.00",
        ],
    )
    invoice = capture("test.pdf")
    assert invoice.id == "test"
    assert invoice.vendor_id is None
    assert invoice.lines[0].qty == 2
    assert invoice.lines[0].unit_price_cents == 1000
    assert invoice.lines[0].amount_cents == invoice.total_cents == 2500


def test_invalid_pdf_raises_capture_error(inbox: Path) -> None:
    (inbox / "broken.pdf").write_bytes(b"not a PDF")
    with pytest.raises(CaptureError, match="Cannot read invoice PDF"):
        capture("broken.pdf")


def test_capture_rejects_paths_outside_the_inbox() -> None:
    with pytest.raises(CaptureError, match="PDF file name"):
        capture("../outside.pdf")


def test_nicrron_layout_fallback_retries_invalid_output(
    inbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pdf(inbox / "alternate.pdf", ["Vendor: Northwind Packaging LLC", "Invoice Ref NW-NEW"])
    model_output = {
        "vendor_name": "Northwind Packaging LLC",
        "invoice_number": "NW-NEW",
        "invoice_date": "2026-10-15",
        "due_date": "2026-11-14",
        "po_id": None,
        "lines": [{"description": "Box", "qty": 1, "unit_price": "1.25", "amount": "1.25"}],
        "subtotal": "1.25",
        "tax": "0.00",
        "total": "1.25",
        "remit_to": None,
    }
    responses = iter([{"unexpected": True}, model_output])
    calls: list[dict[str, object]] = []

    def post(
        url: str, *, headers: dict[str, str], json: dict[str, object], timeout: float
    ) -> httpx.Response:
        calls.append(json)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": dumps(next(responses))}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setenv("NICRRON_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "post", post)
    invoice = capture("alternate.pdf")
    assert len(calls) == 2
    assert invoice.invoice_number == "NW-NEW"
    assert invoice.vendor_id == "V-001"
    assert invoice.total_cents == 125
