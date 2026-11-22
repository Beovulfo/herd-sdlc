# Goldfish Review Report: Stage 5 (zoom-out + inventive-catalyst)

**Target:** `docs/designs/herd-escalation.md` (full file, lines 1-243)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |
| `egm-inventive-catalyst` | completed |

Counts: Blocker 0, Major 13 (zoom-out 7, inventive-catalyst 6), Nit 8 (zoom-out 7, inventive-catalyst 1). Total 21 (not deduplicated across reviewers; overlaps noted).

## Prioritized Findings

### Z-M1 Ceiling off-by-one (G8 vs CUJ 8) - Severity: Major
* **Reviewer Lens:** `egm-zoom-out` (also IC-M6)
* **Affected Scope:** lines 28, 88-92, 219
* **Description:** G8 says no further issue after 3 escalation issues. CUJ 8 says with 2 answered escalations the third trigger opens no issue, so the real ceiling is 2.
* **Recommendation:** Pick one number; fix `test_ceiling`.

### Z-M2 Status values mismatch - Severity: Major
* **Reviewer Lens:** `egm-zoom-out` (also IC-M6)
* **Affected Scope:** G1 line 21, line 96 vs line 214
* **Description:** G1 and Technical Plan list four `herd_status` values; the implementation plan returns five, adding `blocked`. G1 "paused iff hold label or open escalation" omits `herd:blocked`.
* **Recommendation:** Add `blocked` to G1 and the status table.

### Z-M3 `herd:blocked` has no exit - Severity: Major
* **Reviewer Lens:** `egm-zoom-out` (also IC-M6)
* **Affected Scope:** lines 28, 92, 114-120
* **Description:** `stop` and the ceiling set `herd:blocked`; `/herd resume` covers only the hold label. No defined way out.
* **Recommendation:** Define the exit (e.g. maintainer removes label) or state it is terminal in M0.

### Z-M4 Raised limits have nowhere to live - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 120, 126
* **Description:** `rounds` answer adds a round, `budget` answer raises limits by `raise_by`; the state record holds only `budget_used` and the round counter, and `herd.yaml` is static from base branch. Raised cap storage is unspecified; triggers could re-fire forever.
* **Recommendation:** State where it is stored or derived (e.g. count answered escalations from GitHub).

### Z-M5 "Cause" undefined - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** G5, CUJ 2-3; lines 25, 54-62, 100-108
* **Description:** Unclear whether a cause is one per trigger or per finding; G5 needs one number per cause. `low_confidence` option "2 overrule it" does not say overrule to what; Arbiter verdicts are accept/contest/decline/escalate.
* **Recommendation:** Define cause granularity and the overrule outcome.

### Z-M6 Arbiter `malformed` handling inconsistent - Severity: Major
* **Reviewer Lens:** `egm-zoom-out` (also IC-M5)
* **Affected Scope:** lines 105, 108 vs herd-arbiter.md lines 21, 25, 95, 101
* **Description:** Arbiter design makes `malformed` a per-finding `escalate`; this design makes it a `step_failure` issue and omits it from the summary list.
* **Recommendation:** State the override explicitly and update the Arbiter design, or adopt the per-finding behaviour with the all-malformed exception.

### Z-M7 YAGNI: `tradeoff` trigger has no producer - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 106, line 42, line 191
* **Description:** No M0 component raises it.
* **Recommendation:** Cut from the M0 table; keep the Future Improvement.

### IC-M1 No durable escalation history for metrics - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** Technical Plan "Touchpoints"; Future Improvements (`decisions.md`)
* **Description:** Touchpoint count and paused time (headline M0 metrics) are computed only from live GitHub data; deleted comments or issues silently change them. `touchpoint_rule: 1` versions the rule, not the input.
* **Recommendation:** Append one JSONL line to `decisions.md` at answer time (ledger for metrics only; pause stays derived). Liability: second source of truth, M1 tamper gap applies.

### IC-M2 Low-confidence Nit escalations consume touchpoints - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** Triggers table, `low_confidence` row; herd-arbiter.md
* **Description:** A low-confidence `Nit` opens an issue and blocks the loop, threatening the median <=2 touchpoints target; other Arbiter causes go to the summary.
* **Recommendation:** Route `Nit` low_confidence to the PR summary with a no-change default, or batch per round into one cause; state in both designs.

### IC-M3 One issue conflated with one atomic positional answer - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** Technical Plan "Escalation issue", `/herd answer`; G2, G5
* **Description:** Appending a cause after the maintainer read options changes the required answer length; one typo invalidates all.
* **Recommendation:** Stable cause ids (`/herd answer rounds=1 budget=2`), close when all answered, reject unknown causes.

### IC-M4 Unbounded silent wait - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** Non-Goals "Reminders"; `paused_seconds`; NFR Cost
* **Description:** Waiting uses no run and paused time is excluded from budget, with no numeric reminder trigger.
* **Recommendation:** Pure `stale(events, now)` plus an optional scheduled no-model workflow, off until a numeric trigger (e.g. first escalation open over 72h).

### IC-M5 `malformed` conflict between designs - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst` (dup of Z-M6)
* **Affected Scope:** Triggers table `step_failure`; herd-arbiter.md
* **Description/Recommendation:** Per-finding `malformed` goes to the summary; `step_failure` only when every ruling is `malformed`; add to the list.

### IC-M6 `blocked` bolted on; G8/CUJ 8 disagree - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst` (dup of Z-M1/M2/M3)
* **Affected Scope:** G1, G8, CUJ 8, command table
* **Description/Recommendation:** Make `blocked` explicit in G1 and the command table, align G8/CUJ 8, define exit as removing `herd:blocked`; past-issue count must not reset on unblock.

### Z-N8 Weeds in Technical Plan - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 110-112
* **Description:** 140-char cut, marker version string, "never starts a line with `/herd`" (redundant given bot-author ignore), edit handling, quote/fence parsing.
* **Recommendation:** Move to implementation plan.

### Z-N9 Touchpoint data model split - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 124, 213, 221
* **Description:** `touchpoints(events)` counts valid answers but events carry no causes; `answered` and `closed_without_answer` overlap.
* **Recommendation:** One source for "answered".

### Z-N10 Missing `issue_reopened` event - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 213 vs CUJ 7
* **Description:** CUJ 7 reopens issues; `paused_seconds` union is wrong across the gap.
* **Recommendation:** Add the event type or define handling.

### Z-N11 Stale PRD note - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 160
* **Description:** PRD already has `/herd answer <n>` (PRD line 69); the amendment needed is `<n> [<n> ...]`.
* **Recommendation:** Reword.

### Z-N12 Non-test `test_hold_does_not_stop_running_step` - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 226
* **Description:** Described as a "docstring-level assertion".
* **Recommendation:** Define a real ordering assertion or drop.

### Z-N13 Alternative A rationale incomplete - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 141, line 37
* **Description:** Same record holds `budget_used` and round counter, also agent-resettable; M1 tamper gap should say it covers these.
* **Recommendation:** Extend the accepted-gap statement.

### Z-N14 "Maintainer" definition shared - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 35
* **Description:** Defined here only; Triage design and PRD use it undefined.
* **Recommendation:** Single shared definition.

### IC-N7 Hold only at step boundary; transient step_failure costs a touchpoint - Severity: Nit
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** Technical Plan "Pause is derived"; `step_failure`
* **Description:** (a) `/herd hold` takes effect only at the next boundary; (b) a transient harness failure spends a touchpoint at once.
* **Recommendation:** (a) check `herd_status` between agent calls; (b) one delayed automatic retry counted in `budget_used`.
