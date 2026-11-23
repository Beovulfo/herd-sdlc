# Evidence: route-optimizer

Goal: Supermarket route optimizer: plan the delivery guy's shortest pick route through any supermarket layout, with step-by-step simulation, KPIs time-to-prepare-basket and distance-covered, and a comparison against the list-order route showing more than 30% time saved.
Run at 2026-11-23T08:13:39Z on commit c4086971762a plus uncommitted changes
Result: 5 passing, 0 failing, 0 unchecked
First verify: 5 of 5 checks failed before the work
Elapsed: 10m 37s from herd init to this verify; first verify at 2m 42s (wall clock, includes any waiting on the human)
Test budget: Unit and generated-layout tests run in-process on synthetic maps (seeded random layouts of several shapes, plus one 200x200 scale run with a time limit). Not tested: real supermarket maps, real walking speed, GUI or wall-clock real-time playback.
Known limits: The 30% claim is a mean: over 100 seeded baskets on aisle layouts the mean saving is 42.2% but single baskets range from 23.9% to 69.7%, so some baskets save less than 30%. It is not a guarantee for a list already in a good order, nor for layouts the generator does not produce. Each product is picked from one fixed access cell, chosen nearest the entrance.
Adversarial pass: 5 attempts recorded; standard attacks all logged

| id | status | source | check |
| --- | --- | --- | --- |
| C1 | passing | human | `python3 -m unittest tests.test_layouts tests.test_scale` |
| C2 | passing | human | `python3 -m unittest tests.test_simulation` |
| C3 | passing | human | `python3 -m unittest tests.test_compare` |
| C4 | passing | human | `python3 -m unittest tests.test_benchmark` |
| C5 | passing | agent-proposed | `python3 -m unittest tests.test_bad_input` |

Coverage of human criteria (what each check proves and does not):
- C1: Proves valid routes (walkable steps, every product picked, correct distance) on seeded layouts of several shapes. Largest size tried: 200x200 map, 60 products, time limit 60 s. Does not prove real store maps or layouts beyond the generator.
- C2: Proves each simulated step has a position, the cumulative distance and the time-to-prepare-basket, and that the final KPIs match a recount from the trace. Does not prove wall-clock real-time playback, only the simulated clock.
- C3: Proves the comparison reports both KPIs for the same basket, with the list-order route taken in the customer's list order. Does not prove the comparison on store data.
- C4: Proves the mean time saving over seeded benchmark baskets is above 30% and the optimized route is never slower than the list-order route. Does not prove the saving for every basket or every store layout.

Caveats during the run: 1 found, 1 fixed, 2 open
- 9m 29s tried: tests/test_bad_input.py: missing, unreadable, malformed, wrong type, unknown id, empty; each map and list entry point; plus 14 ad-hoc hostile inputs (float row, bool col, empty grid, non-text id, CRLF list, junk bytes): one error line, exit 2, no traceback
- 9m 29s tried: tests/test_bad_input.py: duplicate list lines (A1 twice) and two products on one shelf cell: each line counted, 7.0 s and 1 step
- 9m 29s tried: tests/test_bad_input.py: unrequested unreachable product P9 does not reject the basket; requested P9 fails with its id in the message
- 9m 29s tried: tests/test_simulation.py and tests/test_layouts.py check_route: times and distances recounted from the trace and an independent BFS on the raw grid (tests/support.py steps_between), not the planner code
- 9m 29s tried: generated cases: 3 shapes x 3 seeds at 31x23 (tests/test_layouts.py); 200x200 scale with 60 items (tests/test_scale.py); ad-hoc open and maze shapes at 200x200 with 60 items: open saves 76.7%, maze 45.2%, all routes valid
- 9m 29s found: build_model ran a full BFS for every pair of stops (3721 on a 200x200 map): the herd verify run timed out
- 9m 29s fixed: build_model: one BFS per stop; 200x200 with 60 items now builds in 2.2 s and compares in 4.2 s
- 9m 30s open: one fixed access cell per product (nearest the entrance): a product reachable from two sides is not optimised over both
- 9m 30s open: maze generator (30% random walls) gives small reachable pockets, so it is a weak stress test; open and aisles shapes carry the scale claim
Note: 9 notes were logged within 5 s of each other, so their times show when they were written, not when found.
