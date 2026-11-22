# Evidence: route-optimizer

Goal: Build a route optimizer that works inside any supermarket, any size or layout. Input: a MAP of the supermarket with all products localised (product ID, short name), and a customer list of products (id:short name). Goal: best route for the delivery guy preparing the basket. Simulate the route step by step, measuring in real time the KPIs time-to-prepare-basket and distance-covered, and compare against the list-order (not optimized) route to demonstrate the optimizer saves more than 30% of the time until the basket is ready.
Run at 2026-11-22T20:10:43Z on commit 516e0bd26982 plus uncommitted changes
Result: 5 passing, 0 failing, 0 unchecked
First verify: 5 of 5 checks failed before the work
Elapsed: 8m 22s from herd init to this verify; first verify at 2m 07s (wall clock, includes any waiting on the human)
Test budget: About 15 unittest tests in one file, one per behaviour (layouts, scale, simulation, savings, input errors, route quality). No per-function suites, no mocks.
Known limits: The >30% saving holds for synthetic aisle and random-obstacle stores with at least 20 randomly ordered items (10 items usually, not always: see measurements), 1 m cells, 1.2 m/s walking and 5 s pick dwell. Measured on 60 seeded 41x31 aisle stores, time saving is below 30% in 60/60 runs for 1 item, 41/60 for 3 items, 26/60 for 5 items, 3/60 for 10 items (min 21.9%, median 42.6%), 0/60 for 20 items (min 32.8%, median 51.0%). It also shrinks for lists already in near-optimal order and when pick dwell dominates walking (constant pick time dilutes the time saving). A repeated product id is one stop (quantity is not modelled). Planning 500 stops on a 250x250 store takes about 10 s; larger lists are untested. The route is a heuristic (nearest neighbour + 2-opt + or-opt), not provably optimal; each product is picked from one fixed walkable neighbour cell; movement is 4-connected on a single-floor grid with no one-way aisles, queues or blocked-by-people effects.

| id | status | source | check |
| --- | --- | --- | --- |
| C1 | passing | human | `python3 -m unittest test_routeopt.TestLayouts test_routeopt.TestScale` |
| C2 | passing | human | `python3 -m unittest test_routeopt.TestSimulation` |
| C3 | passing | human | `python3 -m unittest test_routeopt.TestSavings` |
| C4 | passing | agent-proposed | `python3 -m unittest test_routeopt.TestInputErrors` |
| C5 | passing | agent-proposed | `python3 -m unittest test_routeopt.TestRouteQuality` |

Coverage of human criteria (what each check proves and does not):
- C1: Proves a valid route (all items, adjacent walkable steps, start to end) on aisle grids, open-plan, random-obstacle and winding-corridor stores, plus a 250x250 store with thousands of products inside a time bound. Does not prove real store maps, multi-floor stores or lists of thousands of items.
- C2: Proves the simulation yields one event per step and per pick with running distance-covered and time-to-prepare-basket that never decrease, end at the planned route totals, and that the CLI --live output prints them as it goes. Does not prove wall-clock pacing accuracy: --speedup N sleeps between events but is only exercised at a huge N.
- C3: Proves time-to-prepare-basket (walk + pick dwell + walk to end) is more than 30% lower than list-order on every seeded synthetic store/list scenario (10 to 80 items, 8 seeded cases, aisle, open-plan and random layouts). Also proves it for the worst of 30 seeds per layout at 20 items. Does not prove it for real lists, real maps, lists under 20 items (see known_limits), or lists already well ordered (route is then never longer than list order, saving near 0).
