# Stage 8 Report: intermediate zoom-out

**Target:** `docs/designs/herd-triage.md` (lines 1-222)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed (verdict: PASS with Majors and Nits; raw Grep confirmed no corruption; repo has no .py or .yaml files, so no reuse candidates) |

## Major

### ZM1 M0 scope creep - Major
* **Scope:** lines 22-25, 91, 98-100, 152, 162
* M0 is "floor plus display value" (L30) and the Arbiter does not read the record at M0 (L152), yet the design builds tamper detection (G5, CUJ 5, recompute-on-read), base-record-hash race check with retry, a 5-value `triage.cause` enum, `schema_version` escalation and unknown-key preservation. Cheaper: drop G5, race and schema-version handling in M0 since the orchestrator can recompute the floor itself; re-add at M1 when the Arbiter consumes the record. YAGNI unless author justifies. (Tension: Stage 7 design reviewer treats G5 as a Blocker needing a sound mechanism; resolution is for the author: either fix the mechanism or defer G5 explicitly.)

### ZM2 Duplicated fail-closed trust model - Major
* **Scope:** lines 87, 94, 98, 100
* Fail-closed rules stated three times with differing wording (L98 retry once on timeout vs "writer fails closed once" on schema failure; L100 unknown enum fails closed to `high` vs "older schema_version escalates"). Consolidate into one table (condition, effective, status, cause).

### ZM3 Rollback hidden coupling - Major
* **Scope:** line 153
* Rollback drops round counter and budget fields the PRD assigns to this record. Decide now where those fields live or state rollback is unsupported in M0.

## Minor

* **ZN1** Lines 189-190: `floor()`, `effective()`, `write_record()`, `verify_record(record, rules) -> None` signatures and "Pin Python/PyYAML" are code-level; acceptable as sketches, do not expand.
* **ZN2** Line 160: path normalisation "one fixture per form" is detail; fold into one parametrised floor test.
* **ZN3** Lines 169, 37-40: Future Improvements and four Open Questions overlap Non-Goals (M1 ratchet at L30, L37, L168). Keep each once.
* **ZN4** Line 83: G4 maps to four fixtures for the same fail-closed path; collapse to one parametrised test.

## Nit

* **ZT1** Line 189: PyYAML dependency justified (stdlib cannot parse YAML). No action.
* **ZT2** Lines 106 vs 98 and 24: `triage.status` is `ok | fallback`; `failure_defaults_high` is a test name, not a status. Align naming for clarity.

Positives: Alternatives A-C sound; rejecting B (agent writes risk) addresses root problem; writer split from agent is a minimal clean boundary; CUJ-to-fixture table gives testable exit checks.
