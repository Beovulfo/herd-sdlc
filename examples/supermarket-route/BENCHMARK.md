# Benchmark: Herd against no workflow

**Question.** Given the same short prompt, does an agent that follows Herd produce better results than the same model with no workflow, and what does it cost?

**Task.** A route optimizer for a delivery person who picks a customer's shopping list inside a supermarket: read the store map and the list, find the best route, simulate it step by step with live `time-to-prepare-basket` and `distance-covered`, and show it beats a baseline route by a stated percentage. The prompts are in the appendix. They are single paragraphs, the way a person would ask in a vibe-coding session, with no file formats, no scale numbers and no test requirements.

![Animation of one basket: list-order route against the optimized route](images/simulation.svg)

## The arms

| Arm | Model | Workflow | Prompt | How it ran |
| --- | --- | --- | --- | --- |
| Opus, Herd run 1 | Opus | Herd 0.2.0, live | A (random-walk baseline, 20%) | a person's own Claude Code session |
| Opus, no workflow | Opus | none | A | a subagent in a clean context |
| Opus, Herd run 2 | Opus | Herd 0.2.0, live | A plus a fixed command-line contract | a different, easier-to-verify task |
| Haiku, Herd | Haiku | Herd 0.2.1, emulated | B (list-order baseline, 30%) | a subagent following the skills and running the real `herd` CLI; no hooks, and it could not spawn a reviewer |
| Haiku, no workflow | Haiku | none | B | a subagent in a clean context |
| Sonnet, Herd | Sonnet | Herd 0.2.2, live | C (any layout, very big) | a person's own Claude Code session |
| Sonnet, no workflow | Sonnet | none | C | a subagent in a clean context |

The no-workflow arms got exactly the prompt text plus one line giving their working folder. Each transcript was audited: no skill calls, no Herd, and no questions asked.

## How every solution was checked

The agents never saw these checks.

- **Hidden general verifier** ([`verifier/verify_general.py`](verifier/verify_general.py)). It generates stores from eight layout families (parallel aisles, vertical aisles, islands, random obstacles, comb, L-shape, maze corridors, department rooms) at four sizes up to 600 by 400 cells and 200 items. It asks the solution for its optimized and list-order routes as cell-by-cell traces and validates each one itself: legal moves, no walls, every item reached, distance and time recomputed. It compares against the exact optimum on small stores and against plain nearest-neighbour on larger ones. Its own tests include a reference solution and two cheating variants that it rejects.
- **Robustness probe** ([`verifier/robustness_probe.py`](verifier/robustness_probe.py)). The same small store with six scenarios through each solution's own command line: a normal run, an unknown product, a duplicate, an empty list, an unreachable product and a malformed map. A crash with a traceback counts as unhandled.
- **Size and tests.** Code lines, test lines and documented functions per solution.

## Results

### Hidden verifier, Sonnet pair (prompt C: any layout, very big)

| Tier | With Herd | No workflow |
| --- | --- | --- |
| Small, 60 by 40, 7 items | 16 of 16 valid | 14 of 16 valid |
| Mid, 160 by 100, 40 items | 16 of 16 valid | 12 of 16 valid |
| Large, 400 by 300, 100 items | 8 of 8 valid | 6 of 8 valid |
| Extra large, 600 by 400, 200 items | 8 of 8 valid | 6 of 8 valid |
| **All tiers** | **48 of 48** | **38 of 48** |

- Every failure is the same crash, `unreachable item`, on stores where a shelf borders a disconnected pocket of floor (the random-obstacle and department layouts). The no-workflow code treats the "unreachable" marker as the shortest distance. The Herd solution handled all of them.
- Where both finished, route quality is the same: on small stores within 0.5 percent of the exact optimum (Herd) and 0.2 percent (no workflow), and 10 to 15 percent shorter than plain nearest-neighbour on larger ones, for both.
- Median time to plan a 400 by 300 store with 100 items: 4.4 s with Herd, 13.8 s without. For 600 by 400 with 200 items: 17.2 s against 72.7 s (limit 120 s per store).
- On the extra-large tier the no-workflow routes were on average 5.6 percent shorter than plain nearest-neighbour, but on one store 40 percent longer; the Herd routes were on average 12.3 percent shorter and never longer.
- Time saved against list order averaged 25.5 percent on small baskets (7 items), about 67 percent on mid and 78 percent on large, the same for both arms.

![The optimized route on eight generated store layouts](images/layouts.svg)

### Robustness probe, all arms

| Solution | Handled of 6 | Crashed on | Test lines | Code lines |
| --- | --- | --- | --- | --- |
| Opus, Herd run 1 | **6** | none | 172 | 287 |
| Opus, Herd run 2 | **6** | none | 164 | 181 |
| Opus, no workflow | 3 | empty list, unreachable product, malformed map | 26 | 190 |
| Haiku, Herd | **6** | none | 107 | 175 |
| Haiku, no workflow | 3 | empty list, unreachable product, malformed map | 27 | 182 |
| Sonnet, Herd | **6** | none | 180 | 297 |
| Sonnet, no workflow | 4 | unreachable product, malformed map | 20 | 226 |

In all three pairs the Herd solution handled every scenario and had 4 to 9 times the test lines. Code size is comparable, and a similar share of functions has a docstring. The criteria skill asks for an edge or failure case, and every Herd run turned that into tests. The no-workflow agents were not asked and wrote none. This probe therefore measures edge-case handling, not overall quality.

![Robustness and wall-clock time per arm](images/benchmark.svg)

### What did not change

