---
name: run
description: Autopilot a task from goal to verified evidence with minimal human input. Use when the user hands over a feature, fix or change to build end to end, or invokes /herd:run.
argument-hint: "<the task, one or two sentences>"
---

# Herd run: goal in, evidence out

Work the task to the end without waiting on the human. The human gave a goal (and maybe criteria). You deliver code plus **evidence** that the criteria pass. "Done" means `herd done` succeeded, not that you say so. A Stop hook enforces this while a task is active.

Run `herd` commands from the project root (a git repository), written out in full so they work in any shell:
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/herd.py" <command>`. Below, `herd <command>` means exactly that. Check commands you write in `task.toml` also run from the project root.

## Steps

1. **Intake.** Pick a short slug and a route.
   - **Quick** for a trivial change: one file, no new behaviour surface, and an existing command that can fail first. Run `herd init <slug> "<goal>" --quick "<check>" --request "<the user's message, verbatim>"`. It refuses a `high` risk floor. Quick skips the criteria interview, the approval question and the fresh-context review. It still needs red first, `herd verify` and `herd done`. Skip steps 2, 4, 6 and 7 below; continue at step 3.
   - **Standard** for everything else: run `herd init <slug> "<goal>" --request "<the user's message, verbatim>"`. The request is stored so `herd check` can confirm that human criteria quote the human.
   Then run `herd triage "<goal text>"` (standard route). Triage prints a risk floor from `herd.toml` path rules: `high` or `medium` if a rule matched, `medium` by default when the text names no path, `low` only if a maintainer labelled it. You may raise the risk, never lower it. Do not ask clarifying questions: fill gaps with stated assumptions.
2. **Criteria.** Follow the `herd:criteria` skill, then run `herd check`. Run `herd detect` to find the project's real test command instead of guessing. If the user wants to plan the evidence together, point them to `/herd:evidence`.
3. **Red.** Run `herd verify` once before building. It should report the checks failing. A check that already passes proves nothing: tighten it.
4. **Gate.** Risk `high`: show the criteria table and assumptions and ask one approval question before building. Risk `low` or `medium`: print the criteria table and assumptions and continue. If the user said to confirm criteria first, always ask.
5. **Build.** Work on a branch named `herd/<slug>`. Tests first. If Superpowers is installed, use `superpowers:writing-plans`, `superpowers:test-driven-development` and `superpowers:subagent-driven-development`; otherwise do the same in short steps yourself. Keep changes minimal and within the goal.
6. **Break it (adversarial pass, standard route).** Before review, try to break your own work on exactly what the request promises. Take the human's quantifier and size words (`any`, `every`, `whatever`, `many`, `big`, `very big`) and turn each into hostile inputs: generated cases from several different shapes or families, extremes (empty, huge, degenerate, disconnected, malformed), and a scale run with a time limit. Run them. If you can spawn a fresh-context subagent, give it only the request, the criteria and how to run the tool, and ask it to break it and report what fails; otherwise do it yourself and say it was not fresh. Record every attempt and result with `herd note`: `herd note --tried "what you generated and ran"`, `herd note --found "what broke"`, `herd note --fixed "how"`, `herd note --open "a limit you did not fix"`. Turn each failure into a regression test and fix it. Never skip this step because the demo passes: the report shows when no pass was recorded.
7. **Review (medium and high risk).** Get a review from a fresh context, never your own. Use `superpowers:requesting-code-review` or EGM's Goldfish agents (`egm:egm-zoom-out`, `egm:egm-implementation-readiness`) if installed. Otherwise spawn a plain subagent with only the goal, the criteria and the diff, and ask for bugs and missed criteria. If you cannot spawn a reviewer at all, do not stop to ask the human: say in your final report that the review was skipped and why, and treat the change as unreviewed. Include the task's `test_budget` if it has one: ask the reviewer whether the diff matches it, flagging missing coverage and low-value extra tests. Fix Blocker and Major findings; decline Nits with a one-line reason. At most 3 review rounds, then escalate.
8. **Verify.** Run `herd verify` after every change. Fix every failing criterion and run it again. After 3 failed attempts on one criterion, escalate.
9. **Escalate only when needed.** Stop and ask the human **one** question with 2 to 3 numbered options when: an action is irreversible, a real trade-off needs a human, or you are stuck after the caps above. Never stop for missing detail.
10. **Finish.** Commit the work on the task branch if the project allows it (otherwise say it is uncommitted; the evidence records that). Run `herd done`: it refuses unless evidence is fresh and passing, and prints `done: ...` on success. Then report in plain text: what changed, the evidence table, unchecked criteria (never counted as met), each autonomous decision in at most 3 lines (decision, reason, how to override), and the headline claim with its conditions and where it fails (the `known_limits` line), not just your best demo number. The report also lists the caveats you recorded with `herd note`, with when each was found.

## Rules

- Human-written criteria and checks are never weakened to make them pass. If a check is wrong, say so and ask.
- Evidence beats claims: quote command output, not "it works".
- If the Stop hook blocks you, read its reason, fix the cause, run `herd verify`. Do not edit the evidence files by hand.
