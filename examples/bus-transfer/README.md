# Example: a bus transfer planner

Benchmark 2, next to [`supermarket-route`](../supermarket-route). The same prompt goes to several runs, with and without Herd, and a hidden verifier scores the code each run wrote. It checks Herd on a second, different task: earliest arrival on a timetable, not a route in a store.

| | |
| --- | --- |
| [`prompt.md`](prompt.md) | the prompt every run receives, verbatim |
| [`verifier/bus_verify.py`](verifier/bus_verify.py) | the hidden verifier: generators, the oracle, the journey checks |
| [`verifier/bus_probe.py`](verifier/bus_probe.py) | the hidden robustness probe: 6 bad inputs |
| [`verifier/bus_reference.py`](verifier/bus_reference.py) | the reference solver and two wrong solvers, used only by the verifier and its tests |
| [`verifier/ADAPTER_SPEC.md`](verifier/ADAPTER_SPEC.md) | what an adapter must do, given to the agent that writes one |
| [`verifier/test_bus_verify.py`](verifier/test_bus_verify.py) | tests of the verifier itself; hidden too, since it holds a working solver |

## Method

The prompt is what a median person would ask. It does not say how times are written, what "a few minutes" is, or what a timetable file looks like: each run chooses. An adapter per run (written by a fresh agent from `ADAPTER_SPEC.md`, as for the supermarket) maps the verifier's network to the run's own format and its answer back.

Hard by design:

- Earliest arrival on a timetable. A static graph search (Dijkstra on stops) is wrong: a bus that has left cannot be taken.
- Waiting at a stop, trips past midnight (up to 30:00), staying on one bus (no change time) against changing (the minimum applies), trips that overtake each other.
- Scale: networks of up to 6000 stops and tens of thousands of trips (from about 24000 to about 90000, depending on the family), with a time limit per network.
- A refusal is a claim: "not possible" is accepted only when the oracle finds no journey.

The verifier makes networks from six families (small hand cases, random, grid, radial, clusters with few links, overnight) at sizes S, M, L and XL, with `--seeds` seeds per family and size (default 2). Each network has several queries. A case is valid when it finishes in time and every query is right:

- every leg is a real trip, leaves and arrives when the timetable says, and the first leg leaves at or after the departure time;
- every change takes at least the minimum change time (4 minutes in the verifier); staying on one bus needs none;
- the arrival equals the oracle's earliest arrival (a connection scan, apart from the reference solver);
- "not possible" only when the oracle finds nothing.

Decisions the verifier makes for the prompt's open words, so any reading is judged fairly:

- One global change time, passed to the adapter in `min_change`. A journey reported one leg per ride or one per stop-to-stop hop is judged the same.
- A timetable is one service day. A generated query is either solvable that day or has no bus path at all, so it does not matter whether a run lets timetables repeat the next day.
- "Departure time": leave at or after it.
- A timetable has one time per stop (arrival equals departure), so a run that stores a single time loses nothing.
- The probe counts no bad input as handled when the project fails the normal scenario.
- Output that is not UTF-8 fails the case (or the probe scenario) without stopping the run. A selection with no cases (hand cases exist at size S only) is an error, never a pass.

The reference solver is a reachability search over waiting and riding. `bus_verify.py reference` must pass every case; `static` (plain Dijkstra on stops, then follow the path) and `nochange` (ignores the change time) must fail the time-dependent and the change cases. `verifier/test_bus_verify.py` checks all three, and checks the oracle, the reference solver and a plain search against each other on generated and purely random networks.

## Run isolation

Same as the supermarket benchmark: the Herd plugin installs without `examples/` (Herd 0.12.10 and later), but the repository is public, so `run_leg.py` starts every run in a sandbox that denies your home folder, the other runs and legs, and the network, and refuses to start while a copy of a hidden file (`bus_verify.py`, `bus_probe.py`, `bus_reference.py`, or the supermarket ones) is readable. The script is shared: pass `--task bus-transfer` (or `--task examples/bus-transfer/`) and it takes the prompt from `prompt.md`.

```
python3 examples/supermarket-route/verifier/run_leg.py --name haiku-herd-v0.12.10 --runs 6 \
  --model claude-haiku-5-5 --task bus-transfer --herd-tag v0.12.10
python3 examples/supermarket-route/verifier/run_leg.py --name haiku-plain --runs 6 \
  --model claude-haiku-5-5 --task bus-transfer
```

Audit each run's log, which also reports a hidden file found in the run's work folder:

```
python3 examples/supermarket-route/verifier/leak_audit.py RUN.jsonl --work <root>/run-N/work --task bus-transfer
```

Read the isolation details in [`../supermarket-route/README.md`](../supermarket-route/README.md#run-isolation). Results count only for runs whose audit prints `leak audit: clean`. Run `run_leg.py --selftest` first on a new machine.

## How to score

Per run, after it finishes and its audit is clean, give a fresh agent `verifier/ADAPTER_SPEC.md` and the run's folder (read only) and have it write `adapter.py`. Then, from the repository root:

```
python3 examples/bus-transfer/verifier/bus_probe.py RUN=<run>/work:<adapter.py>
python3 examples/bus-transfer/verifier/bus_verify.py file:<adapter.py> <run>/work --tiers S,M,L,XL --seeds 2
```

Report per leg: valid cases (mean and standard deviation across runs, from `CASES valid N of M`), runs with all cases valid, bad inputs handled of 6, cost per run, active minutes and the Herd version. The bar for Herd is 6 of 6 runs with all cases valid. Add `--json FILE` to keep one row per case. Check the verifier itself with `python3 -m unittest discover -s examples/bus-transfer/verifier -p 'test_bus_verify.py'`. It checks sizes S to L; set `BUS_FULL=1`, as CI does, to add XL.

No leg has run yet: this folder holds the task and its verifier. The legs and their numbers are added to a `BENCHMARK.md` here when they run.
