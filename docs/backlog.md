# Backlog

Items not planned for the current version. Newest first.

## Trail Code integration (optional companion)

Source: evaluation on 2026-11-22 of [trailhq/Trail-Code](https://github.com/trailhq/Trail-Code), read from its README only (not installed).

Idea: Herd provides the workflow and evidence; Trail provides shared memory ("learnings" in `.trail/learnings/*.md`). Keep it optional and loosely coupled, no code changes in Herd:
1. After `herd done`, if `trail` is on the PATH, the run skill saves a short learning (decisions, surprises, which checks proved which criteria), likely with `trail note` (text on stdin; syntax unconfirmed).
2. The criteria and evidence skills read `.trail/learnings/*.md` for project conventions, such as the real test command.
3. `trail check` (exits 1 on a conflict) can already be a criterion's `check`.

Do first: a spike with Trail installed to confirm `trail note` and `trail check` usage, and to test Trail's user-level Stop, PostToolUse and UserPromptSubmit hooks together with Herd's Stop gate (ordering undocumented, whether Trail's Stop hook can block is unknown).

Risks: machine-wide hooks and context noise; a Node 22 install and an anonymous usage ping (`DO_NOT_TRACK=1` disables it) cut against "lightweight"; Trail has no documented way to receive events, so deep integration is out.

## Deferred from v0.2 (see `docs/designs/herd-coco-ideas.md`)

Per-criterion `level` and `kind` (`proxy`, `attested`), per-type evidence guidance files, mutation testing, flaky-check reruns, project-wide typecheck at verify, detection beyond Python, Node, Rust and Go.
