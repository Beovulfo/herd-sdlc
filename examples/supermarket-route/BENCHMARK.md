# Benchmark: the same prompt with and without Herd

**Question.** Given one short prompt, does an agent that follows Herd produce a better result than the same model with no workflow? Does that hold for a small model? What does each cost?

**Task.** A route optimizer for a delivery person who picks a customer's shopping list inside a supermarket. It reads the store map and the list, finds the best route, simulates it step by step with live `time-to-prepare-basket` and `distance-covered`, and shows it saves more than 30 percent of the time against the list-order route. The prompt ([`prompt.md`](prompt.md)) is one paragraph, the way a person would ask in a vibe-coding session: it asks for something that works for any supermarket, even very big ones, whatever its layout, and gives no file formats, no scale numbers and no test requirements.

![Animation of one basket: list-order route against the optimized route](images/simulation.svg)

## The runs

Four arms, **6 runs each**, 24 runs in all, on 2026-11-23. A fifth arm, Haiku with Herd 0.12.0, was run later (2026-11-24) with 6 more runs and a different method; see [Haiku with Herd 0.12.0, real sessions](#haiku-with-herd-0120-real-sessions). The figure and the text below the next heading cover the four 0.3.1 arms unless a line says otherwise.

| Arm | Model | Input | Runs |
| --- | --- | --- | --- |
| Sonnet + Herd | Claude Sonnet 5.5 | the prompt, as `/herd:run <prompt>`, with **Herd 0.3.1** (commit `d4f11c6`) | [`runs/sonnet-herd-1`](runs/sonnet-herd-1) to `-6` |
| Sonnet, no workflow | Claude Sonnet 5.5 | the prompt, nothing else | [`runs/sonnet-plain-1`](runs/sonnet-plain-1) to `-6` |
| Haiku + Herd | Claude Haiku 5.5 | the prompt, as `/herd:run <prompt>`, with Herd 0.3.1 | [`runs/haiku-herd-1`](runs/haiku-herd-1) to `-6` |
| Haiku, no workflow | Claude Haiku 5.5 | the prompt, nothing else | [`runs/haiku-plain-1`](runs/haiku-plain-1) to `-6` |
| Haiku + Herd 0.12.0 (added later) | Claude Haiku 5.5 | the prompt, in a real headless `claude -p` session with the installed 0.12.0 plugin | not in the repository; per-run numbers below |

Every run is a clean subagent in its own empty git repository, told only that Python's standard library is allowed, that nobody will answer questions and that it cannot spawn subagents. A Herd run read the run skill and ran the real `herd` CLI; its task file, evidence report and caveat log are in its `herd-task/` folder. It is an emulation of a live session: no Stop hook fired and no fresh-context review happened.

## How the results were checked

No run saw these checks.

- **Hidden general verifier** ([`verifier/verify_general.py`](verifier/verify_general.py)). It generates 48 stores from eight layout families (parallel aisles, vertical aisles, islands, random obstacles, comb, L-shape, maze corridors, department rooms) at four sizes: 16 small (60 by 40 cells, 7 items), 16 mid (160 by 100, 40 items), 8 large (400 by 300, 100 items) and 8 extra large (600 by 400, 200 items). It asks each solution for both routes as cell-by-cell traces and validates every one itself: legal moves, no walls, every item reached, distance and time recomputed. A store counts as valid only if it finished within the time limit (30, 90, 180 and 300 seconds) with both routes valid. Its own tests use a reference solution and two cheating variants that it must reject.
- **Robustness probe** ([`verifier/robustness_probe.py`](verifier/robustness_probe.py), run through [`verifier/probe_runs.py`](verifier/probe_runs.py)). The same small store with six scenarios through each solution's own command line: a normal run, an unknown product, a duplicate, an empty list, an unreachable product and a malformed map. A traceback counts as unhandled.
- **Adapters** ([`runs/adapters/`](runs/adapters)). Every run chose its own file formats and functions, so a separate agent wrote one small adapter per run from a fixed spec ([`verifier/ADAPTER_SPEC.md`](verifier/ADAPTER_SPEC.md)). An adapter translates the verifier's store into the run's own format and calls the run's own planner and simulator; it must not fix or work around anything. Two adapter mistakes were found while scoring and fixed (a probe map that skipped the spec's translation, and a route marked as a round trip that by design ends at the last pick); the scores below are from the fixed adapters.
- **Cost** comes from each run's own log of model requests (input, output, cache-read and cache-write tokens), priced at Anthropic API list prices: Sonnet 5.5 at $2 / $10 per million input / output tokens, $0.10 cache reads, $2.50 cache writes; Haiku 5.5 at $0.10 / $0.50 for prompts up to 100K tokens and $0.50 / $2.50 above. Haiku cache prices assume the usual multipliers (reads 0.1 times, writes 1.25 times input). Rates are from the Claude API reference cached on 2026-11-03.

