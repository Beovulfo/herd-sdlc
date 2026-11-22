# Goldfish Review Report: Stage 7 (design, structural, style)

**Target:** `docs/designs/herd-triage.md` (lines 1-152, FeatureRange). Standard: `feature-spec-standard` (design, structural). One round.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-design` | completed |
| `egm-structural` | completed |
| `egm-style` | completed |

## Prioritized Findings (Blockers -> Major -> Nits)

No Blockers.

### K1. "Display-only" claim conflicts with line 11 and is unsupported; tamper gap stated four times - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-style`
* **Affected Scope:** lines 11, 27, 36, 129, 138
* **Discrepancy Description**: Line 11 says the orchestrator and Arbiter read the record; the Arbiter design has no risk use. If any reader gates on `effective`, it is not display-only. "A forged value is visible to that human" is unevidenced: the H1 PR renders from the same agent-writable record, so forged and computed values look alike. The gap is restated at 27, 36, 129, 138.
* **Rationale & Recommendation**: Fix line 11 or the Arbiter side; state that no M0 consumer gates on risk; have the orchestrator post the computed floor and effective value as an issue comment (outside the branch) for comparison; state the gap once and point back to it.

### K2. `human_override` input contract and write concurrency unspecified - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 21-27, 73, 81, 83, 132
* **Discrepancy Description**: Inputs list no actor, comment id, time, or who verified maintainer role (the writer makes no network call, so the orchestrator must, and the spec never says it does). Atomic rename prevents partial files but not lost updates between other designs' read-modify-write writers; race handling is deferred to M1 only for the LLM case.
* **Rationale & Recommendation**: Specify the override input shape and where the maintainer check happens; name a single-writer assumption or add an ordering rule.

### K3. Alternatives rejected by attribution ("Rejected by author") - Severity: Major
* **Reviewer Lens:** `egm-structural`, `egm-design`, `egm-style`
* **Affected Scope:** lines 111, 117, 123
* **Discrepancy Description**: The standard bars attributing a rejection to a maintainer without a linked issue/discussion/PR. B's reason is only "it breaks P6". C's reason ("the Arbiter reads the state record by design") conflicts with the Arbiter design.
* **Rationale & Recommendation**: Drop the prefix; state trade-offs directly (B: issue text would control its own lower bound; C: a PR body cannot carry a structured override).

### K4. Central design choice and obvious alternatives not weighed - Severity: Major
* **Reviewer Lens:** `egm-structural`, `egm-design`
* **Affected Scope:** lines 16, 35, 105-123
* **Discrepancy Description**: No alternative covers the deterministic path-based floor defaulting to `medium`, nor the manual baseline. Missing: CODEOWNERS-seeded floor, fail-closed default `high`, a structured issue form with a required "affected paths" field.
* **Rationale & Recommendation**: Add and reject at least one with concrete trade-offs.

### K5. Root-anchored default globs and extractor gaps - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 75, 77, 139
* **Discrepancy Description**: `auth/**` misses `src/auth/login.py`; `migrations/**` misses `db/migrations/x.sql`, silently yielding `medium`. URLs tokenise to prefixed paths; `.yml/.yaml` absent from default extensions; extension-less files (Dockerfile, Makefile) missed. "Fixed matcher semantics" does not mitigate this.
* **Rationale & Recommendation**: Ship `**/auth/**` forms or document anchoring with a test; widen extensions.

### K6. Missing `herd.toml` (fallback) vs default rule set unreachable - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 67, 77, 131
* **Discrepancy Description**: CUJ 5 and G3 make a missing file fall back to `high`, but defaults apply "when no `floor` block". A freshly adopting repo is always `fallback/high`, affecting rollout.
* **Rationale & Recommendation**: Decide and state which behaviour applies to a missing file.

### K7. M0 measurement of the hypothesis has no goal, metric or threshold - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 17, 28, 37, 111, 142
* **Discrepancy Description**: Text says M0 "tests" and "measures" the hypothesis, but no data source, metric (e.g. share of `source: default`) or trigger for M1 is defined. Open question 3 cites an edit-rate metric that line 28 places in M1.
* **Rationale & Recommendation**: Add the goal, metric and decision threshold.

### K8. Inconsistent certainty on "most floors are `medium`" - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 17, 75, 110, 142
* **Discrepancy Description**: Line 17 hypothesis; 75 "known to be high"; 110 and 142 as fact. Line 110 is also logically odd: a proposal could raise `medium` to `high`.
* **Rationale & Recommendation**: Reword as expected/hypothesis everywhere.

