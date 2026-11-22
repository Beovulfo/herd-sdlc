# EGM Consolidated Review Report

**Target:** `docs/designs/herd-escalation.md` (FeatureRange 1-194, DetailedRange 195-243)
**Preset:** Consolidated report for all review rubrics, uninterrupted, one round. Design not edited; egm-resolve not run.

## Reviewer Status

| Stage | Reviewer | Scope | Status |
| --- | --- | --- | --- |
| 5 | `egm-zoom-out` | full | completed |
| 5 | `egm-inventive-catalyst` | full | completed |
| 6 | `egm-comprehension` | Feature + Detailed, no GoldfishContext | completed |
| 7 | `egm-design` | FeatureRange | completed |
| 7 | `egm-structural` | FeatureRange | completed |
| 7 | `egm-style` | FeatureRange | completed |
| 8 | `egm-zoom-out` | full | completed |
| 9 | `egm-implementation-readiness` | DetailedRange | completed |
| 9 | `egm-codebase-details` | DetailedRange | completed |
| 9 | `egm-style` | DetailedRange | completed |

All 10 reviewer runs completed; none "not reviewed" or "not run".

## Per-stage raw counts (match the stage files; not deduplicated)

| Stage | File | Blocker | Major | Nit | Total |
| --- | --- | --- | --- | --- | --- |
| 5 | `zoom_out_report.md` | 0 | 13 | 8 | 21 |
| 6 | `comprehension_report.md` | 0 | 12 | 6 | 18 |
| 7 | `critic_report.md` | 0 | 10 | 19 | 29 |
| 8 | `intermediate_zoom_out_report.md` | 0 | 6 | 7 | 13 |
| 9 | `implementation_readiness_report.md` | 3 | 16 | 19 | 38 |
| **Total raw** | | **3** | **57** | **59** | **119** |

Per-reviewer splits are in each stage file. Overall verdict: feature design is sound in structure (derived pause, closed options, one issue per feature) but self-contradicts on three points (ceiling, `blocked`, G4), conflicts with the Arbiter design on `malformed`, and the Detailed plan is not implementation-ready (3 Blockers).

## Prioritized Findings (deduplicated; highest severity among sources wins)

Source IDs refer to stage files: Z/IC = Stage 5, F/D = Stage 6 (F feature, D detailed), D/S/Y = Stage 7 (`egm-design`, `egm-structural`, `egm-style`; critic_report IDs), M/N = Stage 8, R/C/Y = Stage 9 (readiness, codebase, style).

### Blocker

**CB1 Ceiling contradicts itself (G8 3 issues vs CUJ 8 2 answered); count basis and branch order undefined.**
Lines 28, 88-92, 182, 219. Sources: Z-M1, IC-M6, F3, D2, M3, R-B2, C-N8. Fix: one number, define what counts (open/abandoned/reopened/repeat), order branches (append if open, else block at limit, else open); fix `test_ceiling`.

**CB2 Escalation and cause data shapes cannot support `next_escalation`, `build_issue_body`.**
Lines 213, 218-219, 233. Sources: R-B1, C-M2, D-detail D2, M6, Z-N9. Fix: exact schemas (`state` values, `step`, `reason`, `options` item shape, `repeat_of` rule), one source for "answered".

**CB3 Event shape elided with `...`; missing `issue_reopened`; "valid answer" not derivable.**
Lines 213, 220-221. Sources: R-B3, comprehension D3, C-M2, Z-N10. Fix: fields per event type, link to escalation, define valid-answer derivation.

### Major

**CM1 `herd:blocked` is an unlisted fifth status; no exit; precedence unstated.** Lines 13, 21, 28, 92, 96, 114-120, 214. Sources: Z-M2, Z-M3, IC-M6, F1, D1, Y2, M2, C-M3, R-M6. Fix: add to G1, status table, command table; define exit and precedence.

**CM2 G4 ("refused") contradicts command table and CUJ 4.** Lines 24, 64-68, 115-117. Sources: F2, D8, M1. Fix: "resume never clears an escalation; removes hold only and names the issue".

**CM3 Raised round cap and budget have no stated home; `raise_by` one value for two limits; `budget_used` has no owner.** Lines 120, 126, 185, 126. Sources: Z-M4, F5, D6, M4, R-M7, C-N10. Fix: effective cap = base + answered escalations (derived), split `raise_by`, name owner.

