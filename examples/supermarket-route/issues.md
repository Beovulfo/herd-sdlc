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
