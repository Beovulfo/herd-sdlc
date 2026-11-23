# Evidence: route-optimizer

Goal: Route optimizer for the supermarket picker: map and shopping list in, optimized route plus step simulation with KPIs out, compared with list order
Run at 2026-11-23T08:05:25Z on commit 359d5da52243
Result: 6 passing, 0 failing, 0 unchecked
First verify: 6 of 6 checks failed before the work
Elapsed: 5m 58s from herd init to this verify; first verify at 3m 37s (wall clock, includes any waiting on the human)
Test budget: Unit/integration on generated stores: 4 layout families (aisles, islands, open, maze) x seeds, lists of 10-40 items, up to 300x300 cells and 3000 products. Optimality is checked against brute force only on 6-item lists. Not tested: real store maps, one-way aisles, queues, item weight, multi-picker.
Known limits: The 30% claim holds for lists of about 10 or more items in generated stores with random list order; short lists (1-3 items) or a list already in shelf order save little. Above 10 stops the order is a heuristic (2-opt plus or-opt), not proven optimal. Walk speed 1.2 m/s and 5 s per pick are assumptions, configurable in code only. Map is a grid; the picker uses the first reachable cell next to a shelf.
Adversarial pass: 5 attempts recorded; standard attacks all logged

| id | status | source | check |
| --- | --- | --- | --- |
| C1 | passing | human | `python3 -m unittest tests.test_route_optimizer.Scale && python3 -m unittest tests.test_route_optimizer.Saving.test_over_30_percent_every_layout` |
| C2 | passing | human | `python3 -m unittest tests.test_route_optimizer.Saving.test_optimal_on_small_lists && python3 -m unittest tests.test_route_optimizer.Saving.test_heuristic_close_to_optimal` |
| C3 | passing | human | `python3 -m unittest tests.test_route_optimizer.Simulation && python3 -m unittest tests.test_route_optimizer.Cli` |
| C4 | passing | human | `python3 -m unittest tests.test_route_optimizer.Saving.test_over_30_percent_every_layout` |
| C5 | passing | agent-proposed | `python3 -m unittest tests.test_route_optimizer.BadInput` |
| C6 | passing | agent-proposed | `python3 -m unittest tests.test_route_optimizer.Collision && python3 -m unittest tests.test_route_optimizer.OneBadPart` |

Coverage of human criteria (what each check proves and does not):
- C1: Proves route found and >30% saving on 4 generated layout families, and largest tried 301x301 cells, 3000 products, 60 items, limit 30s each; not real maps.
- C2: Proves exact optimum on 6-item lists (vs brute force) and heuristic within 8% of optimum on 9 items; not optimality on large lists.
- C3: Proves each step is a legal adjacent move, all items picked, KPIs recomputed from the trace by separate code, and the CLI prints both KPIs; not wall-clock pacing.
- C4: Proves time saving above 30% for 20 generated stores, lists of 10-40 items; short lists may save less.

Caveats during the run: 1 found, 1 fixed, 1 open
- 4m 50s tried: BadInput tests: 15 malformed map cases, missing/dir/binary map and list files, empty list, unknown id, bad gen --out path, no args; each one error line exit 2, no traceback
- 4m 50s tried: Collision test: two products on one cell with same name, repeated list ids; all 4 picks counted (items=4/4)
- 4m 50s tried: OneBadPart tests: out-of-grid, id-only, non-dict, bad-type records and unreachable product not requested still run; requested broken or unreachable fails with id named
- 4m 51s tried: test_trace_recount: distance and time recomputed from the event trace with literal constants and a separate BFS, adjacency and wall checks
- 4m 51s tried: Hostile scale: 301x301 maze, 300x300 aisles and islands; 1-cell store; 150-item list on 100x150 aisles
- 4m 51s found: Heuristic missed optimum by 2m on a 6-item list (open layout), found by brute-force test
- 4m 51s fixed: Added exact Held-Karp order up to 10 stops; heuristic kept above, tested within 8% of optimum
- 4m 51s open: 150-item basket takes 23s (2-opt/or-opt is O(n^3) per pass); fine for baskets up to about 50 items
Note: 8 notes were logged within 5 s of each other, so their times show when they were written, not when found.
