# Consolidated Goldfish Review Report

**Target:** `docs/designs/herd-arbiter.md` (full file, 251 lines; FeatureRange 1-197, DetailedRange 198-251)
**Preset:** Consolidated report for all review rubrics, uninterrupted. Round 1, fresh review. Design not edited, `egm-resolve` not run.

## Totals (deduplicated across stages)

| Priority | Count |
| --- | --- |
| Blocker | 3 |
| Major | 23 |
| Nit | 20 |

Per-stage raw counts (after in-stage dedup): Stage 5: 0/7/7 (Blocker/Major/Nit... see zoom_out_report: 0 Blocker, 5 Major, 6 Nit as written headings), Stage 6: 0/14/9, Stage 7: 1/14/13 (as listed: 1 Blocker, 12 Major, 12 Nit headings), Stage 8: 0/3/6, Stage 9: 2/10/4. The consolidated counts above are authoritative; the per-stage files carry their own detail.

## Reviewer Status

| Stage | Reviewer | Scope | Status |
| --- | --- | --- | --- |
| 5 | `egm-zoom-out` | full file | completed |
| 5 | `egm-inventive-catalyst` | full file | completed |
| 6 | `egm-comprehension` | 1-197 | completed |
| 6 | `egm-comprehension` | 198-251 | completed |
| 7 | `egm-design` | 1-197 | completed |
| 7 | `egm-structural` | 1-197 | completed |
| 7 | `egm-style` | 1-197 | completed |
| 8 | `egm-zoom-out` | full file | completed |
| 9 | `egm-implementation-readiness` | 198-251 | completed |
| 9 | `egm-codebase-details` | 198-251 | completed |
| 9 | `egm-style` | 198-251 | completed |

All reviewers read their persona (and standard where applicable). No reviewer reported corrupted or missing words; none were verified-and-kept. Stage reports: `zoom_out_report.md`, `comprehension_report.md`, `critic_report.md`, `intermediate_zoom_out_report.md`, `implementation_readiness_report.md` in the same directory.

## Prioritized Findings

### Blocker

**CB1. `contest` on a Blocker/Major is effective and bypasses the Nit-only auto-reject limit.** Lines 58-62, 102, 107, 163-167, 175. G3/CUJ 4 block only `decline`; PRD line 89 allows auto-reject only for Nit. Whether a contested Blocker counts as open at loop exit is undefined. Fix: make `contest` non-effective on Blocker/Major in M0 (or escalate), define open-count status, or justify the PRD divergence. Sources: D-B1, Z2.

**CB2. No function owns the orchestrator work in the Detailed Plan.** Lines 210-219 vs 90, 92, 108. Input assembly, dedup, re-ask, prior parsing, `decisions.md` append, `same_model`, config reading, audit-line writing, entry point are unassigned. Sources: R-B1.

**CB3. "stdlib only" conflicts with reading `herd.yaml`.** Lines 115, 212, 239. No YAML parser in stdlib; owner of config reading and Elephant model supply undecided. Sources: R-B2.

### Major

- **CM1. `defer` verdict incoherent.** Lines 41, 102, 107, 127, 129, 145-149, 184. No EGM mapping (contradicts "does not fork"), rewritten to `escalate` on Blocker/Major yet in the Blocker/Major denominator, no post-merge destination, undefined semantics. Fix: map to an EGM category or cut from M0. Sources: Z2, D-M7, S-M1, ZO-M1, F2.
- **CM2. M0 scope creep (flip rule, citation re-ask, modulo sampling, eight goals).** Lines 21-28, 92, 108, 109, 127. Sources: Z1, ZO-M2.
- **CM3. Finding id unstable; scope and dedup undefined.** Lines 36, 92, 186. Rephrase or line shift yields new id, making flip protection largely inert; same issue from two personas gets two ids. Fix: define scope/dedup, or Arbiter-proposed `same_as` validated by code. Sources: C4, D-M2, ZO-N3, F6.
- **CM4. Re-raised rejected Blocker still burns the 3-round cap.** Problem statement, Risks, G6, CUJ 6-7. Fix: code-side settled set keyed to cited-region hash. Sources: C2.
- **CM5. Flip rule "same citation" brittle.** Lines 26, 109. Compare by quote or spec-hash, not line range. Sources: D-M3, C5.
- **CM6. G5 injection guarantee overstated; second-order injection via prior `reason`; accept path applies raw finding text.** Lines 25, 74, 92, 173. Sources: D-M4, S-M (G5), C6.
- **CM7. Malformed output escalates the whole round; escalate mechanics and re-ask undefined.** Lines 25, 108, 111, 115. Fix: per-ruling validation, single re-ask for malformed, specify escalate mechanics and worst-case counts. Sources: C3, D-M5, F7.
- **CM8. Citation proof weak.** Lines 24, 108, 185. `quote` optional; omissions uncitable. Sources: D-M6.
- **CM9. Reviewer-assigned severity hazard unmitigated.** Lines 17, 24, 113. Sources: D-M1.
- **CM10. Audit, sampling and rollout metric not closed.** Lines 42, 125-127, 175; PRD 39, 45. Adds human minutes; no post-overturn action; 10 percent trigger on about 50 rulings, no escalation-rate guard; original verdict lost on rewrite; sampling vs metric populations unclear; audit machinery built despite non-goal. Sources: Z3, D-M8, ZO-M3, F9.
- **CM11. Alternatives Rule not met.** Lines 143-167. "Rejected by author" unlinked; S1 spike unlinked; C unquantified; central alternatives missing. Sources: D-M9, N12, N13, ZO-N5.
- **CM12. Risks table lacks injection and scalability rows.** Lines 178-187. Sources: T-M1.
- **CM13. Terms not self-contained; H1 cited wrongly.** Lines 11-13, 17, 41, 131, 175. Sources: F1, N1.
- **CM14. Policy-check ordering and edge cases (duplicate, unknown id, flip after rewritten prior).** Lines 26, 104-111, 215. Sources: F4, N2, R-M2.
- **CM15. G7 contradicts log shape (models in header only).** Lines 21, 27, 117-121. Sources: F5, N6.
- **CM16. `same_model` with unset model assumes inheritance.** Line 115. Sources: F8.
- **CM17. Vocabulary: "reject" is not a verdict; "effective" undefined.** Lines 40, 56, 62, 182, 193. Sources: S-M2, F3.
- **CM18. Unsupported assertions (poor calibration, "large multiple", about 50 rulings).** Lines 42, 154, 160. Sources: S-M3.
- **CM19. Detailed plan interfaces and data shapes undefined (validate, sample, overturn_rate, format_lines, summary).** Lines 204, 215-219. Sources: F10, F11, R-M1, R-M3, R-M4, R-M5.
- **CM20. Test plan is names only; CUJ 7 has no test; not self-contained.** Lines 82-88, 221-224, 246. Sources: F13, R-M6, R-M8.
- **CM21. Rubric rule count inconsistent; exit check unverifiable.** Lines 131, 206, 226-229. Sources: F12, R-M7.
- **CM22. Agent file and `herd.yaml` unphased; Triage ordering; `model: null`.** Lines 231-239. Sources: F14, R-M9.
- **CM23. Inconsistent unittest invocation.** Lines 204-205, 244. Sources: F20, R-M10.

