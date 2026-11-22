# Goldfish Review Report: Stage 5 (zoom-out, inventive-catalyst)

**Target:** `docs/designs/herd-triage.md` (lines 1-203, full file)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |
| `egm-inventive-catalyst` | completed |

## Prioritized Findings (Blockers -> Major -> Nits)

No Blockers.

### Z1. No M0 consumer of risk; stated readers and Alternative C rationale wrong - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`, `egm-inventive-catalyst`
* **Affected Scope:** lines 11, 27, 119-123, 138
* **Discrepancy Description**: Line 11 says the orchestrator and Arbiter read the record; neither the Arbiter nor Escalation design reads risk. Only M0 consumer is display at H1. Alternative C's "Arbiter must parse a PR body" does not apply.
* **Rationale & Recommendation**: State M0 is display-only; fix line 11; rewrite Alternative C around the override's structured home and later L2 use.

### Z2. `risk:low` label is a second, unrecorded lowering path - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`, `egm-inventive-catalyst`
* **Affected Scope:** lines 21, 55-57, 77, 83, 143
* **Discrepancy Description**: PRD section 5: only a maintainer's `/herd risk` lowers risk below the rule floor. The label sets `floor: low` with no override record; G1 holds only because the floor was redefined.
* **Rationale & Recommendation**: Drop `risk:low`; keep raise-only `risk:high`/`risk:medium`; lowering only via recorded `/herd risk low`. Removes role-map plumbing, `test_low_label`, and the "non-maintainer label" risk row.

### Z3. `build_record` / `write_record` cannot do what the text promises - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 79, 83, 100, 170-173
* **Discrepancy Description**: No prior record parameter, yet an existing override is never changed; writer writes a fresh dict, wiping round counter and `budget_used`; `triage` and `human_override` events undefined.
* **Rationale & Recommendation**: Read-modify-write touching only `risk`; pass prior record; drop "events" wording.

### Z4. `/herd risk` and "maintainer" not integrated with sibling designs - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`, `egm-inventive-catalyst`
* **Affected Scope:** lines 63, 73, 83, 143
* **Discrepancy Description**: Escalation defines maintainer (permission `write`+) and owns command parsing; its `parse_command` knows only hold, resume, answer. Triage leaves "maintainer" undefined, specifies no parsing, and no behaviour in `blocked`/`held`/`awaiting_answer`. Two parsers with different injection rules.
* **Rationale & Recommendation**: Adopt Escalation's definition; extend the single `parse_command` with `risk <level>`; add a status-table row; close Escalation's open question.

### Z5. Stored `effective` and override share the forgeable record's trust root - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** lines 11, 27, 83, 119-123, 138
* **Discrepancy Description**: Escalation rejected a `paused` field in the agent-pushable record as a P6 break; Triage accepts the same flaw for risk.
* **Rationale & Recommendation**: Derive `effective` at read time (floor on issue snapshot plus base-branch `herd.toml`, override replayed from GitHub comment events via Escalation `replay()`), pin `herd.toml` hash; or state explicitly that display-only M0 makes this acceptable.

### Z6. Alternative A reasoning circular; deterministic raise-only ratchet at step 3 missing - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** lines 17, 28, 110, 142
* **Discrepancy Description**: "Most floors are `medium`, so a proposal can raise nothing" is wrong (a proposal could raise `medium` to `high`). Third option skipped: run the same `floor()` over `concepts_brief.md` and criteria and take the max; raise-only is injection-safe.
* **Rationale & Recommendation**: Consider a deterministic brief-stage ratchet with `floor_inputs.source: brief`, or correct the argument.

### Z7. Top-level `status`/`cause` collide with Escalation `status` vocabulary; `schema_version` ownership unstated - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 83, 86-93
* **Discrepancy Description**: Escalation derives status and never stores it.
* **Rationale & Recommendation**: Rename to `risk.status`/`risk.outcome`; state schema owner.

### Z8. "Four public functions" followed by five bullets - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 168
* **Discrepancy Description**: Count mismatch.
* **Rationale & Recommendation**: Fix.

### Z9. Phase-1 exit check names `TestFloor`; path vs dotted forms - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 21, 159, 178
* **Discrepancy Description**: No classes listed; mixed command forms.
* **Rationale & Recommendation**: Make consistent.

### Z10. Regex/normalisation detail below design altitude; trailing punctuation edge - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 75
* **Discrepancy Description**: `foo.py.` defeats the extension rule; URLs yield path-like tokens.
* **Rationale & Recommendation**: Move to `test_path_normalisation`; trim prose.

### Z11. Strictness inconsistent: unknown key in `floor` falls back - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 67, 83
* **Discrepancy Description**: Elsewhere unknown keys are ignored.
* **Rationale & Recommendation**: One-line fail-closed rationale.

### Z12. Root-anchored globs miss nested layouts; Python 3.13 pin cross-design - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`, `egm-inventive-catalyst`
* **Affected Scope:** lines 77, 139, 167
* **Discrepancy Description**: `auth/**` misses `src/auth/x.py`; `full_match` needs 3.13 for all designs.
* **Rationale & Recommendation**: Use `**/auth/**` or add a test; record pin once.

### Z13. Missing `herd.toml` (fallback) vs missing `floor` block (defaults) ambiguous - Severity: Nit
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** lines 67, 77
* **Discrepancy Description**: Disjoint paths; PRD cites defaults as mitigation.
* **Rationale & Recommendation**: Pick one for a missing file.

### Z14. Fallback is sticky - Severity: Nit
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** line 81
* **Discrepancy Description**: Transient `error` gives `high` until a human overrides.
* **Rationale & Recommendation**: Optionally recompute a `cause: error` fallback once on the next `triage`.

## Counts

Blocker 0, Major 6 (Z1-Z6), Nit 8 (Z7-Z14). Total 14.

## Passes

No LLM or network call; no speculative abstractions; Alternatives A and B sound; rollout and fallback sound; consistent with siblings on zero-touchpoint fallback, `herd.toml` created by whichever design is built first, other top-level keys ignored, `step_failure` covering invalid record.
