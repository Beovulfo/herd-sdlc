# Goldfish Review Report: Stage 9 (implementation-readiness, codebase-details, style)

**Target:** `docs/designs/herd-triage.md` (lines 153-203, DetailedRange). Standard: `implementation-readiness-standard` (readiness, codebase-details).

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-implementation-readiness` | completed (verdict: not ready; zero-decision rule fails) |
| `egm-codebase-details` | completed |
| `egm-style` | completed |

Greenfield repo: no existing Triage code, `scripts/` or `herd.toml` to reuse.

## Prioritized Findings (Blockers -> Major -> Nits)

### R1. No function implements override preservation, unknown-key preservation or `schema_version` rejection - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`
* **Affected Scope:** lines 79, 83, 132, 168-173, 178 (`test_triage_keeps_override`)
* **Discrepancy Description**: `build_record` takes no existing record, so it cannot preserve `override`. No `read_record` exists, so `schema_version` rejection and unknown-key preservation have no home. `write_record` writes the dict it is given, so round counter and budget keys from other designs are clobbered. Nothing says which function treats out-of-range levels as `high` (line 83).
* **Rationale & Recommendation**: Add `existing: dict | None` to `build_record` and a `read_record(path)`; state that `write_record` merges only the `risk` key into existing JSON; name the exception for a bad `schema_version`.

### R2. No invocation contract or entry point - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** lines 73, 100, 168-173
* **Discrepancy Description**: No CLI, argv/stdin contract, exit codes or stdout, and no dispatch for the `triage` and `human_override` events in the diagram. "Python module" does not say whether the orchestrator imports it or runs it. `herd_toml: str` cannot represent a missing file (`None` vs `""`), and which maps to the `herd_toml` fallback cause is unstated.
* **Rationale & Recommendation**: State "import only" with the exact call sequence, or define the CLI; fix the `herd_toml` type.

### R3. "Four public functions" followed by five - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-style`, `egm-implementation-readiness`
* **Affected Scope:** lines 168-173
* **Discrepancy Description**: `extract_paths`, `floor`, `build_record`, `apply_override`, `write_record`. An allowlist or API check built from the text is ambiguous.
* **Rationale & Recommendation**: Say "Five".

### R4. `apply_override` under-specified; conflicts with line 83 - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`
* **Affected Scope:** lines 83, 172, 178
* **Discrepancy Description**: "Rejects" has no mechanism (raise which exception, or unchanged), conflicting with line 83 "treats any value outside the three levels as `high`". Unspecified: `from` (prior `effective` vs `floor`), second override, `to` equal to current, `now` format (ISO 8601 UTC?), mutate vs copy, behaviour on `status: fallback`, and that the maintainer check lives in the caller.
* **Rationale & Recommendation**: Pin one behaviour per question and reconcile with line 83.

### R5. `floor`, `rules`, fallback shape, `cause` and `source` contracts leave decisions to the implementer - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** lines 69, 77, 83, 159, 170-171
* **Discrepancy Description**: Shape of `rules` (whole TOML vs `floor` table) and who applies the default rule set and `path_extensions` default are unstated. Fallback record fields (`floor`, `floor_rules`, `floor_inputs`, `feature`, `issue`) and a `source` enum value for fallback are undefined, as is write failure before fields are known. Failure-to-`cause` mapping, where the unknown-key check lives, non-list `floor.high`, `source` when a rule and a label both match, and checking the `risk:low` applier role are unstated.
* **Rationale & Recommendation**: Give exact shapes and a mapping table.

### R6. Test plan is names only; phase-to-test mapping and layout missing - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** lines 139, 159, 178, 196, 198
* **Discrepancy Description**: Phase 1 runs `TestFloor` but no class or membership is defined; `scripts/test_herd_triage.py` is assigned to no phase. No inputs or expected values (`test_fallback_cases` causes, `test_path_normalisation` outputs). Missing tests: default rule set, `*` not crossing `/`, `**` zero segments, exact-file and case rules (line 139 promises "one test per rule form"), `apply_override` invalid level, `schema_version` rejection, unknown-key preservation, atomic write, non-maintainer `risk:low`, out-of-range level, exception injection method.
* **Rationale & Recommendation**: Name a class per phase, list tests with inputs and assertions.

### R7. `write_record` details missing - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`
* **Affected Scope:** line 173
* **Discrepancy Description**: Temp file naming, `os.replace`, directory creation for `.herd/state/`, JSON formatting (indent, key order, trailing newline) for PR diffs.
* **Rationale & Recommendation**: Specify.

### R8. `herd.toml` "Create" collides with sibling designs - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-implementation-readiness`
* **Affected Scope:** line 180; `herd-arbiter.md` ~206/238; `herd-escalation.md` ~218/257
* **Discrepancy Description**: Escalation: whichever is built first creates, others modify. Arbiter: Modify, create if Triage has not. Triage: plain Create. The allowlist is ambiguous.
* **Rationale & Recommendation**: "Create; Modify if another design already created it"; keep Triage keys to `floor` and `path_extensions`.

### R9. Python 3.13 requirement not enforced - Severity: Nit
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** line 167
* **Discrepancy Description**: `full_match` raises `AttributeError` on 3.12 and the fallback silently turns it into `error`. No assertion or CI pin.
* **Rationale & Recommendation**: Add a version assertion or document the pin.

### R10. Import path and unittest invocation forms - Severity: Nit
* **Reviewer Lens:** `egm-codebase-details`, `egm-style`
* **Affected Scope:** lines 159-160, 165-178, 196
* **Discrepancy Description**: Path vs dotted forms mixed; no `__init__.py` in `scripts/`; test import form (`scripts.herd_triage`) unstated; working directory unstated.
* **Rationale & Recommendation**: Pin dotted form and import form.

### R11. Phase 3 exit check weak - Severity: Nit
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** line 161
* **Discrepancy Description**: Only proves TOML parses; depends on repo-root cwd; no test loads the shipped `herd.toml` through `build_record`; `path_extensions` unchecked.
* **Rationale & Recommendation**: Add the load test and key assertion.

### R12. Extra tests not mapped to CUJs; coverage map duplicated - Severity: Nit
* **Reviewer Lens:** `egm-codebase-details`, `egm-style`
* **Affected Scope:** lines 45-69, 193-199
* **Discrepancy Description**: `test_other_top_level_keys_ignored`, `test_path_normalisation`, `test_triage_keeps_override` have no stated purpose; CUJ-to-test map duplicated.
* **Rationale & Recommendation**: Keep one map.

### R13. Phase 3 term and wording - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 161, 180
* **Discrepancy Description**: "herd.toml example" vs live config "Create, repo root".
* **Rationale & Recommendation**: Use "herd.toml (repo root)".

### R14. Redundant clause line 167 - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 167, 177
* **Discrepancy Description**: "so there is no dependency" repeats "standard library only".
* **Rationale & Recommendation**: Drop.

### R15. Line 178 one long sentence; "generic paths" vague - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** line 178
* **Discrepancy Description**: Two "plus" clauses and a parenthetical.
* **Rationale & Recommendation**: Use a list; say "inline literals, no repo files".

## Counts

Blocker 2 (R1-R2), Major 6 (R3-R8), Nit 7 (R9-R15). Total 15.
