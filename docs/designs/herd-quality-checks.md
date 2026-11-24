# Herd Quality Checks: verbatim criteria, required fields, inputs, what the reviewer saw

* **Author:** Toni
* **Status:** Implemented in 0.10.0
* **Date:** 2026-11-24

--------------------------------------------------------------------------------

## Overview

Three rules that the skills stated in text, or that `herd verify` only warned about, become code:

1. **Verbatim human criteria (Q1).** `herd done` and the Stop gate refuse a `source = "human"` criterion whose text is not a quote of the recorded request.
2. **Required fields (Q2).** On the standard route at medium and high risk they refuse while `test_budget`, `known_limits` or a human criterion's `coverage` is empty.
3. **What the reviewer saw (Q3).** The review hook reads the reviewer's own tool calls. A review counts only if the reviewer printed the diff or read every changed code file. Each `path:line` it cites is checked and the bad ones are shown.
4. **Inputs (Q4).** At medium and high risk `inputs` missing, incomplete or written inside a criterion is refused, not only warned about.
5. **Reviewer one tier above (Q5).** `[review] step` defaults to 1 again.

**Principle.** A check refuses (it adds to `problems()`, which `herd done` and the gate use) only where code can tell for certain. Where it can be wrong, it records the finding and shows it in the report and the PR. No check reads the agent's wording with a word list: such lists can be dodged and flag harmless text.

## Problem

* `herd verify` warned when a human criterion was not a quote of the request, and the warning did not stop `herd done`. An agent could narrow the human's words ("for any call" to "for one call") and finish.
* The criteria skill asked for `test_budget`, `known_limits` and `coverage` at medium and high risk; nothing enforced it.
* The review hook recorded the reviewer's model and verdict, not whether it looked at the change. A reviewer that read nothing and said PASS counted. Its `path:line` findings were never checked.
* In a 0.9.0 Haiku run `herd verify` warned "no `inputs`" and the agent ignored it; it also wrote `inputs = "..."` inside each `[[criteria]]` table, where Herd never reads it. The same run's Haiku reviewer, on the builder's model, gave three FAIL rounds on narrow robustness bugs and the run escalated.

## Design

### Q1. Verbatim human criteria

`_squash(text)` normalizes both sides before the comparison: NFKC and case folding; Markdown links to their text; Markdown escapes; quote marks and code ticks; `*`, `_` and `~` at a word's edge (emphasis, not `2*3` or `max_len`); every dash to a hyphen and a spaced dash to a space; `.,;:!?` and the ellipsis before a space or the end; runs of whitespace to one space. In the request only, line-start quote, heading and list markers go too, so a criterion that starts with `> 5` keeps it. Words, numbers (`20.5`) and operators (`<`, `>=`, `!=`) stay. `_quotes(text, source)` searches the normalized text in the normalized source with whole-word and whole-number edges: `return 1` is not in `return 10`, `return 1.5`, `1-2` or `1,000`. An empty text quotes nothing.

`human_unquoted(task, request, notes)` lists the human criteria that quote neither the request nor a `human-change` note whose text starts with that criterion's id. The frozen-criteria rule in `verify()` accepts a rewording by the same `_quotes` test, so one note settles both rules. A frozen human text that did not quote the request may be changed to one that does without a note: that restores the human's words, it cannot narrow a quote. `problems()` adds one line per id, which says to copy the words, or to record the human's rewording, or words from a file the human named, with `herd note --human-change "C1: <their words>"`. With no `request.md` the list is `None` and it stays a warning.

### Q2. Required fields

When `review_needed(ev)` holds (standard route, medium or high effective risk), `problems()` adds `test_budget is empty: ...`, `known_limits is empty: ...` and `coverage of human criterion C1 is empty: ...`, each one line ending with the TOML line to write. Whitespace counts as empty. `NEXT_STEPS` maps each to a next step for the stop record.

### Q3. What the reviewer saw

