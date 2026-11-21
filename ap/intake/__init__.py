"""LANE 1. STUB: returns the ground-truth fixture instead of reading the PDF.

Replace the body of capture() with real extraction. Keep the signature.
"""

from __future__ import annotations

from ap.shared import Invoice
from ap.shared.load import load_captured_fixture


def capture(source_file: str) -> Invoice:
    return load_captured_fixture(source_file)
