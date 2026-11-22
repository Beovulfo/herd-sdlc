# Consolidated Review Report

**Target:** `docs/designs/herd-arbiter.md` (1-253; FeatureRange 1-194, DetailedRange 195-253)
**Preset:** Consolidated report for all review rubrics (uninterrupted, no human checkpoints). Design not edited; egm-resolve not run.

## Reviewer Status

| Stage | Reviewer | Status | Report |
| --- | --- | --- | --- |
| 5 | `egm-zoom-out` | completed | `zoom_out_report.md` |
| 5 | `egm-inventive-catalyst` | completed | `zoom_out_report.md` |
| 6 | `egm-comprehension` | completed | `comprehension_report.md` |
| 7 | `egm-design` | completed | `critic_report.md` |
| 7 | `egm-structural` | completed | `critic_report.md` |
| 7 | `egm-style` | completed | `critic_report.md` |
| 8 | `egm-zoom-out` | completed | `intermediate_zoom_out_report.md` |
| 9 | `egm-implementation-readiness` | completed | `implementation_readiness_report.md` |
| 9 | `egm-codebase-details` | completed | `implementation_readiness_report.md` |
| 9 | `egm-style` | completed | `implementation_readiness_report.md` |

No reviewer was `not run`; all personas and standards were readable. No corrupted/truncated-text findings were raised by any reviewer.

## Per-stage raw finding counts (match stage files)

| Stage | File | Blocker | Major | Nit | Total |
| --- | --- | --- | --- | --- | --- |
| 5 | zoom_out_report.md | 0 | 12 | 6 | 18 |
| 6 | comprehension_report.md | 0 | 10 | 5 | 15 |
| 7 | critic_report.md | 0 | 12 | 18 | 30 |
| 8 | intermediate_zoom_out_report.md | 0 | 4 | 5 | 9 |
| 9 | implementation_readiness_report.md | 5 | 21 | 14 | 40 |
| **Raw total** | | **5** | **59** | **48** | **112** |

Stage 5 ids: Z1-Z10 (zoom-out), I3-I8 (inventive; I1/I2 merged into Z6/Z1 in the file). Stage 6: C1-C15. Stage 7: D1-D14, T1-T4, S1-S12. Stage 8: M1-M9. Stage 9: R1-R17, CB1-CB13, SD1-SD10.

## Consolidated findings (deduplicated across stages)

Consolidated: Blocker 5, Major 15, Nit 9 (29 distinct findings from 112 raw).

### Blockers

#### K1 Flip check / `prior` cannot be built - Blocker
* **Traces:** R1, CB3, C4, C10 (L82, L100, L109-111, L213, L217)
* **Issue:** `prior` needs `quote_sha`; log and ruling shape lack it; hash algorithm/normalisation undefined; no function derives `prior` from `decisions.md`; `prior` content for escalated or quote-less rulings undefined.
* **Fix:** Add `quote_sha` (named algorithm) to ruling and log; add `load_prior`.

#### K2 Citation resolution undefined - Blocker
* **Traces:** R2, CB5, M8 (L92, L95, L99, L217)
* **Issue:** Line base, inclusivity, join, normalisation, path compare, omission-heading quotes unspecified; exact substring on lossy reads gives spurious `citation` escalations.
* **Fix:** Pin the rules; whitespace-normalised substring; add tests.

#### K3 Re-ask rule contradicts check 1 - Blocker
* **Traces:** R3, CB2, SD1, C1, C2, I7, M4 (L94-95, L217; Escalation L108/L110)
* **Issue:** Any-malformed vs all-malformed trigger; partial failures, id-less objects, retry prompt, second output replacing first undefined; cause precedence when output unparseable.
* **Fix:** One rule across Technical Plan, `validate`, and Escalation.

#### K4 Header, `same_model` and hashes never built - Blocker
* **Traces:** R4, CB7 (L103, L108, L217-218)
* **Fix:** `build_header(...)` with test; name hashes.

#### K5 Audit and metric functions lack usable inputs/outputs - Blocker
* **Traces:** R5, CB7, SD3, SD4, C5, C6, Z3, D3, M5 (L13, L35, L110-115, L219-221)
* **Issue:** Audit lines keyed by id only (ids repeat across rounds/features); `result` values and `agreed_escalations` undefined; return shapes and `n=0` undefined; `feature_index` source undefined and contradicts G8 (id-only); no audit/human-line capture path.
* **Fix:** `feature` and `round` in ruling/audit lines; enumerate results; define shapes; name the capture mechanism.

### Majors

#### K6 Loop semantics for escalated Blocker/Major - Major
* **Traces:** Z1, I2(Z1), D1, M1 (L13, L17, L23, L62, L98; Escalation L105/L110)
* **Issue:** A wrongly raised Blocker/Major stays open as `escalate/policy`, is re-raised, runs to the round cap, then opens a `rounds` issue, against the <=2 median touchpoint target.
* **Fix:** State loop handling ("parked" and carried to the PR, or cost accepted); update CUJ 3 and Escalation `rounds` row.

