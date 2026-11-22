# herd-sdlc

Public, personal open-source project: an evidence-based autopilot SDLC plugin ("Herd") built on the
Elephant-Goldfish Model (EGM, `egm@egm`). Humans supply goals and success criteria (each with an
executable check); agents deliver and attach evidence; humans review evidence.

Source of truth: `PRD — Autopilot SDLC plugin built on the Elephant-Goldfish Model.md`.

## Layout
- `.claude-plugin/` manifest and marketplace; `hooks/hooks.json` Stop gate and lint hook; `skills/{run,criteria,evidence}/SKILL.md`.
- `scripts/herd.py` is the CLI (init, check, detect, verify, status, done, gate, lint, triage, note); `herd_detect.py`, `herd_triage.py`, `herd_arbiter.py`, `herd_escalation.py` are stdlib-only modules, each with `test_*.py`.
- Tests: `python3 -m unittest scripts.test_herd_cli scripts.test_herd_lint scripts.test_herd_detect scripts.test_herd_triage scripts.test_herd_arbiter scripts.test_herd_escalation`; plugin check: `claude plugin validate ./`.
- Bump `version` in `.claude-plugin/plugin.json` whenever plugin files change: `claude plugin update` compares version numbers only, so installed copies stay stale otherwise, and restart the session after updating.
- Specs in `docs/designs/`, EGM run logs in `docs/spikes/`, deferred ideas in `docs/backlog.md`. Keep README, skills and these docs in sync when behaviour changes.

## Rules
- Personal project, public repo: no employer names, internal URLs, credentials, or company data in
  any file, commit, or example. Use generic fixtures.
- Do not use Databricks, Azure, Jira, or any cloud tooling. GitHub (`gh`) is the only external service.
- Use EGM for design work: `/egm-brainstorm` → `/egm-draft` → `/egm-review` → `/egm-resolve`.
  Herd's own specs go in `docs/designs/<feature>.md` (dogfooding).
- A success criterion without a runnable check is incomplete. "Done" means evidence exists
  (command output, commit SHA, timestamp), not that an agent says so.
- Verify before claiming completion: run the check, show the output.
- Keep it minimal: no speculative abstractions, no new dependencies without a reason.
- Commit only when asked.

## Token efficiency (from drona23/claude-token-efficient)
- Read existing files before writing. Don't re-read unless changed.
- Thorough in reasoning, concise in output.
- Skip files over 100KB unless required.
- No sycophantic openers or closing fluff.
- No emojis or em-dashes.
- Do not guess APIs, versions, flags, commit SHAs, or package names. Verify by reading code or docs before asserting.
