# Herd Focused Review: one review pass whose questions come from the evidence

* **Author:** Toni
* **Status:** Draft for Herd 0.13.0. Not built. Merge is gated on the replay and on a benchmark leg (Order).
* **Date:** 2026-11-24

--------------------------------------------------------------------------------

## Overview

Today the `herd-reviewer` reads the whole change and writes findings rated Blocker, Major or Nit. The rating decides the verdict, and the rating is unreliable. This design replaces that with one pass built from the task's own records.

**Decisions taken by the engineer** (kept unless the code shows one cannot work; where it cannot, the Open Questions say so):

1. `herd review-brief` adds a numbered Focus list built by code from `task.toml` and `notes.jsonl`: one item per entry of four categories, each quoting the evidence text and naming what to attack it with. No word list reads the agent's text: items come from fields and structure.
2. The reviewer answers every item by its id with `holds` or `breaks`. A `breaks` carries a command that fails. The review hook checks structurally that every item is answered and runs each `breaks` command itself. Severity labels decide nothing; a failing command does. General findings stay allowed and fail the review only with a failing command.
3. After a `breaks`, the builder fixes and `herd verify` re-runs the checks. The next pass is a delta review: the broken items and what was added since. A pass in which every item holds ends the review.
4. The attacks still run before the review and at every `herd verify`. Nothing about them is relaxed.
5. Cost and time per run are estimated and then measured. The target is fewer review rounds than 0.12.1 (10 rounds over 6 runs) with no lost quality.

No new agent and no new hook entry. The reviewer, the SubagentStop hook and the brief stay; `hooks/hooks.json` only gets a longer review-hook timeout.

**Terms.** Builder, reviewer, tier, active task: as in [`herd-guardrails.md`](herd-guardrails.md). *Attack*: one of the five standard attacks in `ATTACKS` (`bad-input`, `collision`, `one-bad-part`, `recount`, `refusal`), each a command `herd verify` runs. *Saw rule*: a review counts only if the reviewer printed the diff or read every changed code file (`reviewer_saw()`, `review_files()`). *Round*: a review that counts toward the escalation limit; `review_hook()` sets `round`. *Lost store*: in the benchmark, a store whose route the program refused although another side of the shelf was reachable. *Item*: one question in the Focus list. *Benchmark*: the supermarket-route runs in `examples/supermarket-route`, built with Haiku. *Pass line*: the one line `herd verify` prints once a review that counts is recorded (`pass_hint()`). *`EXTRA`*: a general finding line (F3). *Weak pointer*: an item that names the right attack but not the defect. *`GUARD_STATE`*: the list of state files only the CLI may write.

## Problem

The six-run analysis of 2026-11-24 (kept outside the repository) read 31 review rounds over 12 Haiku runs of the benchmark, six on 0.12.0 and six on 0.12.1:

* 10 Major findings in 7 rounds, all real bugs by the analysis (each reproduced or confirmed by a later round). The other 24 rounds found only Nits and Minors. Sonnet reviews were 41% of run cost on 0.12.0 and 28% on 0.12.1.
* Severity is unreliable. One defect (entrance picks mis-ordered) was a Nit, then "correct", then a Major. Another (no list-order fallback) was a Major, then a Minor.
* A defect lost stores in three runs: an input form narrower than the request. The program took a pick cell per product, which pushes a choice onto the caller. Seven rounds raised it as a Nit or Minor and nobody fixed it, because a Nit does not fail the review.
* One refusal attack used a check that shares the code's own assumption (a plain flood fill). It passed and proved nothing.
* The real findings sat in a few places the evidence already marks.

| Category | Source | Real Majors | Lost-store runs |
| --- | --- | --- | --- |
| A | the `coverage` of each human criterion, against its claim | 3 (pick side, probable; mean-only test; unbounded cache) | 0 |
| B | `known_limits`, `test_budget`, `open` and `decision` notes | 3 (no list-order fallback; first access cell; stale `test_budget`) | 1 |
| C | the `tried` text of each attack note | 3 (TypeError traceback; OverflowError; entrance picks, a weak pointer) | 1 (run 6, also D) |
| D | each `inputs` entry, against the request | 0 | 2 |
| none | no field points at it | 1 (README says 12 stops, code 8) | 0 |

That is 10 Majors. The README drift has no pointer in any field; it stays a job for general findings (F5) and a known limit.

Left out for lack of data: an attack marked `n/a` (the string appears in no notes file of the 12 runs) and a claim with "any" or "every" but no random inputs (19 of 42 human criteria lack the words random, seeded, generated or synthetic, and none matched a Major). Neither gets special treatment. An `n/a` attack note is an item like any other C item (F1).

## Goals

