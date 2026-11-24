# Herd Guardrails: guard hook, tier-up review, stop record

* **Author:** Toni
* **Status:** Draft
* **Date:** 2026-11-23

--------------------------------------------------------------------------------

## Overview

Three changes that let a Herd task run with less supervision without lowering the bar for "done":

1. **Guard hook (Part A).** A PreToolUse hook denies a short list of dangerous actions while a task is active: edits to secrets and to Herd's own state files, and irreversible git and GitHub commands.
2. **Tier-up review (Part B).** At medium and high risk the review can no longer be skipped. It must come from a Herd reviewer subagent running one model tier above the builder (builder Haiku, reviewer Sonnet), and Herd records it from a hook, not from the agent's word.
3. **Stop record (Part C).** Whenever a task stops without `herd done` (gate released after 3 blocks, cancel, escalation), Herd writes `stopped.json` saying why, what is left, and whether it can be resumed and how.

All three keep the existing rules: standard library only, no new external service, the CLI decides from files and exit codes, a hook never breaks the session.

**Terms.** Builder: the main-session agent running `/herd:run`. Reviewer: the subagent that reviews the finished change. Tier: a position in the ordered list `[review] tiers` in `herd.toml`. Active task: what `active_slug()` returns and is not cancelled. Gate: `herd gate`, the Stop hook. Release: the gate returning `None` after `MAX_BLOCKS` blocks.

## Problem

* Nothing stops an agent from running `git push --force`, `gh pr merge`, `git reset --hard`, or editing `.env` during a task. The run skill says "ask only on irreversible actions", but that is an instruction, not a rule. It also does not stop the agent from editing `evidence.json`, `frozen.json` or `green.json`, the files the gate trusts.
* `herd review --skipped "<why>"` lets any medium or high risk task finish unreviewed. The report says "unreviewed", but the gate passes. `herd review --by` is free text: the CLI cannot tell a real fresh-context review from the builder reviewing itself, or which model reviewed.
* A reviewer on the same model as the builder shares its blind spots (PRD section 6, "Arbiter rubber-stamps the Elephant"). The PRD wants a different model where the harness allows it; staying on one provider, the nearest thing is a stronger model of the same family.
* When the gate releases after 3 blocks, the task is left half done with no record of why. A human or a reporting agent has to read `notes.jsonl` and `evidence.json` and guess. A new session does not know where to start.

## Goals

* G1: While a task is active, an Edit, Write, MultiEdit or NotebookEdit on a path matching `[guard] protected_paths` is denied with a reason. Check: `test_guard_denies_protected_edit`.
* G2: While a task is active, a Bash command containing a denied command (see Design A3) in any segment of a chain is denied with a reason. `python3 .../herd.py pr` is not denied. Check: `test_guard_denies_push_in_a_chain`, `test_guard_allows_herd_pr`.
* G3: Herd's own state files (`evidence.json`, `notes.jsonl`, `start.json`, `red.json`, `frozen.json`, `green.json`, `fails.json`, `stopped.json`, `gate_blocks`, `done_blocks`, `cancelled`) are always protected, whatever `herd.toml` says. `task.toml` is not. Check: `test_guard_state_files_always_protected`.
* G4: Every denial is appended to `notes.jsonl` as kind `guard` and listed in the final report and the PR. Check: `test_guard_denial_is_reported`.
* G5: No active task, or Python older than 3.11: the guard allows everything and prints nothing. An exception inside the guard allows the action and prints one line to stderr. Check: `test_guard_inactive_allows`, `test_guard_crash_allows`.
* G6: `herd review --skipped` is removed. At medium and high risk, `herd done` and the gate refuse until a review recorded by the review hook counts. Check: `test_done_refuses_without_hook_review`.
* G7: A review counts only if the reviewer's observed model tier is at least the builder's highest observed tier plus `[review] step` (default 1, one tier above: in 0.7.0 and again since 0.10.0; 0, the same tier, in 0.8.0 and 0.9.0), capped at the top tier. A reviewer at the top tier when the builder is already there counts, and the report says "same tier". Check: `test_review_tier_rule`.
* G8: Models are read from the session transcripts, never from what the agent writes. If the reviewer's or the builder's model cannot be read, the review does not count and the reason says which. Check: `test_unreadable_model_does_not_count`.
* G9: The reviewer ends with one line `HERD-REVIEW: PASS` or `HERD-REVIEW: FAIL`. A missing or malformed line, or `FAIL`, does not count. After 3 counted rounds without `PASS` the criterion for escalation is met (Part C). Check: `test_review_verdict_parsed`, `test_three_failed_reviews_escalate`.
* G10: Every stop without `herd done` writes `stopped.json` with the fields in Design C1. `herd status` prints it first. Check: `test_stop_record_on_release`, `test_stop_record_on_cancel`, `test_stop_record_on_escalation`.
* G11: `resumable` and `next` in `stopped.json` are computed by code from `problems()`, never written by the agent. Check: `test_resumable_is_computed`.
* G12: A later passing `herd done` keeps `stopped.json` and adds `resolved_at`. Check: `test_stop_record_resolved`.

