# Evidence: route-optimizer

Goal: Route optimizer for a supermarket map and shopping list, with a step-by-step simulation, KPIs and a comparison against list-order picking
Run at 2026-11-23T08:02:00Z on commit 4bd940621325
Result: 5 passing, 0 failing, 0 unchecked
First verify: 5 of 5 checks failed before the work
Elapsed: 2m 27s from herd init to this verify; first verify at 1m 13s (wall clock, includes any waiting on the human)
Test budget: Unit/integration tests on generated stores (aisles, open, maze) up to 400x400 cells and 40 items, plus CLI end to end. Not tested: real store maps, one-way aisles, shelf-side access, congestion, item weight or fragility.
Known limits: Savings depend on the list: lists of 1-3 items, or items already in pick order, save little. Heuristic (nearest neighbour + 2-opt), not provably optimal. Grid model with uniform walking speed and fixed pick time. Maps over about 1000x1000 cells get slow.
Adversarial pass: 5 attempts recorded; standard attacks all logged

| id | status | source | check |
| --- | --- | --- | --- |
| C1 | passing | human | `python3 -m unittest tests.test_routeopt.Savings tests.test_routeopt.Scale tests.test_routeopt.OneBadPart` |
| C2 | passing | human | `python3 -m unittest tests.test_routeopt.Recount tests.test_routeopt.Collisions` |
| C3 | passing | human | `python3 -m unittest tests.test_routeopt.Savings` |
| C4 | passing | agent-proposed | `python3 -m unittest tests.test_routeopt.BadInput` |
| C5 | passing | agent-proposed | `python3 -m unittest tests.test_routeopt.Scale.test_cli_end_to_end` |

Coverage of human criteria (what each check proves and does not):
- C1: Generated aisle, open and maze layouts, largest tried: 400x400 store with 40 items, time limit 60s; disconnected and blocked maps; not real maps or stores above 1000x1000
- C2: Replays the per-step trace with separate code: each move is one walkable cell, running distance and time match, every requested item is picked; not the live display
- C3: Time saved over 30% on 15 generated stores (3 layouts, 5 seeds, 20 items) and never worse than list order; within 10% of brute force on 7 items; not tiny lists

Caveats during the run: 1 found, 1 fixed, 1 open
- 2m 18s found: maze generator could seal the start (0 m route, 0% saving); a test expected the wrong access cell for a shelf product
- 2m 18s fixed: generator keeps a 3x3 open corner at start; test uses the nearest access cell
- 2m 18s tried: tests.test_routeopt.BadInput: missing/unreadable/non-JSON/malformed map, blocked start, ragged grid, missing/empty/binary/malformed list, unknown id, name mismatch, bad gen args: one error line, exit 2, no traceback
- 2m 18s tried: tests.test_routeopt.Collisions: two products on one cell and a repeated id are all picked (3 picks, time recomputed); duplicate map ids fail only if requested
- 2m 19s tried: tests.test_routeopt.OneBadPart: malformed, out-of-map and walled-off products not on the list are ignored; each requested one fails clearly
- 2m 19s tried: tests.test_routeopt.Recount replays the trace with separate code: adjacency, walkable cells, distance, time and pick counts match reported KPIs
- 2m 19s tried: scale: 800x800 aisle store, 2000 products, 40 items: 24 s wall, saved 76.9% time; 1-item list saves 0% (expected)
- 2m 19s open: heuristic (NN + 2-opt), not provably optimal; savings near 0 for lists of 1-3 items
Note: 8 notes were logged within 5 s of each other, so their times show when they were written, not when found.
