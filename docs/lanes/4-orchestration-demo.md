# Lane 4: Orchestration and demo

**Owner:** _name_

## Mission

Make four people's work run as one product, and make it easy to understand in three minutes. You own `main`, the contract and what the judges see.

## You own

`ap/shared/`, `ap/orchestrator/`, `web/`, `scripts/`, `data/`, `docs/`, `tests/test_contract.py` and the root config.

## Three jobs

### 1. Integrator

- Keep `python scripts/check.py` green on `main`. When it goes red, fixing it is everyone's first priority and you coordinate.
- Review and merge PRs quickly. Small and often beats large and late.
- Own contract changes: make them in a `contract:` PR with nothing else in it, announce them, and make sure everyone rebases.
- Own `scripts/seed.py`. When another lane needs a new scenario or a changed expectation, you add it.
- Watch `pyproject.toml`: it is the one file every lane may touch, so resolve dependency conflicts as they appear.
- Turn on branch protection for `main`: require a PR and the `check` workflow.

### 2. Orchestrator and UI

`ap/orchestrator/run.py` already runs every invoice through every stage from the command line. Build the product around it:

1. **A small API** in `ap/orchestrator/` with FastAPI. Hold invoices in memory (or SQLite) and expose: list invoices, get one invoice with its history, start processing an inbox file, and approve or reject a pending invoice. Return `invoice.model_dump(mode="json")`; the Pydantic models give you the response schema for free.
2. **Run stages as steps, not one blocking call**, so the UI can show an invoice moving. Run the pipeline in a background task, store the invoice after each stage, and let the UI poll or subscribe to server-sent events.
3. **A UI in `web/`.** Pick one at kickoff:
   - **React (or any JavaScript front end) against the API.** More work, and a much better moving board. Choose this if you are comfortable with it.
   - **Streamlit.** All Python and quick to build, but plainer and weaker at live updates. Choose this if nobody wants to write JavaScript.

   Either way, three views:
   - **Pipeline board:** one column per status, invoices as cards that move as stages finish.
   - **Invoice detail:** the PDF beside the extracted fields, the match result line by line (PO, receipt and invoice values side by side), the agent's rationale, and the `history` as a timeline.
   - **Approval queue:** pending invoices with approve and reject buttons that end up calling `approve(invoice, ctx, human)`.
4. **Show the guardrails.** A visible "sandbox" badge, the payment's idempotency key, and the limit that triggered a human approval. Judges ask about safety; put the answers on screen.

### 3. Demo and pitch

- Write and rehearse the script in [docs/demo-script.md](../demo-script.md).
- Record a backup video of the full run once it works, in case the sandbox or the network fails live.
- Build the pitch: the problem, the live demo, what is real against what is mocked, and what comes next.

## Done when

- One command starts the API and the UI.
- Demo invoices A, B and C run from the UI with no terminal visible.
- Every status change on screen comes from `history`, not from UI-side guesses.
- The backup video exists.

## Stretch

- A reset button that reloads the seed data between demo runs.
- Upload a new PDF from the UI.
- A metrics strip: touchless rate, average time from capture to paid, exceptions by code.

## Kickoff prompt

Paste this into your coding agent:

```
You are working in lane 4 (Orchestration and demo) of a 4-person hackathon repo. The project is Python.

First read AGENTS.md, docs/contract.md and docs/lanes/4-orchestration-demo.md.
Then set up the virtual environment, run `pip install -e ".[dev]"` and
`python scripts/check.py`, and confirm the check passes.

Your task: build a FastAPI service around the pipeline in ap/orchestrator and
a UI in web/ with a pipeline board, an invoice detail view and an approval
queue, following the lane brief. Ask me whether the UI is React or Streamlit
before you start on it.

Rules that matter most:
- You own ap/shared/, ap/orchestrator/, web/, scripts/, data/ and docs/. Do not
  edit ap/intake/, ap/match/ or ap/pay/; call their public functions.
- Contract changes go in their own PR titled "contract: ..." with nothing else in it.
- Never hand-edit data/. Change scripts/seed.py and run it.
- The UI shows status from the invoice's history; it never invents state.
- Keep `python scripts/check.py` green on main at all times.
- Run `python scripts/check.py` before every commit. Work on a branch named lane4/<topic>.

Start by showing me your plan in five lines or fewer, then build it.
```
