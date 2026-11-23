# Evidence: route-optimizer

Goal: Supermarket route optimizer: map + shopping list in, optimized pick route out, step-by-step simulation with live time and distance KPIs vs list-order route, over 30% time saved
Run at 2026-11-23T08:03:10Z on commit 73d977ef92a3 plus uncommitted changes
Result: 5 passing, 0 failing, 0 unchecked
First verify: 5 of 5 checks failed before the work
Elapsed: 3m 37s from herd init to this verify; first verify at 1m 51s (wall clock, includes any waiting on the human)
Test budget: Unit/CLI level on generated stores: 4 layout families x 5-8 seeds at 40x30 to 60x40, one 300x300 scale run. Not tested: real store maps, stores over 300x300, lists over 50 items, products reachable from several shelf sides, one-way aisles, congestion.
Known limits: Saving depends on list size and pick time: lists under about 14 items (one 12-item demo saved 27.8%), or very long pick times (PICK_S), can fall below 30%. Heuristic (nearest neighbour + 2-opt + Or-opt), not provably optimal. Each product is picked from one fixed access cell (nearest to the start).
Adversarial pass: 5 attempts recorded; standard attacks all logged

| id | status | source | check |
| --- | --- | --- | --- |
| C1 | passing | human | `python3 -m unittest tests.test_router.TestLayouts tests.test_router.TestScale` |
| C2 | passing | human | `python3 -m unittest tests.test_router.TestSimulation` |
| C3 | passing | human | `python3 -m unittest tests.test_router.TestSavings` |
| C4 | passing | agent-proposed | `python3 -m unittest tests.test_router.TestBadInput` |
| C5 | passing | agent-proposed | `python3 -m unittest tests.test_router.TestCollisionAndBadPart` |

Coverage of human criteria (what each check proves and does not):
- C1: Proves valid routes (walkable, all items, ends at checkout) on 20 generated stores of 4 layout families plus odd shapes, and a 300x300 store (largest size tried) within a 90 s limit; not real maps or larger.
- C2: Proves the CLI prints both KPIs and a per-step trace whose distance and time are recounted from the CSV by separate code; not that the live mode paces in wall-clock time.
- C3: Proves time saved over the list-order route is above 30% on each of 32 generated 15-item cases (4 layouts, 8 seeds); not lists of fewer than 8 items or other pick-time settings.

Caveats during the run: 1 found, 1 fixed, 1 open
- 3m 11s found: unwritable --trace path (and gen outdir) gave a traceback, not an error line
- 3m 26s fixed: OSError now caught in run and gen: one error line, exit 2; regression in TestBadInput
- 3m 26s tried: TestBadInput: missing, directory, invalid JSON, non-object, ragged grid, bad start, empty/comment-only list, bad list line, unknown id, bad flags, unwritable trace/gen path; plus manual CLI runs
- 3m 26s tried: TestCollisionAndBadPart: two products on one shelf cell, equal names, repeated list id: all 4 picks counted; duplicate map id rejected
- 3m 26s tried: TestCollisionAndBadPart: unreachable, malformed, id-less and garbage unrequested products ignored; requested unreachable or malformed fails clearly
- 3m 26s tried: TestSimulation recomputes dist and time from the trace CSV (move rows, pick rows) with separate code, plus check_route validates adjacency, walkability and picks
- 3m 26s tried: layouts: aisles, open, maze, perimeter x seeds; 1x1 store; corridor with disconnected pocket; 500x500 with 60 items in 6s; 300 items on 100x100 in 1s
- 3m 26s open: saving is below 30% for lists under about 8 items (0% for 2-3 items) and for some 12-item lists (27.8% on one demo); heuristic not optimal; one fixed access cell per product
Note: 7 notes were logged within 5 s of each other, so their times show when they were written, not when found.
