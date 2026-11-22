# Benchmark: the same prompt with and without Herd

**Question.** Given one short prompt, does an agent that follows Herd produce a better result than the same model with no workflow, and what does it cost?

**Task.** A route optimizer for a delivery person who picks a customer's shopping list inside a supermarket. It reads the store map and the list, finds the best route, simulates it step by step with live `time-to-prepare-basket` and `distance-covered`, and shows it saves more than 30 percent of the time against the list-order route. The prompt ([`prompt.md`](prompt.md)) is one paragraph, the way a person would ask in a vibe-coding session: it asks for something that works for any supermarket, even very big ones, whatever its layout, and gives no file formats, no scale numbers and no test requirements.

![Animation of one basket: list-order route against the optimized route](images/simulation.svg)

## The two runs

| | With Herd | Without Herd |
| --- | --- | --- |
| Model | Claude Sonnet | Claude Sonnet |
| Input | the prompt, as `/herd:run <prompt>` | the prompt, nothing else |
| Setup | a clean subagent that followed Herd's skills and ran the real `herd` CLI (version 0.2.4) | a clean subagent |
| Code | [`with-herd/`](with-herd) | [`without-herd/`](without-herd) |

Both are clean subagents in an empty git repository, so they ran under the same conditions. The Herd run is an emulation: it had no Stop hook and could not spawn a review subagent. The no-workflow run's transcript was audited: no skill calls, no Herd, no questions.

## How the results were checked

Neither agent saw these checks.

- **Hidden general verifier** ([`verifier/verify_general.py`](verifier/verify_general.py)). It generates stores from eight layout families (parallel aisles, vertical aisles, islands, random obstacles, comb, L-shape, maze corridors, department rooms) at four sizes, from 60 by 40 cells with 7 items up to 600 by 400 with 200 items. It asks each solution for its optimized and list-order routes as cell-by-cell traces and validates every one itself: legal moves, no walls, every item reached, distance and time recomputed. It compares against the exact optimum on small stores and against plain nearest-neighbour on larger ones. Its own tests use a reference solution and two cheating variants that it must reject.
- **Robustness probe** ([`verifier/robustness_probe.py`](verifier/robustness_probe.py)). The same small store with six scenarios through each solution's own command line: a normal run, an unknown product, a duplicate, an empty list, an unreachable product and a malformed map. A crash with a traceback counts as unhandled.

## Results

![Six measures, with and without Herd](images/benchmark.svg)

### Hidden verifier: 48 stores

| Store size | With Herd | Without Herd |
| --- | --- | --- |
| Small, 60 by 40, 7 items (16 stores) | 16 valid | 14 valid |
| Mid, 160 by 100, 40 items (16 stores) | 16 valid | 12 valid |
| Large, 400 by 300, 100 items (8 stores) | 8 valid | 6 valid |
| Extra large, 600 by 400, 200 items (8 stores) | 8 valid | 6 valid |
| **All** | **48 of 48** | **38 of 48** |

- **The failures are one bug.** All 10 are the same crash, `unreachable item`, on stores where a shelf borders a disconnected pocket of floor (the random-obstacle and department layouts). The no-workflow code treats the "unreachable" marker as the shortest distance, so one unreachable side of a shelf stops the whole basket. The Herd solution handled all of them.
- **Route quality is close, and not clearly better.**

| | With Herd | Without Herd |
| --- | --- | --- |
| Small stores, distance above the exact optimum | +0.4% | +0.2% |
| Mid stores, distance against plain nearest-neighbour | 8.8% shorter | 10.4% shorter |
| Large stores, same comparison | 11.4% shorter | 15.0% shorter |
| Extra large, same comparison | 10.9% shorter, never longer | 5.6% shorter, one store 40% longer |
| Time saved against list order (small / mid / large / extra large) | 23.9 / 64.6 / 77.4 / 82.7% | 25.5 / 67.1 / 77.3 / 81.7% |

  The no-workflow routes are slightly shorter on mid and large stores. The Herd routes held up on the extra-large tier, where one no-workflow route came out 40 percent longer than nearest-neighbour.
- **Planning time.** Median to plan a 400 by 300 store with 100 items: 8.9 s with Herd and 13.8 s without. For 600 by 400 with 200 items: 36.1 s and 72.7 s (limit 120 s per store).