#### K7 Merged findings: severity and scope undefined - Major
* **Traces:** Z5, D4, M4, R6, CB4 (L80, L214)
* **Fix:** Highest severity wins; test it; define scope.

#### K8 Sampling claims contradictory and steerable - Major
* **Traces:** Z7, I5, C6, C7, D2, D13, S2, S3, M2 (L25, L68, L115, L167, L177, L219)
* **Issue:** "every effective ruling sampled" vs 1-in-4 after feature 5; id from reviewer-controlled text so sampling is steerable; sampling detects but cannot prevent (fix applied before merge); CUJ 4 outcome untestable.
* **Fix:** One accurate statement everywhere; salt the hash; consider auditing all effective Nit declines.

#### K9 Overturn metric not split by severity - Major
* **Traces:** Z4, D14, S4, M3 (L7, L39-42, L115, L169; PRD section 3)
* **Fix:** Split by severity class or report the B/M subset.

#### K10 Injection containment asserted, not enforced - Major
* **Traces:** I4, D6, S1, R7 (L25, L66-68, L82, L149, L167, L182-183)
* **Issue:** One shared context; Alternative C concedes cross-contamination; fixture cannot prove containment; data-block delimiters and escaping undefined; "many findings in one call" unmitigated.
* **Fix:** Reword G5; define delimiters; consider Blocker/Major vs Nit split; cap findings per call.

#### K11 Arbiter read scope / tools vs citation scope - Major
* **Traces:** D5, Z8, D11, M8 (L78, L97-99, L113, L119, L167, L182; PRD section 8)
* **Issue:** Unrestricted Read/Grep/Glob contradicts PRD "artifact and cited sources"; exfiltration via `reason` into a public PR summary; citations limited to the spec path but rubric rule 1 invites other evidence.
* **Fix:** Restrict reads or drop tools; add the risk; align rule 1 and check.

#### K12 Single-writer claim vs human/audit lines - Major
* **Traces:** Z2, D3, M5, R9 (L78, L105-114; Escalation L112)
* **Fix:** Name writers; define `human` line type and metric treatment; add `append_lines` and path.

#### K13 Policy check precedence and escalate/low_confidence interaction - Major
* **Traces:** C2, C3, R8, CB1, CB6, M7, I3, Z10, D9, D10 (L24, L94-101; Escalation L107/L112)
* **Issue:** Multi-failure cause, Arbiter `escalate` with `L`, duplicate/unknown/missing output shapes, flip scope with prior `escalate`, low-confidence applied to safe `accept`, `low_confidence` before `policy` (opens an issue where `policy` would not), `overrule_arbiter` opposite undefined for `escalate`/decline.
* **Fix:** State "first failing check wins" (or record all); order and scope as recommended; align cause tables across designs.

#### K14 Flip rule does not solve the stated re-raise problem - Major
* **Traces:** Z6, I1, M1, D9 (L17, L26, L74, L80, L100, L178)
* **Issue:** Fires only on verdict change with same quote; rephrase gets new id; bare-heading citations can collide; risk row overclaims.
* **Fix:** Drop or restate as anti-oscillation; key repeat detection on location; fix risk row.

#### K15 Default `model = "inherit"` and shared-model bias - Major
* **Traces:** Z9, I6 (L41, L176, L241)
* **Fix:** Default to a different model where supported; widen Nit-decline sampling when `same_model`.

#### K16 Severity mislabelling has no mitigation - Major
* **Traces:** D7, I8 (L119, L151, L177, L203)
* **Fix:** `severity_dispute` flag or rubric rule 6 (update Phase 3 check).

#### K17 Alternatives attributed to "author", thin rationale - Major
* **Traces:** T1, D8, S9, S10 (L135-155)
* **Fix:** Drop attribution; state trade-offs; link any person-based rejection; add or dismiss missing alternatives.

#### K18 Agent file under-specified - Major
* **Traces:** R11, CB9, SD7 (L233-236, L241)
* **Fix:** Exact frontmatter, exclusion mechanism for inherited instructions, how `inherit` reaches the agent.

#### K19 Test plan not runnable/assertive - Major
* **Traces:** C9, R12, R13, CB8, M9 (L201, L223-226)
* **Fix:** Name classes, assign to phases, table of input/expected including all causes, boundaries, fixture assertion.

#### K20 Ruling shape / naming / referents - Major
* **Traces:** SD2, SD3, C12, R10 (L80, L88, L92, L109, L113, L213, L216, L221)
* **Fix:** One name for `conf`/`confidence`; define `verdict` vs `arbiter_verdict`, `cause` values, `type`/`round`; resolve "order above"; place the 140-char cut.