**CM4 "Cause" undefined; answer actions missing for `step_failure`, `low_confidence`, `tradeoff`; "overrule" to what; human decision path into `decisions.md` unnamed.** Lines 22, 25, 56, 104-120. Sources: Z-M5, F-comprehension, D5, M4, M6. Fix: one cause per trigger with findings listed inside, or `(trigger, step/finding id)`; one action line per option; name the `decisions.md` writer or drop `low_confidence` option 2 from M0.

**CM5 `malformed` handling conflicts with Arbiter design** (per-finding `escalate` there, `step_failure` here, omitted from summary list). Lines 105, 108; herd-arbiter.md 21, 25, 95, 101. Sources: Z-M6, IC-M5, D4, M5, R-N4. Fix: one rule (all findings malformed after re-ask is `step_failure`, else summary); update Arbiter design.

**CM6 Low-confidence Nit escalations consume touchpoints (threatens median <=2); `rounds` escalation cannot settle open `policy` findings.** Lines 102-108. Sources: IC-M2, D4, D3 (critic). Fix: route Nit to summary or batch per round; add "proceed to spec PR with open findings listed" option.

**CM7 "Maintainer" = triage role holds spending/verdict authority; role undefined across PRD and sibling designs; no assignee roster source.** Lines 35, 110, 112, 183. Sources: D7, N13, Z-N14, F8. Fix: require write+ for `/herd answer` or record acceptance; define once.

**CM8 Stale/incorrect PRD claims: `/herd answer <n>` already in PRD section 4; this design extends to `<n> [<n> ...]`; Alternative B misattributes one-issue-per-feature.** Lines 17, 148, 160. Sources: Z-N11, D9, Y1, N8, N9. Fix: reword as extension, amend PRD.

**CM9 Alternatives' "Rejected by author" gives no trade-off; missing alternatives (timeout default, protected state flag).** Lines 140-166. Sources: S1, D10. Fix: state trade-offs.

**CM10 Command table not implemented; maintainer boolean has no receiver (G3 untestable).** Lines 112, 114-118, 215-216. Sources: D1 (detailed), R-M1, C-M1. Fix: `apply_command(...)`/`author_is_maintainer`.

**CM11 `command_of`, `parse_answer`, `build_issue_body` underspecified (parsing algorithm, template, inputs, returns); no `options_for`.** Lines 100-106, 112, 215-218. Sources: R-M2, R-M3, R-M4, Y-N4..N6. Fix: exact algorithm/template/returns.

**CM12 `paused_seconds` and `touchpoints` semantics and return shape undefined; "abandoned" and "median" undefined.** Lines 124, 220-221. Sources: R-M5, C-M4, F6, N12. Fix: define terms, shapes, report owner.

**CM13 Test plan lacks inputs/outputs and class mapping; `test_hold_does_not_stop_running_step` cannot fail.** Lines 201-203, 223-226, 238. Sources: Z-N12, D4 (detailed), N10, R-M6, C-M6, Y-M1. Fix: fixtures and expected values; drop or relocate the non-test.

**CM14 `herd.yaml`/`requirements.txt` ordering with Triage; Phase 4 `import yaml` can fail; "Modify or Create" ambiguous.** Lines 204-206, 228-231. Sources: R-M7, C-M5, D6 (detailed). Fix: declare dependency order or add Create-if-absent `requirements.txt` with same pin.

**CM15 File boundary incomplete (PRD amendment, `budget_used` and round-cap code owners).** Lines 120, 126, 160, 208-231. Source: R-M8.

**CM16 `herd_status` order and "open" ambiguous.** Lines 213-214. Source: Y-M2.

**CM17 Undefined project terms (M0/M1, H2, Evidence Auditor, step boundary, fails closed, etc.).** Lines 13, 33-39, 105, 110. Sources: F7, Y-N11.

**CM18 `rounds` trigger severity inconsistent (table Blocker|Major, CUJ 1 Blocker only).** Lines 47, 102. Source: F4.

**CM19 No durable escalation history for metrics (only live GitHub).** Technical Plan Touchpoints, Future Improvements. Source: IC-M1. Option: append JSONL to `decisions.md` (promote Future Improvement into M0).

**CM20 One atomic positional answer for whole issue; append race and single typo invalidate.** `/herd answer`, G2, G5. Source: IC-M3. Option: cause ids (`rounds=1 budget=2`).

**CM21 Unbounded silent wait (no numeric reminder trigger).** Non-Goals Reminders, `paused_seconds`. Sources: IC-M4, Y-N5. Option: pure `stale()` plus optional scheduled workflow, off until a numeric threshold.

