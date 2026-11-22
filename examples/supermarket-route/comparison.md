# Herd runs vs a no-workflow baseline (one run each, all Opus)

Three runs of the same family of task. Runs 1 and the baseline got **exactly the same input** (the original request text; `/herd:run` removed for the baseline). Run 2 used `goal.md`, which adds a fixed CLI contract, so it is a different, easier-to-verify task: compare it with the others only for process, not for outcome.

- **Baseline:** an empty folder, no Herd. Launched as a subagent of a session where Superpowers was enabled at user level; its transcript was audited: 7 Bash, 4 Write and 2 Edit calls, no Skill calls, no questions.
- **Herd run 1:** the original request, Herd 0.2.0.
- **Herd run 2:** `goal.md` with the contract, Herd 0.2.0 (the installed copy was stale; the 0.2.1 fixes were not exercised).

## Measured

| | Herd run 1 | Baseline | Herd run 2 (contract) |
| --- | --- | --- | --- |
| Wall clock to a finished result | 4m 16s | 2m 03s | 2m 40s |
| Questions asked of the human | 0 | 0 | 0 |
| Tests | 23 unit tests, 5 stored checks | 1 test script | 206-line test file, 4 stored checks |
| Checks that failed before any code | 5 of 5 | not done | 4 of 4 |
| Stored evidence (command, exit, output, SHA, time) | yes | no | yes |
| Fresh-context review | yes, 3 Majors fixed | no | not recorded |
| Human criterion quoted verbatim | no (reworded, narrowed) | n/a | yes (copied from `goal.md`) |

