# Supermarket route optimizer

Orders a picker's walk through any grid-map supermarket and compares it with the list-order walk.

```
python3 router.py gen aisles demo --width 80 --height 50 --products 300 --list-size 25
python3 router.py simulate demo.map.json demo.list.txt [--trace]
```

Map JSON: `rows` (`#` shelf, `.` floor, `S` start, `C` checkout), `products` (`id`, `name`, `x`, `y`), optional `walk_speed_mps`, `pick_s`, `cell_m`.
List file: one `id:short name` (or `id`) per line; a repeated id means quantity.
Output: every pick (every step with `--trace`) with running `distance-covered` and `time-to-prepare-basket`, then both totals and the time saved.

Method: BFS distances on the grid, exact ordering up to 12 items, nearest neighbour + 2-opt + or-opt above.
Limits: one pick cell per product (the reachable neighbour nearest to start); tiny lists (1 to 3 items) may save under 30%.
Tests: `python3 -m unittest discover -s tests -t .`
