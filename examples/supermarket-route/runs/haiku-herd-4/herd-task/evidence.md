# Evidence: route-optimizer

Goal: Build a route optimizer for supermarket picking: given a store map with product locations (id, short name) and a customer shopping list (id:short name), compute a picking route for the delivery guy, simulate it step by step with live KPIs time-to-prepare-basket and distance-covered, and compare against the list-order route; the optimized route must save more than 30% time.
Run at 2026-11-23T08:07:38Z on commit c4086971762a plus uncommitted changes
Result: 5 passing, 0 failing, 0 unchecked
First verify: 5 of 5 checks failed before the work
Elapsed: 4m 35s from herd init to this verify; first verify at 1m 52s (wall clock, includes any waiting on the human)
Test budget: Unit tests (stdlib unittest) on generated layouts, one scale test on a 300x300 store, one demo-store savings test. Not tested: real supermarket maps, stores above 300x300, wall-clock timing on other machines, a UI.
Known limits: Savings depend on the layout and the basket. The 30% claim is shown on the demo store and on generated baskets, not guaranteed for every store. Stores with unreachable products are rejected, not planned around.
Adversarial pass: 6 attempts recorded; standard attacks all logged

| id | status | source | check |
| --- | --- | --- | --- |
| C1 | passing | human | `python3 -m unittest tests.test_layouts` |
| C2 | passing | agent-proposed | `python3 -m unittest tests.test_simulate` |
| C3 | passing | human | `python3 -m unittest tests.test_compare` |
| C4 | passing | human | `python3 -m unittest tests.test_savings` |
| C5 | passing | agent-proposed | `python3 -m unittest tests.test_edges` |

Coverage of human criteria (what each check proves and does not):
- C1: Proves planning on several generated layout shapes (open hall, aisles, maze, rooms) and one 300x300 store within a time limit; not real maps or stores above 300x300
- C3: Proves both KPIs are reported for the optimized and the list-order route and the comparison is computed from them; not a live UI
- C4: Proves the optimized route saves more than 30% time on the demo store and on the generated benchmark baskets; not every store or basket

Caveats during the run: 2 found, 1 fixed, 2 open
- 4m 16s found: CLI printed a traceback for a missing file, bad JSON, wrong field types and a missing product field
- 4m 16s fixed: main() returns exit 1 with one error line; Store.from_dict raises PlanError; regression test in tests/test_edges.py
- 4m 16s tried: every entry point: map file, basket file, map fields, product fields, unknown id, empty basket, usage args; tests/test_edges.py test_cli_bad_files_give_one_clear_message_and_exit_1 plus manual runs
- 4m 16s tried: two products on one cell both counted (test_two_products_on_one_cell_are_both_counted); duplicate basket line is rejected, not counted twice
- 4m 16s open: A duplicate basket line is rejected with an error; the request does not say what to do, so this is a choice
- 4m 17s tried: unrequested unreachable product does not reject the basket; requested unreachable product fails with a clear message (test_unrequested_unreachable_product_does_not_reject_the_basket)
- 4m 17s tried: separate Dijkstra script (outside the repo) recomputed list and optimized distance and time on demo store and a 60x40 generated store: all matched
- 4m 17s tried: scale: 300x300 aisle store with 80 picks planned and simulated in test_big_store_within_time_limit (limit 60 s)
- 4m 17s found: 30% saving does not hold for every basket: 33 of 200 random 10-item baskets on the demo store save 30% or less (mean 37.7%)
- 4m 17s open: Per-basket 30% claim fails on about 16% of random baskets on the demo store; the check asserts the mean over 20 baskets and the demo basket only
- 4m 17s tried: break attempts were run by this agent, not a fresh-context reviewer: no subagent is available in this run
Note: 11 notes were logged within 5 s of each other, so their times show when they were written, not when found.