Times are wall clock from file timestamps (`herd init` to `herd done`; the baseline from the subagent's own duration).

## Independent verification (20 stores and baskets from unseen seeds, every walk validated)

| | Herd run 1 | Baseline | Herd run 2 |
| --- | --- | --- | --- |
| All walks valid, every item picked | yes | yes | yes |
| Time saved vs random walk (claim: more than 20%) | 98.5% | 97.8% | 98.7% |
| Time saved vs a stronger baseline (list order) | 39.9% | 24.8% | 30.6% |
| Never slower than list order | yes | yes | yes |
| Brute-force optimum on small baskets | 4 of 4 | 7 of 9 (gap up to 5.4%) | exact by test |
| Optimizer | exact (Held-Karp) to 12 items, then heuristic | nearest neighbour plus 2-opt | exact (Held-Karp) to 12 items, then heuristic |

Run 1 and the baseline use different time models (pick time 5 s vs 15 s, round trip vs end at the last pick), so compare the pattern, not the absolute numbers. Reproduce: `verifier/verify_routeopt.py`, `verifier/verify_baseline.py` and `verifier/verify_independent.py` (see `RUNBOOK.md`).

## Reading it honestly

- On this well-specified task every run meets the stated criterion by a wide margin. The baseline was the fastest.
- What Herd added: stored, re-runnable evidence; checks that failed first; a fresh review (run 1); an exact optimizer. What it cost: about 1.3 to 2 times the wall clock.
- Herd's first run showed a real weakness: its human criteria were reworded and narrowed to one map, while the baseline's test was broader. Fixed in 0.2.1, not yet confirmed in a live session.
- The baseline's report flagged that a random walk is a weak comparison and offered a list-order baseline. Run 1's report did not; the contract in run 2 asked for it.
- One run each, one model: differences in time or quality may be chance.

# Round 2: Haiku, with and without the Herd workflow (list-order baseline, 30% target)

New request, same text for both arms: compare against the **list-order route** and show more than **30%** time saved. Both arms ran on Claude Haiku as subagents.

- **Herd arm:** it read and followed `skills/run` and `skills/criteria` and ran the real `herd.py` CLI (0.2.1). This is an emulation: no plugin loader, no Stop-gate hook, and the arm could not spawn a review subagent.
- **No-workflow arm:** the request text plus its folder path, nothing else. Transcript audited: 4 Bash, 2 Write, 2 Edit calls, no Skill calls.

## Measured

| | Haiku with Herd | Haiku, no workflow |
| --- | --- | --- |
| Agent time to finish | 2m 58s (evidence at 2m 15s from `herd init`, first verify at 1m 20s) | 1m 32s |
| Tokens, tool calls | 103k, 17 | 83k, 7 |
| Questions asked of the human | 1 (it wanted a fresh-context review it could not spawn; answered "skip it") | 0 |
| Tests | 12 unit and CLI tests, 4 stored checks | 3 self-checks |
| Checks that failed before any code | 4 of 4 | not done |
| Human criteria quoted verbatim | 3 of 3 (confirmed by `herd check`) | n/a |
| Stored evidence | yes | no |
| Fresh-context review | skipped | none |

## Independent verification (20 stores and baskets from unseen seeds, every route recomputed)

| | Haiku with Herd | Haiku, no workflow |
| --- | --- | --- |
| Routes valid, KPIs match my recomputation | yes | yes |
| Mean distance, optimized (cells) | 135.4 | 135.4 |
| Optimal on small baskets (brute force) | 4 of 4 | 4 of 4 |
| Time saved vs list order, mean | 35.9% | 32.2% |
| Baskets at or below 30% saved | 6 of 20 (smallest 6.8%) | 7 of 20 (smallest 6.1%) |
| Simulation granularity | one event per stop (about 12 per route) | one tick per walked cell (about 135 per route), with real-time playback |

## Reading it honestly

- The two optimizers found the same routes (identical mean distance). The different saving percentages come from different assumed time models (walking speed and pick time), not from route quality.
- The 30% claim holds on average for both, but it depends on the basket size and the time model: about a third of the verifier's baskets saved less than 30%. Both agents reported their own demo numbers (42% and 55%), which flatter the claim.
- The no-workflow arm followed "step by step, in real time" more closely: it simulates every walked cell and can play back in real time. The Herd arm emitted one event per stop. Quoting the human's words verbatim did not guarantee the check covered them; coverage is still a prose rule, not an enforced one.
- Herd cost about twice the time and a little more than 20 percent more tokens, and left stored evidence, red-first results and an elapsed-time record. It produced no better route.
- The 0.2.1 features worked: `started`, `request.md`, the `Elapsed` line and the verbatim check were all present.
- Caveats: one run per arm, one model, an emulated Herd without hooks or a reviewer, different time constants per arm.

# Code quality probe: is the code worse without Herd?

`verifier/robustness_probe.py` (run from the repo root) feeds each packaged solution the same small store with six scenarios through its own CLI, and counts code, tests and docstrings. "clean error" means a non-zero exit with no traceback. The "tests" count for the no-workflow Opus solution is assertions in one script, not named tests.

| solution | code lines | test lines | tests | functions documented | normal | unknown_id | duplicate_id | empty_list | unreachable | malformed_map | handled |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Opus, Herd run 1 | 287 | 172 | 23 | 6 of 18 | ok | clean error | ok | ok | clean error | clean error | 6 of 6 |
| Opus, Herd run 2 | 181 | 164 | 19 | 6 of 15 | ok | clean error | ok | ok | clean error | clean error | 6 of 6 |
| Opus, no workflow | 190 | 26 | 4 | 4 of 16 | ok | clean error | clean error | CRASH | CRASH | CRASH | 3 of 6 |
| Haiku, Herd | 175 | 107 | 12 | 6 of 14 | ok | clean error | clean error | ok | clean error | clean error | 6 of 6 |
| Haiku, no workflow | 182 | 27 | 3 | 4 of 12 | ok | clean error | clean error | CRASH | CRASH | CRASH | 3 of 6 |

## Reading it

- **Edge cases and errors: yes, worse without Herd.** Both no-workflow solutions crashed with a traceback on an empty list (division by zero), an unreachable product and a malformed map, so they handled 3 of 6 scenarios; every Herd solution handled 6 of 6. This is a real gap, and it is what Herd asks for: the criteria skill requires an edge or failure case, and each Herd run turned it into tests (`EdgeCaseTests` and similar).
- **Tests: much thinner without Herd.** About 26 test lines against 107 to 172 with Herd, and 3 to 4 checks against 12 to 23.
- **Code size and documentation: about the same.** 175 to 190 lines for comparable features, and a similar share of documented functions (the one outlier is Herd run 1 at 287 lines, because it adds an exact solver and input validation).
- **Core algorithm: no difference on the Haiku pair.** Identical mean route distance. On the Opus pair, run 1 used an exact solver up to 12 items (optimal on 4 of 4 small baskets) against a heuristic (7 of 9).
- **Spec fidelity: better without Herd in one case.** The Haiku no-workflow solution simulates every walked cell with real-time playback; the Haiku Herd solution emits one event per stop.
- **Caveats.** The probe's scenarios overlap what the Herd agents were asked to test (edge cases), so it measures edge-case handling, not overall quality. One run per arm, one small store, five solutions, and the Haiku Herd arm was an emulation. The no-workflow solutions might handle these cases if asked.