### K9. `risk:low` label: no audit trail, ordering and `source` unclear - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 57, 77
* **Discrepancy Description**: Lowers the floor with no applier recorded; a label applied after the `herd` label does nothing (no retriage in M0); `source` undefined when a path is named but matches no rule.
* **Rationale & Recommendation**: Document ordering and define `source`.

### K10. `schema_version` newer than known unspecified - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** line 83
* **Discrepancy Description**: "Missing or older" rejected, newer not specified; at version 1 nothing is older.
* **Rationale & Recommendation**: State reader behaviour on a higher version.

### K11. Override on a `status: fallback` record - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** line 83
* **Discrepancy Description**: Whether `status` stays `fallback` is unspecified.
* **Rationale & Recommendation**: State it.

### K12. Minimum Python version and CI - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** line 77
* **Discrepancy Description**: `full_match` needs 3.13, `tomllib` 3.11; an older runner fails into the `error` fallback.
* **Rationale & Recommendation**: State minimum and confirm CI supplies it.

### K13. Unbounded issue body and `floor_inputs.paths` - Severity: Nit
* **Reviewer Lens:** `egm-design`, `egm-structural` (limits)
* **Affected Scope:** lines 75, 134-143
* **Discrepancy Description**: Regex runs over untrusted unbounded text; no scalability limits in Risks.
* **Rationale & Recommendation**: Cap body length, token count, and add a "Limits" note.

### K14. Rollback and absent `risk` key - Severity: Nit
* **Reviewer Lens:** `egm-design`, `egm-style`
* **Affected Scope:** lines 83, 132
* **Discrepancy Description**: Rollback deletes `risk` but readers reject an absent key with an escalation; "delete fields under `risk`" is ambiguous and wordy.
* **Rationale & Recommendation**: Align; say "Delete the `risk` key; other keys untouched".

### K15. Override may raise risk; argument parsing strictness unstated - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 63, 83
* **Discrepancy Description**: Raising via override not stated as permitted; `/herd risk` arg not stated as strictly parsed.
* **Rationale & Recommendation**: State both.

### K16. G1 check omits the override exception test - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 21, 63
* **Discrepancy Description**: Check lists four tests but not the "unless" clause (`test_override_recorded` at 63).
* **Rationale & Recommendation**: Name it or drop the clause.

### K17. Events `triage` / `human_override` undefined in diagram - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** lines 79-83, 100
* **Discrepancy Description**: Used without definition.
* **Rationale & Recommendation**: Add a short Events list.

### K18. Open Questions placed before the design - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** lines 33-39
* **Discrepancy Description**: Sits between Non-Goals and CUJs.
* **Rationale & Recommendation**: Move after Risks or before Future Improvements.

### K19. Horizontal rules and heading name inconsistent - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** lines 7, 71, 125, 151
* **Discrepancy Description**: `---` used at some H2 boundaries only; "Technical Plan (Architecture)" vs the standard's "Proposed Architecture".
* **Rationale & Recommendation**: Use rules consistently; consider the standard's name.

### K20. Circular wording line 75 ("Case is significant, because rules are case-sensitive") - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** line 75
* **Discrepancy Description**: Circular.
* **Rationale & Recommendation**: "Matching is case-sensitive; the extractor keeps case."

### K21. Line 77 overloaded; line 83 sentence misplaced - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 77, 83
* **Discrepancy Description**: Glob semantics, label rules, defaults and the `herd.toml` edit rule in one block ("edit counts as touching a `high` path" redundant with defaults). "Any value outside the three levels is `high`" belongs under Failure, not Authority.
* **Rationale & Recommendation**: Split into bullets; move the sentence.

### K22. `cause` mapping unclear (lines 67, 69) - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 67, 69
* **Discrepancy Description**: Given mixes `herd_toml` triggers with the writer exception, which maps to `error`.
* **Rationale & Recommendation**: "missing, invalid or unknown-key gives `herd_toml`; writer exception gives `error`".

### K23. Line 11 parenthetical; line 57 precedence test; line 131 P3 clause - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 11, 57, 131
* **Discrepancy Description**: Long parenthetical on level order; "matching rule still wins over the label" lacks its own named test; "without blocking (P3)" gives no reader decision.
* **Rationale & Recommendation**: Own sentence; name a test; state the maintainer action or drop.

## Counts

Blocker 0, Major 8 (K1-K8), Nit 15 (K9-K23). Total 23.
