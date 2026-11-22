# Goldfish Review Report (consolidated, round 2)

**Target:** `docs/designs/herd-triage.md` (lines 1-222; FeatureRange 1-173, DetailedRange 174-222)

Input to `egm-resolve`. Stage reports in the same directory: `zoom_out_report.md`, `comprehension_report.md`, `critic_report.md`, `intermediate_zoom_out_report.md`, `implementation_readiness_report.md`.

## Reviewer Status

| Reviewer | Stage | Status |
| --- | --- | --- |
| `egm-zoom-out` | 5 | completed |
| `egm-inventive-catalyst` | 5 | completed (did not Grep raw file; PRD path not found by it) |
| `egm-comprehension` | 6 | completed |
| `egm-design` | 7 | completed |
| `egm-structural` | 7 | completed |
| `egm-style` | 7 | completed |
| `egm-zoom-out` | 8 | completed |
| `egm-implementation-readiness` | 9 | completed |
| `egm-codebase-details` | 9 | completed |
| `egm-style` | 9 | completed |

No reviewer failed. No corruption findings kept; two possible lossy-view findings dropped (Stage 9). Persona files are `agents/<name>.md` with underscore names (e.g. `zoom_out.md`); the `egm-*.md` names do not exist.

## Prioritized Findings (Blockers -> Major -> Nits)

### 1. Tamper check (G5/CUJ 5) trusts attacker-controlled record - Blocker
* **Lenses:** design (Blocker), zoom-out, inventive-catalyst, comprehension (all Major)
* **Scope:** lines 25, 68-72, 100, 102-114
* Record is on agent-pushable `herd/*` branches; recompute uses `risk.override` and `floor_inputs` from the same record. Forged override or emptied paths verify cleanly. `floor` also depends on labels not stored in the record, and today's `herd.yaml` may differ from intake (false alarms).
* **Rationale:** breaks P6 and G5. **Fix:** authenticated override source (comment event/append-only log, record login and comment ID), record on base branch or bot-only ref, re-derive floor from `body_hash` snapshot, pin `herd.yaml` hash/labels, add forged-override and forged-paths fixtures. Alternative: defer G5 to M1 (see finding 9).

### 2. `floor()`, `write_record`, `verify_record` not implementable as specified - Blocker
* **Lens:** implementation-readiness, style, codebase-details
* **Scope:** line 190 (and 119)
* Glob algorithm, normalisation order, precedence, no-match level, label role, "unknown input" vs fail-closed `high`, event/payload shapes, `base_hash`, retry location, exceptions, atomic write, `herd.yaml` loader all undefined. See `implementation_readiness_report.md` R1, R2.

### 3. Path extraction from issue text unowned - Blocker
* **Lens:** implementation-readiness (Blocker), zoom-out/inventive/comprehension/design (Major)
* **Scope:** lines 17, 22, 46-54, 89, 111, 190
* Agent output is limited to `risk` and `reason` (G2); nothing names who extracts `paths` or sets `floor_inputs.source`. Option: agent emits untrusted candidate path list, deterministic code globs it; or deterministic regex in M0. Add evasion fixtures.

### 4. Version pin deferred, no dependency manifest - Blocker
* **Lens:** implementation-readiness, style | **Scope:** line 189
* State exact Python and PyYAML versions and manifest path.

### 5. Writer-only-writes rule unenforced; agent-writable record - Major
* **Lens:** design | **Scope:** lines 87, 100
* Name enforcement (path-restricted token, CODEOWNERS/branch rule, signed commits) or state G5 detection is the only control. Overlaps finding 1.

### 6. Shadow mode contradicts G5/Overview; failure rules inconsistent and duplicated - Major
* **Lens:** design, style, zoom-out, comprehension
* **Scope:** lines 11, 25, 91, 94, 98, 100, 151-152
* Orchestrator "refuses on mismatch" vs Arbiter not reading record in shadow mode. "G1 always holds" (L152) overstated; should read `effective >= floor` except under recorded `risk.override`. Fail-closed stated three times with differing wording; "transient" undefined; race-retry-failure outcome missing; `escalates` for old `schema_version` undefined and conflicts with G4. Consolidate into one table (condition, effective, status, cause). A race failing closed to `high` can defeat a human override; consider `effective = floor` for timeout/malformed/race (inventive I3).

### 7. LLM value unproven and M0 scope heavy - Major
* **Lens:** zoom-out (x2), design
* **Scope:** lines 17, 22-25, 39-40, 91, 98-100, 128-132, 152, 162
* Most features floor at `medium`, so proposal rarely matters; agent, injection surface, allowlist, shadow rollout, race check, 5-value cause enum, schema-version handling are built before value shown. Consider rules-only M0 with same schema, agent later. No success criterion or owner for shadow-mode exit or edit-rate threshold. Note tension with finding 1: either fix G5 mechanism or defer it.

