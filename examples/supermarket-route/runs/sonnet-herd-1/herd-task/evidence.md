# Evidence: route-opt

Goal: build a route optimizer for any supermarket
Run at 2026-11-23T08:02:35Z on commit c8cf853c1669
Result: 5 passing, 0 failing, 0 unchecked
First verify: 5 of 5 checks failed before the work
Elapsed: 3m 03s from herd init to this verify; first verify at 1m 49s (wall clock, includes any waiting on the human)
Test budget: Unit and CLI-level tests on synthetic stores (aisles, random blocks, open floor) with seeded random lists. Not tested: real store maps, one-way aisles, congestion, multiple pickers, weight or fragile ordering.
Known limits: Savings exceed 30% on lists of about 10 or more items (measured mean 35% at 10, 26% at 5, 16% at 3 on aisle stores). Short lists save less because pick time is fixed. Route is 2-opt plus relocate, not provably optimal. Time model: 1.2 m/s, 1 m cells, 8 s per pick, all adjustable.
Adversarial pass: 6 attempts recorded; standard attacks all logged

| id | status | source | check |
| --- | --- | --- | --- |
| C1 | passing | human | `python3 -m unittest tests.test_routeopt.Scale tests.test_routeopt.Savings.test_near_optimal_vs_brute_force_on_small_lists tests.test_routeopt.Savings.test_never_worse_than_list_order_distance` |
| C2 | passing | human | `python3 -m unittest tests.test_routeopt.Simulation tests.test_routeopt.Edges.test_cli_simulate_prints_each_step_with_live_kpis` |
| C3 | passing | human | `python3 -m unittest tests.test_routeopt.Savings.test_saves_over_30pct_time_on_every_layout_family` |
| C4 | passing | agent-proposed | `python3 -m unittest tests.test_routeopt.Edges.test_bad_input_every_entry_point` |
| C5 | passing | agent-proposed | `python3 -m unittest tests.test_routeopt.Edges` |

Coverage of human criteria (what each check proves and does not):
- C1: Proves valid routes on three generated layout families, scale: largest tried 300x300 cells (90000) with 40 items, limit 60 s (took about 6 s), and near-optimal on small lists. Not real maps or one-way aisles.
- C2: Proves one event per cell step with cumulative KPIs, recomputed from the trace by separate code, and a CLI that prints both routes step by step. Not wall-clock pacing beyond --delay.
- C3: Proves mean time saved above 30% (and min above 20%) over 15 seeded lists of 25 items on each of three layouts. Not short lists under 10 items: see known_limits.

Caveats during the run: 2 found, 0 fixed, 1 open
- 1m 53s found: Red step run with routeopt.py moved away: all 5 criteria failed; module had been drafted first (found at red)
- 2m 33s tried: tests.test_routeopt.Edges.test_bad_input_every_entry_point: map (missing, empty, not JSON, wrong type, ragged, bad char, no entrance, duplicate id, out of bounds, bad field type, binary), list (missing, empty, no colon, no id, unknown id, binary), options (speed, pick-s, cell-m): all exit 2, one error line, no traceback
- 2m 33s tried: tests.test_routeopt.Edges.test_collision_same_cell_and_repeated_item_all_counted: two products on one cell plus a repeated item, all 3 picks counted
- 2m 33s tried: tests.test_routeopt.Edges.test_unrequested_unreachable_product_is_ignored_requested_one_fails: cut-off product not on the list is ignored; requested one fails with a clear message
- 2m 33s tried: tests.test_routeopt.Simulation: distance, time, pick count and adjacency recomputed from the move events with separate code, with non-default speed, cell size and pick time
- 2m 33s tried: hostile inputs: 1x1 grid, enclosed product, 300-item list on 100x100 (11 s), list with colons and CRLF in names, 300x300 store with 40 items (6 s), three layout families, short lists
- 2m 33s found: lists of 3 to 5 items save under 30% (mean 16% and 26%): fixed pick time dominates
- 2m 33s open: Savings claim holds for lists of about 10 or more items only; 300-item lists take about 11 s (relocate step is cubic); not provably optimal
- 2m 34s tried: no fresh-context subagent available (cannot spawn): attacks done by the author, not fresh; review step also unavailable
Note: 8 notes were logged within 5 s of each other, so their times show when they were written, not when found.