`review_hook()` already finds the reviewer's log at `<session>/subagents/agent-<id>.jsonl` (spike S3). `reviewer_saw()` reads every `tool_use` block in its assistant lines:

* `Read` with a `file_path`: a file read.
* `Bash` with a `command`, split with the guard's `_segments()` and following `cd`: a `git diff`, `git show` or `git log -p` (git's global options allowed, matched with the guard's `_rule_hit()`) prints the change unless a summary-only flag (`--stat`, `--name-only`, `--name-status`, `-s`, `--no-patch` and the like) is given without `-p`; `cat`, `nl`, `less`, `more`, `head`, `tail`, `bat` and `sed` read the files they name.

A redirect (`git diff > d.txt`) or `--check` and `--output` print nothing to the reviewer either. The changed code files are `task_changes()` (the red-first rule's view: a file dirty at `herd init` counts once it changes) filtered by `is_code()`; when no code file changed (tests, config, CI only), every changed file counts, so such a change cannot get a blind review counted. The note records `diff_seen`, `code_total`, `code_read`, `code_unread` (at most 20) and `saw`: a diff was printed, or every changed code file was read, or the changed files cannot be told (no commit at `herd init`). `_tier_rule()` returns `the reviewer did not read: <files>, and ran no git diff or git show` when `saw` is false, before the verdict, so such a review is also not a round for the escalation count. A hook review without `saw` (recorded before 0.10.0) does not count.

`bad_refs()` finds `path:line` and `path:first-last` in the report, where the path has a file extension or a folder; URLs, times and `C1:2` do not match. A reference is bad when no file is found (under the project folder, the repository top, or a repository file whose path ends with it, as in `herd.py:5`), or a line is 0 or past the end of every match. The latest review's bad references are a line in `_rule_lines()`, so the report, the final report and the PR list them under Not proven. They never refuse: a cited line can be the old side of the diff.

The hook stays non-blocking and silent. The guard already denies writing Claude Code's session logs (Write, Edit, and Bash `>`, `cp`, `mv`, `tee`), so the builder cannot add tool calls to a reviewer's log.

### Q4. Inputs

`input_warnings(task)` reports, by structure only: a criterion table with an `inputs` key (it belongs at the top level as `[[inputs]]` tables, not inside `[[criteria]]`), `inputs` missing, not a list, or an entry without a non-empty `human` and `program`. `verify()` stores the list in the evidence as `inputs_left`; `problems()` adds it when `review_needed(ev)` holds, next to Q2. Each message shows the table to write. At low risk it stays a warning, and the quick route is exempt. `herd init`'s template has a commented `[[inputs]]` table, and the criteria skill's example puts one at the top level.

### Q5. Reviewer one tier above

`DEFAULT_STEP` is 1, as in 0.7.0. `herd status`, the gate's refusal, the stop record's `review.needed` and `next`, the run skill and the reviewer's description say one tier above the builder. `[review] step = 0` keeps the reviewer on the builder's model.

## Alternatives Considered

| Alternative | Why not |
| --- | --- |
| Compare human criteria by word sets, ignoring order | Lets "x must not fail" match "x must fail, not hang"; order is part of the quote |
| Drop every punctuation mark | Turns `x > 5` and `x < 5` into the same text |
| Refuse a review whose references are bad | A line on the old side of the diff is a real finding |
| Ask the reviewer to list what it read | The reviewer's words are what this check must not trust |

## Known limits

* A verbatim part of a sentence passes, so a quote can still narrow by truncation.
* `human-change` notes are written by the agent: one note gets past Q1. They are shown to the human as changes to confirm.
* A partial read counts as a read. A `git diff` inside `bash -c`, a script or an alias is not seen. A diff that prints nothing for another reason (`--cached` after a commit, a pathspec that matches nothing, `git log -p -0`) still counts.
* A request hard-wrapped right before `>`, `-` or `10.` reads that mark as Markdown, so a quote across that wrap is refused.
* Q4 checks the structure, not whether the `program` form is honest.