* G1: `focus_items(task, notes)` returns one item per entry, from fields and structure only, with a stable id (F1). Check: `test_focus_items_one_per_entry`, `test_focus_items_ids_are_stable`.
* G2: No word list reads the agent's text. Rewording a coverage, limit or note, without changing its fields or line breaks, gives the same ids in the same order. Check: `test_focus_items_ignore_wording`.
* G3: The list has at most 30 items plus its `decision` notes. Only `open` notes are cut, oldest first; if the rest alone exceed 30, nothing more is cut. The brief prints how many were cut. A list with no items sends the review to the old rule (G11). Check: `test_focus_cap_keeps_decisions`.
* G4: `herd review-brief` prints the items, each with its id, quote and what to attack it with, and a brief id; it appends the round to `focus.json`. Check: `test_review_brief_prints_focus`.
* G5: The hook reads the answers (F3 grammar) and checks them against the latest round of `focus.json`, which the reviewer must have echoed by brief id and which it recomputes (F4.1). A missing or unknown id, or a `breaks` without a command, makes the review not count; the reason names the ids. It is not a round. Three such reviews in a row, with no counting review between them, are an escalation. Check: `test_unanswered_focus_item_does_not_count`, `test_breaks_without_command_does_not_count`, `test_unanswered_reviews_escalate`.
* G6: A `holds` needs a command that:
  * equals one of the reviewer's logged one-line Bash calls (strip, collapse whitespace);
  * exited 0 there;
  * is not a file reader, `git diff`, `show` or `log -p`;
  * differs from the command of every other item.

  Check: `test_holds_needs_a_logged_command`. This is a floor: the log shows a command was run, not that it tested the item.
