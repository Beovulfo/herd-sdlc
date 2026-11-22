# Goldfish Review Report: Stage 6 (comprehension)

**Target:** `docs/designs/herd-escalation.md` (FeatureRange 1-206, DetailedRange 207-277). No GoldfishContext given.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-comprehension` | completed |

Counts: Blocker 0, Major 6, Nit 9.

## What this proposes

FeatureRange (lines 1..206): Herd pauses a feature through GitHub events only, with no pause data in the state record. A trigger (`rounds`, `budget`, `low_confidence`, `step_failure`) opens at most one escalation issue per feature. Further triggers add causes to that issue. A maintainer (write/maintain/admin) answers with `/herd answer <trigger>=<n> ...`, one pair per cause. `/herd hold` and `/herd resume` pause and continue independently of any escalation. A valid answer is one touchpoint. The design also covers a 3-issue ceiling that sets `herd:blocked`, limits that rise only through answers, and pause time excluded from the wall-clock budget.

DetailedRange (lines 207..277): It builds one pure stdlib module, `scripts/herd_escalation.py`. Its functions replay an event list into state and compute status, command effects, answer validity, the next escalation action, limits, pause seconds and touchpoints. A unittest file covers each goal. A `[budget]` table is added to `herd.toml`, and one PRD line is edited. Four phases each have a runnable exit check.

## How the existing system works, per this document

A lifecycle of numbered steps is run by an orchestrator. A review loop runs up to 3 rounds, an Arbiter rules on findings, the spec PR is opened at step 9, and H1 is the human gate. The orchestrator calls `gh`, fetches events and checks status at every step boundary. The `herd` label marks feature issues. A per-feature concurrency group serialises work (deferred to the orchestrator design). State record `.herd/state/<feature>.json` holds `budget_used`. `decisions.md` is appended with Arbiter rulings. Triage and Arbiter designs are separate and not described.

## Findings

### C1 Reopen semantics of a closed escalation unstated - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 15, 89, 125, 225
* **Discrepancy Description**: An escalation is open until a valid answer even if its issue is closed, but the text never says `awaiting_answer` persists through reopen or if the reopen fails. CUJ 7 relies on this.
* **Rationale & Recommendation**: One sentence in Technical Plan: reopen is cosmetic, status derives from events.

### C2 Undefined terms in `overrule_arbiter` - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 105, 107, 112
* **Discrepancy Description**: "Elephant", `arbiter_verdict`, "contest", "accept" are not defined or in Terms; "Elephant" appears nowhere else.
* **Rationale & Recommendation**: Define them or link the Arbiter design.

### C3 Repeat rule stated three ways - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 114, 232, G8
* **Discrepancy Description**: Repeat on `(feature, trigger, step)` of an answered escalation opens a new issue and counts a touchpoint again; `next_escalation` sets `repeat_of` only on match; G8 says the ceiling counts "repeats". Unclear if an answered `retry_step` repeat counts toward the ceiling and also gives a second touchpoint.
* **Rationale & Recommendation**: State the rule once.

### C4 Ceiling window boundary unclear - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 99, 125, 232
* **Discrepancy Description**: Ceiling counts issues since last removal of `herd:blocked`, which a `stop` answer also sets. Not stated which removal marks the restart if toggled several times, nor whether the stopping issue counts in the new window.
* **Rationale & Recommendation**: State the restart event and that earlier issues are excluded.

### C5 Who fills `author_is_maintainer`, and when - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 183, 225
* **Discrepancy Description**: Event carries `author_is_maintainer` but Security says the check runs via the API when the comment is processed; replay is pure. Unclear which layer populates it and whether permission is read at comment time or replay time (a later demotion changes results).
* **Rationale & Recommendation**: Name the populating layer and the read time.

### C6 Vague `malformed` ruling rule - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 105, 110
* **Discrepancy Description**: "Some `malformed` rulings short of all of them are such summary items" does not say which go to the summary versus open an issue; only "every ruling malformed" is a trigger.
* **Rationale & Recommendation**: Reword as a precise rule.

### C7 PRD referenced by section number without path - Severity: Nit
* **Affected Scope:** line 13
* **Discrepancy Description / Recommendation**: Terms cite PRD [2],[4],[5],[8] without the filename; add it.

### C8 Lifecycle steps not listed - Severity: Nit
* **Affected Scope:** line 13
* **Discrepancy Description / Recommendation**: "Step 9" and "lifecycle steps" used without a step list; reference or list them.

### C9 Orchestrator and round-loop designs have no path - Severity: Nit
* **Affected Scope:** lines 39, 126, 184, 191
* **Discrepancy Description / Recommendation**: Referenced without paths, unlike Arbiter and Triage; add paths or mark as not yet written.

### C10 `step` for the `rounds` trigger unspecified - Severity: Nit
* **Affected Scope:** line 112
* **Discrepancy Description / Recommendation**: `step` is the lifecycle step number, but `rounds` is raised at end of round 3; state which step applies for the `(feature, trigger, step)` match.

### C11 Assignee mechanism undefined - Severity: Nit
* **Affected Scope:** line 114
* **Discrepancy Description / Recommendation**: "Assigned to the maintainers": team or list from permission API? Say which.

### C12 Phase and test-class assignment consistency - Severity: Nit
* **Affected Scope:** lines 213, 214, 239
* **Discrepancy Description / Recommendation**: Phase exit checks name `TestStatus`/`TestEscalation`, but `test_closed_without_answer_stays_open`, `test_touchpoints` are in "the rest" and `test_ceiling` needs `next_escalation` (phase 2). Check phase 1 can pass; fix assignments.

### C13 Single-PRD glob assumption - Severity: Nit
* **Affected Scope:** lines 216, 264
* **Discrepancy Description / Recommendation**: Check assumes one `PRD*.md` at root; a multi-match gives misleading results. (Also overlaps Z4: the PRD edit may already be done.)

### C14 Python version dependence on sibling design - Severity: Nit
* **Affected Scope:** line 224
* **Discrepancy Description / Recommendation**: `tomllib` needs Python 3.11+; state it directly instead of "the version Triage pins".

### C15 Duplicate answer keys - Severity: Nit
* **Affected Scope:** lines 27, 230
* **Discrepancy Description / Recommendation**: `pairs: dict[str, int]` silently collapses `rounds=1 rounds=2`; specify behaviour (reject).