## Non-Goals

* A sandbox. The guard matches command text; it does not stop `bash -c "$X"`, a script that pushes, or an alias. Claude Code's own sandbox and permissions are the layer for that. The guard catches the honest mistakes and makes them visible.
* A second model provider, or any reviewer outside Claude Code subagents.
* Guarding when no task is active (Open Question 1).
* Token or cost caps (a later design; wall-clock is already recorded).
* Changing the quick route: it still needs no review.
* A human waiver for an unreviewed change (Open Question 3).

## Open Questions

1. Should the guard run always, not only during a task? Always-on protects more but makes Herd intrude on sessions that never asked for it.
2. Should `git push` of the task's own `herd/<slug>` branch be allowed, since `herd pr` pushes it anyway? Default in this design: denied, use `herd pr`.
3. How does a human ship a change no reviewer can review? Options: `herd cancel`, or a waiver that only a human can make (no reliable way to tell a human from the agent inside the session today).
4. Should `step` be 2 at high risk (builder Haiku, reviewer Opus)?

## Critical User Journeys (CUJs)

### CUJ 1: Agent tries to force-push

* **Given**: Task `export-json` is active.
* **When**: The builder runs `git add -A && git push --force origin herd/export-json`.
* **Then**: The tool call is denied with: "Herd guard: `git push` is not allowed during a task. Use `herd pr` to publish, or ask the human one question and stop." A `guard` note is logged. Test: `test_guard_denies_push_in_a_chain`.

### CUJ 2: Agent tries to edit the evidence

* **Given**: Task active.
* **When**: The builder edits `.herd/tasks/export-json/evidence.json`.
* **Then**: Denied: "Herd guard: Herd's state files are written only by the herd CLI. Run `herd verify`." Test: `test_guard_state_files_always_protected`.

### CUJ 3: Haiku builder, Sonnet reviewer

* **Given**: The builder runs on Haiku, risk is medium, all checks pass.
* **When**: The builder spawns `herd-reviewer` with model `sonnet`. The reviewer ends with `HERD-REVIEW: PASS`.
* **Then**: The SubagentStop hook records the review with `by = "claude-sonnet-..."` (as read from the transcript), `tier = sonnet`, `builder_tier = haiku`, `source = "hook"`. The review counts. Test: `test_review_tier_rule`.

### CUJ 4: Reviewer on the same model as a Haiku builder

* **Given**: As CUJ 3, but the builder spawns the reviewer without a model, so it inherits Haiku.
* **When**: The hook records the review.
* **Then**: It is recorded and does not count: "review by haiku does not count: the builder ran on haiku, the reviewer must be sonnet or higher. Spawn herd-reviewer with model sonnet." Test: `test_review_tier_rule`.

### CUJ 5: No reviewer can run

* **Given**: Subagents are not allowed in this session.
* **When**: The builder tries to stop three times.
* **Then**: The gate releases and writes `stopped.json` with `reason = "released"`, `problems` including "review missing", `resumable = true`, `next = "spawn herd-reviewer with model sonnet, then herd verify"`. `herd status` in the next session prints that first. Test: `test_stop_record_on_release`.

## Design

### Spike S3 (do first, before any code)

Confirm in the current Claude Code docs and with a real session, and record in `docs/spikes/s3-hook-inputs.md`:

