# Evidence: supermarket-sim

Goal: Supermarket picker route optimizer: supermarket.py simulate (optimized|random|list-order) on JSON map and list, JSON-lines step output with live KPIs, optimized mean time-to-prepare more than 20 percent below random walk over many seeded baskets.
Run at 2026-11-22T19:04:33Z on commit none plus uncommitted changes
Result: 4 passing, 0 failing, 0 unchecked
First verify: 4 of 4 checks failed before the work
Test budget: Unit: Held-Karp optimality vs brute force, start-cell pick, duplicates. Integration: seeded-basket mean comparison on the example store (30 baskets of 8). End to end: the real CLI for JSON-lines protocol, determinism, error exits. Untested on purpose: lists above 12 items (2-opt fallback), maps above 100x100, wall-clock speed.

| id | status | source | check |
| --- | --- | --- | --- |
| C1 | passing | human | `python3 -m unittest -v tests.test_supermarket.MeanSavingsTests tests.test_supermarket.StreamingTests` |
| C2 | passing | agent-proposed | `python3 -m unittest tests.test_supermarket.StdoutProtocolTests` |
| C3 | passing | agent-proposed | `python3 -m unittest tests.test_supermarket.OptimalityTests` |
| C4 | passing | agent-proposed | `python3 -m unittest tests.test_supermarket.EdgeCaseTests` |
