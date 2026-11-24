# Benchmark adapter spec: bus transfer planner

You write one Python file, `adapter.py`, that lets a fixed scorer drive one bus journey planner (the
"project", a folder you must only read, never change). Standard library only. Do not fix, improve or work
around bugs in the project: call its own public functions and CLI as a user would. If the project crashes
or returns something wrong, let that show.

## 1. `worker(project: Path, canon: dict) -> dict`

Called in a fresh process. `sys.path.insert(0, str(project))` and import the project's module.

`canon` (the scorer's network; times are whole minutes since midnight and may pass 1440, so 1510 is 01:10 the next day):
- `stops`: `[[id, name], ...]`
- `trips`: `[{"id": str, "route": str, "times": [[stop_id, arrival, departure], ...]}, ...]`; one bus run, stops in
  order, never a stop twice. In every generated trip arrival equals departure at each stop, so a project that stores
  one time per stop takes that one value. A route has many trips. Trips may overtake each other.
- `min_change`: the minimum minutes between getting off one bus and onto another. Staying on the same bus needs none.
  Pass it to the project however the project takes it (an option, a file field, a constant it exposes).
- `queries`: `[{"from": stop_id, "to": stop_id, "depart": minutes}, ...]`; leave at or after `depart`.

Translate canon into the project's own network format (files, dicts or objects; mind its time format, such as `HH:MM`
or minutes, and how it writes a time past midnight). Load the network once, then ask the project for the
earliest-arrival journey of each query with its own planner. A timetable is one service day: do not wrap to the next day.

Return `{"answers": [ANSWER, ...]}`, one per query in order:
```
ANSWER = {"found": True, "arrival": <minutes>, "legs": [LEG, ...]}   # or {"found": False} when the project says not possible
LEG    = {"trip": id, "from": stop_id, "dep": minutes, "to": stop_id, "arr": minutes}
```
One leg per bus ride (board at `from`, get off at `to`), or one per stop-to-stop hop: both are read the same.
A journey from a stop to itself has `legs: []` and `arrival` equal to `depart`. Values must come from the project's
output, never computed by you. If the project names trips or stops differently, map them back to canon ids.

## 2. `probe(sc: str, d: Path, bp) -> list[str]`

Builds one robustness scenario in temp dir `d` in the project's own file formats and returns the argv to run the
project's CLI, starting with the script path relative to the project folder, for example
`["planner.py", str(d / "net.json"), "A", "C", "08:30"]`. `bp` is the probe module with:
- `bp.canon(sc)`: the network for this scenario (`stops`, `trips`, `min_change`). For `empty_network` it has no stops and
  no trips. For `duplicate_stop_ids` one stop id appears twice: write it as it is, do not drop the second.
- `bp.query(sc)`: `(start, destination, departure_text)`. The destination is unknown for `unknown_stop`; the departure text
  is `08:30`, or `half past eight` for `bad_departure`: pass it to the project as given, in whatever form the CLI takes a time.
- `bp.MALFORMED`: write this text as the timetable file for `malformed_timetable`.
- `bp.j(obj)` = `json.dumps`.

For `missing_file`, point the argv at a network file that does not exist, such as `d / "absent.json"`.
Each of the six bad scenarios must end with a clear message and a non-zero exit, with no traceback.

## 3. Check it

Before you finish, load your adapter, build a tiny canon (3 stops, 2 trips, one query) and print `worker(...)` keys and
the number of answers, and run `probe("normal", ...)`'s argv once. Report the adapter path and anything about the
project's interface that was ambiguous.
