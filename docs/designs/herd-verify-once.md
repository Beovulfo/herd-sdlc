# Herd Verify Once: run a slow check once per content, not on every verify

* **Author:** Toni
* **Status:** Draft
* **Date:** 2026-11-24
* **Issue:** #39, milestone M3 Fast Herd tasks (0.13.1)

--------------------------------------------------------------------------------

## Overview

`herd verify` runs every criterion check and attack command, one after another, on every call, and reuses nothing between calls. A criterion that runs the whole repo suite costs the full suite on each verify. This design makes Herd time each check. A check whose last real run took `slow_s` seconds or more is a **slow check**. Herd reuses a slow check's passing result while the content is unchanged. While a fast check still fails, it defers the slow check. Otherwise it runs it. A deferred check blocks green and done, so no check is relaxed and none is skipped without a pass on the current content.

**Terms.**
* Content: what `content_id()` returns, the git tree id of the working tree without `.herd/`. A commit does not change it; any edit does.
* Task sha: `_task_sha()`, the hash of `task.toml`.
* Red run: the first verify with a runnable check. It records in `red.json` how many checks failed before the code existed ("red first").
* Green: `green.json`, written the first time every check passes. Reviews count only after it.
* Gate: `problems()`, used by `herd done` and the Stop hook.

## Problem

* Issue #32's session ran 64 minutes. About 20 of them went to 5 `herd verify` runs, because criterion C4 was the whole suite (`ls tests/test_*.py | ... | xargs -P 6 -n 1 python3 -m unittest`, timeout 900 s). Evidence: `.herd/tasks/speed/evidence.json`, `timing.elapsed_s` 7957 (the wall clock until the session ended).
* `verify()` calls `run_check()` for each criterion in a loop. Attack commands are deduplicated by `(check, timeout)` within one verify only.
* Today's workaround is text in Collie's spawn requests ("never make the full suite a criterion"). That is a rule in text, not in code, and a project without CI loses the suite as evidence.

## Goals

* G1: Each result records `duration_s`, `timeout_s`, `content` (taken before it ran), `task_sha` and `ran_at` of its last real run. A deferred or reused result carries these, plus the exit code and output, forward from that run. Check: `test_verify_records_run_fields`.
* G2: On any verify, a slow check whose last real run passed with the same check, timeout, content and task sha is reused: status `passing`, `reused: true`. Check: `test_slow_reused_after_commit`, `test_slow_rerun_after_edit`.
* G3: A slow check that cannot be reused is `deferred` while any fast check fails, and runs once every fast check passes. `herd verify --all` runs it in any case. Output line: `C4 deferred (took 240 s): runs when the other checks pass, or with --all`. Check: `test_slow_deferred_while_fast_fails`, `test_slow_runs_when_fast_pass`.
* G4: The red run runs every check. Check: `test_red_run_runs_all`.
* G5: A deferred result blocks `green.json` and fails the gate with `C4 deferred: fix the failing checks or run herd verify --all`. Check: `test_deferred_blocks_green_and_done`.
* G6: A deferred check keeps its `fails.json` count: it neither adds to it nor resets it. Check: `test_deferred_keeps_fail_count`.
* G7: Attack commands follow the same rule, and `deferred` prints in the CLI, the report and the PR. Check: `test_slow_attack_deferred`, `test_pr_body_shows_deferred`.

## Non-Goals

* No check relaxed: same commands, same timeouts, same pass rule.
* No check skipped without proof: done needs every check passing on the current content.
* Deciding from the command's text whether it is "a whole suite".
* Running checks in parallel (Alternative 3).

## Design

1. `run_check()` also returns the elapsed seconds (`time.monotonic()`).
2. `verify()` computes `content_id()` once before the checks, for the reuse decision and the per-result `content`. The top-level `content` stays as it is today, measured after the checks, so the review rule (`add_review`, the high-risk content compare) does not change.
3. For each command, Herd looks up the previous `evidence.json` entry with the same `(check, timeout_s)`. There is no entry at the red run.
   * No earlier real run, or it took less than `slow_s`: run.
   * Slow, passed, same content and task sha: reuse.
   * Slow, not reusable: fast checks run first. If any fails and `--all` is not given: deferred. Otherwise: run.
   * A timed-out check took at least its timeout, so it is slow. It never reuses (it failed), so it runs whenever the fast checks pass.
4. `summary` gains `deferred`. Green requires `deferred == 0`. The CLI status words, the gate's reason map, `pr_body` and `pass_hint` handle it.
5. `herd.toml`: `[verify] slow_s = 60`. `0` turns the rule off (every check runs, as today).
6. Docs: README settings table, `herd verify [slug] [--verbose] [--all]` usage, CHANGELOG. No skill text: the builder never has to call `--all`, because the gate's refusal names it.

## Alternatives

| Option | Added time per verify | Saved on #32 (5 verifies, C4 about 4 min each) | Verdict |
|---|---|---|---|
| 1. Refuse or warn at `herd check` when a criterion is a whole suite; run it once at the final verify | about 0 | up to about 12 min, but only if detected | Detection reads the command text. The `xargs` form in #32 already dodges a `unittest discover` pattern. Timing does the same job without reading text. |
| 2. Reuse a passing result while `content_id` is unchanged | about 0 (already computed once per verify) | one run per verify that follows only a commit or a note | Too little alone, so it is part of this design. |
| 3. Run independent criteria in parallel | thread start, about 0 | seconds (estimate): C4 already uses 6 processes and the other checks are short; parallel sessions on one machine already compete for CPU | Little gain, more contention. |
| **This design: timing plus reuse plus deferral** | about 0 | about 4-12 min (estimate, see Not proven) | **Recommended** |

## Risks

* A slow check fails late in the loop. Mitigation: it runs as soon as the fast checks pass, not only at the end.
* Reuse trusts `content_id`, which ignores gitignored files and the environment. Mitigation: reuse only slow checks; CI reruns the suite on the PR.
* A flaky slow check passes once and is reused. Same mitigation.
* A busy machine makes a check slow. Effect: deferral only; it still must pass.

## Open Questions

1. Should reuse also apply to fast checks? It saves seconds and widens the `content_id` trust risk. Proposed: no.
2. Is 60 s the right `slow_s` default?
3. Should the PR evidence table mark reused results with the time they really ran?

## Not proven

* The saving. Durations per verify were not recorded in #32, so it is not known how many of the 5 verifies had a failing fast check, followed an edit after green (each of those still needs a full run), or followed only a commit.
* That the 10-minute docs-only bar of M3 is met: that also depends on the 0.13.1 speed work in #32.

## Sources

* `scripts/herd.py`: `verify()`, `run_check()`, `content_id()`, `_task_sha()`, `problems()`, `add_review()`, `DEFAULT_TIMEOUT = 300`. `content_id()` took 67 ms on this repository (5 calls, averaged).
* `CHANGELOG.md` 0.12.1 and 0.12.2.
* Issue #39; the #32 evidence `.herd/tasks/speed/evidence.json`.
* EGM review of the first draft (codebase-details, zoom-out, comprehension): green and escalation interactions, reuse on any verify, auto-run instead of a required `--all`.
* The owner: "PR 32 is running for 60 minutes?? thats way too mucch, root cause analysis of this"; "put on hold any other milestone, we focus on this one".
