# Consolidated Review Report: herd-triage (round 3)

**Target:** `docs/designs/herd-triage.md` (203 lines; FeatureRange 1-152, DetailedRange 153-203)
**Preset:** Consolidated report for all review rubrics, uninterrupted.
**Stage files (same directory):** `zoom_out_report.md`, `comprehension_report.md`, `critic_report.md`, `intermediate_zoom_out_report.md`, `implementation_readiness_report.md`.

## Reviewer Status

| Stage | Reviewer | Status |
| --- | --- | --- |
| 5 | `egm-zoom-out` | completed |
| 5 | `egm-inventive-catalyst` | completed |
| 6 | `egm-comprehension` | completed |
| 7 | `egm-design` | completed |
| 7 | `egm-structural` | completed |
| 7 | `egm-style` | completed |
| 8 | `egm-zoom-out` | completed |
| 9 | `egm-implementation-readiness` | completed (verdict: not ready) |
| 9 | `egm-codebase-details` | completed |
| 9 | `egm-style` | completed |

All 10 reviewer runs completed; none "not run". Only one text finding about wording (line 168 count) was Grep-verified; no reviewer reported corrupted text.

## Per-stage counts (match stage files)

| Stage | File | Blocker | Major | Nit | Total |
| --- | --- | --- | --- | --- | --- |
| 5 | zoom_out_report.md | 0 | 6 | 8 | 14 |
| 6 | comprehension_report.md | 0 | 6 | 10 | 16 |
| 7 | critic_report.md | 0 | 8 | 15 | 23 |
| 8 | intermediate_zoom_out_report.md | 0 | 3 | 8 | 11 |
| 9 | implementation_readiness_report.md | 2 | 6 | 7 | 15 |
| **Sum of stage findings** | | **2** | **29** | **48** | **79** |

Stage findings overlap heavily across stages. Deduplicated issue themes are below (4 Blockers/Majors-level clusters merge many stage IDs).

## Findings by priority (deduplicated)

### Blocker

**B1. Override preservation, unknown-key preservation and `schema_version` rejection have no implementing function** (R1; also Z3, C3, C12, I1).
`build_record` takes no existing record; no `read_record`; `write_record` writes a fresh dict and would clobber other designs' keys (round counter, budget). Fix: `existing` parameter, `read_record`, merge only the `risk` key, name the exception.

**B2. No invocation contract or entry point** (R2; also C3, I1 for the undefined events).
No CLI or import call sequence; `triage`/`human_override` events undefined; `herd_toml: str` cannot represent a missing file.

### Major

**M1. Display-only claim vs readers; tamper gap and trust root of `effective`/override** (Z1, Z5, K1). Line 11 says the Arbiter reads the record, but the Arbiter design never reads risk. Unsupported claim that a forged value is visible at H1. Consider an out-of-branch issue comment, or derive `effective` at read time. State the gap once.

**M2. `risk:low` label is an unrecorded second lowering path** (Z2; K9 nit). Conflicts with PRD section 5 and weakens G1. Drop it; lower only via recorded `/herd risk`.

**M3. `/herd risk` has no owner or parser; "maintainer" undefined** (Z4, C6 nit, I2, K2). Extend Escalation's single `parse_command`, adopt its maintainer definition, add a status-table row, specify the override input shape (actor, comment id, time, who verifies).

**M4. Write concurrency and read-modify-write across designs** (K2, B1). Lost updates between designs' writers; name a single-writer assumption or ordering rule.

**M5. Missing or inconsistent M0 measurement and certainty about "most floors are `medium`"** (Z6, C2, K7, K8, I3). Hypothesis stated as fact in places; no metric, owner, or threshold; Alternative A reasoning circular; consider a deterministic brief-stage ratchet.

**M6. Terms and `source` semantics** (C1, C4). P6, H1, Arbiter, orchestrator, P3 unglossed; `source` precedence undefined when paths match no rule or a rule and label both apply.

**M7. Alternatives section** (K3, K4). "Rejected by author" attribution barred by the standard; missing alternatives (CODEOWNERS seed, default `high`, structured issue form, manual baseline).

**M8. Glob anchoring and extractor gaps** (K5, Z12 nit). `auth/**` misses nested layouts; URLs, `.yml/.yaml`, extension-less files.