### Nit

1. Altitude: signatures/formulas in architecture (Z4, ZO-N1).
2. `arbiter.enabled` config with no off-path behaviour (Z5, ZO-N6).
3. Pipe log placeholder over-specified; JSONL simpler (Z6, ZO-N2).
4. Re-ask cost vs cap and citation-check strength unstated (Z8).
5. Open Questions duplicate PRD/Future Improvements and sit before CUJs (ZO-N4, N10).
6. Citation requirement per verdict unstated (F15).
7. CUJ 7 breaks Given/When/Then, no owner (F16, N7).
8. Summary section named two ways (F17).
9. S1/S2 references unlinked (F18, N11).
10. "3-round cap" introduced in passing (F19).
11. G8 "append-only" unenforced; omits first-5 full audit (N3).
12. "same family" vs `same_model` equality (N4).
13. No token estimate in cost NFR (N5).
14. Unnumbered trailing rule under Policy checks (N8).
15. Heading "Technical Plan (Architecture)" (N9).
16. Filler and subjective pros wording (N12, N13).
17. "Python 3.13" unsourced (R-N1).
18. Plan wording and parameter descriptions (F21, F22, R-N2, R-N3).
19. "First 5 features give overturn data" has no criterion (F23).
20. No round-trip integration test (R-N4).

## Traceability Matrix

Source IDs are in the stage reports (Z/C = `zoom_out_report.md`, F = `comprehension_report.md`, D/S/T/N = `critic_report.md`, ZO = `intermediate_zoom_out_report.md`, R = `implementation_readiness_report.md`).

| Consolidated | Stage 5 | Stage 6 | Stage 7 | Stage 8 | Stage 9 |
| --- | --- | --- | --- | --- | --- |
| CB1 | Z2 | | D-B1 | | |
| CB2 | | | | | R-B1 |
| CB3 | | | | | R-B2 |
| CM1 | Z2 | F2 | D-M7, S-M1 | ZO-M1 | |
| CM2 | Z1 | | | ZO-M2 | |
| CM3 | C4 | F6 | D-M2 | ZO-N3 | |
| CM4 | C2 | | | | |
| CM5 | C5 | | D-M3 | | |
| CM6 | C6 | | D-M4 | | |
| CM7 | C3 | F7 | D-M5 | | |
| CM8 | | | D-M6 | | |
| CM9 | | | D-M1 | | |
| CM10 | Z3 | F9 | D-M8 | ZO-M3 | |
| CM11 | | | D-M9, N12, N13 | ZO-N5 | |
| CM12 | | | T-M1 | | |
| CM13 | | F1 | N1 | | |
| CM14 | | F4 | N2 | | R-M2 |
| CM15 | | F5 | N6 | | |
| CM16 | | F8 | | | |
| CM17 | | F3 | S-M2 | | |
| CM18 | | | S-M3 | | |
| CM19 | | F10, F11 | | | R-M1, R-M3, R-M4, R-M5 |
| CM20 | | F13 | | | R-M6, R-M8 |
| CM21 | | F12 | | | R-M7 |
| CM22 | | F14 | | | R-M9 |
| CM23 | | F20 | | | R-M10 |
| Nits 1-20 | Z4-Z8, C5 | F15-F23 | N3-N11 | ZO-N1-N6 | R-N1-R-N4 |

Every finding in the five stage reports maps to at least one consolidated item.
