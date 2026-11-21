"""ACH credits through the Increase SANDBOX, plus the sandbox simulations.

Request shapes come from https://increase.com/openapi.json and the guides at
https://increase.com/documentation/sending-ach-transfers and
https://increase.com/documentation/idempotency-keys. Nothing here is from memory.

- Auth: ``Authorization: Bearer <sandbox key>``. The base URL must be the
  sandbox host; anything else is refused before a request is built.
- ``POST /ach_transfers`` with an ``Idempotency-Key`` header. A replay with the
  same key returns the same transfer (``Idempotent-Replayed: true``), so a
  retry cannot pay twice.
- Settlement does not happen on its own in the sandbox: the simulation
  endpoints submit and settle a transfer. ``status`` stays ``submitted`` and
  settlement shows up in ``settlement.settled_at``.
- A return creates a second Transaction (``source.ach_transfer_return``) and
  moves the transfer to ``returned``.

Amount and payee always arrive as arguments taken from the invoice record and
the vendor master file. This module never reads bank details from anywhere else.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any, Literal, cast

import httpx

from ap.shared import BankTxn, Invoice, Payment, Vendor, now_utc

SANDBOX_HOST = "sandbox.increase.com"
PaymentStatus = Literal["pending", "submitted", "settled", "returned"]

# NACHA field limits (see the ACH transfer create parameters).
COMPANY_NAME = "MERIDIAN MFG"  # how the payee's bank statement names us, max 16 chars
INDIVIDUAL_NAME_MAX = 22
ENTRY_DESCRIPTION_MAX = 10


class SandboxRequired(RuntimeError):
    """The configured Increase base URL is not the sandbox."""


class IncreaseError(RuntimeError):
    """Increase answered with an error, or a transfer ended in a failed state."""


class IncreaseClient:
    def __init__(
        self,
        api_key: str,
        account_id: str,
        base_url: str = f"https://{SANDBOX_HOST}",
        transport: httpx.BaseTransport | None = None,
        timeout: float = 20.0,
    ) -> None:
        if httpx.URL(base_url).host != SANDBOX_HOST:
            raise SandboxRequired(f"INCREASE_BASE_URL must be https://{SANDBOX_HOST}")
        if not api_key:
            raise IncreaseError("INCREASE_API_KEY is not set")
        self.account_id = account_id
        self._http = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        self._idempotency_keys: dict[str, str | None] = {}

    @classmethod
    def from_env(cls, transport: httpx.BaseTransport | None = None) -> IncreaseClient:
        return cls(
            api_key=os.environ.get("INCREASE_API_KEY", ""),
            account_id=os.environ.get("INCREASE_ACCOUNT_ID", ""),
            base_url=os.environ.get("INCREASE_BASE_URL", f"https://{SANDBOX_HOST}"),
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    # -- low level -----------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = self._http.request(method, path, json=json, params=params, headers=headers)
        if response.status_code >= 400:
            raise IncreaseError(f"{method} {path} -> {response.status_code}: {response.text[:300]}")
        return cast(dict[str, Any], response.json())

    # -- transfers -----------------------------------------------------------

    def create_ach_credit(
        self,
        *,
        amount_cents: int,
        routing_number: str,
        account_number: str,
        payee_name: str,
        idempotency_key: str,
        entry_description: str,
    ) -> dict[str, Any]:
        """Send an ACH credit from our account. Positive amount = credit (we pay)."""
        if amount_cents <= 0:
            raise IncreaseError("an ACH credit needs a positive amount")
        if not self.account_id:
            raise IncreaseError("INCREASE_ACCOUNT_ID is not set")
        body = {
            "account_id": self.account_id,
            "amount": amount_cents,
            "routing_number": routing_number,
            "account_number": account_number,
            "funding": "checking",
            "destination_account_holder": "business",
            "standard_entry_class_code": "corporate_credit_or_debit",
            "company_name": COMPANY_NAME,
            "individual_name": payee_name[:INDIVIDUAL_NAME_MAX],
            "company_entry_description": entry_description[:ENTRY_DESCRIPTION_MAX],
            "require_approval": False,
        }
        return self._request(
            "POST", "/ach_transfers", json=body, headers={"Idempotency-Key": idempotency_key}
        )

    def get_transfer(self, transfer_id: str) -> dict[str, Any]:
        return self._request("GET", f"/ach_transfers/{transfer_id}")

    def simulate_submit(self, transfer_id: str) -> dict[str, Any]:
        return self._request("POST", f"/simulations/ach_transfers/{transfer_id}/submit")

    def simulate_settle(self, transfer_id: str) -> dict[str, Any]:
        return self._request("POST", f"/simulations/ach_transfers/{transfer_id}/settle")

    def simulate_return(self, transfer_id: str, reason: str = "account_closed") -> dict[str, Any]:
        return self._request(
            "POST", f"/simulations/ach_transfers/{transfer_id}/return", json={"reason": reason}
        )

    def settle_in_sandbox(self, transfer_id: str) -> dict[str, Any]:
        """Push a pending transfer through submission and settlement."""
        transfer = self.get_transfer(transfer_id)
        if transfer["status"] == "pending_submission":
            transfer = self.simulate_submit(transfer_id)
        if transfer["status"] == "submitted" and not transfer.get("settlement"):
            transfer = self.simulate_settle(transfer_id)
        return transfer

    # -- transactions --------------------------------------------------------

    def list_transactions(self) -> list[dict[str, Any]]:
        txns: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"account_id": self.account_id, "limit": 100}
            if cursor:
                params["cursor"] = cursor
            page = self._request("GET", "/transactions", params=params)
            txns.extend(page["data"])
            cursor = page.get("next_cursor")
            if not cursor:
                return txns

    def _idempotency_key_of(self, transfer_id: str) -> str | None:
        if transfer_id not in self._idempotency_keys:
            self._idempotency_keys[transfer_id] = self.get_transfer(transfer_id).get(
                "idempotency_key"
            )
        return self._idempotency_keys[transfer_id]

    def bank_txns(self) -> list[BankTxn]:
        """The account's transactions in the contract's statement shape.

        ``reference`` carries the originating transfer's idempotency key, which
        is how ``reconcile`` ties a statement line to a payment. A return shows
        up as a second, positive line with the same reference.
        """
        out: list[BankTxn] = []
        for txn in self.list_transactions():
            source = txn.get("source") or {}
            category = source.get("category")
            reference: str | None = None
            if category in ("ach_transfer_intention", "ach_transfer_return"):
                transfer_id = (source.get(category) or {}).get("transfer_id")
                if transfer_id:
                    reference = self._idempotency_key_of(transfer_id)
            out.append(
                BankTxn(
                    id=txn["id"],
                    posted_at=_date_of(txn["created_at"]),
                    amount_cents=int(txn["amount"]),
                    description=str(txn.get("description") or category or ""),
                    reference=reference,
                )
            )
        return out

    # -- sandbox bootstrap ---------------------------------------------------

    def setup_sandbox(self, funding_cents: int = 100_000_000) -> dict[str, str]:
        """Create an account, an account number and fund it with a simulated wire.

        Returns ids to put in .env. Only ever runs against the sandbox host.
        """
        programs = self._request("GET", "/programs")["data"]
        if not programs:
            raise IncreaseError("sandbox group has no program")
        entities = self._request("GET", "/entities")["data"]
        entity_id = entities[0]["id"] if entities else self._create_demo_entity()["id"]
        account = self._request(
            "POST",
            "/accounts",
            json={"name": "AP operating", "program_id": programs[0]["id"], "entity_id": entity_id},
            headers={"Idempotency-Key": "ap-setup-account"},
        )
        number = self._request(
            "POST",
            "/account_numbers",
            json={"account_id": account["id"], "name": "AP operating"},
            headers={"Idempotency-Key": "ap-setup-account-number"},
        )
        self._request(
            "POST",
            "/simulations/inbound_wire_transfers",
            json={
                "account_number_id": number["id"],
                "amount": funding_cents,
                "debtor_name": "Meridian treasury",
            },
        )
        self.account_id = account["id"]
        return {"INCREASE_ACCOUNT_ID": account["id"], "account_number_id": number["id"]}

    def _create_demo_entity(self) -> dict[str, Any]:
        """The buyer as a sandbox Entity. Every detail is fictional, like the seed data."""
        address = {
            "line1": "100 Meridian Way",
            "city": "Columbus",
            "state": "OH",
            "zip": "43215",
            "country": "US",
        }
        return self._request(
            "POST",
            "/entities",
            json={
                "structure": "corporation",
                "corporation": {
                    "name": "Meridian Manufacturing Co.",
                    "legal_identifier": {
                        "category": "us_employer_identification_number",
                        "value": "123456789",
                    },
                    "incorporation_state": "OH",
                    "address": address,
                    "beneficial_owners": [
                        {
                            "company_title": "CFO",
                            "prongs": ["control"],
                            "individual": {
                                "name": "Avery Demo",
                                "date_of_birth": "1980-01-01",
                                "address": address,
                                "identification": {
                                    "method": "social_security_number",
                                    "number": "078051120",
                                },
                            },
                        }
                    ],
                },
            },
            headers={"Idempotency-Key": "ap-setup-entity"},
        )


def payment_status(transfer: dict[str, Any]) -> PaymentStatus:
    """Map an Increase ACH transfer to the contract's payment status."""
    status = transfer["status"]
    if status == "returned":
        return "returned"
    if status == "submitted":
        return "settled" if transfer.get("settlement") else "submitted"
    if status in (
        "pending_submission",
        "pending_approval",
        "pending_reviewing",
        "pending_transfer_session_confirmation",
    ):
        return "pending"
    raise IncreaseError(f"transfer {transfer.get('id')} ended as {status}")


def pay_with_increase(
    invoice: Invoice,
    vendor: Vendor,
    idempotency_key: str,
    client: IncreaseClient | None = None,
) -> Payment:
    """Send ``invoice.total_cents`` to the vendor master file's bank details."""
    own = client is None
    client = client or IncreaseClient.from_env()
    try:
        transfer = client.create_ach_credit(
            amount_cents=invoice.total_cents,
            routing_number=vendor.bank.routing_number,
            account_number=vendor.bank.account_number,
            payee_name=vendor.name,
            idempotency_key=idempotency_key,
            entry_description=invoice.invoice_number,
        )
    finally:
        if own:
            client.close()
    if int(transfer["amount"]) != invoice.total_cents:
        raise IncreaseError("Increase echoed a different amount than requested")
    return Payment(
        provider="increase",
        transfer_id=transfer["id"],
        amount_cents=invoice.total_cents,
        idempotency_key=idempotency_key,
        status=payment_status(transfer),
        created_at=_parse_ts(transfer.get("created_at")),
    )


def _date_of(ts: str) -> date:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).date()


def _parse_ts(ts: str | None) -> datetime:
    if not ts:
        return now_utc()
    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else now_utc()
