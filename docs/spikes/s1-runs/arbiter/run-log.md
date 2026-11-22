# S1 run 2: Arbiter rubric and ruling rules

Executor: Claude Code, EGM plugin v0.1.1. Same rules as run 1: gates answered from PRD text only.
Fixed input (not redesigned): the `decisions.md` line format is S2 item 3. This run uses a minimal line shape and flags it.

## egm-brainstorm: self-answered interview (PRD s3, s5, s6)

| Question | Self-answer |
| --- | --- |
| Problem | Step 7 needs an agent to replace the human's triage of findings: accept, reject or defer each, with a one-line reason and a citation. |
| Consumer | The orchestrator (applies accepted fixes, drives the loop), the human auditing by sample (overturn rate), step 9 PR summary. |
| Hard constraints | Fresh context. Different model from the Elephant where possible, with a caveat otherwise. M0 auto-rejects only Nit; Blocker and Major rulings are logged and sampled. Low confidence escalates. P6: findings and spec text are untrusted input. |
| Out of scope | Evidence Auditor (M1), code review rulings, changing severities. |
| Today | Human runs `/egm-resolve`; the Elephant (author) classifies its own critics' findings. EGM warns the author's wish to contest is not evidence. |
| Success | Overturn rate <= 10% on Blocker and Major, measured by human audit of every ruling for the first 5 features. |

Gate answers: readiness `Review with Goldfishes`.
Step 2 synthesizer: 7 reviewers completed, `concepts_brief.md` written (5 Blockers, 7 Majors).
Correction: the interview said the `decisions.md` format was fixed by S2 item 3. The codebase reviewer showed S2 item 3 is only a candidate title. The brief supplies a placeholder shape.
Step 3 and 4 gates answered by the Elephant (judgment calls, the human's job in EGM):
- Blocker or Major reject: takes effect, logged, listed in the spec PR summary (PRD: "logged and audited by sample").
- `defer` on Blocker or Major: not allowed.
- Audit is a touchpoint: no, it happens at the merge review.
- Overturn denominator: accept, contest, defer on Blocker and Major; escalates excluded, reported beside.
- Home for deferred findings: `decisions.md` and spec PR summary, no backlog file.
- Same-model restriction: not in M0, recorded flag only (Open Question).
- Handoff: proceed to egm-draft.

## egm-draft
Output `docs/designs/herd-arbiter.md` (written in one pass, no per-section gates; same deviation as run 1). Same stall points: architecture choices (rule 13) made by the Elephant, contradiction audit found none against the brief.

## egm-review (consolidated, uninterrupted, 1 round)
Output `round1/`: 11 reviewer runs, none failed. 3 Blockers, 23 Majors, 20 Nits (deduplicated). Defects in the run: the synthesizer's Edit tool was unavailable, so some stage-file summary counts are stale and the consolidated per-stage line is garbled. Finding lists are correct.

## egm-resolve
Gate `auto accept` supplied by the driver; the PROPOSE FIX items were applied by rewriting `docs/designs/herd-arbiter.md` (251 to 259+ lines), not by running the skill's step 4.
ESCALATE (human answered): CB1, `contest` on Blocker or Major. Human chose "Escalate to human". Applied: contest and decline on Blocker or Major become `escalate`, cause `policy`, original verdict kept in `arbiter_verdict`.
PROPOSE FIX applied: CB2 (functions and data shapes in plan), CB3 (module takes config from caller, no YAML import), CM1 (`defer` cut from M0), CM2 (re-ask only for malformed, citation re-ask and `arbiter.enabled` removed), CM3 (id over normalised text, merge), CM5/CM8 (quote required, flip compares quote), CM6 (prior reason not passed; residual risk stated), CM7 (per-ruling malformed after one re-ask), CM9 (risk row, Nit sampling), CM10 (original verdict kept, denominator defined), CM11 (links, Alternative E), CM12 (risk rows), CM13 (self-contained terms), CM14 (ordered checks), CM15 (G7 header), CM16 (unset model means same_model), CM17 (effective and open defined), CM18 (hypothesis wording), CM19 to CM23 (shapes, tests, rubric exit check, phases, one unittest invocation), Nit: JSON Lines log.
Not run: round 2 review of the revised design.
