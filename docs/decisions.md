# Decisions

One line each, newest at the bottom: date, lane, decision, and why if it is not obvious. Anything another lane would be surprised by goes here.

- Kickoff, lane 4: Python 3.11+ with Pydantic v2 for the contract, because the team knows Python. Only the UI in `web/` may use another language.
- Kickoff, lane 4: One installable package (`ap`), one `pyproject.toml`, plain `venv` and `pip`.
- Kickoff, lane 4: Models are frozen and reject unknown fields. Stages return copies.
- Kickoff, lane 4: Money is integer cents; dates are `datetime.date`; timestamps are timezone-aware UTC.
- Kickoff, lane 4: Stage functions are synchronous.
- Kickoff, lane 3: Payments default to the mock provider; the Increase sandbox is opt-in through `PAYMENT_PROVIDER=increase`.
- Kickoff, lane 2: 3-way match stays deterministic code; the model is used only to investigate and explain exceptions.
