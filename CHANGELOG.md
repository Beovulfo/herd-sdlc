# Changelog

All notable changes to Herd. Versions follow `.claude-plugin/plugin.json`.

## 0.12.2

Reviews now count in headless `claude -p "/herd:run ..."` sessions (issue #40). Before, every review note had `builder_tier` null and `round` false, with the reason "the main session log is not one Herd saw", so the builder reran reviews and tasks took an hour.

- **Why:** the review hook counts a review only when the main session log is one Herd recorded. Only the pre-init hook (right before `herd init`) and the Stop gate recorded it. A real headless run showed the first failed: the agent ran `H="python3 .../herd.py"; $H init calc ...`, and the hook reads the command text, so it cannot see through the variable. `start.json` then had no `sessions` until the first Stop block, which comes after the review. A run that happened to write the literal `herd.py init` was fine, so the bug looked random.
- **Fixed:** the guard hook (PreToolUse, Bash and edit tools) now records the session log from Claude Code's own hook input on every call while a task is active, through the same `_see_session` the Stop gate uses. The first tool call after `herd init` records it, long before a review. A subagent's call (it has an `agent_id`) records nothing.
- **Kept:** the trust rule. Only a session recorded from Claude Code's own hook input counts. `herd guard` and `herd gate` run by hand are denied by the guard when written out as `herd.py guard`, and no path in a command or a note is ever read as a session.
- **Added:** `tests/headless_check.py`, a real headless run (about $0.10) that exits 0 only when a review note shows a builder tier and round true. It is a criterion check, not a unittest.
- **Known limits:** the session is recorded at the first Bash or edit tool call after `herd init`; a review spawned before any such call would not count. Through an alias (`$H guard`) the denial does not see the command, as before (aliases are a stated Non-Goal of the guard). A Claude Code version that omits `transcript_path` from PreToolUse input records nothing, and the review then does not count. The real run depends on the model, so one failure is rerun once before it is called a bug.

## 0.12.1

Cuts review rounds without lowering the bar. The 0.12.0 Haiku run cost $1.07, of which $0.39 was four Sonnet review rounds. Round 2 passed but did not count, because its brief, written by the builder, did not name two changed code files (`__init__.py`, `generator.py`) and the reviewer did not read them. That cost a whole extra round. After the passing round the builder kept polishing Nits and rebuilt its heuristic, which led to more rounds.

- **Added:** `herd review-brief` prints the brief the builder passes to `herd-reviewer` as it is, assembled by code: the goal, each criterion with its check command, `test_budget`, `known_limits`, the request word for word, the `inputs` entries, the changed files the reviewer must read, and the diff command. The file list is the same one the review hook counts against (`review_files()`, shared). The diff command is `git diff <the commit herd init recorded>`, which covers committed and uncommitted work. The gate's refusal for a missing review says to give the reviewer only that output.
- **Added:** once a review that counts is recorded for the current, fresh evidence with no failing check, `herd verify` and `herd status` print one line: `Review passed and counts: fix only Blocker and Major findings, start no new work, commit and run herd done`. The line also says exactly what the rule does with later edits. At medium risk the review keeps counting unless the risk rises to high, though no reviewer sees those edits. At high risk any changed file needs another review, while a commit alone does not.
- **Changed:** the run skill's review step says to pass what `herd review-brief` prints, and to commit and run `herd done` after a PASS that counts (838 words, down from 841; budget unchanged at 845). The `herd-reviewer` agent is told it gets Herd's brief and must read every listed file and run its diff command before judging.
- **Fixed:** a new file git does not track yet is in no `git diff`, so a review that printed the diff but did not Read such a file no longer counts. The reason names the files, and the brief lists them as `New files, in no git diff: read each one with Read`. Before this, a reviewer who ran `git diff` with uncommitted new files counted without seeing them.
- **Unchanged:** the gate already names the changed files a failed review did not read (`the reviewer did not read: a.py, b.py, ...`, up to 20), so a review that missed files is fixed in one round. No new model calls.
- **Known limits:** the hint only advises; nothing stops the builder working after a PASS. At medium risk, edits after it are not reviewed. The cost effect has not been measured in a new run yet.

## 0.12.0

Removes the intake reviewer added in 0.11.0 ([`herd-intake-review.md`](docs/designs/herd-intake-review.md), now marked removed). A live Haiku run on 0.11.0 showed it did not catch the flaw it was built for. The Sonnet intake reviewer passed an `inputs` entry whose `program` form took a pre-chosen walkable pick cell for each product. Its only catch, non-verbatim human criteria, the 0.10.0 verbatim block already refuses in code. It also added review rounds and cost.

- **Removed:**
  - the `herd-intake-reviewer` agent and its SubagentStop entry;
  - its path in `herd review-hook`, the `intake` note kind and `criteria_sha`;
  - the `problems()` rule that needed an intake PASS, its `next` steps, and the escalation after 3 failed intake rounds;
  - the `Intake review` lines in the report, the final report and the PR;
  - the `intake` key `herd init` wrote to `start.json`, and the run skill's intake sentence (run skill budget back from 875 to 845 words).
- **Kept:** the final `herd-reviewer` one tier above the builder, its evidence checks (what it read, its `path:line` references), and its brief with the request and the `inputs` list. Also kept: the `inputs` enforcement, the verbatim block, the required fields, and the 0.11.1 corrections rule.
- **Compatibility:** a task started on 0.11.x keeps its `intake` notes and its `intake` key in `start.json`; nothing reads them now, so it no longer needs an intake review to finish.

## 0.11.1

Fixes a deadlock a live Haiku run hit on 0.11.0. Its human criteria at the first verify were cut quotes, and C4 was its own sentence. The intake reviewer failed them twice, so the agent re-split the request into verbatim quotes under the same ids: new C2 and C3 were other sentences of the request, and C4 joined the old C2 and C3. The intake review then passed, but the frozen-criteria rule from 0.4.0 refused every change until the human's words were recorded with `herd note --human-change`. The agent rightly would not claim the human changed them, and the task stopped.

- **Fixed:** after the first verify, a change that only moves the human criteria toward the recorded request needs no note. That holds when every human criterion now quotes the request, and every frozen human text that quoted it, or that the human reworded with a note, is still inside one of them, so none of the human's words was narrowed or dropped. A frozen text that did not quote the request and was not the human's rewording was never the human's words. Criteria whose text changed in words are re-frozen with their checks. A text changed only in case, spacing or punctuation now counts as unchanged and keeps its frozen check. The report and the PR show `C2, C3, C4 corrected after the first verify to verbatim quotes of the request, keeping every earlier human quote: confirm the split`, noting that their checks may not have been seen failing. This replaces the narrower 0.10.0 rule, which accepted only a non-quote restored to a quote under the same id, and not its check.
- **Unchanged:** these still need the human's note:
  - a quote cut shorter or dropped;
  - a text that is still not a quote;
  - a human rewording replaced;
  - a check changed on a human criterion whose words did not change;
  - a human criterion removed or turned agent-proposed.

  A new id is still shown as "added after the first verify". With no recorded request, today's rules apply.
- **Known limit:** the rule compares quotes, not meaning. A re-split or an id swap that keeps every quote passes, even if it moves a quote to a criterion with a weaker check. The report and the PR list the corrected ids for the human to confirm, and the `corrected` mark stays for the rest of the task.

## 0.11.0

An intake review: a reviewer that reads the criteria as the human would, before any code ([`herd-intake-review.md`](docs/designs/herd-intake-review.md)). No reviewer ever compared the human's words with the program's input form. A Haiku build took a pre-chosen pick cell per product where the human said products are located in the map, and no review or attack noticed, because the final reviewer sees only the diff.

- **Added:** the `herd-intake-reviewer` plugin agent (`agents/herd-intake-reviewer.md`, `model: inherit`, tools Read, Grep, Glob). Its instructions are Herd's: read only the task's `request.md` and `task.toml`, and answer as the human would. Does every criterion cover every word of the request, with generated cases where a word says any or every? Does each `inputs` entry's `program` form equal its `human` form, or must the caller prepare something first? What does the request promise that nothing tests? It edits nothing, lists findings as Blocker, Major or Nit, and ends with `HERD-INTAKE: PASS` or `HERD-INTAKE: FAIL`.
- **Added:** a SubagentStop entry (matcher `^herd:herd-intake-reviewer$`) runs the same `herd review-hook`. It records an `intake` note from the session logs as it does for the final review: the reviewer's and the builder's models, the tier rule with `[review] step` (default 1), and the verdict. It also records whether the reviewer read both files (Read, or a Bash reader such as `cat`) and a hash of what it judged: the goal, the criteria (text, source, check, coverage), `test_budget`, `known_limits` and `inputs`. It never blocks and prints nothing. The guard already keeps the builder from running the hook, writing the session logs or Herd's notes, and editing the installed plugin.
- **Added:** at medium and high risk on the standard route, `herd done` and the Stop gate refuse until the latest intake review is a counted PASS. It must come from the review hook, at the required tier, from a reviewer that read both files, and for the current hash; a change to any judged field voids it, while timeouts and comments do not. A `task.toml` modified after the reviewer's last Read of it (by the file's time against the log's) voids it too. One recorded after all checks first passed still counts, and the report and the PR say it came after the code: refusing it could deadlock a task whose risk rose after green, and a one-character edit would get past it. Three failed intake rounds since the last PASS make the gate tell the agent to ask the human one question. The refusal names the model to spawn, and the stop record's `next` does too. Tasks started before 0.11.0 (no `intake` in `start.json`) are exempt.
- **Changed:** the final `herd-reviewer` gets the request and the `inputs` list too, and its instructions say to flag an input the code reads in another form than they describe. The gate's refusal says what to give it.
- **Changed:** the run skill's criteria step says to spawn `herd-intake-reviewer` before any code, with the two paths (run skill budget raised from 845 to 875 words). The report and the PR show an `Intake review:` line; the final report adds it to the Review line.
- **Known limits:** a model judges the criteria and can be wrong or agree too easily. It cannot see code that does not exist yet, so a program that reads a form other than its `inputs` entry says is left to the final reviewer and the attacks. An agent can write the same words in `human` and `program`, and the intake reviewer sees only what the agent wrote there. The agent writes the prompt that spawns the reviewer; the reviewer's instructions tell it to trust the files over the prompt. "Before all checks first passed" is not "before the code": an agent can write the code and keep one check red. The time check reads file and log times, so a file time set back is not seen.

## 0.10.0

Quality checks moved from skill text and warnings into code ([`herd-quality-checks.md`](docs/designs/herd-quality-checks.md)), the reviewer back one tier above the builder, and `inputs` enforced after a 0.9.0 Haiku run ignored it. Each check refuses only what code can tell for certain; what it can get wrong is recorded and shown instead. None reads the agent's wording with a word list.

- **Changed:** `herd done` and the Stop gate refuse a `human` criterion that is not a verbatim quote of the request `herd init --request` recorded (0.2.1 to 0.9.0 only warned). The comparison ignores what copying changes: Unicode forms, case, spacing and line wraps, quote marks, code ticks, emphasis at a word's edge, escapes, link targets, the request's list, heading and quote markers, dashes and sentence punctuation. Words, numbers, identifiers and operators (`<`, `>=`, `!=`, `2*3`, `max_len`) still count, as whole words and numbers (`return 1` is not in `return 10`, `return 1.5` or `1,000`). A `herd note --human-change "C1: ..."` that quotes the new text is a source for C1 too, the same note the frozen-criteria rule accepts, which now uses the same comparison. A frozen criterion that was not a quote may be restored to the request's words without a note. With no recorded request (`--request` not given, or a task from before 0.2.1) it stays a warning.
- **Added:** on the standard route at medium and high risk, `herd done` and the Stop gate refuse while `test_budget` or `known_limits` is missing or empty, or a human criterion's `coverage` is. Each refusal is one line that says what to write, and the stop record's `next` names the field. Only absence is refused: the content is the agent's. The quick route and low risk are exempt.
- **Changed:** `inputs` is refused, not only warned about, at medium and high risk on the standard route: missing, not a list, an entry without `human` or `program`, or an `inputs` key inside a `[[criteria]]` table. A 0.9.0 Haiku run ignored the warning and wrote `inputs = "..."` in each criterion. The check is structural; each message shows the table to write, and the misplaced one says inputs belong at the top level as `[[inputs]]` tables, not inside `[[criteria]]`. The `task.toml` that `herd init` writes has a commented `[[inputs]]` table, and the criteria skill's example has one (criteria skill budget raised from 470 to 490 words). At low risk these stay warnings. The report and PR line for `inputs` is unchanged.
- **Added:** the review hook reads the reviewer's own tool calls from its log. A review counts only if the reviewer ran `git diff`, `git show` or `git log -p` without a flag that prints no changed lines (`--stat`, `--name-only`, `--check`, `--output` and the like) or a redirect, or read every changed code file (Read, or a Bash reader such as `cat` or `sed`); when no code file changed, every changed file counts. Otherwise `review_state` says `the reviewer did not read: <files>`, and the review is not a round for the escalation count. When the changed files cannot be told (no commit at `herd init`), it does not block. The report, the final report and the PR say how much it read (`ran git diff or git show, read 2 of 3 changed code files`). A hook review recorded before 0.10.0 does not count: review again.
- **Added:** every `path:line` (or `path:first-last`) the review cites is checked: the file must be in the repository (the project folder, the repository top, or a file whose path ends with it) and the line within it. Bad references are listed under Not proven in the report, the final report and the PR, never refused, since a cited line can be the old side of the diff.
- **Changed:** the reviewer runs one tier above the builder by default again: `[review] step` defaults to 1 (Haiku builds, Sonnet reviews; Sonnet builds, Opus reviews; Opus reviews Opus), as in 0.7.0. In a 0.9.0 Haiku run a same-model Haiku reviewer gave three FAIL rounds on narrow robustness bugs and the run escalated. `step = 0` keeps the 0.8.0 behaviour. `herd status`, the gate, the stop record, the run skill and the `herd-reviewer` description say one tier above.
- **Changed:** the `herd-reviewer` agent is told that its tool calls and its references are checked. The criteria skill says `herd done` refuses an unquoted human criterion and empty `test_budget`, `known_limits` and `inputs`. The README's `herd check` row no longer describes the 0.8.0 word list for inputs the caller prepares, which 0.9.0 removed.
- **Known limits:** a verbatim part of a sentence still passes (quoting "for any" out of "for any call"), so a quote can narrow by truncation. The quote check trusts `human-change` notes, which the agent writes: one note gets past it, and the note is shown to the human as a change to confirm. Reading a file counts whether the reviewer read all of it or ten lines. A `git diff` inside `bash -c`, a script or an alias is not seen; one that prints nothing for another reason (`--cached` after a commit, a pathspec that matches nothing, `-0`) still counts. A cited line that existed before the change is reported as bad. A request hard-wrapped right before `>`, `-` or `10.` reads that mark as Markdown, so a quote across that wrap is refused.

## 0.9.0

Moves the question that exposes a Haiku design flaw from after the build to the criteria step. The flaw was a map format that took a pick cell per product, so the caller chose the side of the shelf and the program refused products whose chosen side was walled in. 0.8.0 checks the refusals after building; this version moves the question to the criteria step.

- **Added:** `inputs` in `task.toml`: each input as the human described it (`human`) and as the program receives it (`program`); `inputs = []` for none. `herd verify` warns when it is missing on the standard route or an entry lacks a field. The evidence report and the PR show both forms for the human to compare. No word matching: nothing reads the wording, so it only helps when the agent states the forms honestly and the human reads them.
- **Added:** the first `herd verify` warns when no refusal attack is logged yet, and a later `herd verify` warns when the refusal attack was first logged after the first verify (by note order), so it did not shape the design.
- **Changed:** the criteria skill asks for `inputs` (+18 words, budget 470) and the adversarial reference says to log the refusal attack before building.
- **Removed:** the 0.8.0 warning for a refusal attack marked n/a while the changed code raises a refusal, and no word list was added for inputs: both read wording, which can be dodged and flags harmless text.
- **Known limit:** an agent can describe the program's form as "the map" and still take pick cells. Nothing here sees the code's real input format.

## 0.8.0

Lessons from a Haiku run built and reviewed by Opus with 0.7.0: it passed `herd done` with an Opus review (one tier above) and still failed the same three stores as 0.4.0. Its map format took a free pick cell per product, so the caller chose the side of the shelf, and the planner refused products whose chosen side was walled in although another side was open. The reviewer saw only the goal, the criteria and the diff, and no criterion mentioned shelves.

- **Added:** the `refusal` standard attack, the fifth. Every kind of input the program refuses (cannot be reached, not found, invalid) must be confirmed refusable by separate, simpler code (such as a plain search) on generated inputs, so nothing the program could serve is refused. Like the others, `herd done` and the Stop gate need a command that `herd verify` ran and saw pass, or an `n/a:` reason.
- **Changed:** the reviewer runs on the builder's model by default: `[review] step` is 0, not 1 (set `step = 1` in `herd.toml` for one tier above, as in 0.7.0). The run showed a stronger reviewer did not help here, and the same model costs less and needs no model the session may not have. The tier rule, the hook record, the rounds and the escalation are unchanged; `herd status`, the gate and the run skill name the builder's model.
- **Known limit:** the refusal attack makes the agent check its refusals, but it cannot make it test products on their shelves: an agent whose generator hands the program pre-computed pick cells still passes. Catching a pre-computed input form earlier, at the criteria step, is not built.

## 0.7.0

Part B of [`herd-guardrails.md`](docs/designs/herd-guardrails.md): the tier-up review.

- **Added:** the `herd-reviewer` plugin agent (`agents/herd-reviewer.md`, `model: inherit`, tools Read, Grep, Glob, Bash). Its instructions are Herd's: review only the goal, criteria, `test_budget` and the diff it reads itself, list findings as Blocker, Major or Nit with a path and line, edit nothing, and end with `HERD-REVIEW: PASS` or `HERD-REVIEW: FAIL`.
- **Added:** a SubagentStop hook (`herd review-hook`, matcher `^herd:herd-reviewer$`) records the review. It reads the reviewer's model and report from its session log (the report can be a `SubagentHandback` call, see spike S3) and the builder's highest model since `herd init` from the main session log. Never from what an agent writes. It never blocks and prints nothing. It counts only a reviewer log in the place Claude Code keeps it (`<session>/subagents/agent-<id>.jsonl` next to the main log), and the verdict is the last non-empty line of the reviewer's last turn.
- **Added:** the review hook counts only a main session log that Herd saw itself: `herd init`'s pre-init hook and the Stop gate record each session from Claude Code's own hook input. The guard denies running Herd's hook commands (`gate`, `preinit`, `guard`, `review-hook`) by hand, in any form (`herd.py`, `python3 -m herd`, `-mscripts.herd`), writing into Claude Code's session logs (`*.jsonl`, `subagents/`; memory files stay writable), and editing the installed plugin (`CLAUDE_PLUGIN_ROOT`, unless it is the project), so a builder cannot record its own review with plain tool calls.
- **Changed:** at medium and high risk a review counts only when the hook recorded it, its verdict is PASS, and the reviewer's tier is at least the builder's plus `[review] step` (default 1), capped at the top of `[review] tiers` (default haiku, sonnet, opus), as `herd.toml` had them at `herd init`: editing it during the task does not change the rule. Opus reviewing an Opus build counts, and the report says "same tier". A model that cannot be read, or matches no tier, does not count, and the reason says whether it was the reviewer's or the builder's. The earlier rules still apply: after all checks first passed, at the current risk or higher, and at high risk for the final content.
- **Removed:** `herd review --skipped`. It exits with an error: a review is required at medium and high risk. `herd review --by` stays as a note and never counts at medium or high risk. Old skipped notes are still read and reported as unreviewed.
- **Added:** 3 review rounds since all checks first passed without a PASS (rounds whose tiers would count) make the gate tell the agent to ask the human one question, and write an escalated stop record.
- **Added:** `herd status` prints `Review: needs <tier> or higher (builder on <tier>)`, from the latest session log the gate or the pre-init hook saw; the gate's reason and the stop record's `next` name the model to spawn (`spawn herd-reviewer with model sonnet, then run herd verify`), and the stop record's `review.needed` is that tier.
- **Added:** the report and the PR show the review's first line and how many rounds without PASS came before it; the PR lists those rounds under what is not proven.
- **Changed:** the run skill's review step: spawn `herd-reviewer` one tier above you; there is no skip.
- **Known limits:** the builder's tier comes from the main session log only, so work it delegated to its own subagents does not raise it, and a task resumed in a new session sees only that session. A new model family needs adding to `[review] tiers`. The hook does not check that the reviewer actually read the diff. A builder that runs a copy of `herd.py` as its own script, with logs it wrote, can still record a review: like `bash -c`, that is past what the guard reads.

## 0.6.0

Part A of [`herd-guardrails.md`](docs/designs/herd-guardrails.md): the guard hook.

- **Added:** a PreToolUse hook (`herd guard`) on Bash, Edit, Write, MultiEdit and NotebookEdit. While a task is active it denies, with a reason:
  - edits to secrets: `.env` and `.env.*` in any folder (templates such as `.env.example` stay editable), `**/*.pem`, `**/*.key`, `**/id_rsa*`, `.git` and `.git/**`, plus the globs in `[guard] protected_paths`;
  - edits to Herd's own state files (`evidence.json`, `notes.jsonl`, `start.json`, `red.json`, `frozen.json`, `green.json`, `fails.json`, `stopped.json`, `gate_blocks`, `done_blocks`, `cancelled`, `started`, `request.md`, `base`, `pr`, `.herd/active` and the folders that hold them), whatever `herd.toml` says; `task.toml` stays the agent's;
  - irreversible commands in any segment of a chain: `git push`, `git reset --hard`, `git clean -f` (any `-f` cluster), `git branch -D` (or `-d -f`), `git checkout -- .`, `git checkout .`, `git checkout -f`, `git restore .` (but not `--staged`), `git stash drop` and `clear`, `git switch -f` and `--discard-changes`, `git commit --no-verify` (or `-n`), `gh pr merge`, `gh repo delete`, and `rm -rf` of `/`, `~` or the current folder or one above it (`.`, `..`, `*`, `.*`, an absolute path), plus `[guard] deny_commands`. Flags can come in any order, in clusters, or as unique prefixes of long options (`--forc`); git's and gh's global options (`-C`, `-R`) are skipped; shell keywords (`if`, `then`, `do`, `!`, `{`), `VAR=x` and wrappers (`env`, `sudo`, `command`, `time`, `nohup`, `exec`, `nice`, `timeout`, `xargs`, with their options) are seen through, and so is command substitution, also inside double quotes. Quoted text, heredoc bodies and `#` comments (up to the end of their line) are not commands, so a commit message that mentions `git push` passes. `herd pr` is not denied: it is how a task publishes.
  - Bash writes to a protected path: redirection targets and the arguments of `tee`, `mv`, `rm`, `touch`, `truncate`, `chmod`, `chown`, `sed -i` and `git rm`, the last argument of `cp`, `ln`, `install` and `rsync`, and `dd of=`. A `cd` or `pushd` earlier in the chain moves relative paths. Reading a protected file is allowed. Paths are resolved through symlinks and matched without case, since a case-insensitive disk writes `.ENV` to `.env`.
  - The task is found from the hook's folder, `CLAUDE_PROJECT_DIR`, the edited file and any `cd` target, so a `cd` out of the project or into a nested git repository does not switch the guard off. The search stops at a git worktree's root: a worktree has its own tasks. `--help`, `--dry-run` and `git clean -n` are allowed.
- **Added:** each denial is a `guard` note; the final report's Caveats and the PR description show `Guard: N denied (git push x2, .env x1)`.
- **Known limits:** the guard reads command text, so `bash -c`, scripts, aliases, `eval` and variables pass; Claude Code's sandbox and permissions are the boundary for those. It does nothing while no task is active, on a Python older than 3.11, or when it fails (one stderr line, the action is allowed); a denial whose note cannot be written still stands. It costs about 50 ms per tool call without an active task (it leaves before its imports) and about 90 ms with one. A fresh-context break-it pass found 10 ways past the first version (shell blocks, wrapper options, gh's `-R`, option prefixes, symlinks, case, a `cd` out of the project, a nested repository) and one false block (heredoc bodies); a fresh review found four more (a failed note write allowed the action, `.env` only at the root, `.env.example` blocked, `timeout` and quoted `$(...)`), a second review two (a `cd` earlier in the chain, a worktree reached by the main checkout's task), a third one Blocker (a `#` comment hid every later line), and two checks of that fix four more (an escape before `#`, an apostrophe in a heredoc body, quotes nested in `"$(...)"`, `<<` in arithmetic); each has a regression test. Comments and heredoc bodies are now removed in one pass that tracks quotes, `$(...)` and parentheses, and a heredoc that never closes keeps its body, so it is checked. Reading shell syntax stays best effort.

## 0.5.0

Part C of [`herd-guardrails.md`](docs/designs/herd-guardrails.md), after spike [S3](docs/spikes/s3-hook-inputs.md) confirmed the hook inputs Parts A and B rely on.

- **Added:** a stop record. Whenever a task stops without `herd done`, Herd writes `.herd/tasks/<slug>/stopped.json`: the reason (`released` when the Stop gate lets the agent go after 3 blocks, `done_refused` when the evidence passes but `herd done` kept refusing, `cancelled`, or `escalated` when the gate tells the agent to ask the human because a criterion failed 3 times in a row), the detail, the problems left, the evidence time, commit and staleness, the review state, the elapsed time, the gate's block count, and whether the task can be resumed with the next step. Herd computes `resumable` and `next` from the gate's own problems and state files, never from the agent: a cancelled or escalated task, or one whose state files are lost, is not resumable by the agent. The record is overwritten on each stop. Before, a released task left no record of why, and a new session had to read the notes and guess.
- **Added:** `herd status` prints `Stopped <at>: <reason>. Next: <next>` first (or says the task went on, when newer evidence exists), and `herd status --json` prints the record (or `null`) for a reporting agent. The final report and the PR description name the earlier stop. A later passing `herd done` keeps the record and adds `resolved_at`.
- **Changed:** the Stop gate no longer crashes on a corrupt or wrong-shaped `evidence.json` or `notes.jsonl`: it blocks and names the file, and after 3 blocks it lets the agent stop with a record that says a human must restore the file or cancel. Before, the hook failed with a traceback and let the agent stop with no record.
- **Added:** spike S3 (`docs/spikes/s3-hook-inputs.md`): the SubagentStop and PreToolUse inputs, tested live on Claude Code 2.1.330. A plugin agent's `agent_type` is plugin-scoped (`herd:herd-reviewer`), and the subagent's final text can arrive in a `SubagentHandback` tool call instead of `last_assistant_message`; the design is updated.

## 0.4.1

Lessons from 12 Haiku runs of the supermarket benchmark (Herd 0.3.1 and 0.4.0), kept to changes that add little or no work per run, plus a hook that closes a red-first gap found while building them. Every store they lost came from one bug class: a product reported as unreachable although another side of its shelf was open. Four of six 0.4.0 runs chose a map format that takes the pick cell instead of the shelf, and limits such as "rejected if walls cut it off" or "first neighbour only" contradicted the any-layout claim without reaching the human.

- **Added:** a known limit that narrows a human any/every/all claim (only, first, rejected, skipped, assumed and the like) is listed under Not proven in the report, the final report and the PR, one line per limit naming every such claim, at most five; `herd verify` warns about it. It does not block: the human decides. The check is a word list, so it can miss a limit worded otherwise and flag a harmless one. Replayed on the six 0.3.1 Haiku task files, it flags run 2's "picked from its first open neighbour only" and run 4's "stores with unreachable products are rejected".
- **Changed:** the `recount` attack also runs on the generated and collision inputs. A Haiku run recounted its own examples and missed a time that was short by one pick when two products shared a cell.
- **Added:** `herd verify` warns when the `coverage` of a human any/every criterion names no random, seeded or fuzzed inputs. Five of six 0.3.1 Haiku runs tested the any-layout claim only on layout shapes they designed themselves, which shared the code's blind spot.
- **Added:** a PreToolUse hook on Bash (`herd preinit`). When the agent runs `herd init <slug>`, it reads the session log, and its subagents' logs, and records the files they already edited with Edit, Write, MultiEdit or NotebookEdit; `herd init` then counts them as the agent's code even if they are uncommitted, so red first flags code written before the task started. Before, `herd init` treated every uncommitted file as the human's, so an agent that wrote code first and then ran `herd init` passed red first silently. The record stays inside `.git`, one per task, so a refused or merely mentioned init never reaches another task; `herd init` consumes it and ignores it after 10 minutes. A leading `cd <dir> &&` is followed. Any other command returns at once. Known limits: files changed through Bash (`sed`, `cat >`) are not seen; a file the human edits after the agent did counts as the agent's; agents without Claude Code hooks, and a `python3` older than 3.11, keep the old behaviour.
- **Changed:** the adversarial pass asks for purely random inputs besides the shapes the agent designs, and the criteria skill says to take each input as the human described it (a product on its shelf), not in a pre-computed form.

## 0.4.0

Seven rules of the run skill move from text into the CLI, so an agent that skips the text still meets them. Three fresh-context reviews of this release found holes; each is fixed and covered by a test.

- **Added:** red first is checked. `herd init` records the starting commit, the files already uncommitted (yours, not the agent's, until the agent changes them) and the stash list. The first `herd verify` records which code files the agent changed before it, including code moved aside for that run (by file time) or stashed on the task branch. Tests, docs, config, dotfiles, build output (`__pycache__`, `node_modules`, tool caches) and files without an extension (unless they start with `#!`) are not code. If code came first, the report and the PR say "red first not proven", and `herd done` and the Stop gate refuse until the agent explains it with `herd note --late-red "<why>"`. Benchmark runs often wrote the code first and moved it aside for the first verify. Known limit: code copied out of the tree and back is not detected.
- **Added:** risk and review are recorded. `herd init` stores the risk floor of the goal and the request; `herd verify` raises it when the changed files match a `[floor]` rule, and a broken `herd.toml` makes it high. `herd review --by "<reviewer>" "<what they found>"` or `herd review --skipped "<why>"` records the fresh-context review, and `herd done` refuses medium and high risk on the standard route without one. A review counts only when recorded after all checks first passed and at the current risk or higher; at high risk it counts only for the content it saw (a commit alone keeps it, a changed file voids it). A skipped review counts at any risk, so an agent without a reviewer can finish, but the report and the PR call the change unreviewed.
- **Added:** human criteria are frozen at the first verify, text and check, even when no check can run yet. `herd done` refuses when one is changed or removed afterwards, unless the human's own change is recorded with `herd note --human-change "C1: <the human's words>"`: a rewording note must quote the new text, a drop note must say it was dropped or removed, and each note counts once. A changed check on an agent's criterion, or a criterion added later, is shown as never seen failing.
- **Changed:** `herd done` prints the seven-line final report itself, filled from the evidence and the notes. Decisions are logged as they happen with `herd note --decision "<decision>; <reason>; <how to override>"`.
- **Added:** `herd verify` runs the `herd check` warnings every time, stores them in the evidence, prints one summary line, and lists them in the report and the PR.
- **Added:** `herd verify` counts consecutive failures per criterion (the intended red run excluded) and says to ask the human after 3 in a row; the Stop gate's reason says so too.
- **Added:** `herd done` refuses uncommitted work when pull requests are on (`[pr] open = true`, or a PR opened by `herd pr`) and warns otherwise.
- **Changed:** the Stop gate blocks a passing task up to 3 times until `herd done` runs, so the commit check and the final report are not skipped, and an agent that may not commit is never trapped. Passing again after a failure starts the count again.
- **Added:** Herd's own state files never stop `herd verify`. A corrupt `start.json`, `red.json` or `frozen.json`, or a `frozen.json` deleted after the first verify, blocks `herd done` with the file named, instead of switching the rules off. A task with no `start.json` (started before 0.4.0, or the file deleted) keeps working: its risk is triaged again from the goal and the request, its criteria are frozen from then on, and red first needs a `--late-red` reason.
- **Changed:** the run and criteria skills say less where the CLI now enforces the rule.

## 0.3.2

- **Changed:** each standard attack names a command. `herd note --tried --attack <name>` needs `--check "<command>"`, usually a regression test, or text starting `n/a:` when the attack cannot apply. `herd verify` runs these commands like criterion checks and stores their exit code and output. `herd done` and the Stop gate count an attack only when its command passed at the last verify (one that ran zero tests or was logged after the last verify does not count), or when it is marked `n/a:`. Commands rerun at every verify, so one failing command blocks its attack however many others pass. An attack note with no command counts only as a stated `n/a:`, so notes from 0.3.1 or a hand-edited log do not pass the gate. `herd verify` prints attacks that need attention (all of them with `--verbose`) and exits 1 when one fails. The latest note for an attack decides, so a mistyped or renamed command can be replaced; earlier commands that now fail stay listed in the PR. A command that runs no project code (`true`, `echo`, `test -f`) warns and does not count. `--timeout S` sets an attack command's time limit; each distinct command runs once per verify. Before, a note was only text: a benchmark run logged three attacks as tried before running them, and the gate accepted them.
- **Changed:** the report and the PR description show each attack's state and command (`bad-input passing (`...`)`, `collision n/a`, failing, ran zero tests, or missing); the PR lists attacks without a passing command under what is not proven.

## 0.3.1

Quality first. A benchmark rerun with 0.3.0 was 3% cheaper than 0.2.4 but scored 45 of 48 on the hidden verifier and 0 of 6 on the robustness probe (0.2.4: 48 and 6). Its agent never opened `adversarial.md`, which 0.3.0 had made an optional reference file. A rerun with a first draft of this version, whose agent did read the file, scored 48 of 48 and 6 of 6.

- **Added:** on the standard route, `herd done` and the Stop gate refuse until each of four standard attacks has a recorded attempt, `herd note --tried --attack <name> "..."`: `bad-input` (bad input at every entry point ends in one clear message and a non-zero exit, never a traceback), `collision` (two inputs on the same key or position each still count), `one-bad-part` (a broken entry the request does not ask for does not reject the whole input, while a broken or unreachable requested one still fails with a clear message) and `recount` (every reported number recomputed from the output with separate code). The refusal lists the missing attacks, so an agent that skipped the skill file still learns them. An attack that cannot apply is logged with the reason.
- **Changed:** each adversarial rule is written once. Step 6 of the run skill points to `adversarial.md` and the `herd done` gate instead of repeating the attacks; the note-timing rule is in the run skill's Rules, for every step; empty and malformed input belong to `bad-input` only. An existing test counts for an attack only if it meets that attack's rule, logged with its name and what it covers.
- **Changed:** the report and the PR description say which standard attacks are logged (`Adversarial pass: 5 attempts recorded; standard attacks all logged`, or the missing ones).
- **Docs:** `CLAUDE.md`, the PRD status line, the evidence skill and the README describe the enforced attacks and the mandatory reference reads.
- **Changed:** the run skill makes reading a reference file mandatory when its step applies, and step 6 names the four attacks inline. Its word budget goes from 800 to 900.
- **Added:** a plain `herd init` creates branch `herd/<slug>` from the current branch and switches to it, recording the base for `herd pr`. Uncommitted changes come along. It warns instead of failing on a detached HEAD, a repository with no commit, or an existing branch; outside git it does nothing. Before, the branch was only a sentence in the run skill, and a benchmark run built on `main`.
- **Added:** a plain `herd init` refuses while another task in the same checkout is active (finish it, cancel it, or use `--worktree`). Before, it silently replaced the active task.
- **Added:** `herd pr` records the PR, and `herd done` updates its description with the final evidence. Before, the agent had to remember to run `herd pr` again.
- **Fixed:** parallel `herd init --worktree` calls could fail with `failed to read .git/worktrees/.../commondir`, because git reads every worktree's admin files while another add is half done. The `git worktree add` call now takes a file lock in the git directory (Unix; Windows has no `flock`). This made one CI run on main fail.

## 0.3.0

Herd is short by default. Measured on this repository: the three skills went from 2,592 to 1,662 words (run: 1,286 to 777), a passing `herd verify` from one line per criterion to one line, and `herd done` from the full report (about 1,000 words) to two lines.

- **Changed:** `herd verify` prints one summary line plus only the criteria that need attention (failing, unchecked, ran zero tests); `--verbose` lists all. `herd done` prints two lines (result and the path to `evidence.md`); `--verbose` prints the report. `herd triage` prints one line (`risk: high (auth/**)`, or the config error when `herd.toml` is broken); `--json` prints the full record.
- **Changed:** the run skill is 777 words. The quick route, the worktree start, the adversarial pass and the PR step moved to reference files (`skills/run/quick.md`, `worktree.md`, `adversarial.md`, `pr.md`) that the agent reads only when the step applies. The criteria and evidence skills are under 450 words each.
- **Added:** a fixed final report: seven lines (done, proven, not proven, caveats, decisions, limits, review), filled from `evidence.md`, that link the evidence instead of repeating it, and writing rules in the run skill (answer first, no recap, never drop a negation, numbers and commands exact).
- **Changed:** the PR description shows the result, what is proven and what is not; run details, the caveat log and Reproduce are collapsed `<details>` blocks. Long check commands are cut to 60 characters in the table and kept in full under Reproduce.
- **Added:** `herd check` warns when a criterion text is over 40 words or a coverage note over 50 words.
- **Added:** budget tests (`TestBudgets`) keep these sizes from creeping back.

## 0.2.9

- **Added:** `herd init <slug> "<goal>" --worktree` starts a task on a new `herd/<slug>` branch in its own git worktree at `.claude/worktrees/herd-<slug>`, cut from the local branch you are on. The task's files and active pointer live in that worktree, so several agents can run Herd tasks in one repository at once; a duplicate slug fails cleanly, and a failed init removes the worktree and branch it made. The base branch is recorded and `herd pr` targets it. Uncommitted changes left in the starting checkout are reported.
- **Added:** `[worktree] required = true` in `herd.toml` (opt-in) makes a plain `herd init` refuse outside a linked worktree on `herd/<slug>`.
- **Added:** `herd` commands run from the starting checkout for a task that lives in a worktree refuse and name the worktree, so a forgotten move fails loudly.
- **Added:** `--worktree` adds `/.claude/worktrees/` and `.herd/` to the repository's own `.git/info/exclude` (never committed), so the main checkout's `git status` stays clean, a `git add -A` cannot pick up another agent's worktree, and `git worktree remove` works.
- **Fixed:** the Stop gate and the CLI find the task from any subdirectory: the root is the nearest folder with `.herd/` or `herd.toml`, so a project in a subfolder of a repository keeps its own tasks.
- **Changed:** the run skill's intake step covers the worktree start; the README and `herd.toml` describe it.
- **Docs:** the README is brought up to date for 0.2.7 to 0.2.9: why-use-it points, a Quickstart example asking for a worktree and a PR, a "Several tasks at once" section, `herd pr` in both diagrams and an example PR description, a table of the `herd.toml` settings, the push and merge rule, and the status and roadmap.

## 0.2.8

- **Added:** `herd pr [slug] [--yes]`, an opt-in pull request step. It runs only with `[pr] open = true` in `herd.toml` or `--yes` (which the run skill passes when the request asks for a PR). It pushes the task's `herd/<slug>` branch, refuses any other branch, and opens a pull request, or updates the one that exists. The description is the evidence, first: the result and freshness, a table of what is proven and the check that proved each item, what is not proven (failing and unchecked criteria, zero-test runs, coverage gaps, known limits, open caveats), run details, and the check commands to reproduce. It refuses a dirty working tree, leaves check output out of the description, and lists at most 60 caveats. It never merges.
- **Changed:** the run skill has an opt-in step 11 that uses `herd pr`; the README, `herd.toml` and `CLAUDE.md` describe it.

## 0.2.7

- **Added:** `herd verify` flags a check that exits 0 while its output says it ran zero tests (unittest, pytest, cargo, go, jest and mocha wording). The evidence records `zero_tests`, `herd verify` marks the line `(ran zero tests)` and the report warns. It reads the full output, not only the stored tail, and a run where any suite executed tests is not flagged (cargo's empty doc-tests, go packages without tests). Advisory only: the Stop gate and `herd done` do not change. The README, the run skill and the evidence skill describe it.

## 0.2.6

- **Fixed:** the hooks no longer crash on Python older than 3.11, such as the 3.9 `python3` that ships with macOS. They exit quietly, and the CLI says which version it needs.
- **Changed:** Python 3.11 is now the minimum, down from 3.13. Path globs use `PurePosixPath.full_match` on 3.13 and a tested equivalent on 3.11 and 3.12. CI runs on all three.
- **Added:** `herd cancel [slug] [--reason "text"]` abandons a task. Its files stay as a record and the Stop gate stops blocking. The run skill uses it only when the human drops the task.
- **Added:** every command prints its usage line when arguments are missing. `herd help` lists all commands; an unknown command says so.
- **Changed:** tests moved to `tests/` (`python3 -m unittest discover -s tests -t .`), and `ruff check .` runs in CI.
- **Docs:** the PRD moved to `docs/PRD.md`, `docs/spikes/` keeps the run logs and an index (the raw review reports are in git history), `CLAUDE.md` is a contributor guide, `herd.toml` is annotated, and the README has an architecture section.

## 0.2.5

- The evidence report flags caveat notes logged in a batch (3 or more within 5 seconds), because their times then show when they were written, not when found.
- The benchmark focuses on the Sonnet pair, with and without Herd.

## 0.2.4

- Logo and plugin icon.
- The supermarket route benchmark: a hidden general verifier, a robustness probe, and the results with and without Herd.

## 0.2.3

- `herd check` warns when a human criterion uses quantifier or size words (`any`, `every`, `very big`) and its `coverage` does not say what varies or what scale was tried.
- `herd note --found|--fixed|--open|--tried` logs caveats with timestamps; the report lists them.
- The run skill has an adversarial "break it" step before review.

## 0.2.2

- Criteria take a `coverage` note and tasks a `known_limits` field; `herd check` warns when they are missing.
- Commands fall back to the only task when none is active.
- The run skill reports a skipped review instead of stopping to ask.

## 0.2.1

- Version bump so installed copies pick up the files added after 0.2.0.
- The evidence records elapsed time since `herd init`, and flags human criteria that are not verbatim quotes of the request.

## 0.2.0

- Quick route for trivial changes (`herd init --quick`), refused at a high risk floor.
- `herd detect` proposes test and lint commands for Python, Node, Rust, Go and `make test`.
- Opt-in per-file lint hook after edits.
- The evidence skill (`/herd:evidence`).
- The first verify records how many checks failed before the work.

## 0.1.0

- The evidence harness (`herd init`, `check`, `verify`, `status`, `done`), the Stop gate with a 3-block circuit breaker, and the run and criteria skills.
- Triage, Arbiter and Escalation modules, built test-first from EGM-reviewed designs.
