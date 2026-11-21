# Decisions

One line each, newest at the bottom: date, lane, decision, and why if it is not obvious. Anything another lane would be surprised by goes here.

- Kickoff, lane 4: TypeScript everywhere, npm workspaces, zod for the contract.
- Kickoff, lane 4: Money is integer cents; dates are `YYYY-MM-DD`.
- Kickoff, lane 3: Payments default to the mock provider; the Increase sandbox is opt-in through `PAYMENT_PROVIDER=increase`.
- Kickoff, lane 2: 3-way match stays deterministic code; the model is used only to investigate and explain exceptions.