1. The SubagentStop hook input fields. Expected, to be verified: `session_id`, `transcript_path` (main session), `agent_id`, `agent_type`, `agent_transcript_path`, `stop_hook_active`. If `agent_transcript_path` or `agent_type` is missing, find the subagent transcript by `agent_id` under the session's folder, or adapt B3.
2. That assistant lines in both transcripts carry `message.model` (for example `claude-haiku-...`, `claude-sonnet-...`) and a timestamp.
3. That a plugin can ship `agents/herd-reviewer.md`, and that the Agent tool's `model` argument overrides the agent's frontmatter `model`.
4. The PreToolUse output format for a denial: `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}`, and the input fields `tool_name`, `tool_input.command`, `tool_input.file_path`, `tool_input.notebook_path`, `cwd`.

Do not guess any of these (CLAUDE.md, Writing). If a field does not exist, change this design before writing code.

**Result** ([`s3-hook-inputs.md`](../spikes/s3-hook-inputs.md), Claude Code 2.1.330): all four hold, with three changes made to B3 below. A plugin agent's `agent_type` is plugin-scoped (`herd:herd-reviewer`). `last_assistant_message` was absent: the subagent ended with a `SubagentHandback` tool call that held its report. The task's start time is in the `started` file, not in `start.json`.

### Part A: guard hook

**A1. Wiring.** `hooks/hooks.json` gets a PreToolUse entry, matcher `Bash|Edit|Write|MultiEdit|NotebookEdit`, command `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/herd.py" guard`, timeout 10. `herd.py` adds `guard` to the old-Python early exit next to `gate` and `lint`.

**A2. Function.** `guard(root, hook) -> dict | None` in `herd.py`, next to `lint()`. `None` allows. A dict is the PreToolUse deny output. `main()` reads stdin like `lint`, wraps the call in `try/except Exception`, and on an exception prints one line to stderr and exits 0.

**A3. Rules.** Defaults, extended (never reduced) by `herd.toml`:

```toml
[guard]
# Extra paths to protect, as globs relative to the project root. Herd's state files are always protected.
protected_paths = [".env", ".env.*", "**/*.pem", "**/*.key", "**/id_rsa*", ".git/**"]
# Extra commands to deny, as token prefixes.
deny_commands = []
```

Built-in denied commands (token prefixes after splitting): `git push`, `git reset --hard`, `git clean -f` (and any `-f` combination such as `-fd`, `-xfd`), `git branch -D`, `git checkout -- .`, `git restore .`, `git commit --no-verify` (or `-n`), `gh pr merge`, `gh repo delete`, `rm -rf /`, `rm -rf ~`, `rm -rf .`.

Path protection for Bash is best effort: a command is denied if any token, after stripping redirection characters, matches a protected path glob and the command has a write signal (`>`, `>>`, `tee`, `mv`, `cp`, `rm`, `sed -i`, `truncate`). Reading a protected file is allowed.

**A4. Splitting.** Split the command on `&&`, `||`, `;`, `|` and newlines, then `shlex.split` each segment (on a `ValueError`, fall back to `str.split`). Strip leading `env VAR=x`, `sudo`, `command`, `time`. Match each segment's tokens against each rule's tokens as a prefix. Flags may appear in any order after the subcommand (`git push origin x --force` matches `git push`).

**A5. Output.** The reason names the rule and the way forward:
* `git push`: "use `herd pr` to publish".
* `gh pr merge`: "Herd never merges: a human merges after reading the evidence".
* A state file: "written only by the herd CLI: run `herd verify` or `herd note`".
* Anything else: "irreversible: ask the human one question and stop".

Then `add_note(root, slug, "guard", "<tool>: <rule>")`. Add `"guard"` to `NOTE_KINDS`. `final_report()` and `pr_body()` add one line, "Guard: N denied (git push x2, .env x1)", when there is at least one.

### Part B: tier-up review

**B1. Config.**

```toml
[review]
# Model tiers, lowest first. A model's tier is the first entry that its model id contains.
tiers = ["haiku", "sonnet", "opus"]
# How many tiers above the builder the reviewer must be, capped at the top tier.
# 1 (the default in 0.7.0 and since 0.10.0) is one tier above; 0.8.0 and 0.9.0 defaulted to 0, the builder's own tier.
step = 1
```

Unreadable or missing config means the defaults above. A model id that matches no tier is tier unknown (G8: does not count).

