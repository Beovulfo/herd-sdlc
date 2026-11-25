# Design eval: do a challenger's questions fix design mistakes before the build?

Each case is a benchmark prompt plus a judge rubric for one design decision the benchmark found builders
getting wrong. A Herd session designs the task; a fresh challenger, who sees only the prompt, asks at most
5 questions; the builder answers them in `ANSWERS.md` and updates its Herd task. Nothing is built.

| case | the decision | right | wrong |
| --- | --- | --- | --- |
| `supermarket-route` | where a product is picked from | `shelf` | `cell`, `fixed-side` |
| `bus-transfer` | a unique id given twice with different data | `refused` | `tolerated` |

Both also have `unstated`, which is neither. On `supermarket-route`, `shelf` means the program picks the nearest
reachable side itself; `fixed-side` means a fixed access cell, such as the first neighbour or the one nearest the
entrance.

## Run

From the repository root, with a logged-in `claude` CLI:

```sh
E=examples/design-eval
python3 $E/run_eval.py --case supermarket-route --runs 1 --dry-run   # print the commands, start nothing
python3 $E/run_eval.py --case supermarket-route --parallel 3 --root "$(mktemp -d)/eval"   # every arm, 12 runs each
python3 $E/judge.py <root>/results
python3 $E/report.py <root>/results --case supermarket-route
python3 $E/judge.py --calibrate                                      # needs 10 hand-labelled snapshots per case
```

`--root` must be a new folder outside your home folder. Without a results folder, `report.py` reads the newest one
under `$TMPDIR/design-eval/`, where `run_eval.py` writes by default. Options: `--case` and `--arm` (repeatable),
`--arms` (folder of arm files), `--parallel` (sessions at once, capped at 3), `--runs`, `--model`
(builder, default `claude-haiku-5-5`), `--challenger-model` (default: the builder's), `--herd-tag` (default
`v0.13.1`), `--budget` (USD cap per session and per resume, default 3), `--timeout` (seconds, default 900).
The judge's model is `judge.py --model` (default `claude-sonnet-5-5`).

## Arms

An arm is a file `arms/<name>.json`. A new arm needs no code change.

| key | value |
| --- | --- |
| `name` | the file's name without `.json` |
| `when` | `none`, `after-red` or `before-attacks` |
| `sees` | any of `request`, `inputs_program`, `known_limits`, `criteria` |
| `instruction` | what the challenger is told |
| `tools` | optional: `Agent`, `Skill` or `Agent,Skill` (default none) |
| `skills` | optional: local `SKILL.md` paths, copied into the challenger's temporary project; needs `Skill` |

