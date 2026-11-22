# Goldfish Review Report: Stage 8 (intermediate zoom-out)

**Target:** `docs/designs/herd-triage.md` (lines 1-203, full file)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |

Context sufficient. Greenfield repo: no `scripts/`, `herd.toml`, `.herd/` or `rubrics/` to reuse. Stdlib-only choice judged correct. The one wording finding (I-N1) was verified with Grep on the raw file.

## Prioritized Findings (Blockers -> Major -> Nits)

No Blockers.

### I1. "Events" language does not match the `build_record` API; re-run would wipe other keys - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 79, 83, 100, 132, 168-173, 178
* **Discrepancy Description**: `triage` and `human_override` events are undefined; the API is `build_record()` and `apply_override()`. `build_record(feature, issue, body, labels, herd_toml)` takes no prior record, so it cannot honour "a later `triage` event never changes an existing override" (`test_triage_keeps_override`) and a re-run would overwrite round counter and budget keys that share the file.
* **Rationale & Recommendation**: Drop event language; `build_record` takes an optional existing record, replaces only `risk.floor*` and `status`, keeps `risk.override` and other keys. Or state plainly that Triage runs once per feature and re-labelling is a no-op.

### I2. `/herd risk <level>` has no owner; "maintainer" undefined - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 35, 63, 83; `herd-escalation.md` lines 45, 116-122
* **Discrepancy Description**: Escalation's closed `parse_command` and table list only hold, resume, answer. Triage assumes the orchestrator handles `/herd risk`; maintainer check and idempotency by comment id are assigned to nothing. Escalation defines maintainer; both designs leave it as an open question.
* **Rationale & Recommendation**: Add `risk` to Escalation's `parse_command`/`apply_command`, or state that the orchestrator design owns it; cite Escalation's maintainer definition.

### I3. M0 decision gate has no measurement - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 17, 28, 37, 110-111
* **Discrepancy Description**: Alternative A is rejected on "M0 first measures how often rules land on `medium`", but no report or counter is named; Open Question 37 asks about an edit rate that line 28 puts in M1.
* **Rationale & Recommendation**: Define the measurement as a count of `floor_inputs.source == "default"` and of overrides across records; name the owner; move the edit-rate question to M1.

### I-N1. "Four public functions" followed by five bullets - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 168
* **Discrepancy Description**: `write_record` makes five. Verified intact via Grep.
* **Rationale & Recommendation**: Fix the count.

### I-N2. Test commands inconsistent; `TestFloor` class unassigned - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 21, 159-160, 178, 196
* **Discrepancy Description**: Path form vs dotted module (Arbiter and Escalation use dotted only); test list assigns no classes.
* **Rationale & Recommendation**: Use dotted everywhere; say which tests live in `TestFloor`.

### I-N3. `path_extensions` config is speculative - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 75
* **Discrepancy Description**: Tuning knob nobody asked for; adds a top-level key and a test input.
* **Rationale & Recommendation**: Hardcode; add a key when a repo needs one.

### I-N4. Code-level detail in a design - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 75-77, 168-170
* **Discrepancy Description**: Step-by-step normalisation, regex token rules and signatures.
* **Rationale & Recommendation**: Keep behaviour in the design; move steps to `test_path_normalisation`.

### I-N5. Fallback record shape unspecified; missing file vs missing block unexplained - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 69, 77, 83
* **Discrepancy Description**: What `floor` and `floor_rules` hold when `status` is `fallback` (e.g. `floor: null`); why missing file falls back while a missing `floor` block gets defaults.
* **Rationale & Recommendation**: Specify; give a one-line reason.

### I-N6. `override.from` ambiguous on a second override - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 63
* **Discrepancy Description**: Floor or previous effective value?
* **Rationale & Recommendation**: Define it; accept one overwritten override as stated non-goal.

### I-N7. `source` when paths named but none match - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 77, 93
* **Discrepancy Description**: `issue_text` or `default` unstated; feeds the M0 measurement.
* **Rationale & Recommendation**: Pick one.

### I-N8. Python 3.13 pin is a cross-design hard dependency - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 77, 167
* **Discrepancy Description**: `PurePosixPath.full_match` pins 3.13 for Arbiter and Escalation too.
* **Rationale & Recommendation**: State once in shared constraints; confirm the runner.

## Counts

Blocker 0, Major 3 (I1-I3), Nit 8 (I-N1 to I-N8). Total 11.
