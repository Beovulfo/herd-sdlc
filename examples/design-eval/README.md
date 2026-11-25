# Design eval: do a challenger's questions fix design mistakes before the build?

Each case is a benchmark prompt plus a judge rubric for one design decision the benchmark found builders
getting wrong. A Herd session designs the task; a fresh challenger, who sees only the prompt, asks at most
5 questions; the builder answers them in `ANSWERS.md` and updates its Herd task. Nothing is built.

| case | the decision | right | wrong |
| --- | --- | --- | --- |
| `supermarket-route` | where a product is picked from | `shelf` | `cell` |
| `bus-transfer` | a unique id given twice with different data | `refused` | `tolerated` |

Both also have `unstated`, which is neither.

## Run

From the repository root, with a logged-in `claude` CLI:

```sh
E=examples/design-eval
python3 $E/run_eval.py --case supermarket-route --runs 1 --dry-run   # print the commands, start nothing
python3 $E/run_eval.py --root "$(mktemp -d)/eval"                    # every case, 12 runs per arm
python3 $E/judge.py <root>/results
python3 $E/report.py <root>/results
python3 $E/judge.py --calibrate                                      # needs 10 hand-labelled snapshots per case
```

`--root` must be a new folder outside your home folder. Options: `--case` (repeatable), `--runs`, `--model`
(builder, default `claude-haiku-5-5`), `--challenger-model` (default: the builder's), `--herd-tag` (default
`v0.13.1`), `--budget` (USD cap per session and per resume, default 3), `--timeout` (seconds, default 900).
The judge's model is `judge.py --model` (default `claude-sonnet-5-5`). Runs are sequential.

## The three arms

| arm | stopped first at | then |
| --- | --- | --- |
| `control` | the first `herd verify` | "challenge your own understanding", no questions |
| `after-red` | the same stop, the same start | the challenger's questions |
| `before-attacks` | the first attack-note command, before it runs | the challenger's questions, then its attacks and the first `herd verify` |

`control` and `after-red` fork one session (`--resume <id> --fork-session`) from identical copies of the work
folder. `before-attacks` needs its own session, because a session cannot be rewound. A builder often logs all six
attack notes in one command, so a `PreToolUse` hook, set for that first session only, holds the command before it
runs; a *before* that already has an attack note is `missed-stop`. The resumed session still remembers the command
it tried to run. Each arm is stopped at the
first verify that follows `ANSWERS.md`. *Before* is the task at the first stop, *after* at the second.

## Isolation

`run_eval.py` imports `run_leg.py` and `leak_audit.py` from
[`../supermarket-route/verifier/`](../supermarket-route/verifier/): the same sandbox settings, plugin copy, git
environment and refusal to start while a hidden verifier file is readable (remove stray copies under `/tmp`
first). Earlier snapshots and logs are denied to later runs. A run with an unblocked audit finding is excluded.
The challenger and the judge are fresh `claude -p --tools ""` calls from an empty folder.

## Results

```
<root>/results/<case>/<arm>/run-N/run.json                      status and audit findings
<root>/results/<case>/<arm>/run-N/questions.md                  the questions arms only
<root>/results/<case>/<arm>/run-N/{before,after}/               task.toml, notes.jsonl, ANSWERS.md, files/, label.json
<root>/logs/                                                    session logs
```

Only runs with status `ok` count. The others (`no-start`, `missed-stop`, `no-verify`, `challenger-failed`,
`leak`, `judge-error`) are listed as excluded. `judge.py` keeps labels it already wrote.

The report prints, per case and arm, the before-to-after labels and the right-to-wrong flips. The bar, for each
questions arm against `control`: a share of right final labels higher by at least 6 of 12 on one case, no lower
on the other, and at most one right-to-wrong flip across both. With fewer than 12 counted runs in any compared
arm it says `not evaluated`, so pass `--runs` above 12 to make up for excluded runs. With 6 runs, only near-total
effects separate (6/6 against 3/6 gives Fisher p=0.18).

## Judge calibration

The judge sees only the rubric and one snapshot's `task.toml`, `notes.jsonl` and `ANSWERS.md`, never the arm or
whether it is before or after (`ANSWERS.md` itself exists only after). Results count only when it agrees with hand
labels on at least 9 of 10. Each labelled snapshot is a folder `cases/<case>/labelled/<name>/` with `task.toml`,
`notes.jsonl`, `ANSWERS.md` (if any) and `label.json`, for example `{"label": "shelf"}`. With fewer than 10 for
a case, `--calibrate` refuses to report agreement. [`fixtures/`](fixtures/) shows the format, one per case.

## Add a case

Add `cases/<task>.json` with `task`, `prompt` (a path from the repository root), `question`, `labels` (each an
`id` and what it `means`), `right` and `wrong`. No code changes. The held-out third case is the owner's choice.

## Cost

Measured once, on one live run of `supermarket-route` (2026-11-25, builder and challenger `claude-haiku-5-5`, judge
`claude-sonnet-5-5`). One run is all three arms of one case.

| part | cost per run |
| --- | --- |
| builder: 2 sessions and 3 resumes | about $0.12 |
| 2 challenger calls | about $0.004 |
| judge: 5 distinct snapshots at $0.033, one call measured | about $0.17 |
| total | about $0.29, and 11 minutes |

The default (2 cases, 12 runs) is then about $7 and 4.5 hours. These are estimates from one run: a stopped session
reports no cost, so the builder's figure is its transcript's token counts at list price.

## Limits

- Stop points are found by polling the work folder every 0.2 s, so a session can act briefly past them.
- A builder that writes attack test files before it logs the first attack note keeps them in `before-attacks`.
- The held command can also hold other work chained to it, which then never runs.
- `before-attacks` differs from `control` in when the session was stopped, not only in the questions.
- The rubric and the judge decide what a design says; no code is built or scored.

## Tests

```sh
python3 -m unittest discover -s examples/design-eval -p "test_*.py"
```

They use fake sessions and recorded judge replies and make no model call. CI does not run them.
