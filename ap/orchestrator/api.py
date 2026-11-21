"""LANE 4. Small JSON API plus the static web UI. Standard library only.

    python -m ap.orchestrator.api            # http://localhost:8000

GET  /api/phases                      workflow phases
GET  /api/invoices                    all processed invoices (summaries)
GET  /api/invoices/<id>               one invoice with history, PO, receipts, guardrails
GET  /api/inbox                       files waiting in data/inbox
POST /api/process                     {"file": "INV-0001.pdf"} or {} for all
POST /api/invoices/<id>/decision      {"approver", "decision", "reason"}
POST /api/reset                       clear state between demo runs
"""

from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ap.shared import HumanDecision

from .workflow import PHASES, Workflow

WEB_DIR = Path(__file__).resolve().parents[2] / "web"
INBOX_DIR = Path(__file__).resolve().parents[2] / "data" / "inbox"
STATE = Workflow()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, data: Any) -> None:
        self._send(code, json.dumps(data).encode(), "application/json")

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        data = json.loads(raw or b"{}")
        return data if isinstance(data, dict) else {}

    def _static(self, path: str) -> None:
        if path.startswith("/inbox/"):
            target = (INBOX_DIR / path.removeprefix("/inbox/")).resolve()
            root = INBOX_DIR.resolve()
        else:
            target = (WEB_DIR / (path.lstrip("/") or "index.html")).resolve()
            root = WEB_DIR.resolve()
        if root not in target.parents or not target.is_file():
            self._json(404, {"error": "not found"})
            return
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send(200, target.read_bytes(), ctype)

    def do_GET(self) -> None:  # noqa: N802
        parts = [p for p in self.path.split("?")[0].split("/") if p]
        try:
            if parts == ["api", "phases"]:
                self._json(200, PHASES)
            elif parts == ["api", "inbox"]:
                self._json(200, STATE.inbox())
            elif parts == ["api", "invoices"]:
                self._json(200, [STATE.summary(i) for i in STATE.invoices.values()])
            elif len(parts) == 3 and parts[:2] == ["api", "invoices"]:
                self._json(200, STATE.detail(parts[2]))
            else:
                self._static(self.path.split("?")[0])
        except KeyError:
            self._json(404, {"error": "invoice not found"})

    def do_POST(self) -> None:  # noqa: N802
        parts = [p for p in self.path.split("?")[0].split("/") if p]
        try:
            body = self._body()
            if parts == ["api", "reset"]:
                STATE.reset()
                self._json(200, {"ok": True})
            elif parts == ["api", "process"]:
                file = body.get("file")
                done = [STATE.process(file)] if file else STATE.process_all()
                self._json(200, [STATE.summary(i) for i in done])
            elif len(parts) == 4 and parts[:2] == ["api", "invoices"] and parts[3] == "decision":
                inv = STATE.decide(parts[2], HumanDecision.model_validate(body))
                self._json(200, STATE.summary(inv))
            else:
                self._json(404, {"error": "not found"})
        except KeyError:
            self._json(404, {"error": "invoice not found"})
        except ValueError as err:
            self._json(400, {"error": str(err)})


def main() -> None:
    parser = argparse.ArgumentParser(description="AP agent demo API and UI")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Serving on http://localhost:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
