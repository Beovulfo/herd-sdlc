# Evidence: supermarket-route

Goal: Build a route optimizer for a delivery guy preparing a supermarket basket. Works in any supermarket layout. Input: map of the store with product IDs and short names localised on it, plus a customer's product list (id:short name). Output: best route; simulate step by step, live KPIs time-to-prepare-basket and distance-covered, compare with list-order route; demonstrate more than 30% time saving.
Run at 2026-11-23T08:09:45Z on commit c4086971762a plus uncommitted changes
Result: 6 passing, 0 failing, 0 unchecked
First verify: 6 of 6 checks failed before the work
Elapsed: 6m 42s from herd init to this verify; first verify at 1m 11s (wall clock, includes any waiting on the human)
Test budget: Unit tests on hand-made maps and generated aisle, hall and maze layouts up to 300x300 cells; one 300x300 scale check with 60 items; benchmark of 20 seeded stores. Not tested: real store maps, wall-clock timing of the live display, calibration of walk speed and pick time.
Known limits: The 30 percent saving holds for customer lists in random order against a store with long aisles. The route is a heuristic, not proven optimal. Each product is picked from its first open neighbour only. Walk speed and pick time are fixed constants.
Adversarial pass: 9 attempts recorded; standard attacks all logged

| id | status | source | check |
| --- | --- | --- | --- |
| C1 | passing | human | `python3 -m unittest tests.test_input` |
| C2 | passing | human | `python3 -m unittest tests.test_layouts tests.test_scale` |
| C3 | passing | human | `python3 -m unittest tests.test_simulation` |
| C4 | passing | human | `python3 -m unittest tests.test_savings` |
| C5 | passing | agent-proposed | `python3 -m unittest tests.test_layouts` |
| C6 | passing | agent-proposed | `python3 -m unittest tests.test_input` |

Coverage of human criteria (what each check proves and does not):
- C1: Proves the map and list are read and matched by product ID and short name, with errors on mismatch. Does not prove the map format matches a real store export.
- C2: Proves valid routes on generated aisle, hall and maze layouts of several shapes and sizes, and a 300x300 store with 60 items in under 30 seconds. Does not prove stores beyond 300x300 cells.
- C3: Proves one event per step with both KPIs, final KPIs equal the planned route, and the live CLI output. Does not prove wall-clock real time under load.
- C4: Proves the aggregate time saving over 20 seeded stores is above 30 percent and reports it. Does not prove the saving for every store or every customer list.

Caveats during the run: 4 found, 2 fixed, 1 open
- 4m 33s tried: bad-input battery on CLI: missing/malformed/dir map, missing list, wrong types, unknown id, mismatch, empty and blank list, bad args
- 4m 33s found: CLI prints a traceback for a missing or unreadable map or list file, a malformed JSON map, or a directory given as map (exit 1)
- 4m 33s found: an empty or blank request file exits 0 with no items instead of one clear message
- 4m 33s found: a map missing a key reports bad map: 'x' with no reason
- 4m 33s tried: to run: duplicate ids, shared shelf cells, shelves with the same name
- 4m 33s tried: to run: one unreachable product in a list alongside reachable ones, and a product not requested in the map
- 4m 33s tried: to run: recompute route distance and time from the step list with separate code
- 6m 22s fixed: bad-input: missing, unreadable or malformed map or list, and empty requests now give one error line and exit 2; regression tests in tests/test_input.py CliBadInputTest
- 6m 22s fixed: bad-input: a map missing a key now names it, e.g. missing key 'start'; test_map_missing_a_key_names_the_key
- 6m 22s tried: rerun after fix: 15 bad-file cases on the CLI, each exit 2 with one error line and no traceback; good files exit 0 (attack scripts in scratchpad attacks dir)
- 6m 22s tried: two products on one shelf cell with the same name, a duplicate request line, and a duplicate map id: shared cell and duplicate line are both counted (time 14 s = 4 m + 2 picks); duplicate map id is rejected with a clear error
- 6m 22s open: a duplicate product id in the map is rejected, not counted: the id is the join key with the request
- 6m 22s tried: an unrequested product walled off from the counter is ignored and the request plans; a requested walled-off product fails with 'cannot be reached from the start'
- 6m 23s tried: separate script parsed the CLI printed steps for hall, maze and aisles routes and recomputed moves, picks, time, distance and saving: all match, PASS
- 6m 23s tried: quantifier attacks: generated hall, maze and aisles shapes; 3x3 to 5x5 degenerate stores; single row and column corridors; a product next to the counter; a 500x500 hall with 60 items plans in 9.8 s; 300x300 aisles with 60 items in 2.8 s
- 6m 23s found: earlier, three attack entries (collision, one-bad-part, recount) were logged as tried before they were run; their text says to run. The real results are logged after them
Note: 9 notes were logged within 5 s of each other, so their times show when they were written, not when found.