**CM22 YAGNI: `tradeoff` trigger has no M0 producer.** Lines 42, 106, 191. Source: Z-M7.

### Nit

CN1 Technical Plan weeds (140-char cut, marker version, `/herd` line rule, quote/fence parsing, edit handling) and tuple signatures duplicate prose: Z-N8, N11. CN2 `issue` reopen/close ordering race; `touchpoints()` should read bot record comment and per-event role: D11. CN3 Alternative A rationale should note `budget_used`/round counter also agent-resettable (M1 tamper gap): Z-N13. CN4 Hold takes effect only at step boundary; transient `step_failure` costs a touchpoint immediately: IC-N7. CN5 Risk row "burns touchpoints" says mitigated though repeats count again: N7. CN6 Metric machinery beyond PRD need: N12. CN7 Human-minutes metric unsourced; `step` in repeat key undefined for `rounds`/`budget`: D13. CN8 Command parsing edge cases (no-op reply vs silence, non-escalation issue): D12. CN9 Structure: heading name "Technical Plan" vs "Proposed Architecture", run-in labels not H3, diagram placement, inconsistent horizontal rules, Terms/Open Questions placement, traceability (CUJ 7 test not under G6; new tests unmapped): S2-S7, R-N5. CN10 Wording: "Everything is derived" overclaim, subjective "meaningless", "goes stale", redundant bot sentence, awkward paused-time line, wordy state-record line, unclear line 174, vague "exceed the intent": Y3-Y10 (critic). CN11 Detailed-range wording and checks: Y-N3..N12 (stage 9), R-N1..N3, C-N7, C-N9, F9-F11, D5-D7 (comprehension), IC. CN12 `raise_by` unit stated only in Detailed range; Arbiter cause names only by pointer; duplicate marker/bot statement: F9-F11.

## Traceability Matrix

| Design area | Lines | Consolidated findings | Stage sources |
| --- | --- | --- | --- |
| G1 pause derived / status | 13, 21, 96, 214 | CM1, CM16, CN10 | 5, 6, 7, 8, 9 |
| G3 maintainer only | 25, 112 | CM7, CM10 | 6, 7, 8, 9 |
| G4 hold/resume | 24, 64-68, 114-118 | CM2, CM10 | 6, 7, 8 |
| G5 closed answers / causes | 22, 25, 56, 104-120 | CM4, CM20, CN8 | 5, 6, 7, 8 |
| G6 touchpoints | 122-124, 221 | CM12, CM19, CN6, CN7 | 5, 6, 7, 9 |
| G8 / CUJ 8 ceiling | 28, 88-92, 182, 219 | CB1 | 5, 6, 7, 8, 9 |
| Triggers table | 98-108 | CM4, CM5, CM6, CM18, CM22 | 5, 6, 7, 8, 9 |
| Budget / raised limits | 120, 126, 185 | CM3 | 5, 6, 7, 8, 9 |
| Alternatives A-E | 138-166 | CM8, CM9, CN3 | 5, 7, 8 |
| Risks / NFR / Non-Goals | 176-190 | CM7, CM21, CN5 | 5, 7, 8 |
| Sibling consistency (Arbiter, Triage, PRD) | 105, 108, 160 | CM5, CM8, CM14 | 5, 7, 8, 9 |
| Data shapes and event model | 213, 218-221 | CB2, CB3, CM12, CM16 | 5, 6, 8, 9 |
| Functions and command parsing | 215-218 | CM10, CM11 | 6, 9 |
| Tests | 223-226, 238 | CM13, CN9 | 5, 6, 8, 9 |
| File boundary / `herd.yaml` | 204-206, 208-231 | CM14, CM15 | 6, 9 |
| Structure and style | throughout | CN9, CN10, CN11, CM17 | 6, 7, 9 |

## Counts

Raw (stage files, 5 files): Blocker 3, Major 57, Nit 59, total 119. Deduplicated consolidated findings: Blocker 3 (CB1-CB3), Major 22 (CM1-CM22), Nit 12 grouped entries (CN1-CN12) covering the remaining raw nits.

## Artifacts

All in `docs/spikes/s1-runs/escalation/round1/`: `zoom_out_report.md`, `comprehension_report.md`, `critic_report.md`, `intermediate_zoom_out_report.md`, `implementation_readiness_report.md`, `consolidated_review_report.md`.