![The optimized route on eight generated store layouts](images/layouts.svg)

### Robustness probe

| | With Herd | Without Herd |
| --- | --- | --- |
| Scenarios handled, of 6 | **6** | 4 |
| Crashed on | none | unreachable product, malformed map |
| Test lines | 119 | 20 |
| Code lines | 177 | 226 |

Herd's criteria skill requires an edge or failure case, so the Herd run wrote tests for them. The no-workflow agent was not asked and wrote 20 lines of checks. This probe therefore measures edge-case handling, not overall quality.

### Cost

| | With Herd | Without Herd |
| --- | --- | --- |
| Time to a finished result | 3m 19s | 1m 03s |
| Tokens | 87k | 73k |
| Tool calls | 11 | 5 |
| Questions to the human | 0 | 0 |

Herd took 3.2 times as long and used 19 percent more tokens. Inside the Herd run, the first `herd verify` (all four checks failing) came 1m 35s after `herd init`, and the evidence 3m 02s after it. Herd needs only the single message: it asked the person nothing.

### Did the run find the caveats itself?

The caveats below are what the hidden verifier shows. For each, did the run find and write it down before finishing?

| Caveat | With Herd | Without Herd |
| --- | --- | --- |
| Disconnected pockets of floor | handled (48 of 48 stores) | not found; crashes on 10 stores |
| Malformed maps and bad input | its adversarial pass found a crash on ragged or empty maps and an out-of-grid start, fixed it, and added regression tests | crashes on a malformed map |
| Layout variety | the C1 check covers four layout families and says so in its `coverage` note | tests use one store generator |
| Scale | C1 includes a 250 by 250 store with 120 items inside a time bound; `known_limits` says stores of 400 by 400 and above with 150 or more items take 20 s or more | not tested |
| The 30% claim depends on basket size | `known_limits` says baskets of about 15 items or fewer can fall below 30%, with 27% observed; the hidden verifier agrees (23.9% on 7-item baskets) | reported "34% to 71%" saved, with the small basket as its weakest case |
| Pick time dilutes the saving | in `known_limits` | mentioned in the final text |

The Herd run wrote these into checks and a stated limits field before it finished: its evidence report ([`with-herd/evidence.md`](with-herd/evidence.md)) lists the criteria, a `coverage` note per human criterion saying what each check does and does not prove, the known limits, and the caveats it logged with `herd note`.

## What this does not show

- **One run per arm, one model, one task.** Differences in time or quality may be partly chance.
- **Red-first was gamed.** The Herd run wrote its code before finalizing the criteria. For the "all checks failed first" step it moved the source files aside, ran `herd verify`, and moved them back. Its report says so, but Herd cannot detect it, so "failed first" is visibility, not proof.
- **The Herd run is an emulation.** No Stop hook fired and no fresh-context review happened (a subagent cannot spawn one). A real session adds both.
- **The caveat log was logged in one batch.** All four `herd note` entries carry the same timestamp, so they show when the agent wrote them down, not when each was found. Herd 0.2.5 now flags this in the report.
- **The robustness probe partly measures Herd's own rules.** It tests edge cases, which is what Herd asks agents to write tests for.
- **A random walk is an easy opponent**, so this benchmark compares against the list-order route. The 30 percent saving does not hold for small baskets for any solution, including a perfect one.
- **The no-workflow agent might handle these cases if asked.**

Earlier exploratory runs (an Opus pair, a Haiku pair, and a live-session Sonnet run on Herd 0.2.2), together with the log of issues the test found in Herd, were removed from this folder to keep it focused. They are in git history at commit `d7be0e8`.

## Reproduce

From the repository root:

```bash
python3 examples/supermarket-route/verifier/verify_general.py with_herd examples/supermarket-route/with-herd
python3 examples/supermarket-route/verifier/verify_general.py without_herd examples/supermarket-route/without-herd
python3 examples/supermarket-route/verifier/robustness_probe.py
python3 examples/supermarket-route/images/make_images.py
```

The first two take a few minutes each. Add `--tiers S,M,L,XL --limit-scale 0.4` to include the extra-large tier within the same time limits used here. The raw outputs of the runs are in [`results/`](results).
