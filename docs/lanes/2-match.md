# Lane 2: Match and exceptions

**Owner:** _name_

This lane is the heart of the demo. Matching is rules; the agent that handles what the rules reject is the part judges have not seen.

## Mission

Decide whether an invoice agrees with its purchase order and goods receipt, and when it does not, have an agent work out why and what to do about it.

## You own

`ap/match/` and `tests/match/`. Your public functions are `match(invoice, ctx)` and `resolve_exception(invoice, ctx)`.

## Inputs and outputs

- **`match` in:** a `captured` invoice and the `PipelineContext`.
- **`match` out:** `matched`, or `exception` with one entry in `match.exceptions` per problem.
- **`resolve_exception` in:** an `exception` invoice.
- **`resolve_exception` out:** `matched` with `match.resolution.action == "auto_resolved"`, or still `exception` with `"escalated"`. Either way `match.resolution.rationale` explains the decision in plain language.
- **Ground truth:** `data/expected/outcomes.json`, loaded with `load_expected_outcomes`.

## What you start with

`match` already works as a deterministic baseline and passes all eight seed invoices. `resolve_exception` is a stub that escalates everything. Spend your time on the agent.

## How to build it

1. **Keep the rules deterministic.** The match itself should stay plain Python: it is auditable and it never hallucinates. Extend it only where a rule is missing.
2. **Give the agent tools, not free rein.** Suggested tools, each a small Python function over `ctx`: look up the PO, look up receipts for a PO line, look up the vendor's past invoices, read the policy, and draft a message to the vendor or buyer. The agent reads; it does not edit POs, receipts or vendor records.
3. **Define what it may auto-resolve.** Write the allowed cases down as code, not just as prompt text. A reasonable starting set:

   | Code | Agent may | Otherwise |
   |---|---|---|
   | `PRICE_VARIANCE` | Explain the gap in dollars and draft a query to the buyer | Escalate |
   | `QTY_OVER_RECEIPT` | Recommend paying for the received quantity and draft a short-pay notice | Escalate |
   | `DUPLICATE_INVOICE` | Confirm it is a true duplicate and recommend rejection | Escalate |
   | `MISSING_PO` | Search open POs for the vendor and propose the likely one | Escalate |
   | `UNKNOWN_VENDOR` | Never resolve. Flag the look-alike and the changed bank details as possible fraud | Always escalate |
   | `TOTAL_MISMATCH` | Show the arithmetic | Escalate |

   Anything that would change the amount paid needs a person. Agree with lane 3 how a person's decision on an exception comes back in.
4. **Write the rationale for a finance person.** One or two sentences with the numbers: what was expected, what was billed, what the agent recommends.
5. **Return structured output.** Define a Pydantic model for the agent's decision and validate the reply with it before it touches the invoice. On an invalid reply, escalate.
6. **Test.** In `tests/match/`, assert codes against `outcomes.json`. For the agent, assert the action (resolved or escalated) per scenario, not the exact wording. Skip model-calling tests when no API key is set.

## Done when

- INV-0002 (price variance) produces a clear rationale and a drafted query: this is demo invoice B.
- INV-0008 is always escalated with a fraud warning, however the prompt is worded.
- The stub rationale is gone, and `python scripts/check.py` is green with updated expectations.

## Stretch

- Short-pay: resolve INV-0004 by approving payment for 80 units. This needs a contract change (an approved amount different from the invoice total), so raise it with lane 4 early.
- Learn from past decisions: have the agent cite how a similar exception was resolved before.
- Email the drafted vendor query for real, to a test inbox.

## Kickoff prompt

Paste this into your coding agent:

```
You are working in lane 2 (Match and exceptions) of a 4-person hackathon repo. The project is Python.

First read AGENTS.md, docs/contract.md and docs/lanes/2-match.md. Then set up
the virtual environment, run `pip install -e ".[dev]"` and `python scripts/check.py`,
and confirm the check passes.

Your task: replace the resolve_exception stub in ap/match/__init__.py with an
agent that investigates each exception using read-only tools and either
resolves it or escalates it with a plain-language rationale, following the
lane brief. Leave the deterministic match() rules as code.

Rules that matter most:
- Edit only ap/match/ and tests/match/. If you need anything changed elsewhere, stop and tell me.
- Import all models from ap.shared. Keep both function signatures unchanged.
- Change status only through transition().
- What the agent may auto-resolve is enforced in code, not only in the prompt.
- UNKNOWN_VENDOR is never auto-resolved.
- Validate every model reply with a Pydantic model; on an invalid reply, escalate.
- Read the model provider's current docs before writing tool-use code.
- Run `python scripts/check.py` before every commit. Work on a branch named lane2/<topic>.

Start by showing me your plan in five lines or fewer, then build it.
```