* G7: A `breaks` command must:
  * equal one logged one-line Bash call that exited 3 there (exit 3 is the reviewer's explicit "the defect is present"; any other non-zero exit, such as a typo or `NameError` (1), is not a defect);
  * exit 3 again when the hook reruns it from the project root, within the deadline, and not be denied by the guard's rules.

  Otherwise the break is unconfirmed, and F4.5 sets the verdict: a confirmed break elsewhere still gives FAIL; with none confirmed, the review does not count and the reason names the item. Check: `test_break_confirmed_by_failing_command`, `test_exit_one_is_unconfirmed`, `test_denied_command_is_unconfirmed`, `test_break_that_passes_is_unconfirmed`.
* G8: The verdict is computed from the answers. Severity words decide nothing. An `EXTRA` finding without a command never fails a review. Check: `test_verdict_from_answers_not_severity`, `test_extra_without_command_does_not_fail`.
* G9: After a confirmed break, `herd verify` reruns its command and stores `focus_breaks`; `problems()` refuses `herd done` while it exits 3 (any other result is shown, not blocking), until a later review that counts has answered that id `holds`. The next brief is a delta (F6): at medium risk, the broken items, new items and the files changed; at high risk, the full list again. A delta in which every item holds counts and ends the review; the report says when a break was closed with its command still exiting 3. Check: `test_open_break_blocks_done`, `test_delta_brief_lists_broken_items_and_changed_files`, `test_delta_pass_ends_review`, `test_high_risk_delta_is_full`.
* G10: The hook's total rerun time is capped at 120 s: 20 s per command, at most 6 commands, `breaks` first in item order, then `EXTRA`. Commands past the cap are unconfirmed, and a review with more than 6 `breaks` is `none` under rule 1 of F4.5 (the reason says to report the six that matter first, then review again). Check: `test_rerun_deadline`.
* G11: A task started on 0.13.0 has `focus: true` in `start.json`; its review needs a Focus round. A task without it, and any review recorded before 0.13.0, keeps the old rule and the `HERD-REVIEW` line. Check: `test_review_without_focus_keeps_old_rule`, `test_focus_task_needs_focus_round`.
* G12: The five attacks, the tier rule, the saw rule, the red-first rules and `ESCALATE_AFTER` are unchanged. Every existing test passes, except those F7 names, which get fixtures in the new form. Check: `python3 -m unittest discover -s tests -t .`.
* G13: Replay. `focus_items()` over the saved `task.toml` and `notes.jsonl` of the benchmark runs, notes cut at the first review note, points at each expected finding of the Not proven table. Pass bar: for the six 0.12.1 runs, all expected rows (two: the cache Major and the run 6 lost store; the fixtures are the six runs' cut files under `tests/fixtures/focus-replay/`, unskipped); for the six 0.12.0 runs, at least 8 of the 10 expected rows that name an item (run from `HERD_BENCH_DIR`; skipped when unset). Merge needs the 0.12.0 replay to have run: its folders must be restored first. Both replays show fit, not prediction. The replay prints the item count per run (none above 30 besides decision notes) and the items that point at no finding. Check: `test_replay_points_at_findings_0121`, `test_replay_points_at_findings_0120`.
* G14: Benchmark leg. Six Haiku runs on the new version, scored by the benchmark verifier. Pass: at most 8 review rounds over the six runs (0.12.1: 10), no run loses a store, Sonnet cost per run at most 0.12.1 plus 50% ($0.15). Six runs are a smoke test: they cannot prove "no lost quality" (3 of the 12 earlier runs lost stores). Check: the leg's table, measured.

## Non-Goals

* No new agent, no second reviewer, no change to which tier reviews.
* Attacks are not relaxed, replaced or moved (decision 4). The reviewer is a second look at what they left.
* No judgement of wording: no word list on coverage, limit, note or input text. Splitting `known_limits` reads line breaks and list markers only.
* No item for a field that has no entry. A missing limit is a general finding.
* No change to the quick route or to low risk.
* No special treatment of `n/a` attacks or of "any" claims without random inputs (Problem).

## Open Questions

1. **For B and D, what does an item name to attack?** Code can name a criterion's `check` (A) and an attack's `check` (C). For B (limits, notes) and D (inputs) the only structural pointer is the changed code files; mapping a limit or an input to a file would read wording. D lost two stores, so its item carries the strongest instruction: build the input from the `human` words and request, not from the `program` form (F1). The replay (G13) and the benchmark leg show whether that is enough.
2. **Is a delta safe at medium risk?** It can miss a regression in an item it did not re-ask. Mitigation: the attacks and checks rerun at every verify. At high risk the delta is the full list. Whether to re-ask all items after any code change at medium risk is for the benchmark leg to answer, by counting regressions.
3. **Decision 2 says a `breaks` command "fails".** A plain non-zero exit cannot show a defect (a typo exits 1), so the design narrows "fails" to exit 3, which the reviewer must choose on purpose (G7). Does a Sonnet reviewer do that reliably? Spike S5(b) tests it; if not, the fallback is a `BREAK:` line in the output instead of an exit code.

## Critical User Journeys (CUJs)

### CUJ 1: A narrow input form, caught

* **Given**: Haiku builder, medium risk, checks and attacks pass. `inputs` has `human = "all the products localised in the map"` and `program = "{id, short_name, x, y}; x,y is a floor cell next to the shelf"`.
* **When**: Item `D:1` of the brief says: build the input from the request's words (a product on its shelf cell), not from the `program` form. The reviewer runs `python3 -c "..."` that calls the program with a product on a shelf cell whose first neighbour is walled in, and exits 3 when the program refuses it.
* **Then**: The reviewer answers `FOCUS D:1: breaks: python3 -c "..."`. The hook reruns that call, sees the same exit 3, and records FAIL. The command is self-contained, so `herd verify` can rerun it after the fix. Test: `test_break_confirmed_by_failing_command`.

### CUJ 2: A limit that is a bug

* **Given**: `known_limits` has a line "may fail on stores whose products are already in list order".
* **When**: Item `B:limit-1` quotes it. The reviewer builds such a store with `python3 -c` and the program does worse than list order.
* **Then**: `breaks` with that command, confirmed by the rerun. Before this design the same defect was a Major in one round and a Minor in the next. Test: `test_verdict_from_answers_not_severity`.

### CUJ 3: Every item holds

* **Given**: 14 items. The reviewer answers each `FOCUS <id>: holds: <command>`; each command is in its log and exited 0.
* **When**: The hook records the review.
* **Then**: The verdict is PASS and the round counts. `herd verify` prints the pass line, and the builder commits and runs `herd done`. One round. Test: `test_holds_needs_a_logged_command`.

### CUJ 4: A break, a fix, a delta pass

* **Given**: Item `C:refusal` broke with a confirmed command.
* **When**: `herd done` refuses: "focus item C:refusal still breaks: `<command>`". The builder fixes the code and runs `herd verify`, which reports the command now passes. The builder runs `herd review-brief` again: a delta of `C:refusal`, new items and the changed files.
* **Then**: The reviewer answers them; all hold; the review counts. Tests: `test_open_break_blocks_done`, `test_delta_pass_ends_review`.

### CUJ 5: A reviewer that does not answer

* **Given**: The reviewer writes prose and no `FOCUS` lines, or answers `breaks` with a command that exits 0 or 1.
* **When**: The hook records it.
* **Then**: It does not count and is not a round. The reason names the ids and says to spawn the reviewer again with the brief. After three such reviews in a row the gate escalates to the human. Test: `test_unanswered_focus_item_does_not_count`, `test_unanswered_reviews_escalate`.

## Design

### F1. The focus list

`focus_items(task, notes)` in `herd.py`, next to `review_brief()`. `task` is `load_task()`, `notes` is `load_notes()`. It returns dicts `{id, cat, quote, qhash, attack_with}` in this order. Ids are append-only: adding a note or an entry never changes another item's id.

* **A**, id `A:<criterion id>`: each criterion with `source == "human"` and a non-empty `coverage`. `quote` is the coverage; `attack_with` is the criterion's `check` (or "no check") and its text as the claim.
* **B**: `B:budget` for `test_budget`; `B:limit-<k>` for each non-empty line of `known_limits`, `k` counting from 1 (`known_limits` is a string; a list marker `-`, `*` or `1.` starts a line; a hard-wrapped limit becomes several items, so the agent file asks for one limit per line); `B:note-<n>` for each `open` and `decision` note, `n` being its 0-based position in `notes.jsonl` (timestamps have one-second resolution and collide). `attack_with` is the changed code files (`review_files()`).
* **C**, id `C:<attack>`: for each attack in `ATTACKS`, the latest `tried` note with that `attack`, read from `load_notes()` (`_attack_states()` reads the evidence, which the brief does not have). `quote` is its text; `attack_with` is its `check`, or its `n/a:` text. An attack with no note gets no item: `problems()` already refuses that.
* **D**, id `D:<k>`, `k` from 1: each `inputs` entry that is a dict, positional. `quote` is `human -> program`, in the form `inputs_line()` prints for one entry (it takes a list, so the item passes a one-entry list). `attack_with` is the changed code files and the instruction: build the input from the `human` words and the request, not from the `program` form, and run the program on it.

`qhash` is a hash of the quote. Only fields and structure are read: a note's `kind`, `attack`, `check` and position, a criterion's `source` and `coverage`, line breaks and list markers. A human criterion with no `coverage` gets no A item; `problems()` already refuses it at medium and high risk. The cap (G3) cuts the oldest `open` notes first and prints the cut.

### F2. The brief and `focus.json`

`review_brief()` appends, before the file list, `Focus list: answer every id`, the items, and a line `Brief: <id>`, the id being a hash of the items and the time. It appends the round `{brief, at, kind, items (id, qhash), files_sha}` to `.herd/tasks/<slug>/focus.json`. `kind` is `full` or `delta` (F6); `files_sha` is a hash of each file in `review_files()` at that time. A second `review-brief` adds a round and overwrites nothing. `focus.json` is added to `GUARD_STATE`: Herd's CLI and hooks write it, the agent never does. `herd init` writes `focus: true` to `start.json` (G11).

### F3. The reviewer's answer

`agents/herd-reviewer.md` keeps its instructions to read every listed file and run the diff command. When the brief has a Focus list it is told to:

* start its final report with `BRIEF <id>`, then one line per item, each matching `^FOCUS (\S+): (holds|breaks): (.+)$` after trimming whitespace and Markdown marks (as `VERDICT` is read), the rest of the line being one Bash command;
* attack the item, not read it: write a small input and run the program. For a `breaks`, give a command that exits 3 when the defect is present (for example `python3 -c "import sys; ...; sys.exit(3)"`), and exit 3 for no other reason;
* make each command one line, self-contained, idempotent and at most 20 s: it may not write a file or depend on `cd`, because it is run again after the fix, by the hook and by `herd verify`, from the project root;
* add general findings as `EXTRA: <path:line> <what is wrong> :: <command>`, the command optional and, if given, held to the same rules as a `breaks`.

Without a Focus list it ends with `HERD-REVIEW: PASS` or `FAIL` as before (G11). The Blocker, Major and Nit scale is removed from the focus case.

### F4. The hook

`review_hook()` keeps its inputs (`agent_type`, `transcript_path`, `agent_transcript_path`, `agent_id`, `cwd`, `last_assistant_message`) and its checks (model, tier, `saw`, `bad_refs`). After `text` is read, and before it is clipped to `REVIEW_CHARS` (2000, too short for 20 answers):

1. **Parse and select the round.** An `open` or `decision` note added while the reviewer runs adds an item, so the builder must add none until the review is recorded (the run skill says so). `parse_focus(text)` reads `BRIEF <id>` and the lines matching the F3 regex. The id must be the latest round of `focus.json`. For a `full` round the hook also recomputes `focus_items()` and requires every recomputed id to be in the round (the builder cannot show the reviewer an older, smaller brief); for a `delta` round every id still open must be in it. No `BRIEF` line, an older round, or a missing id makes the review `none`, naming the ids.
2. **Logged calls.** `_assistant_lines()` keeps only assistant lines, but a tool result is a `user` line. A new loader `_log_lines()` returns both, and a new `reviewer_calls(lines)` returns each Bash call's normalised command, its exit status and whether it was denied, matching result to call by `tool_use_id`. `reviewer_saw()` is unchanged. Its tests in `tests/test_herd_quality.py` stay; the new function gets its own. Spike S5(a) decides whether the log has an exit status: if it holds only an error flag, zero against non-zero is all that can be read, a break cannot be confirmed by exit 3 in the log, and the design changes. A result that cannot be read is unconfirmable, never a pass.
3. **Answers.** Missing ids, unknown ids and malformed lines are listed. `holds` is checked by G6.
4. **Reruns.** Each `breaks` command, then each `EXTRA` command, is rerun with `run_check()` from the project root, within the G10 deadline, after the guard's rule check has been asked about it (the rule check only: it must not write a `guard` note, so `guard()`'s rule match is called without its `add_note`, with a test). A command the guard denies, or the log shows as denied, is unconfirmed. The hook never reruns a `holds` command. It compares `content_id()` before and after the reruns (`.herd/` is ignored by it); a change is recorded as `none`, so a rerun cannot void a high-risk review.
5. **Verdict.** Apply these in order; the first that matches wins:
   1. `none`, for structure: a stale or unknown round, a missing, unknown or malformed id, a `holds` without evidence, more than 6 `breaks` (G10), or a content change caused by the reruns (F4.4). Nothing is judged then, so a confirmed break does not make it FAIL. The reason names the ids, missing answers first, so the builder fixes one thing at a time.
   2. FAIL: every id is answered and at least one `breaks` is confirmed. The reason also names unconfirmed ones.
   3. `none`, for an unconfirmed `breaks` with none confirmed: the reason names the item. An unconfirmed `EXTRA` is shown and never makes the review `none`.
   4. PASS: every id answered with evidence, no `breaks` left unconfirmed.

   A `none` review does not count and `round` is false; a new `_tier_rule` reason carries the text.
   `_escalations()` counts three `none` focus reviews in a row, with no counting review between them, as its own cause, apart from `_failed_rounds()`.
6. **Record.** The review note stores `focus: {brief, kind, answered, unanswered, unconfirmed, holds: [ids, at most 30], breaks: [{id, command (clipped to 300), exit, tail (clipped to 300), confirmed}], extra: [...]}`. The hook appends the full answers, commands and exits to the round in `focus.json`, which `REVIEW_CHARS` does not clip. One round is a few kilobytes.

`hooks/hooks.json` keeps the review hook's timeout at 30 s today; this raises it to 180 s: the G10 deadline of 120 s plus parsing and the existing log reads. The guard and pre-init hooks keep 10 s.

### F5. General findings

A finding that matches no item is an `EXTRA` line. It appears in the report and the PR and never fails a review without a failing command (exit 3, rerun by the hook). An `EXTRA` break has an id, `x1`, `x2` in line order, so a delta can ask about it. A README that disagrees with the code is such a finding: a `grep` that exits 3 on the stale number would make it count; without one it is shown and the builder decides.

### F6. After a break

An *open break* is the latest confirmed break whose item has no later counting review answering `holds` for it. `verify()` and the delta both read it.

* `verify()` reruns the `command` of each open break, like an attack check, and stores `focus_breaks` in the evidence (command, exit, output tail). `problems()` adds `focus item <id> still breaks: <command>` while it exits 3, with a `NEXT_STEPS` entry. Any other exit (a fix that changed the command's inputs, 126, 127, a timeout) is shown, not blocking. This is the verify-time feedback `review_state()` does not give. A later review that is `none` does not close an open break.
* `herd review-brief` builds a delta (`kind: delta`) when there is an open break and the risk is medium. It holds: the open breaks' ids, matched by id and `qhash` (an item whose quote changed is new); the new items, meaning ids absent from the previous round or with a different `qhash`, including notes added since; and the files whose hash differs from that round's `files_sha`, plus the "New files, in no `git diff`" line. The diff command is `git diff <the commit herd init recorded> -- <those files>`, the commit `review_brief()` already prints. The hook counts reads against that file list. At high risk `review_state()` already needs a review of the final content, so the brief is `full`.
* A delta where every item holds counts and ends the review. A `holds` for an open break's id, with a logged command that exited 0, closes it even if its old command still exits 3: the reviewer decided the old command was wrong, and the report says so for the human to read. The builder cannot close it.

### F7. Review states, strings and tests

What counts, by review kind and risk:

| Case | Medium risk | High risk |
| --- | --- | --- |
| Full focus review, PASS | counts | counts for that content only (a commit alone does not change it) |
| FAIL, then a clean `herd verify` | `herd done` still needs a counting review: a delta | needs a full review of the final content |
| Review `none` | does not count, not a round | same |
| Task without `focus: true`, or review before 0.13.0 | old rule: `HERD-REVIEW` line | same |
| Task with `focus: true`, review with a trailing `HERD-REVIEW: PASS` and no focus answers | does not count; the reason says to answer the Focus list | same |

`review_state()` and `_tier_rule()` implement the table. The legacy path stays for tasks started before 0.13.0 and is removed in a later version, noted in the changelog.

* `skills/run/SKILL.md` step 7: pass what `herd review-brief` prints; the reviewer answers each id; fix breaks, run `herd verify`, run `herd review-brief` again for a delta; commit and `herd done` after a PASS that counts. The run skill's word budget is raised in its test by the 30 or so words the step needs, and "decline Nits in one line" goes. The three-round limit lives in code (`ESCALATE_AFTER`, `_escalations()`).
* Strings that say Blocker or Major: `_tier_rule()` (the verdict reason), `pass_hint()`, `final_report()` and `pr_body()`, `README.md` (the review rows), `agents/herd-reviewer.md`.
* Existing tests that change: `tests/test_herd_review.py`, `tests/test_herd_quality.py` (the `reviewer_saw` callers), `tests/test_harness_rules.py` and `tests/test_herd_cli.py` (hook-review fixtures: fixtures of the old rule start the task without the `focus` key; the others get focus answers), `tests/test_herd_guard.py` (`GUARD_STATE` gains `focus.json`). `herd_arbiter.py` and `herd_escalation.py` read no review field, so their tests stay.
* `CHANGELOG.md` 0.13.0 and `version` in `.claude-plugin/plugin.json`.

### F8. Cost and time estimate

From the analysis: a 0.12.1 review round cost Sonnet $0.059 on average ($0.591 over 10 rounds), a 0.12.0 round $0.088 ($1.858 over 21). A focus round runs a command per item, so assume 1.5 to 2 times a round: $0.09 to $0.12 on the 0.12.1 base. Assume 1.2 rounds per run (a delta in about one run in five). That gives $0.11 to $0.14 per run, against $0.10 on 0.12.1 and $0.31 on 0.12.0. So the design costs 10% to 40% more than 0.12.1 and under half of 0.12.0, and fits the G14 cap of $0.15. Pessimistic: twice a round on the 0.12.0 base ($0.18) and two rounds is $0.35, above the cap; above $0.15 the owner decides whether the rounds saved are worth it, because Herd does not trade quality for tokens. The hook adds up to two minutes of wall time per round and no model cost. Rounds per run: 1.7 on 0.12.1, 3.5 on 0.12.0, assumed 1.2 here.

## Order

1. **Spike S5** (`docs/spikes/s5-focus-answers.md`), before any code, in the way of S3 in the guardrails design: (a) the reviewer's log carries, for each Bash call, a result matched by `tool_use_id` with an exit status or a denial, as G6, G7 and F4.2 need; (b) a Sonnet reviewer follows the `BRIEF` and `FOCUS` line shapes, and exit 3, from a brief of 14 items. Change this design if either fails.
2. **Replay.** Create `focus_items()` and the fixtures `tests/fixtures/focus-replay/` (cut `task.toml` and `notes.jsonl` of the six 0.12.1 runs, generic benchmark data) and both replay tests. If an expected row is not pointed at, stop and change the categories before any hook change.
3. Modify `herd.py`: split `guard()`'s rule check from its `add_note` call, `parse_focus()`, `_log_lines()`, `reviewer_calls()`, the verdict and the reruns (`tests/test_herd_review.py`, fixture logs).
4. Modify `review_brief()`, `focus.json`, `GUARD_STATE`, `herd init`'s `start.json`, `agents/herd-reviewer.md`.
5. Modify `verify()`, `problems()`, `review_state()`, `_tier_rule()`, `NEXT_STEPS`, `_escalations()` and the delta (F6, F7 table).
6. Modify the skill, README, strings of F7, `CHANGELOG.md`, `plugin.json`, `hooks/hooks.json`; update the named existing tests.
7. **Benchmark leg before merge.** Six Haiku runs on the new version (G14). This changes what ships as reviewed: quality comes before tokens. Merge only if G13 and G14 hold.

Use Herd on Herd: each step is a `/herd:run` task whose criteria are the Goals above. "Not proven" and Order step 1 extend the guardrails format.

## Alternatives Considered

| Alternative | Why not |
| --- | --- |
| Keep severity and ask for better ratings | One defect got three ratings in three rounds; a prompt does not fix that |
| A word list on the agent's text to find narrowing words | It reads wording, can be dodged and flags harmless text (the lesson of [0.9.0 and 0.10.0](../../CHANGELOG.md)); items come from fields |
| A focus list written by the builder | The builder would choose what is checked; code builds it from records |
| `holds` accepted with no evidence | The same failure as a prose "looks fine"; see the intake review below |
| The hook also reruns `holds` commands | A passing command proves little and doubles hook time |
| `herd verify` runs the `breaks` commands only at the next verify | A break is not confirmed before the builder edits |
| A probe directory for break scripts | It changes the reviewed content and the guard; self-contained commands do not |
| Two reviewers, one per category | Twice the cost for the same evidence |
| Drop review rounds and rely on attacks | The attacks missed the lost-store defect in three runs; review found 10 real Majors |

### How this design avoids the failure of the intake review

[`herd-intake-review.md`](herd-intake-review.md) was removed in 0.12.0 because its reviewer passed the very flaw it was built for: an `inputs` entry that pre-chose the pick cell.

| Intake review | This design |
| --- | --- |
| Ran before the code; it judged words and could not see the real input form | Runs after the code and all checks; D items say to run the program on the request's form |
| A PASS needed only a model's opinion | A PASS needs a logged command per item that exited 0; a FAIL needs a command that fails when Herd reruns it |
| One verdict for the whole file | One id per entry, so the input form is its own item that cannot be skipped |
| An extra agent, hook entry and round | The same reviewer and hook, one pass; a delta only after a real break |

It does not remove the weakness that a model can agree too easily. It makes agreeing cost a logged command, and makes the input form a numbered item of the final review. It does not read the log's output: a `holds` command that tests nothing passes (Risks).

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| A `holds` command proves nothing (`echo ok`) | G6 bars readers and diffs; the report lists every `holds` command for the human; stays a known limit |
| A `breaks` command fails for the wrong reason | G7: exit 3 is explicit, in the log and on the rerun; a typo exits 1 and is unconfirmed. Known limit: a reviewer's wrapper can still exit 3 wrongly; the report shows the output tail |
| The rerun is as dangerous as the reviewer's own call | It is no safer than that call: the guard is asked first, a denied command is unconfirmed, and only whole logged calls run |
| A rerun changes files and voids a high-risk review | Commands are self-contained and idempotent (F3); the hook compares `content_id()` before and after (F4.4) and records a change as `none` |
| The item list grows with the notes | Cap of 30, decisions kept, the cut printed (G3) |
| A delta misses a regression at medium risk | Open Question 2; attacks and checks rerun at every verify; the leg counts regressions |
| The builder trims the brief, shows an old one or deletes `focus.json` | The hook needs the echoed id to be the latest round and recomputes the items (F4.1); `start.json` says a focus round is needed (G11) |
| The reviewer writes prose | G5: the review does not count, and three in a row escalate |
| Cost per round rises | F8 estimate; G14 measures it |
| A finding has no field (README drift) | A general finding; a known limit |

## Not proven

* That the items point at the findings. The replay is the test. Only the six 0.12.1 runs are on the machine this was written on; the six 0.12.0 folders the analysis names are not. Checked by reading the saved 0.12.1 run 6: criterion C2 has the coverage "Does not prove ... stores beyond 300x300" against the human claim "even very big ones" (the unbounded-cache Major, A); its `inputs` entry gives each product as bare `x,y` with "cells not in blocked are walkable" (D); its refusal note says "refused exactly when a plain flood fill says unreachable" (C), the check that shared the code's assumption. The other rows below come from the analysis and are not replayed yet.

| Finding | Expected item |
| --- | --- |
| 0.12.0 run 1, pick side (Major) | `A` on the "whatever layout" criterion, probable |
| 0.12.0 run 1, TypeError traceback (Major) | `C:bad-input` ("every CLI entry point") |
| 0.12.0 run 4, OverflowError (Major) | `C:bad-input` ("every map and list file bad in each way") |
| 0.12.0 run 4, entrance picks (Major) | `C:collision` or `C:recount`, weak |
| 0.12.0 run 5, no list-order fallback (Major) | `B:limit-k` on list order |
| 0.12.0 run 5, mean-only test (Major) | `A:C4` ("mean time saving") |
| 0.12.0 run 6, first access cell (Major) | `B:budget` ("Not tested: access cells") |
| 0.12.0 run 6, stale `test_budget` (Major) | `B:budget` |
| 0.12.0 run 6, README 12 vs 8 (Major) | none: general finding |
| 0.12.1 run 6, unbounded cache (Major) | `A:C2` (checked above) |
| Lost stores, 0.12.0 run 2 | `B:note-<n>` on the first walkable neighbour |
| Lost stores, 0.12.0 run 5 | `D:1` ("a floor cell next to the shelf") |
| Lost stores, 0.12.1 run 6 | `D:1` and `C:refusal` (checked above) |

The G13 bar for 0.12.0 is 8 of the 10 rows that name an item (the README row names none).
* That a model with an item in front of it attacks the item. The leg tests that, on six runs.
* The cost and time: an estimate until the leg.
* That a `holds` command in the log tests the item (G6 is a floor), and that exit 3 means the defect and nothing else.
* Part of the lost-store score is the benchmark adapter's contract (it hands over a first-neighbour cell with no reachability check), not Herd. The request says "whatever its layout", so the categories apply, but a harness fix would change the baseline.
* The categories were fitted to the same 12 runs the replay checks, so the replay shows fit, not prediction. The leg runs new tasks.

## Context and sources

* The six-run analysis of 2026-11-24, kept outside the repository: the table of 31 rounds, the real-or-not verdict of each Major, the pointer categories, the lost-store section and the cost figures.
* `scripts/herd.py`: `review_brief()`, `review_files()`, `review_hook()`, `reviewer_saw()`, `review_state()`, `_tier_rule()`, `_failed_rounds()`, `_escalations()`, `problems()`, `verify()`, `run_check()`, `inputs_line()`, `bad_refs()`, `add_review()`, `_clip()`, `GUARD_STATE`, `REVIEW_CHARS`, `ATTACKS`, `VERDICT`, `ESCALATE_AFTER`. The hook inputs are those the review hook reads today (spike S3, [`s3-hook-inputs.md`](../spikes/s3-hook-inputs.md)).
* `agents/herd-reviewer.md`, `skills/run/SKILL.md` step 7, `skills/run/adversarial.md`.
* `CHANGELOG.md` 0.12.1, 0.12.0, 0.10.0, 0.9.0 and 0.7.0.
* [`herd-guardrails.md`](herd-guardrails.md) (format and the tier rule), [`herd-intake-review.md`](herd-intake-review.md) (the removed reviewer).
* The owner's cost rule, "no significant added cost", is the basis of G14; the PRD's principles stop at P6.

## Review

Two EGM rounds, each run by the synthesizer over seven fresh-context reviewers (structural, design, zoom-out, implementation-readiness, codebase-details, comprehension, style). Round 2 was the last allowed.

**Round 1** on the first draft: 5 Blockers and 14 Majors after deduplication.

| Reviewer | Found | Changed |
| --- | --- | --- |
| structural | decision numbers cited but not listed; Major counts that did not add up; the replay gate could pass with 6 of 12 runs; G9 against the test edits | Decisions listed in the Overview; Problem table reconciled to 10; G12 and G13 restated |
| design | break commands had no durable home; any non-zero exit confirmed a break; an unconfirmed break still passed; free `holds` evidence; D items had no pointer | self-contained one-line commands (F3); explicit exit 3 (G7); unconfirmed means `none`; G6 bars readers and diffs; D item carries the instruction to build the input from the request |
| zoom-out | unstable numbering; hook timeout equal to its worst case; delta against G9; replay not runnable | stable ids (F1); 120 s deadline inside a 180 s timeout (G10); F6 delta rules; fixtures for the 0.12.1 replay |
| implementation-readiness | no answer grammar; `none` was not a round in code; delta state undefined | F3 regex; F4.5 and F7 table; F2 `focus.json` schema |
| codebase-details | all cited names exist; reruns bypass the guard; `_segments` returns word lists; the review note is written last | guard rule check first (F4.4); whole-call match, no segments; hook deadline |
| comprehension | mitigation claims unproven; retry bound; "latest review" unclear | open break defined (F6); three `none` reviews escalate (G5) |
| style | misstated risk row; cost target against estimate; dangling decision and P9 references | rows and F8 rewritten; references replaced |

**Round 2** on the revised draft: 1 Blocker and 12 Majors.

| Reviewer | Found | Changed |
| --- | --- | --- |
| codebase-details | Blocker: `reviewer_saw()` is fed assistant lines only and cannot see tool results; id collisions; rerun directory; test files undercounted | new `_log_lines()` and `reviewer_calls()`, S5(a) as a gate (F4.2); `B:note-<n>` by position; project root only; F7 lists the test files |
| structural | cap rule; FAIL then `none` hid the open break; retry count disagreed | G3 rewritten; open break defined (F6); three `none` reviews, one rule |
| design | an older round could be accepted; a typo confirmed a break | latest round only and recomputed items (F4.1); exit 3 (G7) |
| zoom-out | the delta is speculative; stale brief id | kept, because decision 3 asks for it, but reduced to F6 rules and judged by the leg (Open Question 2); latest round only |
| implementation-readiness | `qhash` and "new item" undefined; multi-line commands cannot match | `qhash` and the definition (F1, F6); one-line commands, normalised (F3, G6) |
| comprehension | undefined terms; precedence of confirmed against unconfirmed | Terms extended; F4.5 precedence |
| style | claims stronger than the evidence; "named fixtures" vague | G13, G14 and Problem wording calibrated; F7 names the tests |

**Not re-reviewed.** The round 2 findings were fixed in the text above; no third round was run, so no reviewer has read the final text. The synthesis of round 2 had 1 Blocker and 12 Majors; all 13 were addressed as listed, and none is known to be open. A reader should treat the final text as unreviewed by EGM until a later round or the implementation task's own review reads it.
