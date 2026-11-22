# Consolidated review: Herd PRD

Target: `PRD — Autopilot SDLC plugin built on the Elephant-Goldfish Model.md`. Mode: consolidated, Stages 5 to 8 (Stage 9 skipped: the PRD has no implementation-plan section).
Stage reports: `zoom_out_report.md`, `comprehension_report.md`, `critic_report.md`, and the Stage 8 results below. Reviewers ran in fresh contexts.

## Verdict
The PRD does not pass. The problem is well identified (the human is the scheduler and the judge), but the document (1) still presents its central bet as proven, (2) is over-scoped for a first version, (3) contradicts itself on human touchpoints, and (4) has no safety ordering between auto-merge and rollback. The Stage 6 schema gaps are real but should go into per-milestone design docs, not the PRD.

## Stage 8: intermediate zoom-out (no mitigations existed yet, so these confirm earlier findings)

| # | Severity | Finding | Direction |
| --- | --- | --- | --- |
| A1 | Blocker | Z1, Z2, Z4 and Z6 are unresolved: still 5 new personas, 6 skills, 3 adapters, L0-L3, evidence grading, a digest and a custom state file around an unproven Arbiter. | Decide scope first. Cut to M0 (Define half plus Arbiter at L1); keep P1 items as one-line roadmap entries. |
| A2 | Blocker | Applying all Stage 6 and 7 hardening would roughly double the PRD before the bet is validated. | Take the cheap ones now: one gate-by-level matrix; a short Alternatives section; a path-based risk floor; an "untrusted input" note (issue text and comments can carry prompt injection; only maintainers may apply `herd` or `/herd hold`). Defer the rest to `docs/designs/`. |
| A3 | Major | EGM already has `egm-lite` and `egm-review-loop`; Code Auditor overlaps Codebase Auditor; Test Critic and Release Reviewer are likely rubric swaps. | New personas only for Arbiter and Evidence Auditor. Reuse EGM for Lite and the review loop. |
| A4 | Major | State file and "only the Orchestrator merges" reinvent GitHub labels, check runs, branch protection and Actions concurrency. | Derive state from GitHub; keep a file only for what GitHub cannot hold, with each field justified. |
| A5 | Major | The evidence layer is the biggest speculative block. | v1: criteria point at existing tests, CI is the evidence, the PR comment is the report. Defer grades and the matrix. |
| A6 | Major | Silent departure from EGM's human-judge philosophy; premise still asserted. | One paragraph naming the departure, stated as a hypothesis with a pilot metric. Consider Arbiter auto-rejecting Nits only in v1. |
| A7 | Major | FR-02 and FR-04 assume EGM runs non-interactively; EGM's docs describe interactive checkpoints. The PRD also calls dependency vs vendor both decided and open. | Settle with a spike first; it decides fork vs upstream. |
| A8 | Major | FR-11 auto-merge (P0) precedes rollback (FR-13, P1); FR-12 has no pilot release path. | Leave auto-merge out of the pilot (M0 and M1 at L1), or move minimal rollback to P0. The first is simpler. |
| A9 | Minor | Design detail inside a PRD (file tree, state path, numbers, scanner list). | Move to `docs/designs/herd-*.md`. |
| A10 | Minor | `docs/designs/<feature>/` vs EGM's `<feature>.md`; `resources/standards/` vs `document_standards/`; `herd_*` vs hyphenated names; "mirrors EGM" is inaccurate. | Align or drop the claim. |
| A11 | Nit | Three first-party deploy adapters. | One `herd.yaml` contract (deploy, health, rollback commands); no adapters. |

## Totals before deduplication
Stage 5: 9 zoom-out plus 8 inventive-catalyst. Stage 6: 4 blockers, 11 majors, 3 nits. Stage 7: 6 blockers, 14 majors, grouped nits. Stage 8: 2 blockers, 6 majors, 3 minor or nit.

## Traceability: raw findings to action items

| Action | Closes |
| --- | --- |
| 1. Scope decision: M0 only (Define half, Arbiter, L1); P1 as roadmap lines | Z1, Z2, Z4, Z6, A1, A5, I7, A11, K3 (partly) |
| 2. Spike: can EGM run non-interactively; depend vs vendor | M1, A7, C6 |
| 3. Add Alternatives Considered | K1, Structural 1 |
| 4. One gate-by-level matrix; fix Goal 1, metrics, FR-15, L3 | K5, C10, C18 |
| 5. Replace the diagram placeholder with a numbered list; map steps to FRs | K4, C2 (partly), C16 |
| 6. Restate premise as a hypothesis; name the departure from EGM; constrain Arbiter authority | K6, K2, Z5, A6, I2 |
| 7. Path-based risk floor; auto-merge only with rollback or at L1 | M5, I5, A8, C4 |
| 8. Untrusted-input and permissions note | M2, Design 5 |
| 9. Evidence floor: no auto-merge on `none` or agent-only criteria | K3, I3 |
| 10. Reuse EGM (Lite, review loop, rubrics on existing personas) | Z3, A3 |
| 11. Derive state from GitHub | M4, Z2, A4, I4 |
| 12. Metrics: baselines, guard metrics, rename "Arbiter agreement" | M6, Z9, I8, C12 |
| 13. Move detail and schemas to `docs/designs/` | Z7, A9, M8, C1, C3, C5, C8, C9, C11, C13 |
| 14. Terminology, style, structure, hygiene | M9 to M14, Z8, A10, all nits |
| Deferred (cost model, multi-vendor Arbiters, mutation testing, adaptive H1) | M3, I1, I6; revisit after M0 data |
