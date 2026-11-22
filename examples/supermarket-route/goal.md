# Goal for `/herd:run` (paste everything below the line)

---

Build a route optimizer that works inside a big supermarket.

**Input.** The map of the supermarket, with all products located on it (product ID and short name), and a customer's shopping list of products (id and short name). A delivery person walks the store preparing the basket for shipping.

**Goal.** Find the optimal route for the delivery person to collect everything on the list.

**Success looks like** this: we can simulate the delivery person's route step by step, measuring two KPIs in real time, `time-to-prepare-basket` and `distance-covered`, and compare the optimized route against a random-walk algorithm (not optimized), demonstrating that the optimization saves more than 20 percent of the time for the basket to be ready.

**Human success criterion (authoritative, do not weaken):** over many seeded baskets, the mean time-to-prepare of the optimized algorithm is more than 20 percent lower than the mean of the random walk, and the simulation emits the KPIs step by step while it runs.

**Constraints.**
- Python standard library only, no network.
- One command: `python3 supermarket.py simulate --map MAP.json --list LIST.json --algo optimized|random|list-order --seed N`. `list-order` visits items in the order of the list, by shortest paths: a stronger baseline to report next to the random walk.
- Map file: `{"grid": ["#####", "#.S.#", ...], "products": {"P001": {"name": "milk", "cell": [x, y]}}, "start": [x, y]}`. `#` is a shelf or wall, `.` is walkable. A product is picked from its `cell` (always a walkable cell). `[x, y]` is column, row, from the top left.
- List file: `{"items": [{"id": "P001", "name": "milk"}]}`.
- Output: JSON lines on stdout, one `{"type": "step", "n": 1, "pos": [x, y], "time": 12.0, "distance": 12, "picked": ["P001"]}` per step (`picked` lists items picked at that step, usually empty), then exactly one last line `{"type": "final", "algo": "...", "time_to_prepare": 123.0, "distance": 100, "picked": 8}`. Moves are one cell up, down, left or right. Distance counts moves. You choose walking speed and pick time, and use the same time model for every algorithm.
- Handle an empty list, an unknown product ID (clear error, non-zero exit) and an unreachable product (clear error, non-zero exit).