**B2. Reviewer agent.** New file `agents/herd-reviewer.md` in the plugin, frontmatter `model: inherit`, `tools: Read, Grep, Glob, Bash`. Its prompt is Herd's, not the builder's: review only the goal, criteria, `test_budget` and the diff it is given; list findings as `Blocker`, `Major` or `Nit` with a path and line; do not edit files; end with exactly one line `HERD-REVIEW: PASS` (no Blocker or Major) or `HERD-REVIEW: FAIL`.

**B3. Recording by hook.** `hooks/hooks.json` gets a SubagentStop entry, matcher `^herd:herd-reviewer$`, running `herd.py review-hook`. `review_hook(root, hook)`:

1. No active task, or `agent_type` is not `herd:herd-reviewer`: return, record nothing. A project's own `.claude/agents/herd-reviewer.md` does not count: its prompt is not Herd's (S3).
2. Read the reviewer transcript (`agent_transcript_path`): its model (the last assistant `message.model` other than `<synthetic>`) and its final text: the last of its assistant text blocks and `SubagentHandback` `input.message` values, else the hook input's `last_assistant_message` (S3).
3. Read the main transcript (`transcript_path`): the builder's highest tier among assistant lines at or after the time in the task's `started` file (S3: `start.json` has no time).
4. Parse the last line matching `^HERD-REVIEW: (PASS|FAIL)$`. As built: the report's last non-empty line must be that line (Markdown around it is ignored), and only the reviewer's last turn is read.
5. Call `add_review()` with `by = <reviewer model id>`, `text = <findings, clipped to 2,000 chars>`, and extra fields `source = "hook"`, `tier`, `builder_tier`, `verdict` (`PASS`, `FAIL` or `none`).

Never block, never print to stdout. On an exception: one stderr line, exit 0.

As built, after a fresh review: the hook counts only a main session log Herd saw itself (the pre-init hook at `herd init`, the guard on each tool call since 0.12.2, and the Stop gate record each session into `start.json`), and only a reviewer log at `<session>/subagents/agent-<id>.jsonl` next to it. The guard denies running Herd's hook commands by hand, writing the session logs, and editing the installed plugin. `[review]` is fixed at `herd init`.

**B4. Counting.** `review_state()` gains these rules, checked after the existing ones:
* The note has no `source == "hook"`: "recorded by hand, not by the review hook: spawn herd-reviewer".
* `tier` or `builder_tier` is unknown: "the reviewer's (or builder's) model could not be read: <which>".
* `verdict != "PASS"`: "the review found Blocker or Major issues, or gave no verdict: fix them and review again".
* Required tier = `min(index(builder_tier) + step, top)`. If `index(tier)` is below it: "review by <tier> does not count: the builder ran on <builder_tier>, the reviewer must be <required> or higher. Spawn herd-reviewer with model <required>".

**B5. CLI.** `herd review --skipped` exits with an error saying a review is required at medium and high risk. `herd review --by` stays for low risk and for notes, but it never counts at medium or high (rule 1 above). Old `skipped` notes in existing tasks are still read and reported as "unreviewed".

**B6. Skill.** `skills/run/SKILL.md` step 7 becomes: "Spawn the `herd-reviewer` subagent with a model one tier above yours (`herd status` prints it; on your own model in 0.8.0 and 0.9.0), giving it only the goal, criteria, `test_budget` and the diff. The hook records the review. Fix Blocker and Major findings and review again, at most 3 rounds. There is no skip: if no reviewer can run, say so and stop; Herd records why." `herd status` prints `Review: needs <tier> or higher (builder on <tier>)`.

