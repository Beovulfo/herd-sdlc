# Benchmark adapter spec

You write one Python file, `adapter.py`, that lets a fixed scorer drive one supermarket route optimizer
(the "project", a folder you must only read, never change). Stdlib only. Do not fix, improve or work
around bugs in the project: call its own public functions and CLI as a user would. If the project
crashes or returns something wrong, let that show.

## 1. `worker(project: Path, canon: dict) -> dict`

Called in a fresh process. `sys.path.insert(0, str(project))` and import the project's module.

`canon` (the scorer's store, row/col coordinates, `#` = blocked, anything else walkable):
- `grid`: list of equal-length strings
- `station`: `[row, col]`, the start and the end (round trip), always walkable
- `products`: `{id: {"name": str, "shelf": [row, col], "access": [[row, col], ...]}}`; `shelf` is
  usually a `#` cell picked from a walkable neighbour, sometimes a walkable cell itself. Ignore `access`
  (it is the scorer's answer key): give the project only what its own map format takes.
- `ids`: the customer's list, in list order (ids are distinct)

Translate canon into the project's own map and list format (mind its coordinate order, its station or
start/end convention, and whether it wants a file path or a dict). If the project needs a start/end
or station marker in the grid, put it at `station`. Ask the project to plan both the list-order route
and its optimized route, and simulate both with its own simulator.

Return:
```
{"round_trip": True,                       # False only if the project's route does not end at the station
 "list": ROUTE, "opt": ROUTE}
ROUTE = {"dist": <project's reported final distance in cells>,
         "time": <project's reported final time-to-prepare-basket in seconds>,
         "speed": <project's walking speed constant, cells per second>,
         "pick": <project's seconds per pick constant>,
         "trace": [[row, col], ...]}       # every cell the picker steps onto, in order, from the project's
                                           # own step-by-step simulation; exclude the start cell and any
                                           # repeated entry for a pick (a pick does not move the picker)
```
If the project cannot take a product on a blocked cell (it wants the pick cell itself), place each
product on the first in-grid walkable neighbour of its shelf in the order up, down, left, right (a naive
user's translation, with no reachability check), and say so in your reply. Use the project's defaults
(speed, pick time, cell size 1 m). When you test the probe argv, use absolute paths. If the project's distance is in metres
with 1 m cells, it equals cells. Values must come from the project's output, never computed by you.

## 2. `probe(sc: str, d: Path, rp) -> list[str]`

Builds one robustness scenario in temp dir `d` in the project's own file formats and returns the argv
to run the project's CLI, starting with the script path relative to the project folder, for example
`["route.py", "run", str(d / "m.json"), str(d / "l.txt")]`. `rp` is the probe module with:
- `rp.GRID` (list of strings, row/col), `rp.START` (a tuple **(x, y) = (col, row)**),
- `rp.SHELF` `{id: (row, col)}` shelf cells, `rp.NAMES` `{id: name}`, `rp.lines(sc)` the list lines
  `"id:name"` for this scenario, `rp.j(obj)` = `json.dumps`.

Write the map with every product in `rp.SHELF` (P3 is sealed off on purpose). For `sc == "malformed_map"`
write the text `{bad` as the map file instead of valid JSON. Write the list file from `rp.lines(sc)`
(one per line, an empty file for the empty list). Put the station or start/end at row `START[1]`,
col `START[0]`.

## 3. Check it

Before you finish, run on the given example: `python3 -c` that loads your adapter, builds a tiny canon
(a 5x7 open grid, station [1,1], three products on walkable cells) and prints `worker(...)` keys and
trace length, and run `probe("normal", ...)`'s argv once. Report the adapter path and anything about the
project's interface that was ambiguous.
