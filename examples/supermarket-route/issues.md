# Issues found in the live test

Run: date ____, model ____, herd ____, superpowers ____, egm ____

| # | Step | What happened | What was expected | Component (skill, CLI, hook, README) | Severity (blocker, major, minor) | Fix or backlog |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

Checklist from the main run: criteria table shown [ ]; checks failed first [ ]; `herd/<slug>` branch [ ]; fresh-context review [ ]; lint feedback seen [ ]; Stop gate blocked an early finish [ ]; `herd done` printed `done:` [ ].

## Timing (from file timestamps, UTC; model Opus)

| Milestone | Time | Since start |
| --- | --- | --- |
| `herd init` (task folder created) | 18:41:56 | 0:00 |
| First `herd verify` (red.json: 5 of 5 failed) | 18:43:07 | 1:11 |
| Last `herd verify` / `herd done` (evidence written) | 18:46:12 | 4:16 |

Wall clock, including any time spent waiting on the human. Git has no commits in `test/`, so there are no commit timestamps. Herd does not record elapsed time itself yet (added to the harness after this run).

## Early observations (live run, read-only)

1. The task used `routeopt.py compare|simulate` and `data/list.txt`, not the `supermarket.py` JSON contract in `goal.md`. If the original goal text (without the contract) was pasted, the contract-based verifier cannot run as is.
2. Two criteria are `source = "human"` (C1 the 20% rule, C2 live KPIs), so the human criteria were picked up. Check they are verbatim.
3. Headline check C1: `compare --runs 10 --min-savings 20` on one agent-made map (`data/store_map.json`). Check how many seeds and whether the map is varied.
4. Evidence says `commit none plus uncommitted changes`: the work was not committed, and the repo had no initial commit.
5. No sign yet of the fresh-context review for a medium-risk task.

## Results of the main run (Opus, 4m 16s to evidence)

Independent verification (`verifier/verify_routeopt.py`, 20 stores and baskets from unseen seeds, every step stream validated):
- optimized saves 98.5% of time vs random walk (smallest single-basket saving 97.9%), against the 20% claim: pass.
- optimized saves 39.9% vs the stronger list-order baseline, and is never slower than list order: the honest number to show next to the headline.
- optimal on 4 of 4 brute-force-checked small baskets.
- the 5 checks reproduce in a fresh copy (`herd verify route-optimizer`: 5 passing).
- the agent's own review found and fixed Majors (exact Held-Karp up to 12 items, bad-input crashes, error coverage).

## Issues

| # | Step | What happened | Expected | Component | Severity | Fix or backlog |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Criteria | Human criteria C1 and C2 were reworded into Given/When/Then and narrowed to one map, one 12-item basket and 10 random-walk seeds (the optimized side is deterministic), yet labelled `human`. The headline check did not test "many baskets". The claim happens to hold (see above). | `human` text is the human's own words; the check covers all of them | criteria skill, `herd check` | major | Fixed: `herd init --request` stores the message, `herd check` and the report flag human criteria that are not verbatim quotes; criteria skill says quote, and the check must cover all the words (vary inputs). 8 tests. |
| 2 | Report | No elapsed time in the evidence | Time to build is relevant | CLI | minor | Fixed: `herd init` records the start, the report shows elapsed and first-verify time. 6 tests. Verify on the next run. |
| 3 | Build | Superpowers (enabled) was not used for TDD, planning or subagents; the agent said so in its report | Use them when installed, or say so | run skill | minor | Left: the agent stated it, tests were written first, and the evidence stands. Revisit if it recurs. |
| 4 | Finish | Work left uncommitted on `herd/route-optimizer`; the repo had no commit, so evidence says `commit none plus uncommitted changes` | Commit on the task branch | environment | minor | Not a Herd bug: the enclosing repo's CLAUDE.md says commit only when asked, and the agent complied. |
| 5 | Probes | Stop gate block, quick route and high-risk approval not yet exercised; lint hook not configured (`test/herd.toml` absent) | Observed in a live session | all | open | Probes pending (RUNBOOK) |

## Clean run (Opus, `goal.md` with the contract, Herd 0.2.0 copy)

