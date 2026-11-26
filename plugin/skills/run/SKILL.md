---
name: run
description: Autopilot a task from goal to verified evidence with minimal human input. Use when the user hands over a feature, fix or change to build end to end, or invokes /herd:run.
argument-hint: "<the task, one or two sentences>"
---

# Herd run: goal in, evidence out

Work the task to the end without waiting on the human. You deliver code plus **evidence** that the criteria pass. "Done" means `herd done` succeeded, not that you say so. A Stop hook enforces this while a task is active.

`herd <command>` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/herd.py" <command>`, written out in full, run from the project root (or the task's worktree). Checks in `task.toml` run from there too.

Reference files hold the detail of a step. When a step names one, open it and read all of it before you act on that step. A summary in this file never replaces it: [quick.md](quick.md) (quick route), [worktree.md](worktree.md) (own worktree), [adversarial.md](adversarial.md) (every standard-route task), [pr.md](pr.md) (pull request).

## Who designs, who builds

Run `herd status` first: it prints `Design:` and `Build:` lines (before init, also `no active task`). The quick route has no design steps. The design steps, in order: init, criteria and inputs (steps 1, 2), the second look (`herd design-brief`, answered in ANSWERS.md), then the six attacks and red (steps 3, 4).

- `Design: here`: do them yourself.
- `Design: spawn herd:herd-designer with model M`: spawn it with the Agent tool on `model` M, in the foreground (a full name the tool rejects: pass its tier). Give it the request verbatim, the full `herd` command, the project folder, whether to use `--worktree`, and the paths of adversarial.md and worktree.md. Never design first or rewrite its criteria or attacks. Then continue at step 5.
- `Build: spawn herd:herd-builder with model M`: after step 5, spawn it for step 6 with the full `herd` command, the task folder and this skill's folder. Then do steps 7 to 9 yourself. `Build: here`: build yourself.

## Steps

1. **Intake.** If `herd status` starts with `Stopped` and gives a `Next`, do that first. Otherwise pick a short slug. Trivial change (one file, no new behaviour, an existing check can fail first)? Take the quick route: [quick.md](quick.md). Otherwise run `herd init <slug> "<goal>" --request "<verbatim message>"`. Herd records the `/herd:run` message itself. Add `--worktree` when `herd.toml` has `[worktree] required = true`, the user asks for it, or other agents work in this repository: [worktree.md](worktree.md). Then run `herd triage "<goal text>"`. It prints the risk floor: raise it, never lower. Ask no clarifying questions: state assumptions.
2. **Criteria.** Follow the `herd:criteria` skill, then run `herd check` and fix its warnings. Use `herd detect` for the real test command. To plan evidence with the user, point them to `/herd:evidence`. Then, on the standard route and before any attack, the second look: run `herd design-brief`, do what it says, and write `.herd/tasks/<slug>/ANSWERS.md`. The first `herd verify` refuses without it. Add no scope nobody asked for.
3. **Break it** (standard route, never skipped), before any code. Read [adversarial.md](adversarial.md) now: attack exactly what the request promises. Log all six standard attacks, each with its check, in one Bash call: the first `herd verify` refuses while one has no note. Solve one tiny case by hand for `--expect`. `herd done` refuses until each one has a command that `herd verify` ran and saw pass.
4. **Red.** Run `herd verify` before writing code. Checks must fail. A check that already passes proves nothing: tighten it. A check marked `(ran zero tests)` found no tests: fix its command.
5. **Gate.** Risk `high`: show the criteria table and assumptions, ask one approval question, wait. Otherwise show them and continue. Always ask if the user said to confirm criteria first.
6. **Build.** On branch `herd/<slug>` (`herd init` creates it and switches to it; if it warns that it could not, create it yourself), tests first, minimal changes within the goal. Use Superpowers (`writing-plans`, `test-driven-development`, `subagent-driven-development`) when installed. Then try to break the result, as adversarial.md says.
7. **Verify.** Run `herd verify` once the work is done. While working, run only your changed tests or `herd verify --only <id>` (writes no evidence). It prints one timed line, plus what needs attention, including when to escalate. It skips an unchanged tree; use `--fresh` after outside changes.
8. **Escalate only when needed:** an irreversible action, a real trade-off, or stuck after the caps. Ask **one** question with 2 or 3 numbered options. Never stop for missing detail. If the human drops the task, run `herd cancel --reason "<their words>"`. Never cancel to get past the gate.
9. **Finish.** Finish docs and commit before the final `herd verify` and `herd done`. Commit on the task branch if allowed; else say it is uncommitted. If the request asked for a pull request or `herd.toml` has `[pr] open = true`, follow [pr.md](pr.md): it opens the PR before the final verify. Run `herd verify`, then `herd done`. It prints the final report, filled from the evidence and the notes.

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
- Log every finding, fix, open limit and attack with `herd note --found|--fixed|--open|--tried "..."` the moment it happens, in any step: one call each. Resolved: `--fixed --closes N`. Notes logged together are flagged: their times mean nothing. Except attack notes: step 3.
- If the Stop hook blocks you, fix the cause and run `herd verify`. Never edit evidence files by hand.
- A `Herd guard` denial is final: follow its reason, never work around it.
