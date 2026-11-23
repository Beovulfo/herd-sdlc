# Evidence: route-optimizer

Goal: Build a route optimizer for a supermarket delivery picker: given a store map with product locations and a customer shopping list, find a short picking route, simulate it step by step with time-to-prepare-basket and distance-covered KPIs, and compare against the list-order route (target: more than 30% time saving).
Run at 2026-11-23T08:10:17Z on commit c4086971762a plus uncommitted changes
Result: 6 passing, 0 failing, 0 unchecked
First verify: 6 of 6 checks failed before the work
Elapsed: 7m 09s from herd init to this verify; first verify at 2m 31s (wall clock, includes any waiting on the human)
Test budget: Unit tests on generated stores: 4 layout families x 25 seeds (library level, plus CLI for bad input); one 300x300 store with 1000 products and a 60-item list under 120 s; a 20-seed benchmark of 60x40 aisle stores. Not tested: real supermarket maps, the speed of real pickers, moves that are not one grid cell at a time.
Known limits: The 30% claim holds on generated aisle stores with random customer list orders (mean 61.9%, min 55.3%); it is not shown for real stores. Time is a model (1 s per cell, 5 s per pick), not a measurement of people. The optimizer is nearest-neighbour plus 2-opt, not provably optimal: on 7-item lists it matched the brute-force optimum in 37 of 40 stores, worst 13% longer. Scale: 300x300 with 60 items runs in 7.5 s; 500x500 with 100 items took 31 to 35 s, not under a check.
Adversarial pass: 6 attempts recorded; standard attacks all logged

| id | status | source | check |
| --- | --- | --- | --- |
| C1 | passing | human | `python3 -m unittest test_routeopt.Layouts test_routeopt.Scale` |
| C2 | passing | human | `python3 -m unittest test_routeopt.Simulate` |
| C3 | passing | human | `python3 -m unittest test_routeopt.Compare` |
| C4 | passing | human | `python3 routeopt.py bench --min-saving 30` |
| C5 | passing | agent-proposed | `python3 -m unittest test_routeopt.BadInput` |
| C6 | passing | agent-proposed | `python3 -m unittest test_routeopt.Collision` |

Coverage of human criteria (what each check proves and does not):
- C1: Proves valid, complete routes on generated open, aisle, random-wall and split layouts over many seeds, and one 300x300 store with a time limit. Does not prove real store plans or layouts with more than 1000 products.
- C2: Proves each simulated move is one free cell and the printed KPIs match a separate recount of the step lines. Does not prove wall-clock pacing of the output.
- C3: Proves the compare output reports both routes with the same picks, and the optimized route is never longer than the list-order route. Does not prove the customer's list order is realistic.
- C4: Proves the mean time-to-prepare-basket saving is above 30% over 20 generated aisle stores with random list orders, and prints the min and max. Does not prove a saving for real stores or for other layouts.

Caveats during the run: 2 found, 1 fixed, 3 open
- 6m 44s tried: CLI probe and BadInput tests: missing, directory, malformed JSON, wrong-type rows, no or two entrances, unknown char, unknown id, empty list, binary list, unreachable, wall cell. Each one exit 2, one error line, no traceback.
- 6m 49s found: bench --seeds 0 gave ZeroDivisionError traceback; --step-s -1 gave negative times; gen --list-size 0 wrote an empty list
- 6m 49s fixed: argument checks added in routeopt.py; regression tests in test_routeopt.BadArguments
- 6m 49s tried: Collision tests: two products on one cell both picked; repeated list lines counted twice; duplicate product id on map is unusable when requested
- 6m 50s tried: BadInput.test_unrequested_broken_entry_is_skipped_with_warning: unrequested out-of-map and duplicate entries warn and skip; requested broken entries still exit 2
- 6m 50s tried: Simulate.test_cli_trace_recount_matches_kpis: recount() in the test reads CLI step/pick lines and raw rows, separate from routeopt code; Compare test recomputes the saving formula
- 6m 50s tried: Quantifiers: 4 layout families x 25 seeds; 80x60 families x 5 seeds (20 stores, all valid); 300x300 store with 1000 products and 60 items (7.5 s); corridor, one-cell map, all-wall map, 1x1 map with products on entrance
- 6m 50s tried: Scale probe, outside the suite: 500x500 aisles with 1000 products and 100 items took 31 s; 500x500 random took 35 s. Both valid routes.
- 6m 50s found: 2-opt route is not always optimal: vs brute force on 40 aisle stores with 7 items, exact in 37, worst gap 13.2% longer
- 6m 50s open: 2-opt gap: worst case 13% longer than optimum on 7-item lists; not provably optimal
- 6m 51s open: scale: 500x500 with 100 items takes about 31 to 35 s, not in any check; run time grows with map cells times items
- 6m 51s open: 30% claim is measured against random list orders on generated aisle stores; no real store data
Note: 11 notes were logged within 5 s of each other, so their times show when they were written, not when found.
