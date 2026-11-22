# Evidence: supermarket-router

Goal: Build a supermarket route optimizer: input a map with product locations plus a shopping list, output the picker route; simulate step by step with live KPIs time-to-prepare-basket and distance-covered, compared against list-order route; show more than 30% time saving
Run at 2026-11-22T20:33:22Z on commit 7f2275b34bff
Result: 4 passing, 0 failing, 0 unchecked
First verify: 4 of 4 checks failed before the work
Elapsed: 3m 02s from herd init to this verify; first verify at 1m 35s (wall clock, includes any waiting on the human)
Test budget: Unit/integration in test_router.py: 4 layout families (aisles, open floor, maze, ring) x several seeds validated by replaying the simulation (adjacent walkable steps, every item picked at its cell, ends at start); extremes (empty list, one item, 1x2 map, duplicates, unknown ids, walled-off products); one 250x250 store with 120 items under 60s; CLI end to end with files. Not tested: real store maps, one-way aisles, shelf-side picking (products must sit on walkable cells), congestion, multiple pickers, optimality (heuristic, no exact comparison).
Known limits: Saving is measured with assumed constants (1.4 m/s, 8 s per pick, 1 cell = 1 m) on synthetic stores with random-order lists of 30 items. Small baskets (about 15 items or fewer) can fall under 30% (observed min 27% in aisle and ring stores at 15 items) because pick time is fixed and dominates. Stores above about 300x300 cells with 200+ items take 10s+ (pure-Python BFS plus O(n^2) 2-opt). Result is a heuristic tour, not proven optimal.
Adversarial pass: 1 attempt recorded

| id | status | source | check |
| --- | --- | --- | --- |
| C1 | passing | human | `python3 -m unittest test_router.AnyLayout` |
| C2 | passing | human | `python3 -m unittest test_router.Cli` |
| C3 | passing | human | `python3 -m unittest test_router.Simulation` |
| C4 | passing | human | `python3 -m unittest test_router.Saving` |

Coverage of human criteria (what each check proves and does not):
- C1: proves: valid routes (replayed step by step) on 4 generated layout families x 6 seeds, extremes (empty, single item, 1x2 map, duplicates, unknown, walled-off products reported not crashed), and a store at the largest size tried, 250x250 cells with 120 items, in under 60s (scale limit 60s). does not prove: real store maps, one-way aisles, stores bigger than 250x250, shelf-side picking.
- C2: proves: CLI reads a JSON map (grid, start, products with id/name/pos) and an id:short name list file, exits 0 on valid input and 2 with an 'unknown' warning on an unknown id. does not prove: other map file formats, names matching ids (only ids are used for routing).
- C3: proves: one event per step with running distance and time that never decrease, final KPIs equal moves and picks recomputed independently, --trace prints both KPI names per step for both routes. does not prove: wall-clock real-time pacing (events are a generator, a UI can pace them).
- C4: proves: over 4 families x 12 seeds with 30-item random-order lists in 61x81 stores both the mean and the minimum time saving exceed 30%, and optimized is never slower than list order on small 8-item baskets. does not prove: the claim for small baskets under about 15 items, other speed/pick constants, real stores.

Caveats during the run: 1 found, 1 fixed, 1 open
- 2m 38s tried: stress: 150x150 aisles store with 1000 items (18s, saving 0.88), 301x301 maze 100 items (5s), 400x400 open floor 150 items (23s); malformed maps (ragged rows, empty grid, start outside grid, blocked start, product off-map)
- 2m 38s found: ragged/empty grid and out-of-grid start crashed with IndexError instead of a clear error
- 2m 38s fixed: Store validates grid/start and raises ValueError; CLI prints 'bad map' and exits 1; regression tests added
- 2m 38s open: 400x400 stores take ~23s (pure Python BFS per item); small baskets (~15 items) can save under 30% (min 27% observed)
