# Supermarket route optimizer

    python3 route.py run map.json list.txt [--steps] [--speed 1.0] [--pick-s 10]
    python3 route.py demo --size 200x300 --layout aisles --items 60 --seed 1

Map JSON: `{"grid": ["#####", "#S..#"], "products": [{"id": "p1", "name": "milk", "row": 0, "col": 2}]}`.
`#` blocked or shelf, `.` floor, `S` start and packing point (exactly one). A product on a `#` cell is picked from any floor cell next to it.
List file: one `id:short name` per line, no duplicate ids.

Both routes are simulated step by step (`--steps` prints every step) with live `time-to-prepare-basket` and `distance-covered`; the picker returns to `S`.
Time = cells / speed + picks x pick time. Optimizer: nearest neighbour, then 2-opt and or-opt on true shortest-path distances. List-order baseline uses shortest paths in list order.
Tests: `python3 -m unittest discover -s tests -t .`. Limits are in `.herd/tasks/route/task.toml`.
