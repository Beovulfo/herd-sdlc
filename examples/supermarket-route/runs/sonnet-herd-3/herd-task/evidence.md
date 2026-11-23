# Evidence: route

Goal: Supermarket route optimizer with step-by-step simulation, KPIs, and >30% time saving vs list order
Run at 2026-11-23T08:03:25Z on commit 73d977ef92a3 plus uncommitted changes
Result: 5 passing, 0 failing, 0 unchecked
First verify: 5 of 5 checks failed before the work
Elapsed: 3m 53s from herd init to this verify; first verify at 1m 49s (wall clock, includes any waiting on the human)
Test budget: Unit tests on generated stores: 3 layouts (aisles, random obstacles, open pillars) x several seeds, a 200x300 scale run, hostile inputs. Not tested: real store maps, one-way aisles, shelf-side picking rules, congestion, multiple pickers.
Known limits: Heuristic (nearest neighbour + 2-opt + or-opt), not provably optimal. Saving depends on the list: lists under about 10 items, a list already in store order, or a pick time much larger than walk time can fall below 30%. Pick time (10 s) and speed (1 cell/s) are assumptions, flags change them. Optimizer matrix needs one BFS per item: very large stores with hundreds of items get slow.
Adversarial pass: 5 attempts recorded; standard attacks all logged

| id | status | source | check |
| --- | --- | --- | --- |
| C1 | passing | human | `python3 -m unittest tests.test_route.Layouts tests.test_route.Scale` |
| C2 | passing | human | `python3 -m unittest tests.test_route.CliInput` |
| C3 | passing | human | `python3 -m unittest tests.test_route.Simulation` |
| C4 | passing | human | `python3 -m unittest tests.test_route.Saving` |
| C5 | passing | agent-proposed | `python3 -m unittest tests.test_route.BadInput` |

Coverage of human criteria (what each check proves and does not):
- C1: Scale: largest tried 200x300 cells with 60 items, time limit 60 s. Proves valid full routes on 3 generated layout families x 5 seeds, odd shapes (1-wide, no aisles, unreachable pockets) ; not real maps.
- C2: Proves the CLI reads a map JSON and an id:short-name list file and routes exactly the listed products; not other map formats.
- C3: Proves one event per step, adjacent walkable moves, KPIs rising with each event, final KPIs equal to an independent recount of the trace; not a graphical animation.
- C4: Proves >30% time saved on every one of 30 generated stores (3 layouts x 10 seeds, 20 items, random list order); not short lists or lists already in store order.

Caveats during the run: 2 found, 2 fixed, 1 open
- 2m 35s found: demo --items 0 crashed with a traceback (empty list reached the optimizer); found by the bad-flags test
- 2m 35s fixed: demo --items 0 now exits 2 with one error line
- 3m 01s tried: tests.test_route.BadInput: missing/dir/malformed/non-JSON map, 13 bad map shapes, missing/empty/binary/malformed list, unknown/duplicate id, name mismatch, bad CLI flags; each exits 2 with one stderr line
- 3m 01s found: binary (non-UTF-8) list file crashed with UnicodeDecodeError traceback
- 3m 01s fixed: binary list now gives 'not UTF-8 text'; regression test test_binary_list
- 3m 01s tried: BadInput.test_shared_cell_counts_each: two products on one cell both picked (time = distance + 2 picks); duplicate id in list rejected with clear message
- 3m 01s tried: BadInput.test_unreachable: unreachable unrequested product ignored (exit 0); requested unreachable product fails 'cannot be reached'
- 3m 01s tried: Simulation.test_steps_and_live_kpis and Layouts recount() rebuild distance, picks, time from the trace only (adjacency, walls, pick cell next to product) on 3 layouts x 5 seeds and 2 speeds
- 3m 01s tried: scale: 200x300, 60 items: 7s, saving 52%; hostile shapes: 1x1 map, 1-wide corridor, boxed-in start (random layout, caught generator bug, fixed by carving a ring)
- 3m 01s open: heuristic is not provably optimal; 12-item lists can drop to 30% saving (aisles seed 7: 30.0%)
Note: 8 notes were logged within 5 s of each other, so their times show when they were written, not when found.
