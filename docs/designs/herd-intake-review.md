# Herd Intake Review: the criteria read as the human would, before the code

* **Author:** Toni
* **Status:** Implemented in 0.11.0, removed in 0.12.0 (see Removal below). Kept as a record; none of it is in the code.
* **Date:** 2026-11-24

--------------------------------------------------------------------------------

## Removal (0.12.0)

A live Haiku run on 0.11.0 showed the intake review did not do its job. The Sonnet intake reviewer passed an `inputs` entry whose `program` form took a pre-chosen walkable pick cell for each product, the exact flaw it was built to catch. Its one real catch, human criteria that were not verbatim quotes, the 0.10.0 verbatim block already refuses in code. Meanwhile it added review rounds and cost, and it played a part in the deadlock 0.11.1 fixed. 0.12.0 removes the agent, its hook entry and the `intake` note, along with the `problems()` rule, the escalation rule, the report lines and the run skill step. Kept: the final reviewer also gets the request and the `inputs` list (I4), and the 0.10.0 checks. Old tasks keep any `intake` notes and `intake` key in `start.json`; Herd ignores them.

## Overview

Before any code, at medium and high risk, a fresh-context reviewer reads the human's request next to the agent's `task.toml` and answers as the human would. A hook records the review from the session logs, and `herd done` needs its PASS for the criteria as they are; one recorded after all checks first passed is shown as late.

## Problem

* The final `herd-reviewer` sees the goal, the criteria and the diff. None of them shows whether the program's input form is the one the human described. A Haiku build took a pre-chosen pick cell per product where the human said products are located in the map. No review and no attack noticed.
* `inputs` (0.9.0) asks the agent to write both forms, but nothing compares them with the request except the agent itself.
* A finding about the criteria is cheap before the code and expensive after it.

## Design

**I1. Agent.** `agents/herd-intake-reviewer.md`, `model: inherit`, tools Read, Grep and Glob (no Bash, no edits). It is given two paths, `.herd/tasks/<slug>/request.md` and `task.toml`, and answers four questions: does every criterion cover every word of the request, with generated cases for any or every; is each `inputs` entry's `program` form its `human` form, or what must the caller prepare first; what does the request promise that nothing tests; does any criterion or `known_limits` narrow the human's words. It ends with exactly `HERD-INTAKE: PASS` or `HERD-INTAKE: FAIL`.

**I2. Recording.** A second SubagentStop entry, matcher `^herd:herd-intake-reviewer$`, runs `herd review-hook`. `review_hook()` handles both agents with the same log reading (spike S3), models, sessions Herd saw, and verdict line (`INTAKE_VERDICT`). For the intake reviewer it records an `intake` note with:

* `saw`: the reviewer read `request.md` (when one was recorded) and `task.toml`, from its Read calls and Bash readers (`reviewer_saw()`); `code_unread` names the ones it did not.
* `criteria_sha`: `criteria_sha(task)`, a hash of the goal, each criterion's id, text, source, check and coverage, `test_budget`, `known_limits` and `inputs`, from `task.toml` at the hook. This is what the reviewer judged; timeouts and comments are left out. An unreadable `task.toml` gives `None`, which never matches. When `task.toml` was modified after the reviewer's last Read of it (its time against the log line's), the file counts as not read, so a builder cannot rewrite it while the reviewer runs.
* `round`: whether the reviewer's tier would count, for the escalation count.

**I3. Counting.** `intake_needed()` holds when `review_needed(ev)` does and `start.json` has `intake: true` (written by `herd init` from 0.11.0). `intake_state()` takes the latest intake note:

1. Its `criteria_sha` must equal the evidence's: otherwise "changed after the intake review: review them again".
2. `_tier_rule()`: recorded by the hook, both models known, `saw`, PASS, and the tier at least the builder's plus `[review] step`.

One recorded at or after `green.json`'s note index (when all checks first passed) still counts, and `_rule_lines()` says it came after the code, in the report and the PR. A refusal there would deadlock a task whose risk rose after green, and a one-character edit to `test_budget` would get past it, so it is shown, not refused.

`problems()` adds `intake review missing (<why>)` with the model to spawn and the two paths; `NEXT_STEPS` maps it to the stop record's `next`. `_escalations()` adds "3 intake review rounds gave no PASS", by the same `_failed_rounds()` count as the final review.

**I4. Final review.** `agents/herd-reviewer.md` and the gate's refusal give the final reviewer the request and the `inputs` list, and its instructions ask it to flag an input the code reads in another form than they describe. This is where the code's real input form is checked.

**I5. Guard.** No change was needed: the guard denies running `herd review-hook` by hand, writing Claude Code's session logs and Herd's `notes.jsonl` and `green.json`, and editing the installed plugin's agents. `herd note` has no intake kind.

**I6. Skill.** The run skill's criteria step: at medium and high risk, before code, spawn `herd-intake-reviewer` one tier above with only the two paths; fix its Blocker and Major findings in `task.toml`, then spawn it again.

## Alternatives Considered

| Alternative | Why not |
| --- | --- |
| Hash `task.toml` as a file | A timeout or a comment would void the review |
| Require the intake review before the first verify | The failing first verify is part of writing the checks; the code comes after it |
| Refuse an intake review after green | It deadlocks a task whose risk rose after green, and a one-character criteria edit gets past it |
| Parse the reviewer's Read result to hash what it saw | The log shows numbered, possibly cut lines; the file time against the log time is simpler and deterministic |
| Give the reviewer the criteria in the prompt | The builder writes the prompt; the files are what Herd recorded |

## Known limits

* A model judges the criteria; it can be wrong or agree too easily.
* It cannot see code that does not exist yet: the final reviewer and the attacks check the code's real input form.
* An agent can write the same words in `human` and `program`.
* "Before all checks first passed" is not "before the code": an agent can write the code and keep one check red. A late review is shown, not refused.
* The rewrite check compares file and log times: a file time set back is not seen.
