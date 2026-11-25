---
name: run
description: Autopilot a task from goal to verified evidence with minimal human input. Use when the user hands over a feature, fix or change to build end to end, or invokes /herd:run.
argument-hint: "<the task, one or two sentences>"
---

# Herd run: goal in, evidence out

Work the task to the end without waiting on the human. You deliver code plus **evidence** that the criteria pass. "Done" means `herd done` succeeded, not that you say so. A Stop hook enforces this while a task is active.

`herd <command>` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/herd.py" <command>`, written out in full, run from the project root (or the task's worktree). Checks in `task.toml` run from there too.

Reference files hold the detail of a step. When a step names one, open it and read all of it before you act on that step. A summary in this file never replaces it: [quick.md](quick.md) (quick route), [worktree.md](worktree.md) (own worktree), [adversarial.md](adversarial.md) (every standard-route task), [pr.md](pr.md) (pull request).

## Steps

1. **Intake.** If `herd status` starts with `Stopped` and gives a `Next`, do that first. Otherwise pick a short slug. Trivial change (one file, no new behaviour, an existing check can fail first)? Take the quick route: [quick.md](quick.md). Otherwise run `herd init <slug> "<goal>" --request "<the user's message, verbatim>"`. Add `--worktree` when `herd.toml` has `[worktree] required = true`, the user asks for it, or other agents work in this repository: [worktree.md](worktree.md). Then run `herd triage "<goal text>"`. It prints the risk floor. You may raise it, never lower it. Do not ask clarifying questions: state assumptions.
2. **Criteria.** Follow the `herd:criteria` skill, then run `herd check` and fix its warnings. Use `herd detect` for the real test command. To plan evidence with the user, point them to `/herd:evidence`.
3. **Break it** (standard route, never skipped), before any code. Read [adversarial.md](adversarial.md) now: attack exactly what the request promises. Log all six standard attacks, each with its check. Solve one tiny case by hand for `--expect`. `herd done` refuses until each one has a command that `herd verify` ran and saw pass.
4. **Red.** Run `herd verify` before writing code. Checks must fail. A check that already passes proves nothing: tighten it. A check marked `(ran zero tests)` found no tests: fix its command.
5. **Gate.** Risk `high`: show the criteria table and assumptions, ask one approval question, wait. Otherwise show them and continue. Always ask if the user said to confirm criteria first.
6. **Build.** On branch `herd/<slug>` (`herd init` creates it and switches to it; if it warns that it could not, create it yourself), tests first, minimal changes within the goal. Use Superpowers (`writing-plans`, `test-driven-development`, `subagent-driven-development`) when installed. Then try to break the result, as adversarial.md says.
7. **Verify.** Run `herd verify` once the work is done. While working, run only your changed tests or `herd verify --only <id>` (writes no evidence). It prints one line, plus what needs attention, including when to escalate.
8. **Escalate only when needed:** an irreversible action, a real trade-off, or stuck after the caps. Ask **one** question with 2 or 3 numbered options. Never stop for missing detail. If the human drops the task, run `herd cancel --reason "<their words>"`. Never cancel to get past the gate.
9. **Finish.** Commit on the task branch if the project allows it; otherwise say it is uncommitted. If the request asked for a pull request or `herd.toml` has `[pr] open = true`, follow [pr.md](pr.md): it opens the PR before the final verify. Run `herd verify`, then `herd done`. It prints the final report, filled from the evidence and the notes.

## Final report

Paste the report `herd done` prints, as written. Log each decision the moment you make it: `herd note --decision "<decision>; <reason>; <how to override>"`.

## Writing

- Answer first. No greeting, no recap, no closing offer.
- One idea per sentence, 20 words at most. Active voice.
- Short words; standard terms only, no invented abbreviations.
- Never drop not, never, no, only or except. Numbers, paths and commands exact.
- Quote command output, not "it works". Link files instead of pasting them.

## Rules

- Never weaken human criteria or checks to make them pass. If a check is wrong, say so and ask. Record a human's change with `herd note --human-change`.
- Log every finding, fix, open limit and attack attempt with `herd note --found|--fixed|--open|--tried "..."` the moment it happens, in any step: one call each. Notes logged together are flagged, because their times then mean nothing.
- If the Stop hook blocks you, fix the cause and run `herd verify`. Never edit evidence files by hand.
- A `Herd guard` denial is final: follow its reason, never work around it.
