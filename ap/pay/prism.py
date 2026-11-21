"""Prism (Block Convey) guardrails and audit tracing for the pay lane.

Prism is an observability and guardrails service for AI agents. Lane 3 uses two
of its endpoints, both documented at https://blockconvey.com/docs:

- ``POST /api/guardrails/evaluate``: before money moves, the free text that
  drives the decision (vendor name, line descriptions, approval reason) is
  checked against the project's rules: prompt injection, PII, custom regex.
  ``pay()`` enforces a block by refusing the payment.
- ``POST /api/traces``: every approve / pay / reconcile decision is recorded,
  grouped per invoice as a Prism session, so the audit trail shows up in the
  dashboard and alert rules can fire on refusals or returns.

Both calls fail open, as Prism documents: Prism being down never raises and
never blocks a payment on its own. The hard guardrails in ``pay()`` do not
depend on Prism. Traces never carry bank account or routing numbers.

Auth is the ``X-PRISMtrace-Key`` header, not a bearer token.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

log = logging.getLogger(__name__)

DEFAULT_HOST = "https://api.prism.blockconvey.com"
AGENT_ID = "ap-pay"
AGENT_NAME = "AP approve-and-pay"
# Prism requires a model name on every trace. These decisions are rule-based,
# so one constant keeps the Model Inventory to a single entry.
POLICY_MODEL = "ap-pay-policy"
TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class PrismConfig:
    host: str
    project_id: str
    api_key: str

    @classmethod
    def from_env(cls) -> PrismConfig | None:
        """None when Prism is not configured; callers then skip it entirely."""
        api_key = os.environ.get("PRISMTRACE_API_KEY")
        project_id = os.environ.get("PRISMTRACE_PROJECT_ID")
        if not api_key or not project_id:
            return None
        host = os.environ.get("PRISMTRACE_HOST") or DEFAULT_HOST
        return cls(host=host.rstrip("/"), project_id=project_id, api_key=api_key)


@dataclass(frozen=True)
class Verdict:
    """Answer from ``/api/guardrails/evaluate``.

    ``evaluated`` False means no rule ran (plan not entitled, no text, Prism
    unreachable); ``reason`` says why. Only ``blocked`` True stops a payment.
    """

    blocked: bool
    evaluated: bool
    reason: str | None = None
    rule_name: str | None = None
    rule_type: str | None = None
    matched_text: str | None = None
    fallback_message: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def skipped(cls, reason: str) -> Verdict:
        return cls(blocked=False, evaluated=False, reason=reason)


Message = dict[str, str]


class PrismClient:
    def __init__(
        self,
        config: PrismConfig,
        transport: httpx.BaseTransport | None = None,
        timeout: float = TIMEOUT_SECONDS,
    ) -> None:
        self.config = config
        self._http = httpx.Client(
            base_url=config.host,
            timeout=timeout,
            transport=transport,
            headers={"X-PRISMtrace-Key": config.api_key, "Content-Type": "application/json"},
        )

    def close(self) -> None:
        self._http.close()

    def evaluate(
        self,
        trace_id: str,
        messages: list[Message],
        agent_id: str = AGENT_ID,
        direction: str = "input",
    ) -> Verdict:
        """Ask Prism whether the last user message trips a block rule. Fails open."""
        body = {
            "project_id": self.config.project_id,
            "trace_id": trace_id,
            "agent_id": agent_id,
            "direction": direction,
            "messages": messages,
        }
        try:
            response = self._http.post("/api/guardrails/evaluate", json=body)
        except httpx.HTTPError as exc:
            log.warning("prism evaluate unreachable: %s", exc)
            return Verdict.skipped("unreachable")
        if response.status_code != 200:
            log.warning("prism evaluate HTTP %s: %s", response.status_code, response.text[:200])
            return Verdict.skipped(f"http_{response.status_code}")
        try:
            data = response.json()
        except ValueError:
            log.warning("prism evaluate returned non-JSON: %s", response.text[:100])
            return Verdict.skipped("malformed_response")
        if not isinstance(data, dict) or "blocked" not in data:
            return Verdict.skipped("malformed_response")
        return Verdict(
            blocked=bool(data.get("blocked")),
            evaluated=bool(data.get("evaluated")),
            reason=data.get("reason"),
            rule_name=data.get("rule_name"),
            rule_type=data.get("rule_type"),
            matched_text=data.get("matched_text"),
            fallback_message=data.get("fallback_message"),
            raw=data,
        )

    def trace(
        self,
        trace_id: str,
        session_id: str,
        input_messages: list[Message],
        output_message: str,
        latency_ms: int,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Record one decision. Returns True when Prism stored it. Never raises."""
        body = {
            "project_id": self.config.project_id,
            "trace_id": trace_id,
            "session_id": session_id,
            "agent_id": AGENT_ID,
            "agent_name": AGENT_NAME,
            "model": POLICY_MODEL,
            "input_messages": input_messages,
            "output_message": output_message,
            "latency_ms": max(0, int(latency_ms)),
            "metadata": metadata or {},
        }
        try:
            response = self._http.post("/api/traces", json=body)
        except httpx.HTTPError as exc:
            log.warning("prism trace unreachable: %s", exc)
            return False
        if response.status_code != 200:
            log.warning("prism trace HTTP %s: %s", response.status_code, response.text[:200])
            return False
        return True


_override: PrismClient | None = None
_override_set = False
_cached: tuple[PrismConfig, PrismClient] | None = None


def configure_prism(client: PrismClient | None) -> None:
    """Pin the client the stages use (tests). ``reset_prism()`` goes back to env."""
    global _override, _override_set
    _override = client
    _override_set = True


def reset_prism() -> None:
    global _override, _override_set
    _override = None
    _override_set = False


def prism_client() -> PrismClient | None:
    """The client the stages should use right now, or None when Prism is off.

    One client (one connection pool) is kept per configuration, so the evaluate
    and trace calls of a payment reuse a connection and nothing leaks per call.
    """
    global _cached
    if _override_set:
        return _override
    config = PrismConfig.from_env()
    if config is None:
        return None
    if _cached is None or _cached[0] != config:
        if _cached is not None:
            _cached[1].close()
        _cached = (config, PrismClient(config))
    return _cached[1]


class Stopwatch:
    def __init__(self) -> None:
        self._start = time.monotonic()

    @property
    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self._start) * 1000)
