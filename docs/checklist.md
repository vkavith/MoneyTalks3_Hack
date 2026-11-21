# What else we need

Things that are not code in this repo. Tick them off at kickoff.

## Decide

- [ ] Who owns each lane. Write the names into `README.md` and the lane briefs.
- [ ] Which coding agent and model each person uses, and who pays for the usage.
- [ ] One chat channel for the team, with a rule: contract changes and a red `main` get announced there.
- [ ] Where the demo runs: a laptop, or a deployed URL. If deployed, who owns the deploy.
- [ ] Who presents and who drives.

## Set up

- [ ] All four people have write access to the GitHub repo.
- [ ] Branch protection on `main`: pull request required, `check` workflow required, no force-push.
- [ ] Sandbox payment account created; key and account ID shared through a password manager or the chat's private message, never in the repo.
- [ ] A model API key per person, or one shared key with a spending cap.
- [ ] Everyone has run `npm run check` on their own machine before the event starts.
- [ ] Node 22 on every machine.

## Read before you build

- [ ] The hackathon's rules: who owns what you build, whether code must be open-sourced, whether pre-written code is allowed, and what must be disclosed. This starter kit is pre-written code, so check that it is allowed or declare it.
- [ ] The judging criteria. Put the top two in front of the lane 4 owner.
- [ ] The terms of the sandbox and model providers you use.

## Agree in writing

- [ ] Who owns the result and what happens if some of you keep working on it afterwards. A short message that all four reply "agreed" to is enough for now.
- [ ] Whether anyone's employer could have a claim on their contribution.

## Have ready for the demo

- [ ] The script in `docs/demo-script.md`, rehearsed three times.
- [ ] A backup video of a clean run.
- [ ] A slide or two: the problem, what is real against mocked, what comes next.
- [ ] A reset command so the demo starts from the same state every time.
- [ ] A plan for no network: mock provider and local model fallback, or the video.

## Keep an eye on

- [ ] Model spend, if keys are shared.
- [ ] Sandbox rate limits during rehearsal.
- [ ] The time. Feature freeze is not optional.
