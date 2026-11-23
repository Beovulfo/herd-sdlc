# Evidence: route-optimizer

Goal: Supermarket route optimizer with step-by-step simulation and KPIs vs list-order
Run at 2026-11-23T08:03:50Z on commit 89d9cc11bbe7
Result: 6 passing, 0 failing, 0 unchecked
First verify: 6 of 6 checks failed before the work
Elapsed: 4m 17s from herd init to this verify; first verify at 1m 47s (wall clock, includes any waiting on the human)
Test budget: Unit/integration tests on generated maps (aisles, islands, random, open, disconnected; up to 200x200). Not tested: real store maps, congestion, multi-picker, shelf-side access choice, travel-time limits above 60s.
Known limits: Savings depend on list size: tiny lists (1 to 3 items) may save under 30 percent. Lists over 12 items use a heuristic (nearest neighbour + 2-opt + or-opt), not proven optimal. One pick cell per product (nearest to start). Unit-cost grid moves, no congestion.
Adversarial pass: 5 attempts recorded; standard attacks all logged

| id | status | source | check |
| --- | --- | --- | --- |
| C1 | passing | human | `python3 -m unittest tests.test_router.Layouts` |
| C2 | passing | human | `python3 -m unittest tests.test_router.Inputs` |
| C3 | passing | human | `python3 -m unittest tests.test_router.Simulation` |
| C4 | passing | human | `python3 -m unittest tests.test_router.Savings` |
| C5 | passing | agent-proposed | `python3 -m unittest tests.test_router.BadInput` |
| C6 | passing | agent-proposed | `python3 -m unittest tests.test_router.Optimality` |

Coverage of human criteria (what each check proves and does not):
- C1: Proves valid walkable routes on 4 generated layout families, many sizes and seeds, a 200x200 map with 2000 products under 60s, and a disconnected map. Not real store maps.
- C2: Proves the CLI reads a JSON map file with id, name and x,y per product plus an id:name list file, and parses the list format. Not other map file formats.
- C3: Proves one event per step and pick with running distance and time, monotonic, matching an independent replay recount; --trace prints each step. Not wall-clock pacing.
- C4: Proves over 30 percent time saved on every one of 32 runs (4 layouts, 8 seeds, 20-item lists on 60x40, 200 products). Not tiny lists or real baskets.

Caveats during the run: 2 found, 1 fixed, 1 open
- 1m 50s found: draft router.py existed before red run; hid it so checks failed for the right reason (all 6 failed)
- 2m 27s tried: probed NaN speed, directory as map, unwritable gen path, negative/float coords, missing list arg, empty list
- 2m 27s found: NaN walk_speed accepted (json allows NaN); gen to unwritable path gave a traceback
- 2m 28s fixed: NaN/inf rejected via isfinite; gen write errors caught; regression tests added
- 3m 44s tried: test_collision_same_cell_and_duplicate_ids_all_counted: two products on one cell plus a repeated list id, 3 picks counted; duplicate map ids warn, first kept
- 3m 44s tried: test_one_bad_unrequested_product_does_not_reject_map (out-of-map, malformed, junk, float coords) and test_walled_in_requested_product_fails_clearly and disconnected-pocket test
- 3m 45s tried: replay() in tests recomputes steps, adjacency, walkability, pick location and time from the event stream with separate code; also brute-force optimality (C6)
- 3m 45s tried: scale: random 200x200 100 items 6s, islands 300x150 150 items 13s, open 250x250, aisles 400x60; savings 78-85%; corridor and single item saves 0% (open limit)
- 3m 45s open: 1 to 3 item lists can save under 30%; heuristic above 12 items; one pick cell per product
Note: 5 notes were logged within 5 s of each other, so their times show when they were written, not when found.
