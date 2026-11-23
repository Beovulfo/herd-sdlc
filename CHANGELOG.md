# Changelog

All notable changes to Herd. Versions follow `.claude-plugin/plugin.json`.

## 0.2.8

- **Added:** `herd pr [slug] [--yes]`, an opt-in pull request step. It runs only with `[pr] open = true` in `herd.toml` or `--yes` (which the run skill passes when the request asks for a PR). It pushes the task's `herd/<slug>` branch, refuses any other branch, and opens a pull request, or updates the one that exists. The description is the evidence, first: the result and freshness, a table of what is proven and the check that proved each item, what is not proven (failing and unchecked criteria, zero-test runs, coverage gaps, known limits, open caveats), run details, and the check commands to reproduce. It refuses a dirty working tree, leaves check output out of the description, and lists at most 60 caveats. It never merges.
- **Changed:** the run skill has an opt-in step 11 that uses `herd pr`; the README, `herd.toml` and `CLAUDE.md` describe it.

## 0.2.7

- **Added:** `herd verify` flags a check that exits 0 while its output says it ran zero tests (unittest, pytest, cargo, go, jest and mocha wording). The evidence records `zero_tests`, `herd verify` marks the line `(ran zero tests)` and the report warns. It reads the full output, not only the stored tail, and a run where any suite executed tests is not flagged (cargo's empty doc-tests, go packages without tests). Advisory only: the Stop gate and `herd done` do not change. The README, the run skill and the evidence skill describe it.

## 0.2.6

- **Fixed:** the hooks no longer crash on Python older than 3.11, such as the 3.9 `python3` that ships with macOS. They exit quietly, and the CLI says which version it needs.
- **Changed:** Python 3.11 is now the minimum, down from 3.13. Path globs use `PurePosixPath.full_match` on 3.13 and a tested equivalent on 3.11 and 3.12. CI runs on all three.
- **Added:** `herd cancel [slug] [--reason "text"]` abandons a task. Its files stay as a record and the Stop gate stops blocking. The run skill uses it only when the human drops the task.
- **Added:** every command prints its usage line when arguments are missing. `herd help` lists all commands; an unknown command says so.
- **Changed:** tests moved to `tests/` (`python3 -m unittest discover -s tests -t .`), and `ruff check .` runs in CI.
- **Docs:** the PRD moved to `docs/PRD.md`, `docs/spikes/` keeps the run logs and an index (the raw review reports are in git history), `CLAUDE.md` is a contributor guide, `herd.toml` is annotated, and the README has an architecture section.

## 0.2.5

- The evidence report flags caveat notes logged in a batch (3 or more within 5 seconds), because their times then show when they were written, not when found.
- The benchmark focuses on the Sonnet pair, with and without Herd.

## 0.2.4

- Logo and plugin icon.
- The supermarket route benchmark: a hidden general verifier, a robustness probe, and the results with and without Herd.

## 0.2.3

- `herd check` warns when a human criterion uses quantifier or size words (`any`, `every`, `very big`) and its `coverage` does not say what varies or what scale was tried.
- `herd note --found|--fixed|--open|--tried` logs caveats with timestamps; the report lists them.
- The run skill has an adversarial "break it" step before review.

## 0.2.2

- Criteria take a `coverage` note and tasks a `known_limits` field; `herd check` warns when they are missing.
- Commands fall back to the only task when none is active.
- The run skill reports a skipped review instead of stopping to ask.

## 0.2.1

- Version bump so installed copies pick up the files added after 0.2.0.
- The evidence records elapsed time since `herd init`, and flags human criteria that are not verbatim quotes of the request.

## 0.2.0

- Quick route for trivial changes (`herd init --quick`), refused at a high risk floor.
- `herd detect` proposes test and lint commands for Python, Node, Rust, Go and `make test`.
- Opt-in per-file lint hook after edits.
- The evidence skill (`/herd:evidence`).
- The first verify records how many checks failed before the work.

## 0.1.0

- The evidence harness (`herd init`, `check`, `verify`, `status`, `done`), the Stop gate with a 3-block circuit breaker, and the run and criteria skills.
- Triage, Arbiter and Escalation modules, built test-first from EGM-reviewed designs.
