"""An in-memory stand-in for the Increase sandbox, served through httpx.MockTransport.

It mirrors the pieces of the API this lane uses: ACH transfer creation with
idempotency replay, retrieval, the submit/settle/return simulations, and the
transactions list with ``source.ach_transfer_intention`` / ``ach_transfer_return``.
"""

from __future__ import annotations

import json
from typing import Any

import httpx


class FakeIncrease:
    def __init__(self) -> None:
        self.transfers: dict[str, dict[str, Any]] = {}
        self.by_key: dict[str, str] = {}
        self.transactions: list[dict[str, Any]] = []
        self.requests: list[httpx.Request] = []
        self._n = 0

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def _id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}_{self._n:04d}"

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.headers.get("Authorization") != "Bearer test-sandbox-key":
            return httpx.Response(401, json={"title": "bad key"})
        path, method = request.url.path, request.method
        body = json.loads(request.content) if request.content else {}
        if method == "POST" and path == "/ach_transfers":
            return self._create(body, request.headers.get("Idempotency-Key"))
        if method == "GET" and path.startswith("/ach_transfers/"):
            return self._transfer(path.rsplit("/", 1)[1])
        if method == "POST" and path.startswith("/simulations/ach_transfers/"):
            _, _, _, transfer_id, action = path.split("/")
            return self._simulate(transfer_id, action, body)
        if method == "GET" and path == "/transactions":
            return httpx.Response(200, json={"data": self.transactions, "next_cursor": None})
        if method == "GET" and path == "/programs":
            return httpx.Response(200, json={"data": [{"id": "program_1"}], "next_cursor": None})
        if method == "GET" and path == "/entities":
            return httpx.Response(200, json={"data": [], "next_cursor": None})
        if method == "POST" and path == "/entities":
            if body.get("structure") != "corporation" or "corporation" not in body:
                return httpx.Response(400, json={"title": "bad entity"})
            return httpx.Response(200, json={"id": "entity_new", "structure": "corporation"})
        if method == "POST" and path == "/accounts":
            if "entity_id" not in body:
                return httpx.Response(409, json={"detail": "No entity_id provided"})
            return httpx.Response(200, json={"id": "account_new", "name": body["name"]})
        if method == "POST" and path == "/account_numbers":
            return httpx.Response(200, json={"id": "account_number_new"})
        if method == "POST" and path == "/simulations/inbound_wire_transfers":
            return httpx.Response(200, json={"id": "inbound_wire_1", "amount": body["amount"]})
        return httpx.Response(404, json={"title": f"no route {method} {path}"})

    def _create(self, body: dict[str, Any], key: str | None) -> httpx.Response:
        if key and key in self.by_key:
            existing = self.transfers[self.by_key[key]]
            if existing["amount"] != body["amount"]:
                return httpx.Response(409, json={"type": "idempotency_key_already_used_error"})
            return httpx.Response(200, json=existing, headers={"Idempotent-Replayed": "true"})
        required = {
            "account_id",
            "amount",
            "routing_number",
            "account_number",
            "company_name",
            "individual_name",
        }
        missing = required - set(body)
        if missing:
            return httpx.Response(400, json={"title": f"missing {sorted(missing)}"})
        transfer = {
            "id": self._id("ach_transfer"),
            "type": "ach_transfer",
            "status": "pending_submission",
            "amount": body["amount"],
            "account_id": body["account_id"],
            "routing_number": body["routing_number"],
            "account_number": body["account_number"],
            "idempotency_key": key,
            "created_at": "2026-11-21T12:00:00Z",
            "submission": None,
            "settlement": None,
            "return": None,
        }
        self.transfers[transfer["id"]] = transfer
        if key:
            self.by_key[key] = transfer["id"]
        return httpx.Response(200, json=transfer)

    def _transfer(self, transfer_id: str) -> httpx.Response:
        if transfer_id not in self.transfers:
            return httpx.Response(404, json={"title": "no such transfer"})
        return httpx.Response(200, json=self.transfers[transfer_id])

    def _simulate(self, transfer_id: str, action: str, body: dict[str, Any]) -> httpx.Response:
        t = self.transfers.get(transfer_id)
        if t is None:
            return httpx.Response(404, json={"title": "no such transfer"})
        if action == "submit":
            if t["status"] != "pending_submission":
                return httpx.Response(400, json={"title": "not pending_submission"})
            t["status"] = "submitted"
            t["submission"] = {"submitted_at": "2026-11-21T12:01:00Z", "trace_number": "0001"}
        elif action == "settle":
            if t["status"] != "submitted":
                return httpx.Response(400, json={"title": "not submitted"})
            t["settlement"] = {"settled_at": "2026-11-21T12:02:00Z"}
            self.transactions.append(
                {
                    "id": self._id("transaction"),
                    "amount": -t["amount"],
                    "created_at": "2026-11-21T12:02:00Z",
                    "description": "ACH transfer",
                    "source": {
                        "category": "ach_transfer_intention",
                        "ach_transfer_intention": {"transfer_id": transfer_id},
                    },
                }
            )
        elif action == "return":
            if not t.get("settlement"):
                return httpx.Response(400, json={"title": "settle it first"})
            t["status"] = "returned"
            t["return"] = {"return_reason_code": body.get("reason", "no_account")}
            self.transactions.append(
                {
                    "id": self._id("transaction"),
                    "amount": t["amount"],
                    "created_at": "2026-11-21T12:03:00Z",
                    "description": "ACH return",
                    "source": {
                        "category": "ach_transfer_return",
                        "ach_transfer_return": {"transfer_id": transfer_id},
                    },
                }
            )
        else:
            return httpx.Response(404, json={"title": f"no simulation {action}"})
        return httpx.Response(200, json=t)
