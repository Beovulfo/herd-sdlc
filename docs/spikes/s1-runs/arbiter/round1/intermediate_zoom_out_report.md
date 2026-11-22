# Goldfish Review Report: Stage 8 (intermediate zoom-out)

**Target:** `docs/designs/herd-arbiter.md` (full file, lines 1-251)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |

## Prioritized Findings

No Blockers. 3 Major, 6 Nit. Positives to keep: severity excluded from schema and copied by code (G2); policy checks in code; one call per round; stdlib-only Python; small file footprint; fail-closed on missing fresh context.

### ZO-M1 `defer` verdict is the weakest part of the design - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 41, 102, 107, 129, 184, 145-149
* **Description:** `defer` has no EGM equivalent, forks the `egm-resolve` vocabulary Alternative A says not to fork, and drives extra rules (Blocker/Major rewrite, "counts as open", defer-rate metric, unresolved destination question). PRD section 5 (line 89) does mention defer, so it is not speculative, but the design has no post-merge destination for it.
* **Recommendation:** Map `defer` onto an existing EGM category (ESCALATE for Blocker/Major, backlog note only for Nit) or cut it from M0 until a backlog destination exists.

### ZO-M2 M0 mechanisms exceed the stated hypothesis (re-ask, flip, sampling) - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 17, 42, 92, 108, 109, 125, 127, 186
* **Description:** Citation re-ask adds a second LLM call against "one call per round". `flip` needs persisted prior rulings and same-citation comparison, but ids change on rephrase (line 186), so it may rarely fire. Sampling by id mod 4 has little value at n of about 50 when the human reads the whole summary.
* **Recommendation:** Escalate on first citation failure; confirm id stability before building `flip` or mark it unvalidated; audit everything in M0 and add sampling in M1.

### ZO-M3 Rollout trigger uses overturn rate alone - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 42, 127, 175, 184; PRD line 39
* **Description:** Overturn excludes escalations, so the Arbiter can lower it by escalating more. Risks (line 184) and extra rates mitigate partly, but the 10 percent trigger has no escalation-rate guard.
* **Recommendation:** State a joint stop/continue rule or say the pilot owner judges the three rates together.

### ZO-N1 Altitude: function signatures and formulas in plan - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 204-205, 210-220
* **Recommendation:** Trim to module responsibilities; the modulo formula is already at line 127.

### ZO-N2 Over-specified placeholder log format - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 117-125
* **Recommendation:** Reduce to needed fields, or use JSONL and drop escaping rules and `test_reason_escaped`.

### ZO-N3 Dedup owner and rule unnamed; persona in id hash - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 35, 92
* **Description:** Same issue from two personas gets two ids; who deduplicates and how is unstated.
* **Recommendation:** Name the owner and rule or point to where defined.

### ZO-N4 Open Questions duplicate PRD or Future Improvements - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 36, 41, 42, 193
* **Recommendation:** Keep each item in one place.

### ZO-N5 Alternatives lack evidence links - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 149, 155, 161, 167
* **Recommendation:** Add the S1 spike path (`docs/spikes/s1-egm-unattended.md` per PRD) to A; give evidence for B-D.

### ZO-N6 `arbiter.enabled` / `arbiter.model` config surface - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 115, 175, 236, 240
* **Recommendation:** If `enabled` is a rollback switch, state it falls back to batched human triage; otherwise drop it.
