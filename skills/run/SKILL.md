---
name: run
description: Autopilot a task from goal to verified evidence with minimal human input. Use when the user hands over a feature, fix or change to build end to end, or invokes /herd:run.
argument-hint: "<the task, one or two sentences>"
---

# Herd run: goal in, evidence out

Work the task to the end without waiting on the human. The human gave a goal (and maybe criteria). You deliver code plus **evidence** that the criteria pass. "Done" means `herd done` succeeded, not that you say so. A Stop hook enforces this while a task is active.

`HERD="python3 ${CLAUDE_PLUGIN_ROOT}/scripts/herd.py"` (run it from the project root, a git repository).

## Steps

1. **Intake.** Pick a short slug. Run `$HERD init <slug> "<goal>"` and `$HERD triage "<goal text>"`. Triage prints a risk floor (low, medium, high) from `herd.toml` path rules; you may raise it, never lower it. Do not ask clarifying questions: fill gaps with stated assumptions.
2. **Criteria.** Follow the `herd:criteria` skill. Run `$HERD check`, then `$HERD verify` once: the checks should fail before the work.
3. **Gate.** Risk `high`: show the criteria table and assumptions and ask one approval question before building. Risk `low` or `medium`: print the criteria table and assumptions and continue. If the user said to confirm criteria first, always ask.
4. **Build.** Work on a branch or worktree. Tests first. If Superpowers is installed, use `superpowers:writing-plans`, `superpowers:test-driven-development` and `superpowers:subagent-driven-development`; otherwise do the same in short steps yourself. Keep changes minimal and within the goal.
5. **Review (medium and high risk).** Get a fresh-context review of the diff: `superpowers:requesting-code-review`, or EGM's Goldfish agents (`egm:egm-zoom-out`, `egm:egm-implementation-readiness`) if EGM is installed. Fix Blocker and Major findings; decline Nits with a one-line reason. At most 3 review rounds, then escalate.
6. **Verify.** `$HERD verify`. Fix every failing criterion and run it again. After 3 failed attempts on one criterion, escalate.
7. **Escalate only when needed.** Stop and ask the human **one** question with 2 to 3 numbered options when: an action is irreversible, a real trade-off needs a human, or you are stuck after the caps above. Never stop for missing detail.
8. **Finish.** `$HERD done`. It refuses unless evidence is fresh and passing. Then report in plain text: what changed, the evidence table, unchecked criteria (never counted as met), and each autonomous decision in at most 3 lines (decision, reason, how to override).

## Rules

- Human-written criteria and checks are never weakened to make them pass. If a check is wrong, say so and ask.
- Evidence beats claims: quote command output, not "it works".
- If the Stop hook blocks you, read its reason, fix the cause, run `$HERD verify`. Do not edit the evidence files by hand.