**B7. Escalation.** (Changed in 0.12.3: the limit is `MAX_REVIEW_ROUNDS = 2` hook-recorded reviews of any kind since the last counting PASS, issue #45.) Three hook-recorded reviews with `FAIL` since green adds the task to the existing escalation list with cause `review`, so the gate says to ask the human one question.

### Part C: stop record

**C1. File.** `.herd/tasks/<slug>/stopped.json`, overwritten on each stop:

```json
{
  "at": "2026-11-23T21:40:00Z",
  "reason": "released | done_refused | cancelled | escalated",
  "detail": "the cancel reason, or the escalated criteria and causes",
  "problems": ["<problems(root, slug) at that moment>"],
  "evidence": {"verified_at": "...", "sha": "...", "stale": true},
  "review": {"needed": "sonnet", "latest": "haiku, does not count"},
  "elapsed_s": 1234,
  "gate_blocks": 3,
  "resumable": true,
  "next": "spawn herd-reviewer with model sonnet, then herd verify"
}
```

**C2. Writers.** `write_stop(root, slug, reason, detail="")`, called:
* in `gate()` on both release branches (`reason = "released"`, or `"done_refused"` when the evidence passes but `herd done` keeps refusing);
* in `cancel_task()` (`"cancelled"`);
* in `gate()` when it blocks with escalation causes (`"escalated"`), before returning the block.

**C3. Resumable.** Computed, in this order:
* `cancelled`: false, `next = "start a new task"`.
* Corrupt or missing state files: false, `next = "a human restores the state files, or cancels"`.
* `escalated`: false, `next = "the human answers: <the question>"`.
* Otherwise true, and `next` is the action of the first problem, taken from a small table keyed by problem type (stale evidence: `herd verify`; failing criterion: "fix <id>, then herd verify"; review: B4's message; attacks: the adversarial line).

Until Part B, `review.needed` is a boolean (the risk needs a review) and the escalated `next` is "the human answers one question about: <the causes>".

**C4. Readers.** `herd status` prints `Stopped <at>: <reason>. Next: <next>` before anything else, and `herd status --json` returns the record for reporting agents. `final_report()` and `pr_body()` add "Stopped before: <reason> at <at>" if a record exists. `herd done` that passes adds `resolved_at`.

## Order

1. Spike S3. Update this design with what it found.
2. Part C. It needs no hook inputs, and Parts A and B use it.
3. Part A.
4. Part B, last: it changes what counts as done, so existing tests in `test_harness_rules.py` that use `--skipped` are rewritten to record hook reviews from fixture transcripts.
5. For each part: tests in a new `tests/test_herd_guard.py` and `tests/test_herd_review.py` (Part C in `test_harness_rules.py`), README sections "How it works" steps 4 and 6 and "Architecture", skills, `CHANGELOG.md`, and a `version` bump in `.claude-plugin/plugin.json`. One version per part.

Use Herd on Herd: each part is a `/herd:run` task with criteria taken from the Goals above, each Goal's named test as its check.

## Alternatives Considered

* **Guard as Claude Code permission deny rules** (`permissions.deny` in settings). No code, but a plugin cannot reliably set them for the user, they do not know about Herd's state files, and denials are not logged in the evidence. Rejected; the guard can sit next to them.
* **Reviewer chosen by the agent with `herd review --by "<model>"`.** No hook needed, but it trusts the agent's word, the problem this design fixes.
* **Fixed reviewer model** (always Opus). Simpler, but costs more for Haiku builds and gives no higher tier when the builder is on Opus anyway. The tier rule covers both.
* **Stop record as notes in `notes.jsonl`.** Fewer files, but a reader has to replay the log to know the current state; one overwritten file answers "why did it stop" directly.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Hook input fields differ from what this design expects | Spike S3 first; G8 makes an unreadable model fail closed, not count |
| Transcript format changes in a Claude Code update | One reader function with fixture tests; it fails closed (review does not count) and the reason names the file |
| Guard blocks legitimate work (a project that commits generated `.pem` fixtures) | Only additions are configurable; the reason says what was blocked; denials are in the report, so false blocks are visible and can lead to a narrower default |
| Guard is bypassed through `bash -c`, scripts or aliases | Stated as a Non-Goal; Claude Code sandbox is the real boundary |
| Higher review cost (Sonnet reviews every Haiku build) | Review only at medium and high risk, as today; quick route unchanged; reviewer gets only goal, criteria and diff |
| Builder writes a misleading prompt to the reviewer | Reviewer's instructions come from Herd's agent file; the diff is read by the reviewer itself with `git diff`; Open Question for M1: have the hook check the reviewer ran `git diff` |
| No subagents allowed, so medium-risk tasks can never finish | Intended: CUJ 5 ends in a stop record that says so, and the human decides |

## Context and sources

* `scripts/herd.py`: `add_review()`, `review_state()`, `problems()`, `gate()`, `cancel_task()`, `lint()`.
* PRD section 6: shared-model bias risk. Section 8: constraints.
* Comparison with Code Copilot Team v2.1.0 (gosha70/code-copilot-team): its `protect-files.sh` and `protect-git.sh` hooks and its `termination.json` plus `triage-report.md` for aborted runs were the inspiration for Parts A and C. Its second-provider peer review was not adopted; Part B keeps one provider and uses model tiers instead.
