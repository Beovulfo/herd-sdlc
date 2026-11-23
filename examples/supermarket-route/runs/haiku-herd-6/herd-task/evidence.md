# Evidence: route-optimizer

Goal: Build a supermarket route optimizer: plan the delivery guy's route through any supermarket layout to prepare a basket, simulate it step by step, report time-to-prepare-basket and distance-covered live, and compare with the list-order route (target: more than 30% time saved).
Run at 2026-11-23T08:13:09Z on commit 16f2d197129f plus uncommitted changes
Result: 4 passing, 0 failing, 0 unchecked
First verify: 4 of 4 checks failed before the work
Elapsed: 10m 05s from herd init to this verify; first verify at 2m 09s (wall clock, includes any waiting on the human)
Test budget: Unit tests on small hand-made maps; generated layouts of 4 shapes (25x25, 5 seeds each); one 300x300 scale run with a 60 s limit; a benchmark of 30 generated stores with 3 random lists each (90 runs). Not tested: real store maps, a GUI, device or wall-clock timing, stores above 300x300.
Known limits: The 30% claim is measured on generated stores with random product placement and random list order, not on real supermarkets. Time model: 1 s per grid step, 2 s per pick (both fixed in optimizer/simulate.py). The saving shrinks with short lists, small stores, or expensive picks.
Adversarial pass: 5 attempts recorded; standard attacks all logged

| id | status | source | check |
| --- | --- | --- | --- |
| C1 | passing | human | `python3 -m unittest tests.test_layouts` |
| C2 | passing | human | `python3 -m unittest tests.test_simulate` |
| C3 | passing | human | `python3 -m unittest tests.test_savings` |
| C4 | passing | agent-proposed | `python3 -m unittest tests.test_input` |

Coverage of human criteria (what each check proves and does not):
- C1: Proves a full valid route on generated layouts of 4 shapes; largest size tried is 300x300 with a 60 s time limit. Does not prove real store maps or stores above 300x300.
- C2: Proves each move is one free adjacent cell, KPIs update at every event and match a separate recount; does not prove wall-clock real-time playback.
- C3: Proves more than 30% aggregate time saving over 90 generated runs versus list order; does not prove the saving on real stores or other time models.

Caveats during the run: 3 found, 3 fixed, 4 open
- 8m 26s tried: map missing/dir/empty/not json/top-level list; layout wrong type/ragged/empty; products number/null; product bad row/id/name/out of map; list unknown id/no colon/empty id/empty/binary bytes/directory; scratchpad attacks/bad_input.py, 31 cases
- 8m 26s found: products set to a number or null raised a TypeError traceback
- 8m 26s fixed: parse_store rejects non-list products with one error line
- 8m 26s found: a broken product the list does not ask for rejected the whole map (one-bad-part)
- 8m 26s fixed: broken products kept in Store.broken; only a requested one fails, with its reason; regression tests in tests/test_input.py
- 8m 27s found: duplicate product ids rejected the whole map even when unrequested
- 8m 27s fixed: duplicate ids mark the id broken, so only a requested duplicate fails
- 9m 21s tried: tests/test_input.py test_duplicate_list_entries_are_each_counted (same product 5x counted 5 picks in scratchpad too) and test_two_products_on_one_cell_are_each_counted; not fresh
- 9m 21s tried: tests/test_input.py test_unused_unreachable_product_does_not_block_the_plan, test_broken_unrequested_product_does_not_reject_the_map, test_requested_broken_product_fails_with_its_reason, and unreachable requested product in bad-input list
- 9m 21s tried: scratchpad attacks/recount.py: 12 generated runs, run and compare output re-added with separate code; 0 mismatches
- 9m 21s tried: scratchpad attacks/hostile.py: degenerate 1x1, 1-row corridor, walled start, same product 5x, unreachable, odd sizes 1x50 50x1 7x9 101x33 across 4 shapes x 3 seeds, 500x500 scale
- 9m 21s open: 500x500 store with 60 items takes about 26 s to compare; the 60 s test limit covers 300x300 only
- 9m 21s open: the 30% saving is for 15-item lists; a 6-item demo list saves 25.7%, below 30%
- 9m 21s open: not fresh-context: attacks were run by the same agent that built the code
- 9m 28s open: review skipped: this run cannot spawn a fresh-context reviewer, so the change is unreviewed
Note: 7 notes were logged within 5 s of each other, so their times show when they were written, not when found.
