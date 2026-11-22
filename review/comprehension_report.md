# Stage 6: Comprehension report

Reviewer: egm-comprehension (fresh context, PRD only, re-implementation standard). Verdict: **fails the re-implementation standard**. This is a PRD, so some deferral is expected, but Blockers 1-4 are contracts that other sections assume exist.

## What proposes

The PRD proposes "Herd", a plugin (repo `herd-sdlc`) on top of EGM that replaces the human's two roles (scheduler and judge of findings) with an Orchestrator agent and an Arbiter agent. It extends Goldfish fresh-context verification to every artifact (brief, spec, plan, code, tests, release, drift). A feature goes from a GitHub issue labelled `herd` to a merged, released, drift-monitored change. The human supplies a goal, approves at H1 (intent), approves at H2 (release, high risk only), and answers escalations. Progress is proven by graded, stored evidence per success criterion.

## How existing system works, per this document

EGM today is a spec-driven flow of slash commands: `/egm-brainstorm`, `/egm-draft`, `/egm-review`, `/egm-resolve`, `/egm-drift-report`, `/egm-bootstrap`. An Elephant agent (full context) drafts; Goldfish personas (Zoom-out, Comprehension, Critic, Implementation Readiness) review with no context and a Synthesizer dedups findings. A human answers interviews, approves each section, triages every finding and merges a spec PR. Implementation, testing and release are not covered; drift is reported but never reconciled; no state is kept beyond checked-in files. The document does not say how the EGM commands are invoked non-interactively (see C6).

## Findings

| # | Severity | Scope | Discrepancy |
| --- | --- | --- | --- |
| C1 | Blocker | P1/P3/P4, FR-03, FR-10a: criterion, `check`, evidence grade, `matrix.md`, `evidence/` | No schema: field names, file format, location. Not stated whether criteria live in `concepts_brief.md`. Provenance (`human`/`agent-proposed`), "stale" (FR-10b) and `evidence/` naming undefined. Two engineers would build incompatible formats. |
| C2 | Blocker | `.herd/state/<feature>.yaml`, "Resumable and idempotent", Orchestrator | Called the single source of truth but no schema. The 13 steps are not enumerated (the lifecycle diagram is an unrendered embed). Transitions, round counters, budget use, risk fields and update/locking rule unspecified. Orchestrator "sees state file only" yet must open escalations and merge PRs; mechanism not described. |
| C3 | Blocker | `herd.yaml` | Autonomy, budgets and gates are "configured here" but no keys, types, defaults or units. "Budget exceeded" has no numeric meaning. Unclear whether 24 h and 3 rounds are configurable. |
| C4 | Blocker | Risk scoring (FR-01, H2, Triage, Release Reviewer) | Low/medium/high only hinted at by the H2 list. Size has no scale or use. Rubric deferred to `resources/standards/` (does not exist yet). How two agents' scores combine, and who wins on disagreement, is unstated. |
| C5 | Major | Arbiter (FR-06, FR-07, `decisions.md`) | "Blocking findings" undefined. "Defer" has no backlog destination or format. Arbiter rubric undefined. `decisions.md` line format and inputs-hash computation unstated. "Confidence is low" has no scale. Unclear if the 3-round limit is per loop or per feature, and what "escalate" does to state. |
| C6 | Major | FR-02, FR-04 | Non-interactive run of EGM skills: no flag, override or wrapper described. What happens to invented answers vs the open-questions list is unstated. The open question admits it is unresolved, yet FR-02 is P0. |
| C7 | Major | FR-03, H1, "comment on the issue or PR" | What "merged" means for the intent PR vs the later spec; how comments are parsed; what a rejected PR does to state; what "next step" is. `/herd hold` has no resume and no in-flight behaviour. |
| C8 | Major | FR-08 `plan.yaml` | No schema, ID format or ordering rule. "Goldfish checks coverage" has no failure behaviour. DetailedRange/FeatureRange used without definition. |
| C9 | Major | FR-09 to FR-11 | How "one PR per task" interacts with per-criterion evidence; when criteria are verified; merge order by dependency; which CI, lint, SAST and secret-scan tools; what "no criterion failing" means before the task merges; worktree and branch naming; how the Orchestrator merges. |
| C10 | Major | Autonomy table vs H1/H2 and FR-15 | L3 "H1 only for high risk" conflicts with H1 applying to every feature and H2 being the high-risk gate. L0 and L1 not mapped to FRs. Lite skips the Intent gate yet L2 default implies H1 always on. Goal 1 says "two gates" while H2 is conditional. |
| C11 | Major | FR-12 to FR-14 | Deploy adapter interface, canary, health check, rollback thresholds and rollback effect on state undefined. FR-12 is P0 but FR-13 is P1, so a high-risk feature cannot be released in the pilot. Doc-side vs code-side drift rule and rejected drift PR undefined. |
| C12 | Major | Success metrics | Several lack a measuring mechanism (who records overturns, how the 10% sample is chosen, how the human baseline is computed). The 20-feature M0 exit and "on median" window have no time frame. |
| C13 | Major | Context isolation, FR-05, least privilege | How "proof of fresh context" is obtained; what "fail closed" does to state; mechanism for "secrets never enter agent context"; how Builder CI and deploy access work with it. |
| C14 | Major | EGM terms (Zoom-out, Critic, Synthesizer, Lite/Full, `<project>-elephant`, golden-run fixtures, harness) | Used but not defined; the document links to the README without summarizing persona inputs and outputs. |
| C15 | Major | P2/P3, `none` and `weak` handling | Channel and completion record for a manual step undefined. FR-10a loops weak criteria back to the Builder with no exit if the gap cannot be closed (the 3-round limit covers review/resolve only). |
| C16 | Nit | Section 5 embed | The lifecycle diagram is not present in the text, so the "highlighted gates" cannot be read. |
| C17 | Nit | FR-17 digest, goal 4 "Antigravity" | Digest format, schedule, channel unspecified. "Antigravity" unexplained. |
| C18 | Nit | Goal 1 "two gates" vs Escalation | Escalations are a third human touchpoint that the metrics count. Reword. |