## Results

![Four measures for the four arms: mean and standard deviation of 6 runs](images/benchmark.svg)

Mean ± standard deviation over the 6 runs of each arm ([`verifier/aggregate.py`](verifier/aggregate.py)):

| Measure | Sonnet + Herd 0.3.1 | Sonnet, no workflow | Haiku + Herd 0.3.1 | Haiku, no workflow | Haiku + Herd 0.12.0 (real hooks) |
| --- | --- | --- | --- | --- | --- |
| **Valid stores, of 48** | **48.0 ± 0.0** | 45.2 ± 4.8 | 44.3 ± 2.0 | 41.7 ± 2.7 | 46.2 ± 3.0 |
| Runs with all 48 valid | **6 of 6** | 3 of 6 | 1 of 6 | 0 of 6 | 4 of 6 |
| **Bad-input scenarios handled, of 6** | **6.0 ± 0.0** | 3.5 ± 0.5 | **6.0 ± 0.0** | 4.3 ± 2.0 | **6.0 ± 0.0** |
| Valid small stores, of 16 | 16.0 ± 0.0 | 15.3 ± 1.2 | 15.8 ± 0.4 | 15.7 ± 0.5 | 15.8 ± 0.4 |
| Valid mid stores, of 16 | 16.0 ± 0.0 | 15.3 ± 1.6 | 13.5 ± 1.2 | 13.2 ± 0.8 | 14.8 ± 1.8 |
| Valid large stores, of 8 | 8.0 ± 0.0 | 7.2 ± 1.3 | 7.8 ± 0.4 | 7.2 ± 1.0 | 7.8 ± 0.4 |
| Valid extra-large stores, of 8 | 8.0 ± 0.0 | 7.3 ± 0.8 | 7.2 ± 0.4 | 5.7 ± 2.3 | 7.7 ± 0.5 |
| Time saved against list order, small (%) | 25.0 ± 0.9 | 25.5 ± 2.1 | 30.1 ± 3.4 | 26.8 ± 3.0 | 28.0 ± 2.8 |
| Time saved, mid (%) | 66.8 ± 1.3 | 66.7 ± 1.1 | 68.2 ± 1.8 | 66.8 ± 1.4 | 68.5 ± 1.0 |
| Time saved, large (%) | 78.4 ± 0.6 | 80.2 ± 3.1 | 79.1 ± 0.8 | 77.7 ± 1.4 | 79.3 ± 0.6 |
| Time saved, extra large (%) | 83.5 ± 0.6 | 82.9 ± 0.6 | 83.7 ± 0.7 | 84.1 ± 3.8 | 84.0 ± 0.5 |
| Median time to plan an extra-large store (s) | 63.7 ± 33.9 | 94.2 ± 50.0 | 69.9 ± 31.3 | 49.1 ± 15.5 | 59.2 ± 19.0 |
| Time to a finished result (min) | 4.2 ± 1.2 | 1.1 ± 0.2 | 10.3 ± 5.5 | 2.7 ± 0.9 | about 22 ± 10 (rough) |
| Tool calls | 16 ± 4 | 3 ± 2 | 34 ± 9 | 9 ± 2 | not counted |
| Model requests | 17 ± 4 | 4 ± 2 | 31 ± 9 | 8 ± 2 | not counted |
| Output tokens (thousands) | 23.4 ± 4.1 | 8.4 ± 1.5 | 65.8 ± 10.9 | 27.6 ± 5.1 | not counted |
| Tokens read, including cache (thousands) | 1457 ± 369 | 255 ± 136 | 3576 ± 1315 | 663 ± 150 | not counted |
| **Estimated cost per run (USD)** | **0.61 ± 0.09** | 0.29 ± 0.03 | **0.29 ± 0.09** | 0.04 ± 0.02 | **0.76 ± 0.26** (the session's own cost) |

### What the numbers say

- **Sonnet with Herd had no failure in 6 runs.** Every run produced a valid route on all 48 stores and handled all six bad inputs, with zero spread. Without Herd, Sonnet was right 3 times out of 6: the other runs lost 1 to 12 stores, and every one of the six crashed on a malformed map.
- **Herd made bad input safe on both models.** All 12 Herd runs handled 6 of 6 probe scenarios; the 12 runs without it averaged 3.5 (Sonnet) and 4.3 (Haiku). This is what Herd's enforced attacks ask for, so read it as Herd doing what it says.
- **Herd helps Haiku less on route validity.** Haiku with Herd solved 44.3 stores, against 41.7 without. Its failures are one bug class, below.
- **Route quality is the same in every arm.** Once a store is solved, the time saved against list order is within a few points across all four arms. Herd buys robustness and evidence, not a better optimizer.
- **Herd costs about twice as much on Sonnet and eight times as much on Haiku.** A Herd run makes about 4 times as many model requests and reads 5 to 6 times as many tokens. On Haiku, many of those requests carry more than 100K tokens of context, where Haiku's price is five times higher.

### Is Haiku cheaper and as good?

This table and the bullets under it are about the four 0.3.1 arms; the 0.12.0 arm is compared in the next section.

| | Cost per run | Valid stores, of 48 | Bad inputs handled, of 6 | Runs fully clean |
| --- | --- | --- | --- | --- |
| Sonnet + Herd | $0.61 | 48.0 | 6.0 | 6 of 6 |
| Haiku + Herd | $0.29 | 44.3 | 6.0 | 1 of 6 |
| Sonnet, no workflow | $0.29 | 45.2 | 3.5 | 0 of 6 |
| Haiku, no workflow | $0.04 | 41.7 | 4.3 | 0 of 6 |

- **Cheaper, yes; the same results, no.** Haiku with Herd costs half as much as Sonnet with Herd and matches it on bad input, but fails 3.7 stores per run on average and was fully clean once in 6 runs.
- **For the same money, Haiku with Herd beats Sonnet without it on safety.** Both cost $0.29. Haiku with Herd handles every bad input (6.0 against 3.5) and solves about as many stores (44.3 against 45.2).
- **Haiku with no workflow is the cheapest by far** ($0.04, 15 times cheaper than Sonnet with Herd) and the least reliable.

### Why stores fail

- **One bug class explains almost every lost store: a sealed shelf side.** In the random-obstacle and department layouts, a shelf can border a pocket of floor that the picker cannot reach. A solution that always picks from one fixed side of the shelf (the first free neighbour) reports the product as unreachable although another side is open. Of the 77 lost stores in all 24 runs, 55 are this crash. The rest are timeouts (15, in three runs without Herd), a reported time that does not match the route (6, in two Sonnet runs without Herd) and one product the run refused because no free cell was next to it.
- **For 7 Haiku runs, the shelf side was chosen by the adapter.** Their map format takes the pick cell itself, not the shelf, so the adapter had to choose a side: by the spec it took the first free neighbour, as a naive user would, with no reachability check. That caused 28 of the lost stores (4 each in Haiku + Herd runs 3 to 6, Haiku without workflow runs 1, 3 and 4). Counting those 28 as solved, Haiku + Herd would solve 47.0 ± 2.4 stores and Haiku without workflow 43.7 ± 4.6. The Sonnet arms are unaffected.
- **Herd's attacks did not catch it in the Haiku runs.** The sealed side is a "disconnected" input. Herd's adversarial pass lists it among the extremes to try, but it is not one of the four enforced attacks, and several Haiku runs logged it as a known limit ("picked from the first walkable neighbour, not the better side") without testing whether it breaks the claim.

## Haiku with Herd 0.12.0, real sessions

**Method, and how it differs.** Each run is a real headless `claude -p` session (`--model claude-haiku-5-5`) with the plugin loaded from the installed 0.12.0 and all its hooks active: the Stop gate, the guard and the review hook. The builder spawns a Sonnet 5.5 reviewer, one tier above itself. Same one-paragraph prompt, an empty git repository, a spend cap of $10, no human answers. Every run ended with `herd done` passing. The four 0.3.1 arms were emulated sessions: no Stop hook fired and no reviewer ran. So this arm is not a repeat of the Haiku + Herd arm with a newer version; both the Herd version and the way it was run changed. Scoring is the same: the hidden verifier (48 stores, S 16, M 16, L 8, XL 8) and the six-scenario probe, through adapters written by a model from [`verifier/ADAPTER_SPEC.md`](verifier/ADAPTER_SPEC.md). When a solution takes a pick cell instead of the shelf, the adapter takes the first walkable neighbour (up, down, left, right) with no reachability check and no retry. Run 1 is an earlier single run on 0.12.0 whose extra-large tier was scored in a second pass; runs 2 to 6 were scored together.

| Run | Valid stores, of 48 | Bad inputs, of 6 | Time saved, mid (%) | Cost (USD) | Minutes |
| --- | --- | --- | --- | --- | --- |
| 1 | 48 | 6 | 68.9 | 1.07 | 30 |
| 2 | 41 | 6 | 67.2 | 0.56 | 10 |
| 3 | 48 | 6 | 68.2 | 0.44 | 15 |
| 4 | 48 | 6 | 68.6 | 0.75 | 20 |
| 5 | 44 | 6 | 68.3 | 0.68 | 19 |
| 6 | 48 | 6 | 70.1 | 1.08 | 37 |
| Mean ± sd | 46.2 ± 3.0 | 6.0 ± 0.0 | 68.5 ± 1.0 | 0.76 ± 0.26 | about 22 ± 10 |

Cost is the `total_cost_usd` in each session's result event, at API list prices. Haiku was about $0.27 to $0.67 per run and the Sonnet reviewers $0.17 to $0.52. Five runs ran at the same time on one machine, so minutes are rough.

- **Better than 0.3.1 on Haiku, not at Sonnet's level.** 46.2 against 44.3 stores, 4 of 6 runs fully valid against 1 of 6, bad input 6 of 6 in all six runs as before, at about 2.6 times the cost ($0.76 against $0.29). Sonnet with Herd 0.3.1 solved 48.0 and 6 of 6 runs. With six runs and a different method, the gap to 0.3.1 is a direction, not a measured effect of the version alone.
- **The two failing runs hit the old bug class.** Run 2 lost 7 stores and run 5 lost 4 (M random 0, M clusters 0 and 1, XL random 0): a product refused because the side of its shelf the solution tried first is sealed while another side is open. Run 2 takes the shelf but tries one neighbour order only; run 5 takes a pick cell from the caller, so part of that loss is the adapter's first-neighbour choice (see above).
- **Reviews found real things.** 21 review rounds in six runs: 6 returned FAIL with real findings (tracebacks on malformed input, a gap to the best route caused by fixing the side, a pick-order bug at the entrance, and README and test claims that disagreed with the code). 8 PASS rounds did not count because the reviewer had not read every changed file; `herd review-brief` in 0.12.1 fixes that, and these runs did not have it. The round counts were taken from the run logs and were not recounted when this section was written.

## What this does not show

- **The 0.12.0 arm is one cohort of six runs on one task, with a different method.** It was run as real sessions with hooks and a reviewer; the 0.3.1 arms were emulated without them. Differences between that arm and the others mix the Herd version, the method and run-to-run luck.

- **One task.** Six runs per arm measure the spread of results on this task, not on other kinds of work.
- **The 0.3.1 Herd runs are emulations.** No Stop hook fired and no fresh-context review happened, which a live session adds. Several Herd runs wrote code before their criteria and produced the "failed first" step by moving the code aside; their reports say so.
- **The no-workflow agents were not asked to test.** They might handle these cases if asked.
- **Timing is noisy.** Up to 12 runs were built at the same time and up to 5 were scored at the same time on one machine, so build times and plan times carry load from the others. Plan-time spreads are large for every arm.
- **Adapters are written by a model.** Every arm, including the 0.12.0 one, is scored through adapters that a model wrote from the spec, and for solutions that take a pick cell the adapter's side choice decides some stores.
- **Shared configuration.** All runs used the same Claude Code installation and global settings, so both arms in each pair saw the same environment.
- **Costs are estimates at list prices.** A subscription, a discount or a different cache mix changes them; the ratios between arms are the more stable figure.
- **Time saved is not compared like for like everywhere.** Some solutions end the route at the last pick and others return to the start; the verifier scores each against its own list-order route.

## History

The first version of this benchmark used one run per arm with Sonnet and Herd 0.2.4. Its two solutions are kept in [`with-herd/`](with-herd) and [`without-herd/`](without-herd) (Herd: 48 of 48 stores and 6 of 6 probe scenarios; without: 38 of 48 and 4 of 6), and the images are drawn from the first one. Its full write-up is in git history at commit `d4f11c6`.

## Reproduce

From the repository root. Scoring one run takes a few minutes; the extra-large stores take the longest.

```bash
sh examples/supermarket-route/verifier/score_run.sh sonnet-herd-1
```

```bash
python3 examples/supermarket-route/verifier/aggregate.py
```

```bash
python3 examples/supermarket-route/images/make_images.py
```

The raw output of every run is in [`runs/results/`](runs/results), and per-run tokens, requests, tool calls, time and cost are in [`runs/usage.json`](runs/usage.json).
