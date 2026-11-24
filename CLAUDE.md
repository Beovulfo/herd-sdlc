# herd-sdlc

Herd is a Claude Code plugin: an evidence-based autopilot for building software. Humans give a goal
and success criteria, each with an executable check; agents deliver code and attach evidence; humans
review the evidence. Requirements: [`docs/PRD.md`](docs/PRD.md). Changes: [`CHANGELOG.md`](CHANGELOG.md).

## Layout
- `.claude-plugin/marketplace.json`: the marketplace, with the plugin's `source` set to `./plugin`. Everything an install ships is under `plugin/` (so `examples/` and `tests/` are never copied): `plugin/.claude-plugin/plugin.json`: the manifest. `plugin/hooks/hooks.json`: the Stop gate, the pre-init hook (`herd preinit`, before `herd init`), the guard (`herd guard`, PreToolUse), the review hook (`herd review-hook`, SubagentStop) and the lint hook. `plugin/agents/herd-reviewer.md`: the reviewer subagent. `plugin/skills/{run,criteria,evidence}/SKILL.md`: the skills; `plugin/skills/run/*.md` are reference files the run skill must read in full when their step applies; `herd done` enforces the adversarial one.
- `plugin/scripts/herd.py`: the CLI (init, check, detect, verify, status, done, cancel, pr, gate, preinit, guard, review-hook, review-brief, lint, triage, note, review). It uses `herd_detect.py` and `herd_triage.py`.
- `plugin/scripts/herd_arbiter.py`, `plugin/scripts/herd_escalation.py`: tested building blocks for the planned GitHub automation, not wired into the CLI yet.
- `tests/`: one `test_*.py` per module.
- `docs/designs/`: specs, written with the Elephant-Goldfish Model (Herd dogfoods its own method). `docs/spikes/`: experiments. `docs/backlog.md`: deferred ideas.
- `examples/supermarket-route/`: the benchmark, with and without Herd.

## Checks
- Tests: `python3 -m unittest discover -s tests -t .` (CI runs Python 3.11, 3.12 and 3.13).
- Lint: `ruff check .`
- Plugin: `claude plugin validate ./plugin` and, for the marketplace, `claude plugin validate .`

## Rules
- Python standard library only, Python 3.11 or newer. No new dependencies without a reason.
- GitHub (`gh`) is the only external service Herd talks to.
- Bump `version` in `plugin/.claude-plugin/plugin.json` and add a `CHANGELOG.md` entry whenever plugin files change: `claude plugin update` compares version numbers only, so installed copies stay stale otherwise.
- Keep the README, the skills and these docs in sync when behaviour changes.
- A success criterion without a runnable check is incomplete. "Done" means evidence exists (command output, commit SHA, timestamp), not that an agent says so. Run the check and show the output before claiming completion.
- Keep it minimal: no speculative abstractions.
- No credentials or private data in any file, commit or example. Use generic fixtures.

## Writing
- Plain, concise English. No emojis or em-dashes.
- Do not guess APIs, versions, flags, commit SHAs or package names: verify them in code or docs first.
