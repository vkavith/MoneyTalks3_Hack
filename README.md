# AP agent: invoice to payment

An agent that takes a vendor invoice from PDF to paid: capture, 3-way match, exception handling, approval, sandbox payment and reconciliation. Python 3.11+ and Pydantic.

## Start here

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
python scripts/check.py          # lint, types, data check, tests, end-to-end pipeline
```

The check passes on day zero because every stage has a stub or a baseline. Your job is to replace your stage with the real thing without breaking it.

```bash
python -m ap.orchestrator.run                      # run all 8 seed invoices end to end
python -m ap.orchestrator.run --approve INV-0003   # same, with a human approving the $48,000 invoice
python -m pytest                                   # tests only
python -m ruff format .                            # format before committing
python scripts/seed.py                             # regenerate data/ (lane 4 only)
```

## API keys

Keys never go in the repo (see [AGENTS.md](AGENTS.md)). Every key the project uses is named in `.env.example`; the values live in each person's git-ignored `.env`.

The agents call LLMs through [Nicrron](https://nicrron.ai), an OpenAI-compatible gateway: point the OpenAI SDK at `NICRRON_BASE_URL` with `NICRRON_API_KEY` and use provider-prefixed model names such as `anthropic/claude-sonnet-5-5`. Dylan holds the shared Nicrron and Prism keys; ask in the team chat and paste them into your `.env`. Both keys are revoked after the event.

## Who does what

| Lane | Owner | Builds | Brief |
|---|---|---|---|
| 1 Intake | _name_ | Invoice PDF to a structured `Invoice` | [docs/lanes/1-intake.md](docs/lanes/1-intake.md) |
| 2 Match & exceptions | _name_ | 3-way match and the agent that resolves mismatches | [docs/lanes/2-match.md](docs/lanes/2-match.md) |
| 3 Approve & pay | _name_ | Approval rules, sandbox payment, reconciliation | [docs/lanes/3-pay.md](docs/lanes/3-pay.md) |
| 4 Orchestration & demo | _name_ | API, UI, audit trail, pitch; owns `main` and the contract | [docs/lanes/4-orchestration-demo.md](docs/lanes/4-orchestration-demo.md) |

Each brief ends with a kickoff prompt to paste into your coding agent.

## How we stay in sync

- **[AGENTS.md](AGENTS.md)** is the shared prompt. Every coding agent reads it first. `CLAUDE.md` points to it.
- **[docs/contract.md](docs/contract.md)** describes the one `Invoice` record, its statuses and the stage functions. The code is in `ap/shared/`.
- **`data/`** is the shared data source, described in [data/README.md](data/README.md).
- **`python scripts/check.py`** runs in CI on every PR. If it is red, fixing it comes before anything else.

## Layout

```
ap/shared/         the contract: models, transitions, stage signatures   (lane 4)
ap/intake/         capture()                                             (lane 1)
ap/match/          match(), resolve_exception()                          (lane 2)
ap/pay/            approve(), pay(), reconcile()                         (lane 3)
ap/orchestrator/   runs the stages in order                              (lane 4)
web/               demo UI, to be created                                (lane 4)
tests/             test_contract.py, plus one folder per lane
data/              seed data and ground truth, generated
scripts/           check.py, seed.py, check_data.py
docs/              contract, lane briefs, schedule, demo script, checklist
```

## Schedule

See [docs/schedule.md](docs/schedule.md). It assumes a 24-hour event; scale the checkpoints if yours is different.
