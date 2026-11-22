# Goldfish Review Report: Stage 6 (comprehension)

**Target:** `docs/designs/herd-triage.md` (FeatureRange 1-152, DetailedRange 153-203). No GoldfishContext.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-comprehension` | completed |

## FeatureRange (lines 1..152)

**What this proposes**
- Triage is a deterministic step with no LLM. When a maintainer labels an issue `herd`, it computes a risk floor (`low`, `medium` or `high`) from glob rules in `herd.toml`.
- It extracts path-like tokens from the issue body and matches them against `floor.high` and `floor.medium`. `risk:*` labels can adjust the result.
- If no path is named, the floor is `medium`.
- It writes the result to `.herd/state/<feature>.json`.
- A human can override only with the comment `/herd risk <level>`, and the override is recorded.
- Any failure gives `effective: high` and `status: fallback`.
- In M0 the value is display-only at H1. Tamper protection, an LLM proposal and ratchets are deferred to M1.

**How the existing system works, per this document**
- Herd has a lifecycle whose step 1 is Triage. There is an orchestrator, an Arbiter, and "H1 Intent gate" PRs. All are defined only in the PRD, so they cannot be paraphrased from this document.
- Today a person sets risk by hand.
- The orchestrator owns the label-triggered workflow, the issue snapshot, comment posting and creation of the `herd/<feature>` branch. It passes inputs to the writer.
- The state record sits on an agent-pushable branch, so agents can edit it. That is the accepted M0 gap.

## DetailedRange (lines 153..203)

**What this proposes**
- Build in three phases: (1) `extract_paths` and `floor`; (2) `build_record`, `apply_override` and an atomic write; (3) a sample `herd.toml`.
- Create `scripts/herd_triage.py` (Python 3.13+, stdlib only, `tomllib` for config, JSON for the record).
- Create `scripts/test_herd_triage.py` with named `unittest` tests covering every CUJ, path normalisation, ignored top-level keys and override persistence.
- Create the root `herd.toml` with the default rules.
- Verification is unit tests only. The end-to-end flow belongs to the orchestrator design.

**How the existing system works, per this document**
- No Triage code or `herd.toml` exists yet (all three files marked Create).
- Existing repo tooling for build and lint is stated as none.
- Orchestrator wiring is out of scope and not described.

## Prioritized Findings (Blockers -> Major -> Nits)

No Blockers.

### C1. Terms defer to the PRD; P6, H1, Arbiter, orchestrator, P3 never glossed - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 13, 17, 27, 83, 117, 129, 131
* **Discrepancy Description**: Line 13 says "all in the PRD" with section numbers only. P6 is the central security rationale and is never stated. H1, Arbiter, autonomy levels and P3 (used at line 131, absent from Terms) are undefined.
* **Rationale & Recommendation**: Add one-line inline glosses or a PRD link.

### C2. Inconsistent certainty about "most issues name no path" - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 17, 75, 110
* **Discrepancy Description**: Line 17 "Hypothesis, not yet measured"; line 75 "is known to be high"; line 110 "Most floors are `medium`" as fact.
* **Rationale & Recommendation**: Pick one stance; reword 75 and 110 as expected.

### C3. Events `triage` and `human_override` undefined; where the existing record enters is unclear - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 73, 79, 100
* **Discrepancy Description**: Emitter and mapping to functions are not stated. Line 79 says a later `triage` event never changes an override, but inputs (line 73) exclude the existing record.
* **Rationale & Recommendation**: Define the events and the entry point of the existing record.

### C4. `source` semantics ambiguous - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 51, 77, 93
* **Discrepancy Description**: Paths named but matching no rule, a `medium` rule match, or a label also applying: `source` could be `issue_text` or `default`. CUJ 2 covers only "names no path".
* **Rationale & Recommendation**: Add a precedence table for `source`.

### C5. Missing file vs missing `floor` block vs unknown key distinctions unstated - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 67, 77, 83
* **Discrepancy Description**: Defaults apply without a `floor` block, a missing file falls back to `high`, an unknown key in `floor` falls back; "readers ignore unknown keys" concerns the record, not config.
* **Rationale & Recommendation**: State the distinctions explicitly.

### C6. Who verifies the commenter's maintainer role - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** line 83
* **Discrepancy Description**: "Issued by a maintainer" names no verifier (presumably the orchestrator).
* **Rationale & Recommendation**: Say so.

### C7. Project terms unglossed (ratchet, shadow mode, golden-set canary, Lite/Full path) - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 28, 147
* **Discrepancy Description**: No gloss or "see PRD" pointer.
* **Rationale & Recommendation**: Add short gloss.

### C8. `<feature>` and "base branch" undefined - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 11, 30, 73
* **Discrepancy Description**: Identifier derivation unclear; feature branch is created later, so "base branch" is unclear.
* **Rationale & Recommendation**: Define both.

### C9. "The writer" used for the whole path; "raises" vs "catches everything" - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 69, 81
* **Discrepancy Description**: Line 69 "the writer raises", line 81 says it catches everything.
* **Rationale & Recommendation**: Name the function.

### C10. Trailing punctuation not covered by token rules - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** line 75
* **Discrepancy Description**: `foo.py.` case unspecified.
* **Rationale & Recommendation**: Specify the behaviour.

### C11. "Four public functions" but five listed - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 168-173
* **Discrepancy Description**: `extract_paths`, `floor`, `build_record`, `apply_override`, `write_record` are five.
* **Rationale & Recommendation**: Fix the count.

### C12. `build_record` cannot preserve an override yet a test requires it - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 170, 178
* **Discrepancy Description**: `build_record` takes no existing record; `test_triage_keeps_override` requires preservation.
* **Rationale & Recommendation**: Add an `existing` parameter or say the caller merges.

### C13. Phase 1 exit check names `TestFloor`; tests listed without classes - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 159, 178
* **Discrepancy Description**: Class not defined.
* **Rationale & Recommendation**: Name classes or drop the class.

### C14. Test command in two forms (path and dotted module) - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 21, 160, 196
* **Discrepancy Description**: Inconsistent invocation.
* **Rationale & Recommendation**: Pick one.

### C15. `herd.toml` "Create" but other designs may also create it - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 67, 180
* **Discrepancy Description**: Creation ownership unstated.
* **Rationale & Recommendation**: Name the owner.

### C16. `test_fallback_cases` "exception in matching": injection method unstated - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** line 178
* **Discrepancy Description**: No stated way to inject an exception.
* **Rationale & Recommendation**: Specify (e.g. a patched matcher).

## Counts

Blocker 0, Major 6 (C1-C4, C11, C12), Nit 10 (C5-C10, C13-C16). Total 16.