### 8. Rollback not viable - Major
* **Lens:** design, zoom-out (x2), inventive, comprehension | **Scope:** line 153
* Dropping `.herd/state` loses round counter and budget fields the PRD assigns to it; fields absent from sample schema. Put `risk`/`triage` in own file/key, move fields first, or state rollback unsupported in M0.

### 9. `reason` field: schema gap and injection/leak channel - Major
* **Lens:** design, comprehension | **Scope:** lines 22, 60, 96, 102-114
* CUJ 3 stores `reason` (200 chars) but schema has no key; "quoted inert data" undefined; reason can quote issue body and is shown at H1/PR. Specify plain-text rendering, charset and length check, and who reads it.

### 10. Override identity and label authority weak - Major/Nit
* **Lens:** design | **Scope:** lines 23, 31, 66, 89, 163-164
* Store GitHub login and comment ID; who may run `/herd risk`; single-maintainer lowering of a `high` floor; who may apply `risk:*` labels; conflicting labels only implicitly "highest wins"; override persists silently if `herd.yaml` later raises floor.

### 11. Alternatives weak, "Rejected by author" unlinked - Major
* **Lens:** design, structural, style | **Scope:** lines 126-144
* Drop attribution or link a source; A's reason is a learning goal; C's reason is a bare assertion; add an alternative that stores the record outside the agent-writable repo; heading "Reason Rejection" -> "Reason for Rejection".

### 12. Undefined terms and unlinked dependencies - Major
* **Lens:** comprehension | **Scope:** lines 13, 30-31, 37, 152, 164, 168, 190
* "Ratchet", "step 5", "edit-rate metric", "shadow mode", P3, EGM, `base_hash`; "the orchestrator design" cited without filename; edit-rate metric "not in PRD section 3"; record location and committer (L87, L100); `herd.yaml` edit rule (L94) has no M0 enforcement point (no diff at intake).

### 13. Open Questions malformed and duplicated - Major
* **Lens:** style, structural, zoom-out | **Scope:** lines 30, 35-40, 168
* L40 is a fragment, not a question; L37 duplicates L30 and L168 (M1 ratchet). Rewrite as questions or drop.

### 14. Detailed plan: PRD edits state conflict and weak exit check - Major
* **Lens:** codebase-details, implementation-readiness, style, zoom-out | **Scope:** lines 183, 207-210
* Codebase-details found all three PRD edits already applied (PRD lines 77, 136, 69); implementation-readiness found the edit text inexact. Reconcile against the PRD, mark file as modified or drop Phase 4. Exit check `grep -n "size" PRD*.md` matches unrelated lines; scope it to the row.

### 15. Detailed plan: fixtures, phases, `herd.yaml`, verification gaps - Major
* **Lens:** implementation-readiness, codebase-details
* **Scope:** lines 176-218
* Fixture schema cannot express tamper/override/failure fixtures; G4 and path-normalisation fixtures in no phase; test names not fixed (`-k floor`); `herd.yaml` default YAML not written and is a Create; no `conftest`/import rule; no `.herd/state/` wiring phase; E2E step has no procedure and writes `docs/spikes/s2-baseline.md` outside Target Files. See `implementation_readiness_report.md` R6-R10.

### 16. Altitude drop: Python signatures in the design body - Major
* **Lens:** zoom-out | **Scope:** line 190
* Stage 8 zoom-out accepted as interface sketches; Stage 5 flagged altitude. Note tension with finding 2, which wants more detail in the Detailed Plan. Resolve by keeping signatures in the Detailed Plan only.

### 17. Structure and style nits - Nit
* Risks and mitigations is H3 under NFR (L155-164): promote to H2; no scalability row (L148-164). Rule at L146; inconsistent bold labels; list after bold label without blank line (L93-96); trailing whitespace L76.
* Vague or duplicate lines: L11 parenthetical repeats L30; L89 "keeps the agent's proposal from lowering anything"; L131 repeats L17; L169 canary comparison; L216/L214 combine; L218 "shadow-mode run" undefined.
* Coverage and naming: G4's four fixtures collapse to one parametrised test; path-normalisation fixtures fold into one parametrised floor test; `triage.status` (`ok | fallback`) vs `failure_defaults_high` test name; case sensitivity of path matching undecided; `body_hash` unconsumed; no token/latency cap on agent call; base-record-hash race check premature for a single writer; reuse `pathlib.PurePath.full_match` or CODEOWNERS before custom matcher (L38, L89, L160).

## Conflicts for the author (for egm-resolve)

* Finding 1 vs 7: fix G5 mechanism (design Blocker) or defer G5 and race handling to M1 (zoom-out).
* Finding 14: codebase-details says PRD edits already applied; implementation-readiness treats them as pending. Verify against the PRD before resolving.
* Finding 16 vs 2: less code detail in the design body, more in the Detailed Plan.

## Verdict

Not ready. Four Blockers (1-4). Fix 1-4 first, then 5-9 and 14-15.