- 2m 40s from the task folder (20:01:53) to evidence (20:04:33); first verify at 20:02:21 (4 of 4 failed). 0 questions.
- Black-box verifier: pass. 98.7% time saved vs random walk, 30.6% vs list order, never slower than list order.
- The human criterion is quoted verbatim from `goal.md`; that comes from the input, not from the fix.
- Evidence has no `timing` or `human_not_verbatim` and the task folder has no `started` or `request.md`: the session used the old 0.2.0 plugin copy, so the 0.2.1 fixes were **not exercised**.
- Extra files appeared after the task (`viz.py`, `simulation.html`); not part of the Herd task.

| # | Step | What happened | Expected | Component | Severity | Fix or backlog |
| --- | --- | --- | --- | --- | --- | --- |
| 6 | Test setup | The clean run used the stale 0.2.0 plugin: `claude plugin update` compares version numbers and the bump to 0.2.1 came after the session started | Run the version under test | process | minor | Restart the session after updating; bump the version when plugin files change |
| 7 | Verify the fixes | 0.2.1 behaviour (start time, request, verbatim flag, quick route) not yet seen live | Observed live | all | open | One short live check pending |

## Round 2: Haiku, list-order baseline (emulated Herd arm, 0.2.1)

| # | Step | What happened | Expected | Component | Severity | Fix or backlog |
| --- | --- | --- | --- | --- | --- | --- |
| 7 | 0.2.1 features | `started`, `request.md`, the `Elapsed` line and the verbatim check (3 of 3 human criteria quoted) all appeared | Observed | CLI, skills | closed | Seen in the emulation; still not seen in a real plugin session with the Stop hook |
| 8 | Review step | The agent could not spawn a reviewer, stopped and asked the human (one interaction) | Do not stop for this: say the review was skipped | run skill | minor | Fixed: skill says to report the review as skipped and treat the change as unreviewed instead of asking |
| 9 | Criteria | C1 quoted "step by step ... in real time" but the check only tested one event per stop, not per walked step | A check that covers all the words of the human criterion | criteria skill | major | Open: only a prose rule so far. Candidate: ask the agent to list, per human criterion, what its check does and does not cover, and show it in the report |
| 10 | Claims | Both agents reported flattering demo numbers (42%, 55%); independent verification found about a third of baskets under 30% | Report the claim with its conditions | run skill | minor | Open: the final report could require "claim, conditions, and where it fails" |
| 11 | Coverage | A criterion's check can cover fewer words than the human's criterion (issue 9) | State what each human criterion's check proves and does not | criteria skill, CLI | major | Fixed in 0.2.2: per human criterion `coverage`; `herd check` warns when missing; the report prints it |
| 12 | Claims | Reports quoted the best demo number (issue 10) | State the claim with its conditions | run skill, CLI | minor | Fixed in 0.2.2: task-level `known_limits`; `herd check` warns when missing; shown in the report; the run skill's final report must give the claim with its conditions |
| 13 | CLI | After `herd done`, `herd verify` and `herd status` said "no active task" even though one task existed | Use the only task | CLI | minor | Fixed in 0.2.2: falls back to the only task; several tasks and none active lists them; the Stop gate still ignores finished tasks |
| 14 | Process | `claude plugin update` compares version numbers, so changed plugin files were not picked up | A rule | docs | minor | Fixed: `CLAUDE.md` says to bump the version when plugin files change and restart the session |

## Round 3: goal-v2 (any layout, very big), Sonnet

| # | Step | What happened | Expected | Component | Severity | Fix or backlog |
| --- | --- | --- | --- | --- | --- | --- |
| 15 | Request capture | In the Sonnet Herd run, `request.md` held a compressed paraphrase of the human's message (articles dropped; the session had the caveman plugin active). `herd init --request` stores what the agent passes, so "verbatim" cannot be guaranteed | The human's exact words | CLI, hooks | major | Open: a `UserPromptSubmit` hook in the plugin could record the raw prompt for `herd init` to read. First confirm in the docs that the hook payload carries the prompt |
| 16 | Experiment | The Herd session had the user's own plugins (caveman, Superpowers, others); the baseline subagent ran in a clean context | Both arms in the same environment | process | major | Open: run the no-Herd baseline in the user's own session setup with Herd disabled; keep the clean-subagent baseline as a second data point |
