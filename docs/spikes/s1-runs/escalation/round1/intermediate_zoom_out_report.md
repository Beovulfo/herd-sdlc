# Goldfish Review Report: Stage 8 (intermediate zoom-out)

**Target:** `docs/designs/herd-escalation.md` (full file, lines 1-243)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |

Counts: Blocker 0, Major 6, Nit 7. Total 13. Sibling consistency: Triage `herd.yaml` additions compatible (other top-level keys ignored, PyYAML pin shared); Arbiter `escalate` cause names match apart from item M5; PRD "reminder to H1 only" non-goal consistent.

## Prioritized Findings

### M1 G4 contradicts the command table - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 24 vs lines 115-117, CUJ 4 (line 68)
* **Description:** G4 says `/herd resume` is refused while an escalation is open; table (Held and awaiting) and CUJ 4 say it removes the hold and names the issue.
* **Recommendation:** Reword G4: resume never clears an escalation; with hold and open escalation it removes the hold only and the reply names the issue. Then `test_hold_and_escalation_independent` has one meaning.

### M2 `blocked` is a fifth status G1 does not list - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 21, 96, 214
* **Description:** G1 and Overview say four values and pause iff `herd:hold` or open escalation; the plan returns `blocked`, never `running`. No exit from `herd:blocked`; `/herd resume` has no `blocked` column.
* **Recommendation:** Add `blocked` to G1 and the table; state the exit path (e.g. maintainer removes label, ceiling count restarts) or state M0 has none.

### M3 Ceiling off by one - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 28 vs lines 88-92
* **Description:** G8 blocks after 3 issues; CUJ 8 blocks the third trigger after 2 answered. Unclear whether abandoned or reopened issues count.
* **Recommendation:** Pick one rule and say what counts.

### M4 Answers for three of five triggers have no defined effect - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 98-108, 120
* **Description:** Only `rounds`, `budget`, `stop` defined. `low_confidence` "overrule it" (to what?), `step_failure` "retry", `tradeoff` undefined. Arbiter makes `decisions.md` single-writer (`herd_arbiter.py`) and keeps a finding open until a human decides; this design never says how a human decision reaches `decisions.md` or where the raised cap is persisted. The record's `rounds` key belongs to the review loop, yet this design mutates the cap.
* **Recommendation:** One line per trigger per option; name the module writing the decision into `decisions.md` (e.g. an Arbiter-style `audit` line); say where the raised cap lives; or drop `low_confidence` option 2 from M0.

### M5 `malformed` rules conflict - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 105 vs 108; herd-arbiter.md (G5, check 1)
* **Description:** `step_failure` fires on malformed after re-ask; the "other causes" list sends `malformed` to the summary; Arbiter makes it a per-finding `escalate`. A malformed Arbiter round matches both rules.
* **Recommendation:** One rule, e.g. malformed on every finding (Arbiter check 1 fails twice) is `step_failure`, otherwise a summary item.

### M6 Unit of a cause undefined - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 108, 110, 213, 219
* **Description:** Ten `low_confidence` findings could yield ten causes and ten numbers. Repeat key `(feature, trigger, step)` but the escalation shape has no `step`.
* **Recommendation:** One cause per trigger, findings listed inside, one answer applies to all; add `step` to the shape.

### N7 Risk row says repeat "burns touchpoints" is mitigated - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 110, line 182
* **Description:** A repeat counts as a touchpoint again; the "repeat of #N" label does not mitigate it.
* **Recommendation:** Reword as accepted and measured (repeat rate is reported).

### N8 Alternative D stale PRD claim - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 160
* **Description:** PRD line 69 already lists `/herd answer <n>`.
* **Recommendation:** "extends the PRD form to multiple numbers".

### N9 Alternative B cites PRD for one issue per feature - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 148, line 17
* **Description:** Problem section says the PRD does not settle several triggers; PRD only says "One GitHub issue".
* **Recommendation:** Call it this design's reading of the PRD.

### N10 `test_hold_does_not_stop_running_step` not a test - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 226 (and `test_status_table` ordering mention)
* **Description:** "Docstring-level assertion"; the orchestrator owns step execution.
* **Recommendation:** Drop or move to the orchestrator design.

### N11 Below-altitude detail - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 112, 35, 214-221
* **Description:** Quote/fence and edit handling in the Technical Plan (keep as P6 surface); tuple type signatures duplicate the prose.
* **Recommendation:** Drop the signatures.

### N12 Metric machinery beyond PRD need (YAGNI, mild) - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 122-124
* **Description:** `touchpoint_rule`, repeat rate, abandoned count and interval-union `paused_seconds` exceed the PRD metric; baseline not yet run.
* **Recommendation:** Closed-issue count plus total paused time suffices for M0; keep `touchpoint_rule: 1` only if the baseline needs versioning.

### N13 Triage role can answer budget/overrule escalations - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 112, 183
* **Description:** Accepted for labels, but an answer carries more authority; sibling designs silent.
* **Recommendation:** Add one Risks row or define "maintainer" once for all three designs.
