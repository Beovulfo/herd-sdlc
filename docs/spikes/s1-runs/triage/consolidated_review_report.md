# EGM Consolidated Review Report

**Target:** `docs/designs/herd-triage.md` (198 lines). Split at `## Detailed Implementation Plan` (L154): FeatureRange 1-153, DetailedRange 154-198.
**Preset:** Consolidated report, all review rubrics. Uninterrupted, no human checkpoints.
**Next step:** `/egm-resolve` on the Blockers and Majors below.

## Stage and Reviewer Status

| Stage | Reviewer | Status | Report |
| --- | --- | --- | --- |
| 5 Initial Zoom Out | `egm-zoom-out` | completed | `zoom_out_report.md` |
| 5 Initial Zoom Out | `egm-inventive-catalyst` | completed | `zoom_out_report.md` |
| 6 Comprehension | `egm-comprehension` | completed | `comprehension_report.md` |
| 7 Critic | `egm-design`, `egm-structural`, `egm-style` | completed | `critic_report.md` |
| 8 Intermediate Zoom Out | `egm-zoom-out` | completed | `intermediate_zoom_out_report.md` |
| 9 Implementation Readiness | `egm-implementation-readiness`, `egm-codebase-details`, `egm-style` | completed | `implementation_readiness_report.md` |

All reviewers ran once; none failed or were retried.

## Run caveats (read first)

