# Herd Verify Once: fewer full verifies, and a cheap way to run one check

* **Author:** Toni
* **Status:** Built in 0.12.3. 0.12.5 replaced the content tree id with a hash of changed files.
* **Date:** 2026-11-24
* **Issue:** #39, milestone M3 Fast Herd tasks (0.13.1)

--------------------------------------------------------------------------------

## Overview

`herd verify` runs every criterion and attack check and writes the evidence that the gate reads. It recommends two cheap fixes: (A) the run skill asks for a full verify only at fixed points; (B) `herd verify --only <id>` runs one check and writes nothing. The earlier draft's slow-check reuse and defer rules are dropped: on #32 they add nothing to A (Design 4).

**Terms.**
* Criterion: an entry in `task.toml` with an id (`C1`...) and a check. In #32, C4 was the whole suite.
* Attack: a `tried` note with an `attack` name (from `ATTACKS`) and a `check` command.
* Gate: `problems()`, behind `herd done` and the Stop hook.
* Content: `content_id()`, a hash of the files that differ from the start commit, without `.herd/` (a tree id before 0.12.5); any edit changes it.
* Red run: the first verify that runs a check, recorded in `red.json`.
* Fix round: edits after a failed review, then a verify.

## Problem

From the #32 session log (agent-kennel `runs/collie/spawn/speed-coding-20261124T164734Z.jsonl`) and each verify's output file:

| Verify | Before it | Took |
|---|---|---|
| red | criteria written, no C4 yet | 30 s |
| 1 | code done, C4 added | 221 s |
| 2, 3 | fix rounds 1, 2 | 323, 274 s |
| 4 | one more edit, no review | 273 s |
| 5 | fix round 3 | 278 s |
| 11 | notes only, no file edit | at most 376 s |
| 6 to 10 | fix rounds 4 to 8 | 235, 230, 231, 226, 237 s |

Sum: 2558 s measured plus verify 11: 43 to 49 min. After the red run, every verify had all 5 checks passing. Without C4 a verify takes about 30 s.

## Goals

* G1 (A): The run skill asks for a full verify at red, when the work is done, and after each fix round. Check: `test_skill_verify_points` reads step 8 of `skills/run/SKILL.md`.
* G2 (B): `herd verify --only <id>` takes a criterion id or an attack name (its latest note), runs its check with its timeout, prints `C4 passing (221 s)` or the failure, and exits 0 or 1. It writes nothing under `.herd/`. Check: `test_only_writes_nothing`.
* G3 (B): A passing `--only` after an edit leaves the gate reporting stale evidence, and the Stop hook still blocks. Check: `test_only_does_not_satisfy_gate`.
* G4 (B): An unknown id exits 1 and lists the criterion ids and attack names; with no `red.json` it exits 1 and asks for a full verify, so red first holds. Check: `test_only_unknown_id`, `test_only_before_red_refuses`.

## Non-Goals

* No check relaxed: same commands, timeouts and pass rule. The gate still needs evidence whose content matches the files.
* Deciding from a command's text whether it is a suite.

## Design

1. **(A) Skill text.** Step 8 changes from "Run `herd verify` after every change" to: "Run `herd verify` once the work is done and after each review fix. While working, run only the tests you changed, or `herd verify --only <id>`." Steps 3 and 10 stay. Minimum: red, one after the code, one per fix round. Extra verifies cost time, never correctness.
2. **(B) `--only`.** Usage: `herd verify [slug] [--verbose] [--only <id>]`; the flag is popped before the slug. `verify(root, slug, only=id)` resolves the id and returns before its first write (legacy `start.json`, `frozen.json`, `red.json`, `fails.json`, `green.json`, `evidence.json`). A timeout prints as failing. The gate reads `evidence.json`, `notes.jsonl` and the file fingerprint, which `--only` never changes, so the gate needs no change.
3. **How A and B fit.** B is how the builder follows A for one check, with Herd's exact command, timeout and directory (attack checks live in notes). On #32 it saves no time beyond A.
4. **Slow-check reuse and defer: dropped.** Reuse needs unchanged content: only verify 11 had it, the verify A removes. Defer needs a failing fast check: no verify after the red run had one. So on #32 they add nothing to A. This is one session; a second log could revive them.
5. Docs: README usage line, step 8, CHANGELOG.

## Saving on #32

| Change | Verifies with C4 | Saved |
|---|---|---|
| A | 11 to 9 (after code, 8 fix rounds) | verify 4 (273 s) plus 11 (up to 376 s): 5 to 11 min |
| B | same | none beyond A |
| Reuse and defer, on top of A | 9 | 0 |
| C4 not a criterion (today's spawn rule, text) | 0 | about 37 min (2528 s for verifies 1 to 10, about 300 s without C4) |

After A and B, about 34 min of C4 runs remain (9 verifies); reuse and defer remove none. The 8 fix rounds came from the unknown builder tier, fixed by #42 (`b39b2cd`).

## Alternatives

| Option | Saved on #32 | Verdict |
|---|---|---|
| 1. Refuse a whole-suite criterion at `herd check` | about 37 min | Reads command text; the #32 `xargs` form dodges a pattern (P5). |
| 2, 3. Reuse or defer slow checks | 0 beyond A | Dropped (Design 4). |
| 4. Slow checks run only at the final verify | about 30 min (2034 s in fix rounds, less 8 x 30 s) | Reviews judge evidence without C4. Open Question 2. |
| **A plus B** | **5 to 11 min** | **Recommended** |

## Risks

* An agent can skip A's text: that costs time, not quality.

## Open Questions

1. A only, or A plus B? B adds a flag and four tests, no time saved on #32.
2. For projects without CI, is Alternative 4 worth its review risk, or is "keep the suite out of criteria" enough?
3. Should the rule "never make the full suite a criterion" move from spawn's request text into code?

## Not proven

* M3's 10-minute docs-only bar: it also needs #32's docs-only skip and fewer review rounds.

## Sources

* `scripts/herd.py` (`verify()`, `problems()`, `main()`, `ATTACKS`); `skills/run/SKILL.md` steps 3, 8, 10.
* The #32 log; `/tmp/speedbase/verifyN.txt` mtimes.
* EGM reviews of both drafts.
* The owner: "What is really doing herd verify ? Do we need to run it more than once per run?"; "remember that Herd is a lean solution, if start getting slow is not going to fit the purpose."
