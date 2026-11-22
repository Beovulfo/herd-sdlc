---
name: criteria
description: Write success criteria with runnable checks for a Herd task. Use when defining what "done" means for a goal, or when a Herd task has no criteria yet.
---

# Success criteria with checks

A task is done when its criteria pass, proven by commands, not by your say-so.
Criteria live in `.herd/tasks/<slug>/task.toml`.

## Rules

1. **Outcomes, not steps.** "Given X, when Y, then Z", observable from outside. Aim for 3 to 6 criteria. No list of requirements.
2. **Every criterion has a `check`.** A shell command; exit 0 means pass. Prefer an existing test command, a new test you write, or a probe (`curl`, a script run, a file or output assertion).
3. **Human criteria are authoritative.** If the human wrote criteria, copy them with `source = "human"` and never reword, drop or weaken them. Add your own as `source = "agent-proposed"`.
4. **Fill gaps, never block.** A missing check is yours to write: a test, a script, or a proxy measure. Say which in `text`. Only if nothing can run, set `check = ""`; the criterion is then `unchecked` and is reported as such, never counted as met.
5. **Include one edge or failure case.** Wrong input, empty state, or the thing that must not change.
6. **The check must fail first.** Run `herd verify` before building (`herd` is `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/herd.py"`). A check that already passes proves nothing: tighten it.
7. **Fast checks.** Each under a minute. For slow ones set `timeout_s`.

## Format

```toml
goal = "Add a --json flag to the export command"

[[criteria]]
id = "C1"
text = "Given data, when `export --json` runs, then stdout is valid JSON with every row"
source = "human"
check = "python3 -m unittest tests.test_export_json"

[[criteria]]
id = "C2"
text = "Given no data, when `export --json` runs, then it prints [] and exits 0"
source = "agent-proposed"
check = "python3 -m unittest tests.test_export_empty"
```

Checks run from the project root. Validate the file with `herd check`.