`request` is the case's prompt. The other `sees` fields are read by code from the stopped session's `task.toml`
(`inputs_program` is each `[[inputs]]` table's `program`). An arm whose skill file is missing is skipped with a
message. A run in which the challenger never calls an arm's skill is `challenger-failed`.

| arm | when | the challenger |
| --- | --- | --- |
| `control` | `none` | no challenger: "challenge your own understanding" only |
| `generic-after-red` | `after-red` | sees the request, asks general questions |
| `generic-before-attacks` | `before-attacks` | the same instruction |
| `design-aware-before-attacks` | `before-attacks` | also sees the inputs' form and known limits, challenges the stated design |
| `limit-cost-before-attacks` | `before-attacks` | the same view, asks what each known limit costs the user |
| `adhd-before-attacks` | `before-attacks` | runs the `adhd` skill (`~/.claude/skills/adhd/SKILL.md`, not in this repository) on the request, asks where its designs disagree |

An `adhd` reply puts its questions after a `QUESTIONS:` line, so numbered design lists are not taken for questions.

`when` `none` and `after-red` stop at the first `herd verify`; `before-attacks` stops at the first attack-note
command, before it runs. Per case and run, all arms with the same stop fork one session
(`--resume <id> --fork-session`) from identical copies of the work folder. A builder often logs all six attack notes
in one command, so a `PreToolUse` hook, set for that first session only, holds the command before it runs; a
*before* that already has an attack note is `missed-stop`. The resumed session still remembers the command it tried
to run. Each arm is stopped at the first verify that follows `ANSWERS.md`. *Before* is the task at the first stop,
*after* at the second.

## Isolation

`run_eval.py` imports `run_leg.py` and `leak_audit.py` from
[`../supermarket-route/verifier/`](../supermarket-route/verifier/): the same sandbox settings, plugin copy, git
environment and refusal to start while a hidden verifier file is readable (remove stray copies under `/tmp`
first). Earlier snapshots and logs are denied to later runs. A run with an unblocked audit finding is excluded.
The judge is a fresh `claude -p --tools ""` call from an empty folder. The challenger is a fresh `claude -p` call
from a temporary project that holds only the arm's skills, with only the arm's tools. It is not sandboxed, so arms
may not name tools that read files, run commands or reach the network.

## Results

```
<root>/results/<case>/<arm>/run-N/run.json                      status, audit findings, cost and seconds
<root>/results/<case>/<arm>/run-N/challenger_input.md           what the challenger was told and shown
<root>/results/<case>/<arm>/run-N/questions.md                  both only for arms with a challenger
<root>/results/<case>/<arm>/run-N/{before,after}/               task.toml, notes.jsonl, ANSWERS.md, files/, label.json
<root>/logs/                                                    session logs
```

Only runs with status `ok` count. The others (`no-start`, `missed-stop`, `no-verify`, `challenger-failed`,
`leak`, `judge-error`) are listed as excluded. `judge.py` keeps labels it already wrote.

`report.py` prints one row per arm and no verdict; the owner decides.

| column | meaning |
| --- | --- |
| runs | counted runs |
| right before, right after | designs labelled right |
| gain | right after minus `control`'s right after (raw counts, so compare the runs column too) |
| transitions, right-to-wrong flips | before-to-after labels |
| challenger $/run | the challenger's own cost, subagents included |
| extra $/run, extra min/run | mean of first session, challenger and resume, minus `control`'s |
| $ per extra right design | extra $/run times the arm's runs, divided by the gain; `n/a` when the gain is 0 or less |
| Fisher p | exact two-sided, right against not right, arm against `control`; information only |

A value that cannot be computed is `n/a`. With 6 runs, only near-total effects separate (6/6 against 3/6 gives
p=0.18). With six arms, one low p among five comparisons can easily be chance.

A stopped session reports no cost, so `money.py` prices its stream's token counts at list price. The challenger's
cost is the call's own `total_cost_usd`. Minutes are wall time, so `--parallel` can inflate them.

## Judge calibration

The judge sees only the rubric and one snapshot's `task.toml`, `notes.jsonl` and `ANSWERS.md`, never the arm or
whether it is before or after (`ANSWERS.md` itself exists only after). Results count only when it agrees with hand
labels on at least 9 of 10. Each labelled snapshot is a folder `cases/<case>/labelled/<name>/` with `task.toml`,
`notes.jsonl`, `ANSWERS.md` (if any) and `label.json`, for example `{"label": "shelf"}`. With fewer than 10 for
a case, `--calibrate` refuses to report agreement. [`fixtures/`](fixtures/) shows the format, one per case.

## Add a case

Add `cases/<task>.json` with `task`, `prompt` (a path from the repository root), `question`, `labels` (an object
of label id to what it means, or a list of `{id, means}`), `right` and `wrong`. No code changes. The held-out third case is the owner's choice.

## Cost

Measured once, on one live run of `supermarket-route` (2026-11-25, builder and challenger `claude-haiku-5-5`, judge
`claude-sonnet-5-5`), with the three arms of the prototype. The `adhd` arm was not measured; its challenger runs
about 10 subagents.

| part | cost per run |
| --- | --- |
| builder: 2 sessions and 3 resumes | about $0.12 |
| 2 challenger calls | about $0.004 |
| judge: 5 distinct snapshots at $0.033, one call measured | about $0.17 |
| total | about $0.29, and 11 minutes |

Six arms use 2 sessions and 6 resumes per case and run, so expect more than the table above. These are estimates from one run: a stopped session
reports no cost, so the builder's figure is its transcript's token counts at list price.

## Limits

- Stop points are found by polling the work folder every 0.2 s, so a session can act briefly past them.
- A builder that writes attack test files before it logs the first attack note keeps them in `before-attacks`.
- The held command can also hold other work chained to it, which then never runs.
- `before-attacks` arms differ from `control` in when the session was stopped, not only in the questions.
- Builder cost can be low: a reply cut off by the stop and a background subagent are not priced, and a subagent
  of several turns may be priced by its last turn only. The challenger's cost is billed in full.
- The rubric and the judge decide what a design says; no code is built or scored.

## Tests

```sh
python3 -m unittest discover -s examples/design-eval -p "test_*.py"
```

They use fake sessions and recorded judge replies and make no model call. CI does not run them.