**M9. Missing `herd.toml` fallback vs default rule set** (K6, Z13, C5, I-N5).

**M10. Detailed plan under-specified** (R3 function count, R4 `apply_override` and conflict with line 83, R5 `floor`/`rules`/fallback shape/`cause`/`source`, R6 test plan and phase mapping, R7 `write_record` details, C11/C12).

**M11. `herd.toml` creation ownership vs siblings** (R8). Triage "Create" vs Arbiter and Escalation "Create if absent / Modify".

### Nit

Itemised in the stage files; grouped here: Python 3.13 pin and enforcement (Z12, I-N8, K12, R9); test command forms, import path, `TestFloor` (Z9, I-N2, R10, R13); `status`/`cause` naming collision (Z7); regex and normalisation altitude, trailing punctuation, hardcode `path_extensions` (Z10, I-N3, I-N4, C10, K20); unknown-key strictness rationale (Z11); fallback stickiness (Z14); `schema_version` newer / override on fallback / `from` ambiguity / override may raise (K10, K11, K15, I-N6); body size caps and limits (K13); rollback wording (K14); events undefined (K17); section order, rules, heading name (K18, K19); wording and clarity (K16, K21-K23, C7-C9, C13-C16, R11-R15); `<feature>`/"base branch" undefined (C8).

## Traceability matrix

| Cluster | Zoom/Inventive (5) | Comprehension (6) | Critic (7) | Intermediate (8) | Readiness (9) |
| --- | --- | --- | --- | --- | --- |
| B1 override/merge/read functions | Z3 | C3, C12 | K14 | I1 | R1 |
| B2 invocation contract | | C3 | K2 | I1 | R2 |
| M1 display-only / trust root | Z1, Z5 | | K1 | | |
| M2 `risk:low` label | Z2 | | K9 | | R5 (applier check) |
| M3 `/herd risk` owner, maintainer | Z4 | C6 | K2, K15 | I2 | R4 |
| M5 measurement / certainty | Z6 | C2 | K7, K8 | I3 | |
| M6 terms, `source` | | C1, C4 | K9 | I-N7 | R5 |
| M7 alternatives | Z1 | | K3, K4 | | |
| M8 glob anchoring | Z12 | C10 | K5 | | |
| M9 missing `herd.toml` | Z13 | C5 | K6 | I-N5 | |
| M10 detailed plan gaps | Z8, Z9 | C11-C16 | K16 | I-N1, I-N2 | R3-R7, R9-R15 |
| M11 `herd.toml` ownership | | C15 | | | R8 |
| Python 3.13 pin | Z12 | | K12 | I-N8 | R9 |

## Compared with the previous round

Previous reports were not read, so no regression can be confirmed. Observations only.

Probable regressions or edit-induced inconsistencies (typical of a fix pass that updated one place and not the rest):
- Line 168 says four functions, five are listed.
- Line 83 "treats out-of-range level as `high`" vs line 172 "rejects" a level outside the three.
- Rules requiring override preservation (line 79) and unknown-key preservation (line 83) with a `build_record` signature that takes no prior record.
- Test and phase text: `TestFloor` in the Phase 1 exit check with no class named in the test list; path vs dotted unittest forms.
- The recent TOML/JSON switch itself looks clean: no reviewer found a defect in `tomllib` or JSON use; only the Python 3.13/3.11 floors and a missing-file representation (`herd_toml: str`) are open.

Leftover inconsistencies with the two siblings:
- Line 11 says the Arbiter reads the record; the Arbiter design has no risk use. Escalation does not read risk either.
- `/herd risk` is absent from Escalation's closed `parse_command` and status table; "maintainer" is defined only in Escalation (and both leave it as an open question).
- `herd.toml` creation: Triage "Create"; Arbiter assumes Triage creates it; Escalation "whichever is built first".
- Python 3.13 pin is deferred to Triage by both siblings but not enforced or shared.
- Top-level `status` stored in the record vs Escalation's derived, never-stored feature status.
- Escalation rejected storing a control field in the agent-pushable record as a P6 break; Triage accepts the same pattern for risk (acceptable only if display-only is stated and true).