- **The route itself.** Both arms found routes of the same length on the Haiku pair (identical mean distance) and the Sonnet pair. On the Opus pair, run 1 used an exact solver up to 12 items (optimal on 4 of 4 small baskets) against a heuristic (7 of 9), so Herd had a small edge there.
- **Simulation fidelity, in one case.** The Haiku no-workflow solution simulates every walked cell with real-time playback; the Haiku Herd solution emits one event per stop. Quoting the human's words verbatim did not guarantee that the check covered them. Coverage is a prose rule that the new `coverage` note and quantifier warning now push on, but they are warnings, not proof.

### Cost

| Arm | Wall time to a finished result | Tokens | Tool calls | Questions to the human |
| --- | --- | --- | --- | --- |
| Opus, Herd run 1 | 4m 16s | not recorded | not recorded | 0 |
| Opus, no workflow | 2m 03s | 75k | 10 | 0 |
| Opus, Herd run 2 (different task) | 2m 40s | not recorded | not recorded | 0 |
| Haiku, Herd (emulated) | 2m 58s | 103k | 17 | 1 (it wanted a review it could not spawn; fixed in the skill) |
| Haiku, no workflow | 1m 32s | 83k | 7 | 0 |
| Sonnet, Herd | 8m 22s to the last verify | not recorded | not recorded | not recorded |
| Sonnet, no workflow | 1m 03s | 73k | 5 | 0 |

Herd took 1.3 to 8 times the wall-clock time. Tokens were measured only where the arm ran as a subagent: on the Haiku pair, Herd used 23 percent more. Herd times from a person's live session include any time the session waited on them; the first verify, with all checks failing, came 30 to 130 seconds in. Herd needs only the single message: the live runs asked the person nothing.

### Did Herd find the caveats during the run?

The caveats below are what the hidden verifier showed. For each arm, did the run itself find and encode it before finishing?

| Caveat | Sonnet with Herd | Sonnet, no workflow |
| --- | --- | --- |
| Disconnected pockets of floor | handled; its layout checks included random-obstacle stores | not found; crashes on 10 of 48 stores |
| Layout variety | the C1 check covers four layout types, and says so in `coverage` | tests use one store generator |
| Scale | C1 includes a 250 by 250 store with thousands of products inside a time bound; `known_limits` says 500 stops take about 10 s and larger is untested | not tested; the final text says it is fine to about 200 items |
| The 30% claim depends on basket size | quantified in `known_limits`: fails on 1 item in 60 of 60 runs, on 3 items in 41 of 60, on 5 in 26 of 60, on 10 in 3 of 60, never on 20 | reported "34% to 71%" saved, with the small-basket case as its weakest |
| Pick time dilutes the saving | in `known_limits` | mentioned in the final text |
| Bad inputs | 6 of 6 | 4 of 6 |

The Herd run wrote these into checks and a stated limits field before it finished. The no-workflow run mentioned some at the end, in text, and fixed none. That run used Herd 0.2.2, which had no timestamped log of problems found; version 0.2.3 adds one (`herd note`), so a future run can show when each was found.

## Caveats on this benchmark

- One run per arm, three models, one task. Differences in time or quality may be partly chance.
- The Herd and no-workflow arms did not run in the same environment: the Herd runs on Opus and Sonnet were in a person's own session, with that person's other plugins active; the no-workflow arms were clean subagents. The Haiku Herd arm was an emulation with no hooks and no reviewer.
- The prompts differ between model pairs, so compare within a pair.
- The verifier's scenarios overlap what Herd asks agents to test (edge cases), so the robustness result partly measures Herd's own rules working.
- A random walk is an easy opponent; the stronger list-order comparison is the one to quote. The 30 percent saving does not hold for small baskets, for any solution, including a perfect one.
- The no-workflow agents might handle these cases if asked.

## Issues the benchmark found in Herd

Fourteen issues were logged and most were fixed during the test, including human criteria that were reworded and narrowed, a stale plugin cache, a review step that stopped to ask, and claims reported without their conditions. See [`issues.md`](issues.md).

## Reproduce

From the repository root:

```bash
python3 examples/supermarket-route/verifier/verify_general.py sonnet_herd examples/supermarket-route/sonnet-herd-run/solution --tiers S,M,L
python3 examples/supermarket-route/verifier/verify_general.py sonnet_baseline examples/supermarket-route/sonnet-baseline-run --tiers S,M,L
python3 examples/supermarket-route/verifier/robustness_probe.py
python3 examples/supermarket-route/images/make_images.py
```

The raw outputs of these runs are in [`results/`](results). The older verifiers for the Opus and Haiku solutions are in [`verifier/`](verifier). Each solution, with its task file and evidence where Herd produced them, is in its own folder: `herd-run`, `run-1-original-prompt`, `baseline-run`, `haiku-herd-run`, `haiku-baseline-run`, `sonnet-herd-run`, `sonnet-baseline-run`. A running log of every round is in [`comparison.md`](comparison.md).

## Appendix: the prompts

**A.** build a route optimizer that works inside a big supermarket. It uses as input the MAP of the supermarket with all the products localised in the map with the product ID and the short-name, and the list of products (id:short name) requested by a customer. The goal is to find the optimal route for the "delivery guy" that is preparing the basket and shipping the shopping list to the customer. Success looks like we can simulate step by step the route of the delivery guy, measuring in real time the KPIs: "time-to-prepare-basket" and "distance-covered", and compare it with a random walk algorithm (not optimized) so we can demosntrated that our optimiation algoritm successfully saves more than 20% of time for the basket to be ready

**B.** The same, comparing with the list-order route (not optimized) and a 30% saving.

**C.** [`goal-v2.md`](goal-v2.md): the same again, but the optimizer "works inside any supermarket, even very big ones, whatever its layout".
