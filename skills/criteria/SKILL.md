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
3. **Human criteria are authoritative and quoted.** If the human wrote criteria, put their words in `text` exactly as written (no Given/When/Then conversion, no added scenario details), with `source = "human"`. Never reword, drop or narrow them. `herd check` warns when a `human` text is not a verbatim quote of the request. Put your concrete scenario in a separate `agent-proposed` criterion.
   **The check must cover all the words of a human criterion.** If it says "many baskets" or "any input", the check varies the inputs (several seeds, stores or cases), not one fixture. If you can cover only part of it, say which part in `test_budget` and add `agent-proposed` criteria for the rest. Quoting the human while testing one example is still narrowing. For every `human` criterion add `coverage = "..."`: what its check proves and what it does not, word by word (for example "proves one event per stop, not one per walked cell"). `herd check` warns when it is missing and the report prints it.
4. **Fill gaps, never block.** A missing check is yours to write: a test, a script, or a proxy measure. Say which in `text`. Only if nothing can run, set `check = ""`; the criterion is then `unchecked` and is reported as such, never counted as met.
5. **Include one edge or failure case.** Wrong input, empty state, or the thing that must not change.
6. **The check must fail first.** Run `herd verify` before building (`herd` is `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/herd.py"`). A check that already passes proves nothing: tighten it.
7. **Fast checks.** Each under a minute. For slow ones set `timeout_s`.
8. **Say what you do not test, and when the claim may fail.** For medium and high risk, add a top-level `test_budget = "..."` to `task.toml`: which behaviours are tested at which level (unit, integration, end to end) and what is deliberately left untested. Add `known_limits = "..."`: under what conditions the claim may fail or has not been shown (store, input size, assumed constants). A reviewer compares the diff to the budget. Pick the level by risk: logic is a unit test, a user flow is an end-to-end test.
9. **Know your commands.** `herd detect` proposes the project's test and lint commands. `herd check` warns about checks that do not run project code (`true`, `echo`, `test -f`).

## Format

```toml
# The user's request said: "Add a --json flag to the export command. The output must be valid JSON with every row."
goal = "Add a --json flag to the export command"

[[criteria]]
id = "C1"
text = "The output must be valid JSON with every row"   # the human's words, quoted
source = "human"
check = "python3 -m unittest tests.test_export_json"   # covers several inputs, not one fixture

[[criteria]]
id = "C2"
text = "Given no data, when `export --json` runs, then it prints [] and exits 0"
source = "agent-proposed"
check = "python3 -m unittest tests.test_export_empty"
```

Checks run from the project root. Validate the file with `herd check`.