1. **False "corrupted text" findings.** The Read tool returned a lossy, compressed view (short words dropped) to several reviewers and to the synthesizer. Stage 5 zoom-out Blocker B1, the stage 6 Blockers on L26-29, CUJ 3/4, Alt A, L80, L158-160, L188-198, and stage 7 design and structural "missing text" findings are view artifacts. Grep by the synthesizer, stage 8 zoom-out and all stage 9 reviewers confirmed the file text is intact (for example L33, L121 and `### Verification Plan` at L188). These items are dropped from the priority list below. The author may still check the raw file at L26-29, L57, L80 and L149 for real wording gaps.
2. **Persona and PRD paths.** Some task-supplied persona filenames (`egm-*.md`) and the PRD path (missing "the" in one reviewer's task) did not exist; reviewers recovered by globbing. The structural reviewer did not check PRD cross-references.
3. **Single-round critic.** Stage 7 ran one round, no review loop, as instructed.

## Blockers

### B1. Agent-editable state file: floor and effective integrity unenforced
* **Lens:** design. **Scope:** L20 (G2), L86.
* State file sits on `herd/<feature>`, which agents push to in steps 2-5. "Writer rejects agent output" covers only the Triage call. Later agent commits can edit `floor` or `effective`. Add an enforced control (CI diff check, CODEOWNERS, signed commits, read-time hash) and a test (`state_file_tamper_detected`).

### B2. Design not justified for M0 (YAGNI vs PRD)
* **Lens:** zoom-out (stages 5, 8 partial). **Scope:** L15, L21, L127-143.
* M0 is L0/L1 only, H1 is human-required for every feature, rollout and rollback make the value display-only. Yet the design builds floor engine, ratchet, append-only history, retriage and idempotency. G3's H1 edit-rate metric is not in PRD section 3. Name the M0 consumer of risk or cut scope and defer audit trail and ratchet to M1.

### B3. stdlib only, but YAML everywhere
* **Lens:** implementation-readiness, codebase-details, style. **Scope:** L158, L165, L170-180.
* Python stdlib has no YAML parser. Choose PyYAML, hand parser, or JSON/TOML (`tomllib`); pin a Python version.

### B4. Glob dialect and default rule set undefined
* **Lens:** implementation-readiness, codebase-details, inventive-catalyst, zoom-out. **Scope:** L34, L36, L75, L161, L165.
* `fnmatch` lets `*` cross `/` (silent floor bypass); `**` semantics differ by matcher. Default rule set is never listed (security-relevant). Label-to-level mapping absent. Consider reusing CODEOWNERS and dropping the `floor` block. Resolve Open Questions L34 and L36 first.

### B5. PRD edit and size/path divergence left as either/or
* **Lens:** implementation-readiness, codebase-details, style, zoom-out. **Scope:** L33, L35, L183-186 (PRD L77).
* Decide now (dropping size and path is sound YAGNI per L26), name exact PRD line and destination (PRD has no Future Improvements section), also decide L0 (default: Triage runs at L0 too).

### B6. Detailed plan does not cover the Technical Plan
* **Lens:** implementation-readiness, codebase-details. **Scope:** L163-176 vs L71-113.
* No file or step for: label-triggered workflow, `/herd retriage`, issue snapshot and hash, agent prompt and read-only restrictions, comment posting, orchestrator H1 write, step 5 recompute, shadow mode, `risk_delta`. Add them or declare out of scope.

### B7. `triage_record.py` has no interface
* **Lens:** implementation-readiness, codebase-details, style. **Scope:** L171, L86.
* Specify input channel, error boundary, write mechanism to `herd/<feature>`, `run_id` and `at` source, agent-field detection, `schema_version` escalation, append-only enforcement, exact fallback field and value.

### B8. No phasing or checkpoints in the plan
* **Lens:** style, implementation-readiness, codebase-details. **Scope:** L154-194.
* Add ordered phases, each with an exit check (floor plus fixtures; record writer; runner; wiring in shadow mode; `herd.yaml`; PRD edit).

## Majors

### M1. Alternative A (rules only, no LLM) not evaluated and no threshold
* **Lens:** zoom-out, style, design. **Scope:** L15, L47-51, L117-121.
* Most issues name no paths and land at `medium`; the LLM adds only the injection-exposed low/high distinction. Evaluate on the S2 baseline or ship the LLM as advisory. State a measurable threshold for "adds little"; support or soften "often names no paths" and "most features land on medium".

### M2. Floor input is untrusted and extraction unspecified
* **Lens:** inventive-catalyst, design. **Scope:** L15, L75, CUJ 2.
* Floor sees only paths the issue names; a benign-path issue gives `low` while the change touches `migrations/`. Who extracts paths (LLM breaks G2; regex undefined)? Options: repo index plus CODEOWNERS as trusted `floor_inputs.source`, or floor `medium` unless a maintainer label confirms scope. Add CUJ 3 variants.

### M3. Ratchet vs human override; contradictory write semantics; two writers
* **Lens:** inventive-catalyst, design, zoom-out. **Scope:** L63, L69, L73, L77, L81, L86.
* "Never lowers" vs "never overwrites human value"; "written once" vs later writes; "only record writer writes" vs orchestrator writes. Define one writer (orchestrator calls it with a typed event), an explicit write-event list, a precedence table (for example per-rule `overridden_rules`), and H1 re-open termination.

### M4. Ratchet and extras are speculative M0 scope
* **Lens:** zoom-out. **Scope:** L65-69, L77, L80, L98, L141-143.
* Ratchet needs a real diff (M1) and re-opens H1, against the PRD "only human step is 4". `risk_delta`, `run_id`, correlation key, `herd_yaml_hash`, `failed` status, lazy runs and `/herd retriage` have no consumer, CUJ or test. Keep only fields a named reader uses.

### M5. Two stores of truth for risk
* **Lens:** zoom-out, comprehension. **Scope:** L63, L86, L129, Alt C.
* Record and H1 PR value both authoritative; orchestrator must parse the PR body (Alt C's rejection cost). Pick one authority (for example a `/herd risk <level>` command or label).

### M6. Fail-closed `high` for every failure class
* **Lens:** inventive-catalyst. **Scope:** L22, L84, L143.
* Transient failures inflate `high` and pollute edit-rate signals. Bounded retry for transient causes, immediate fail-closed for schema and `herd.yaml` invalidity, add `cause` to `triage.status: fallback`. Define "race" and add a test.

### M7. Shadow mode contradicts G1 and has no exit criterion
* **Lens:** design, style, implementation-readiness. **Scope:** L19, L141, L194.
* "Arbiter ignores" vs G1; "agreement" and threshold undefined; S2 5-feature baseline is not the PRD 20-feature bar and is hand-run EGM. Cite `docs/spikes/s2-baseline.md`; give command, output location and criterion.

### M8. No Risks and Mitigations section
* **Lens:** design, structural, style. **Scope:** FeatureRange.
* Uncovered: glob mis-specification, path normalisation, `herd.yaml` drift, concurrency, `medium` default weakness, label-spam or retriage DoS, scalability limits. Add a table.

### M9. Verification names, paths and fixture contract inconsistent
* **Lens:** all stage 7 and 9 reviewers, zoom-out, comprehension. **Scope:** L19-22, L45, L69, L175-181, L191-193.
* `fixtures/` vs `fixtures/triage/`; CUJ 1 "fixture in `scripts/triage_check.py`"; runner argument and output format conflict (L175-176 vs L191); G2-G4 test names match no fixture; no fixtures for `agent_cannot_set_floor`, `history_append_only`, unknown enum, old `schema_version`, idempotency, retriage-not-overwrite, base-branch read, label match; `bad_herd_yaml` maps to no CUJ; exact fixture paths and schema undefined; "generic content only" untestable. Add a CUJ-to-fixture table.

### M10. `triage_floor.py` contracts underspecified
* **Lens:** implementation-readiness, codebase-details, style, zoom-out. **Scope:** L165-166.
* No types, return shape, level order, "unknown" definition, history entry validation, or explicit never-lower behavior; `labels` role unspecified. Provide signatures and a rule table (one short pseudocode block). Consider merging the three scripts into one module plus a test (altitude).

### M11. Altitude and over-decomposition
* **Lens:** zoom-out. **Scope:** L88-101, L163-181.
* Field-level schema, function signatures and three scripts plus runner for about 100 lines; move field detail to code and tests.

### M12. Verification and G2 mechanism
* **Lens:** style. **Scope:** L20, L45.
* G2 "rejects fields from agent output" names no mechanism; specify the typed enum plus reason contract and how agent origin is determined.

### M13. Rejection attributed to author; heading hierarchy
* **Lens:** structural, style, design. **Scope:** L121, L127, L133, L147.
* Drop "Rejected by author:" (standard bars attribution without a link) and rename "Reason Rejection". `### Future Improvements` should be `##`. Section names drift from standard ("Problem Statement", "Proposed Architecture"); Open Questions precede CUJs.

### M14. Undefined terms and unstated actors
* **Lens:** comprehension. **Scope:** L11, L15, L19-22, L73, L112, L141.
* Add glossary or links (Arbiter, orchestrator, H1, P3, P6, S2, M0/M1/M3, L0, step 5); say what runs the flow and where the agent runs.

### M15. Floor `medium`/`low` rule self-inconsistent
* **Lens:** comprehension. **Scope:** L75, L48-51.
* Clarify "known" input and whether a labelled issue with no paths counts as known.

## Nits

* Injection CUJ stores a one-line reason (L57) but L82 bars copying issue text and the schema has no reason field; grep check weak. (zoom-out)
* `triage.status` enum `ok | failed | fallback`: `failed` never defined (L22, L92). (design, style, comprehension)
* Rollback "ignore `.herd/state`" drops round counter and budget the PRD assigns to the record (L142, PRD L91). (design, zoom-out)
* No token or latency ceiling for the Triage call (L140); edit-rate threshold open (L37); golden canary parked correctly (L147-150). (design, style, zoom-out)
* Idempotency by body hash belongs in the Technical Plan, not Rollout (L141) and conflicts with manual-only retriage (L81). (zoom-out)
* Non-Goals wording: "Size and path (Full or Lite)" reads as three items; add "(manual `/herd retriage` is in scope)" to L29. (zoom-out, style)
* Wording: use "record writer" not "Code" (L11, L73); trim L15 "The difficulty:"; "loud warning" to "posts a comment" (L80); "agents may push only to `herd/*` branches" (L86); state low<medium<high once (L99, L110); rewrite L140, L143, L149; consistent horizontal rules (L135, L145, L152). (style, structural, comprehension)
* Type/Scope entries mix type and behavior (L160, L167, L174, L185); `herd.yaml` Create vs existing-on-base (L158); committed vs docs-only example rules (L160); "Build: n/a"; linter and `py_compile` stance (L192); em-dash PRD filename must match exactly (L183); drop "Drafted with EGM" footer if template allows (L198). (implementation-readiness, style)
* Hand-rolled glob grammar: reuse one dialect with known semantics (CODEOWNERS or gitignore-style). (inventive-catalyst, zoom-out)
* Possible real wording gaps to confirm in the raw file: L26-29, L57, L80, L149 (see caveat 1).

## Positives

Trust split (agent returns enum, code computes floor, `herd.yaml` from base branch, fail closed), up-only ratchet intent and shadow-mode rollout match PRD P6; dropping size path is good YAGNI. Fences balanced; PRD citation accurate.
