---
name: criteria
description: Write success criteria with runnable checks for a Herd task. Use when defining what "done" means for a goal, or when a Herd task has no criteria yet.
---

# Success criteria with checks

A task is done when its criteria pass, proven by commands. Criteria live in `.herd/tasks/<slug>/task.toml`. `herd` is `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/herd.py"`.

## Rules

1. **Outcomes, not steps.** "Given X, when Y, then Z", observable from outside. 3 to 6 criteria. Your own: one sentence, about 25 words.
2. **Every criterion has a `check`:** a shell command, exit 0 means pass: an existing test, a new test, or a probe. Under a minute each; slow ones set `timeout_s`.
3. **Human criteria are quoted, never changed.** Put the human's words in `text` exactly, with `source = "human"`. Never reword, drop or narrow them. Put your concrete scenario in a separate `agent-proposed` criterion.
4. **Cover every word of a human criterion.** Quoting it while testing one example is still narrowing. `any`, `every`, `whatever`, `many`, `each`, `arbitrary` need generated cases of different shapes. `big`, `large`, `huge`, `thousands` need a scale check with a time limit. Covering only part? Name it in `test_budget`; add `agent-proposed` criteria for the rest. Add `coverage` to each: what its check proves and misses, about 30 words.
5. **Fill gaps, never block.** Write missing checks yourself. If nothing can run, set `check = ""`: `unchecked`, never counted as met.
6. **Include one edge or failure case:** wrong input, empty state, or what must not change.
7. **Fail first.** Run `herd verify` before building. A check that already passes proves nothing: tighten it.
8. **Say what is not tested** (medium and high risk). Top-level `test_budget = "..."`: what is tested at which level, and what is not. `known_limits = "..."`: when the claim may fail.
9. **Validate.** `herd check` warns about checks that run no project code (`true`, `echo`, `test -f`), unquoted human criteria, missing or vague `coverage`, and your texts over 40 or coverage over 50 words (human quotes exempt). `herd detect` proposes the test command.

## Format

```toml
# The request said: "Add a --json flag to the export command. The output must be valid JSON with every row."
goal = "Add a --json flag to the export command"

[[criteria]]
id = "C1"
text = "The output must be valid JSON with every row"   # the human's words
source = "human"
coverage = "Proves valid JSON and row count on 5 generated tables; not very large exports"
check = "python3 -m unittest tests.test_export_json"

[[criteria]]
id = "C2"
text = "Given no data, when `export --json` runs, then it prints [] and exits 0"
source = "agent-proposed"
check = "python3 -m unittest tests.test_export_empty"
```
