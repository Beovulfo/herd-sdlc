# Evidence: route-optimizer

Goal: Build a supermarket route optimizer that finds the shortest delivery-guy route through the store, simulates it step by step with live KPIs, and compares it with the list-order route.
Run at 2026-11-22T19:34:23Z on commit none plus uncommitted changes
Result: 4 passing, 0 failing, 0 unchecked
First verify: 4 of 4 checks failed before the work
Elapsed: 2m 15s from herd init to this verify; first verify at 1m 20s (wall clock, includes any waiting on the human)
Test budget: Unit tests in test_route_optimizer.py. Logic (BFS distances, nearest-neighbour + 2-opt ordering, KPI math) is unit-tested. The step-by-step simulation and the compare CLI are tested end to end via subprocess. Savings are measured on 30 seeded baskets in the demo store (seeds 1 to 30, 12 items each). Not tested: real store layouts, real walking speeds and pick times (the time model is an assumption), and optimality of the heuristic (2-opt is not guaranteed optimal).

| id | status | source | check |
| --- | --- | --- | --- |
| C1 | passing | human | `python3 -m unittest test_route_optimizer.TestSimulation` |
| C2 | passing | human | `python3 -m unittest test_route_optimizer.TestCompare` |
| C3 | passing | human | `python3 -m unittest test_route_optimizer.TestSavings` |
| C4 | passing | agent-proposed | `python3 -m unittest test_route_optimizer.TestEdges` |
