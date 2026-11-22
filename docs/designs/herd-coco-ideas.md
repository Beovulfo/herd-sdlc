# Herd v0.2: lean routing, evidence guidance and a lint hook

* **Author:** Toni
* **Status:** Built (steps A to G), revised after EGM review round 1. Not re-reviewed after the rewrite.
* **Date:** 2026-11-22

## Overview

Herd (see `README.md`) runs a task as a goal plus success criteria, each with a runnable `check`. `herd verify` stores evidence, and a Stop hook blocks finishing without fresh passing evidence. `herd triage` gives a risk floor from `herd.toml` path rules (PRD section 5).

v0.2 adds four small things, three of them ideas from the [Coco workflow plugin](https://github.com/skullninja/coco-workflow) and one from research on adapting verification to the project type: lean routing for trivial changes, a test-budget note, a post-edit lint hook, and an evidence-planning skill. All keep the core rule: a task is done only when fresh runnable checks pass.

## Problem

1. Trivial changes (a typo, a one-line fix) pay the full criteria ceremony.
2. Reviewers cannot tell which behaviours were meant to be tested and which were deliberately skipped.
3. Lint and type errors surface only at the end, after many edits.
4. Humans do not know what good evidence looks like for their kind of project, and agents guess test commands that may run zero tests and still exit 0.

## Goals

* G1: A trivial task needs one criterion and one check, and still ends in fresh passing evidence.
* G2: A task can state what is tested and what is not, and the report shows it.
* G3: With an opt-in config, an edit that breaks lint produces feedback to the agent immediately.
* G4: A human can run one skill to choose evidence for their project type, with detected commands proposed and confirmed.
* G5: The report shows whether each check failed before the work started, so a check that was green from the start is visible.

## Non-Goals

* Per-criterion `level`, `kind` (`proxy`, `attested`), per-type guidance files, mutation testing and flaky-check reruns. They are deferred; see Alternatives.
* Zero-test detection and any check-content analysis beyond an advisory denylist.
* Project-wide `typecheck` at verify time.
* Detection of more than Python, Node, Rust and Go (plus a `Makefile` test target).
* Changes to the Stop gate or the evidence freshness rule.

## Alternatives Considered

* **Adopt Coco as is.** Rejected by author: it is a full pipeline (PRD to merged PR, 14 commands, its own tracker). Herd stays a small harness that reuses Superpowers and EGM.
* **Lint and tests as criteria only.** A criterion `ruff check .` already works today. Kept as the fallback, but it runs only at verify time, so errors surface late; the hook gives feedback per edit.
* **A pre-commit hook for lint.** Rejected by author: it needs a git commit, which Herd does not require during a task.
* **Lint at `herd verify` instead of a hook.** Rejected for now: the feedback loop is the point of the idea. Revisit if the hook proves noisy.
* **Static guidance in the skill instead of `herd detect`.** Rejected by author: detected commands can be confirmed or corrected by the human in the repository's own terms, and the lint config reuses them.
* **Per-criterion `level` and `kind`.** Deferred: nothing consumes `level` yet, and `attested` and `proxy` evidence weaken the guarantee unless the gate understands them (an agent-writable file would count as passing).

## Design

### Step A: `scripts/herd_detect.py`

`detect(root) -> list[dict]`, each `{type, markers, test, lint}`, proposals only (nothing runs). Rows:

| Marker | Type | test | lint |
| --- | --- | --- | --- |
| `pyproject.toml`, `setup.cfg` or `requirements.txt` | python | `pytest` | `ruff check .` |
| `package.json` | node | `npm test` (only when the `test` script exists and is not the npm-init stub) | `npm run lint` when a `lint` script exists, else `npx eslint .` |
| `Cargo.toml` | rust | `cargo test` | `cargo clippy -- -D warnings` |
| `go.mod` | go | `go test ./...` | `go vet ./...` |
| `Makefile` with a `test:` target | make | `make test` | none |

The conventions are from general knowledge, not docs; the human confirms them in the skill. Other ecosystems return an empty list. Wrapped by `herd detect` (prints JSON). Check: `python3 -m unittest tests.test_herd_detect`, one fixture directory per row plus the npm-init stub and an empty directory.

### Step B: check hygiene (advisory)

`herd check` prints warnings, still exit 0, for a `check` that is only `true`, `:`, `exit 0`, `echo ...`, `test -f` or `test -e`. It is a denylist: it will miss `python3 -c pass` and may flag a legitimate `grep -q`. A warning never blocks. Warnings are a separate list returned by `validate_task`, printed after `ok`. Check: `python3 -m unittest tests.test_herd_cli -k hygiene`.

### Step C: quick route

* `herd init <slug> "<goal>" --quick "<check>"` runs triage on the goal text (with `herd.toml` if present) and refuses if the floor is `high` or the check is empty. It writes one criterion `C1`, `text` = the goal, `source = "agent-proposed"`, and `route = "quick"` at the top of `task.toml`.
* `validate_task`: `route` must be `quick` or `standard` (default `standard`); `quick` needs exactly one criterion with a non-empty check.
* **What quick skips:** the criteria interview, the approval question and the fresh-context review. **What it keeps:** red first (reported, see Step D), `verify`, the Stop gate and the evidence report.
* Triage is advisory: a goal that names no path floors at `medium`, so a risky change can be described to dodge a `high` floor. The human sees `route = "quick"` in the report. Quick is meant for one-file changes the agent states as such.
* `skills/run`: step 1 chooses the route.
Check: `python3 -m unittest tests.test_herd_cli -k quick`.

### Step D: test-budget note and red report

* `task.toml` gains optional `test_budget`, a free-text string: what is tested at which level and what is deliberately not tested. `report` prints it. No warning, no enforcement.
* `herd verify` writes `red.json` once, on the first verify for a task: each criterion's status. `report` adds a line: `first verify: N of M checks failed before the work`. No gate rule and no waiver: a check green from the start is visible, and the human judges it. This is a visibility aid, not a guard.
* `skills/criteria` gets a short "test budget" section; `skills/run` review step compares the diff to the budget in both directions (missing coverage and low-value extra tests).
Check: `python3 -m unittest tests.test_herd_cli -k budget` and `-k red`.

### Step E: lint hook

* Opt-in in the project's `herd.toml`: `[lint]` with `command` (for example `ruff check {file}`), optional `globs` (default `["**/*"]`) and `timeout_s` (default 20). `herd lint --suggest` prints a block from `herd detect` for the human to paste.
* `herd lint` is a PostToolUse command hook. It reads the payload, takes `tool_input.file_path` and `cwd`, and does nothing unless a Herd task is active in `cwd`, `[lint]` is configured and the path matches the globs. It runs the command through the existing `run_check` with the path shell-quoted. On a non-zero exit it prints `{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "<output tail, 2000 chars>"}}`, which adds context without blocking, so there is no loop and no circuit breaker is needed. Exit 0 and no output otherwise. This output shape is from the Claude Code hooks docs (https://code.claude.com/docs/en/hooks); the test checks that exact shape.
* `hooks/hooks.json` adds `PostToolUse` with matcher `Edit|Write` and `timeout` 30 (above the 20 second default). Other editing tools (`MultiEdit`, `NotebookEdit`) are not matched, and the README says so.
* **Trust:** the command comes from `herd.toml` in the repository and runs with the user's permissions, the same trust as a `check` in `task.toml`. `herd.toml` is on the triage high-floor list, so editing it is already a high-risk change. `herd_triage` ignores other top-level tables, so `[lint]` does not break triage (covered by `test_other_top_level_keys_ignored`).
Check: `python3 -m unittest tests.test_herd_lint`: no config, no active task, glob miss, failing lint, passing lint, timeout, a path with spaces and shell characters, and the exact JSON shape.

### Step F: `/herd:evidence` skill

A human-invoked, interactive skill (not part of `/herd:run`, which asks nothing). Named `evidence` so it does not collide with the `herd verify` command. A single `SKILL.md`, under 120 lines:
1. Run `herd detect` and show the proposals. The human confirms or corrects them.
2. Ask only the unanswered questions, at most 5: what working looks like from outside; what the agent can run; what it cannot run (credentials, hardware, a human eye); what must not change; how slow a check may be.
3. Draft criteria with a `check` each. A criterion that cannot be automated stays `unchecked` and visible; the draft may label a proxy check in its `text` (for example "proxy: screenshot diff").
4. Show the advisory hygiene warnings (Step B) and ask for a check that runs project code.
5. Run `herd verify` and show the evidence for the human to review.
`skills/run` points to detected defaults. Per-type reference files are deferred.
Check: `python3 -m unittest tests.test_herd_cli -k detect_cli`, plus an agent trial on a scratch repo (manual).

### Step G: docs

README commands table and skill pointers; one line on the unmatched tools; a note that `herd.toml` commands are trusted.

## Order

A, B, C, D, E, F, G. B before C, because C reuses its empty-check rule. Each step is test first. Finish with a scratch-repo run of a quick task and a lint failure, an agent trial on a trivial task, and CI.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| An agent picks `quick` to skip criteria | Refuses at a `high` floor; the route is shown in the report; the Stop gate still applies |
| Wrong detected command or a check that runs no tests | The human confirms commands; hygiene warnings; `red.json` shows a check that never failed |
| Lint hook latency or noise | Opt-in, 20 second timeout, active task only, non-blocking output |
| Shell commands from `herd.toml` | Same trust as `task.toml`; documented; `herd.toml` edits are high floor |
| Hygiene denylist is incomplete | Advisory only, documented limits |
| Scope growth | Non-Goals list; each step small and test first |

## Context and sources

* Existing system: `scripts/herd.py`, `skills/run/SKILL.md`, `skills/criteria/SKILL.md`, `hooks/hooks.json`, `herd.toml`, and the PRD (section 5 for triage and the risk floor).
* Verified in docs: Claude Code best practices (https://code.claude.com/docs/en/best-practices): give the agent a pass/fail check and ask for evidence. Hooks (https://code.claude.com/docs/en/hooks): PostToolUse payload has `tool_input.file_path` and `cwd`; JSON output supports `additionalContext`; the `Edit|Write` matcher matches those tool names. Skills (https://code.claude.com/docs/en/skills): reference files load on demand.
* Inferred, not checked: the per-ecosystem commands in Step A.
* The research report behind this plan was produced in the working session and is summarised here; it is not stored in the repository.
