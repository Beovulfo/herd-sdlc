# Evidence: route-optimizer

Goal: Build a route optimizer for supermarket picking: find the shortest delivery-guy route through any store layout, simulate it step by step with live KPIs time-to-prepare-basket and distance-covered, and compare against the list-order route, proving more than 30 percent time saved.
Run at 2026-11-23T08:23:12Z on commit 2a01140e4ce6 plus uncommitted changes
Result: 6 passing, 0 failing, 0 unchecked
First verify: 6 of 6 checks failed before the work
Elapsed: 20m 07s from herd init to this verify; first verify at 2m 01s (wall clock, includes any waiting on the human)
Test budget: Unit tests on generated and hand-made layouts (open hall, aisles, comb, dead ends), one 300x300 store with 40 items under a 60 s limit, seeded benchmark of 50 random baskets on a 200x200 store. Not tested: real supermarket maps, real pick times, stores above 300x300.
Known limits: The saving depends on the baseline: the list-order route is the customer's list order, shuffled in the benchmark. A list already in walking order saves much less. Pick time is a fixed constant, so it dilutes the saving. The 2-opt heuristic is not guaranteed optimal.
Adversarial pass: 5 attempts recorded; standard attacks all logged

| id | status | source | check |
| --- | --- | --- | --- |
| C1 | passing | human | `python3 -m unittest tests.test_layouts` |
| C2 | passing | human | `python3 -m unittest tests.test_input` |
| C3 | passing | human | `python3 -m unittest tests.test_route` |
| C4 | passing | human | `python3 -m unittest tests.test_simulation` |
| C5 | passing | human | `python3 -m unittest tests.test_benchmark` |
| C6 | passing | agent-proposed | `python3 -m unittest tests.test_edges` |

Coverage of human criteria (what each check proves and does not):
- C1: Proves valid routes over generated inputs of 4 layout families (open hall, aisle grid, comb, dead ends) at several seeds and sizes, plus a scale run: 300x300 store, 40 items, under 60 s. Not real maps or stores above 300x300
- C2: Proves the map and basket file formats load and bad files fail with one clear message; not other input formats
- C3: Proves each basket stop is visited once and the optimized walk is never longer than the list-order walk on generated layouts; does not prove global optimality
- C4: Proves every step moves to a walkable neighbour and the live KPIs equal a separate recount from the trace; does not measure wall-clock real time
- C5: Proves the median and minimum time saving over 50 seeded random baskets are above 30 percent on a 200x200 store; not other stores or basket sizes

Caveats during the run: 4 found, 4 fixed, 2 open
- 15m 35s found: BFS early-stop: with no targets the search stopped at once, so every product looked unreachable (test_layouts caught it)
- 15m 35s fixed: BFS explores fully when no targets are given
- 15m 35s found: distance matrix ran one BFS per pair of stops, about 40 times too slow on the 300x300 store
- 15m 35s fixed: one BFS per stop; 300x300 store with 40 items plans in seconds
- 15m 35s found: benchmark CLI gave a Python traceback for bad counts (items above products, items 0, baskets 0, too many products)
- 15m 35s fixed: benchmark and make_store raise RouteError, so the CLI exits 2 with one error line
- 15m 35s found: one broken product entry in the store map (on a wall, no name, duplicate id) rejected the whole map
- 15m 35s fixed: broken product entries now fail only the baskets that request them; regression test in tests/test_input.py
- 15m 35s tried: CLI probes: missing store and basket files, unreadable basket, binary basket, empty basket, malformed line, unknown id, grid given as a number, entrance on a wall, JSON file used as basket, bad --order, bad --delay, bad benchmark counts. All exit 2 with one error line; tests/test_input.py covers the file cases
- 15m 36s tried: basket line A:milk twice counts two picks (30.7 s); two products on one cell both picked at one stop; tests/test_route.py test_collision_same_cell_counted_twice
- 15m 36s tried: unreachable product not in the basket (enclosed cell) and broken map entries not in the basket do not block; tests/test_edges.py and tests/test_input.py
- 15m 36s tried: separate script att/recount.py parses the run trace text only: 143.2 s and 95.0 m match, 30.7 s and 8.0 m match; tests/test_simulation.py also recounts from the trace
- 15m 36s tried: quantifiers: four layout families (open hall, aisle grid, comb, maze) over seeds and sizes 12x9 to 61x40, enclosed cell, single item at entrance, 300x300 store with 40 items under 60 s (tests/test_layouts.py)
- 15m 36s open: benchmark test takes about 100 s on this machine; its check has timeout_s = 400
- 15m 36s open: 2-opt is a local optimum: the walk is not proven shortest; known_limits says so
Note: 15 notes were logged within 5 s of each other, so their times show when they were written, not when found.