### Nits

* **K21** `herd.toml` creator ownership and build order across Triage/Escalation (R14, CB10, SD6; L206, L238). Triage entry should say "Create if absent, else Modify"; add coexistence check (CB13) and agent-file exit check.
* **K22** PRD divergence not carried back (`defer` dropped, verdict renames) (M6, S5; L34, L89-92; PRD L89, L120).
* **K23** Normalisation, Python version, rubric text and weak Phase 3 grep (CB11, CB12, R16, R17, SD5; L80, L203, L212, L231).
* **K24** Structure: heading vs siblings, run-in labels, dense Terms, fence labels (T2, T3, T4; L13, L71, L84-111).
* **K25** Wording/unsupported claims: L48/L62 vague Given, L68 "valid, escalated or sampled", L103 harness behaviour, L153, L135 (S6, S7, S8, S9, S10, T1 overlap).
* **K26** Detailed plan altitude (Z10; L195-221): trim trivial function descriptions.
* **K27** Glossary/provenance: "hypothesis 2" ungloss, S2 placeholder owner, "reject" vs `decline`, cross-design dependency note (C11, C13, C14, C15).
* **K28** `escalate` as ruling and cause; optional clarifying sentence (S12).
* **K29** Pilot-measurement text in E2E line; `(TOML has no null)` aside; `feature_index` base (SD9, SD10, R15).

## Traceability matrix (consolidated finding to source ids)

| Consolidated | Stage 5 | Stage 6 | Stage 7 | Stage 8 | Stage 9 |
| --- | --- | --- | --- | --- | --- |
| K1 | | C4, C10 | | | R1, CB3 |
| K2 | | | | M8 | R2, CB5 |
| K3 | I7 | C1, C2 | | M4 | R3, CB2, SD1 |
| K4 | | | | | R4, CB7 |
| K5 | Z3 | C5, C6 | D3 | M5 | R5, CB7, SD3, SD4 |
| K6 | Z1 | | D1 | M1 | |
| K7 | Z5 | | D4 | M4 | R6, CB4 |
| K8 | Z7, I5 | C6, C7 | D2, D13, S2, S3 | M2 | |
| K9 | Z4, I5 | | D14, S4 | M3 | |
| K10 | I4 | | D6, S1 | | R7 |
| K11 | Z8 | | D5, D11 | M8 | |
| K12 | Z2 | | D3 | M5 | R9 |
| K13 | Z10, I3 | C2, C3 | D9, D10 | M7 | R8, CB1, CB6 |
| K14 | Z6 | | D9 | M1 | |
| K15 | Z9, I6 | | | | |
| K16 | I8 | | D7 | | |
| K17 | | C14 | T1, D8, S9, S10 | | |
| K18 | | | | | R11, CB9, SD7 |
| K19 | | C9 | | M9 | R12, R13, CB8 |
| K20 | | C12 | | | SD2, SD3, R10 |
| K21 | | C15 | | | R14, CB10, CB13, SD6 |
| K22 | | C14 | S5 | M6 | |
| K23 | | | | | CB11, CB12, R16, R17, SD5 |
| K24 | | | T2, T3, T4 | | |
| K25 | | | S6, S7, S8, S9, S10 | | |
| K26 | Z10 | | | | |
| K27 | | C11, C13, C14, C15 | | | |
| K28 | | | S12 | | |
| K29 | | | | | SD9, SD10, R15 |

Every raw finding id is covered by at least one consolidated finding. Raw S11 (L183 risk row) is folded into K10.

## Compared with the previous round

Previous reports were not read, so no regression can be asserted from a diff. Observations about the current text only:

* **Sibling consistency leftovers (likely leftover inconsistencies, not new regressions):** (1) re-ask condition: Escalation L108/L110 matches only the "all malformed" reading of L217, not check 1 at L95; (2) Escalation L112 `{"type":"human"}` lines vs Arbiter "only writer" claim at L78; (3) Escalation `overrule_arbiter` "opposite verdict" undefined for `escalate` and for decline; (4) `low_confidence` trigger fires on `escalate`/accept in a way Escalation L107 does not distinguish; (5) `herd.toml` is "Create" in Triage and "create if absent" in Escalation, while the Arbiter L206/L238 names only Triage; (6) PRD L89/L120 still says "accepts, rejects or defers", not updated.
* **Possible regression from the recent TOML/JSON Lines switch:** none found. `tomllib` Phase 4 check and TOML "no null" rationale verified sound; remaining gaps (hash algorithms, `quote_sha` in the JSON line, `round`/`feature` keys, `result` values) are JSON Lines schema omissions rather than format defects. Format-change coherence with the Triage Python 3.13 pin: confirmed.
* **Fixes appear to have held:** codebase-details confirmed the Triage pin, namespace-package unittest invocation and `int(id,16) % 4` validity; structure has no skipped heading levels.
