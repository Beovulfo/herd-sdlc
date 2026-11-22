# Goldfish Review Report: Stage 7 (design, structural, style on FeatureRange)

**Target:** `docs/designs/herd-escalation.md` (1-206). Standard: feature-spec-standard. One round.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-design` | completed |
| `egm-structural` | completed |
| `egm-style` | completed |

Counts (deduplicated): Blocker 0, Major 13 (F1-F13), Nit 21 (F14-F34).

## Major

### F1 Alternatives rejected "by author" without trade-off - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-structural`, `egm-style`
* **Affected Scope:** lines 147, 153, 159, 165, 171
* **Discrepancy Description**: A, C, D, E give "Rejected by author" with no linked discussion; C, D, E restate the con. Violates the standard's Alternatives Rule. Missing alternatives: labels-only state; snapshot of labels and open issues with timeline only for `paused_seconds`; escalation as a comment on the feature issue (excluded by PRD section 4; say so).
* **Rationale & Recommendation**: Replace attribution with the concrete trade-off (e.g. D: an accidental close would count as a decision and distort the median); cite PRD as Alt F does.

### F2 Orchestrator design relied on but does not exist - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 99, 114, 185, 191
* **Discrepancy Description**: `docs/designs/herd-orchestrator.md` is absent. Serialisation, per-feature concurrency, restart on comment events, report code, round loop and `budget_used` are deferred to it; the race mitigation depends solely on it.
* **Rationale & Recommendation**: Add a Dependencies section stating the minimum contract, marked unverified.

### F3 Replay input undefined and tamperable - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 99, 112, 114
* **Discrepancy Description**: Timeline carries no comment bodies; where causes live is not stated. If in the issue body, any write-access user can edit a bot-authored body and change options or causes. "The bot" identity undefined (shared `github-actions[bot]`). Pagination unstated.
* **Rationale & Recommendation**: Say which APIs are fetched; keep causes in a bot comment or recompute; compare to a recorded hash; define bot identity.

### F4 Answer semantics do not combine across causes - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 27, 65, 103-107, 112, 114
* **Discrepancy Description**: CUJ 3 example `rounds=1 budget=2` mixes continue and `stop` with no precedence. Duplicate pairs, extra pairs and `stop` mixed with others undefined. One number per `low_confidence` cause applies to all its findings.
* **Rationale & Recommendation**: Define precedence (any `stop` wins, atomic), reject duplicates and extras, fix the example; state per-finding is out of scope or split.

### F5 `overrule_arbiter` undefined for decline/escalate; `decisions.md` writer conflict - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-style`
* **Affected Scope:** line 112; Arbiter design (sole writer, `audit` line)
* **Discrepancy Description**: Opposite defined only for accept/contest; `low_confidence` can wrap `decline`. The orchestrator-written `{"type":"human"}` line conflicts with Arbiter sole-writer rule and its `audit` line; effect on flip check (`prior`) and overturn metric unstated.
* **Rationale & Recommendation**: Define all verdicts; name the writer; align with Arbiter `audit`.

### F6 Policy escalations never settled before round cap - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 105, 110; Arbiter CUJ 3
* **Discrepancy Description**: `policy`/`citation`/`flip` findings count in `rounds` yet go to the summary; they stay open, the loop runs to round 3, and a `rounds` touchpoint is charged for a ruling Arbiter describes as free. Effect on PRD median target (at most 2) unstated.
* **Rationale & Recommendation**: State the consequence or define how such findings leave the open set.

### F7 Blocked time not excluded from wall-clock budget - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 124, 125, 128
* **Discrepancy Description**: `paused_seconds` covers hold and open escalation only; time in `blocked` accrues, so unblocking may trigger an immediate `budget` escalation consuming one of 3.
* **Rationale & Recommendation**: Include `herd:blocked` in the paused union or justify.

### F8 After the ceiling: dropped trigger and stuck escalation - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 30, 95, 124
* **Discrepancy Description**: A fourth trigger opens no issue and is not stated as remembered; after unblock nothing says it is re-derived. A manual `herd:blocked` while an escalation is open leaves `/herd answer` "no action", so it can never be answered.
* **Rationale & Recommendation**: State re-derivation at next boundary; define answers in `blocked`.

### F9 `herd.toml` base-branch rule missing - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 106, 126, 196; Triage line 83
* **Discrepancy Description**: Triage reads `herd.toml` from the base branch only; this design is silent, so `[budget]` limits and `raise_by_pct` could be raised from a `herd/*` branch.
* **Rationale & Recommendation**: State base-branch-only, consistent with P6 and Alt A.

### F10 No scalability limit in Risks - Severity: Major
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** lines 187-197
* **Discrepancy Description**: Standard requires scalability limits. Replaying the whole timeline at each step boundary grows with feature age and hits pagination and rate limits.
* **Rationale & Recommendation**: Add a risk row with limit and mitigation, or declare out of scope.

### F11 "Cause" has two meanings - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 24, 59, 105-112
* **Discrepancy Description**: Arbiter `cause` is a ruling field; here "Cause" is the issue-side `{trigger, step, findings, options}` record. Line 110 mixes both.
* **Rationale & Recommendation**: Rename the issue-side object or always qualify.

### F12 Unreadable `malformed` sentence - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** line 110 (also comprehension C6)
* **Discrepancy Description**: "Some `malformed` rulings short of all of them are such summary items" is unclear.
* **Rationale & Recommendation**: "If only some rulings are `malformed`, they go to the spec PR summary. `step_failure` fires only when every ruling is `malformed` after the re-ask."

### F13 "Extends that issue's cause" undefined - Severity: Major
* **Reviewer Lens:** `egm-style`, `egm-design`
* **Affected Scope:** lines 24, 59, 114
* **Discrepancy Description**: Not stated what extension changes; conflicts with line 114 where a repeat opens a new issue. A cause added after a maintainer prepared an answer invalidates it; unstated.
* **Rationale & Recommendation**: Say "adds finding ids to that cause" or drop; state invalidation.

## Nit

* **F14** (`egm-design`, lines 59, 99): say triggers raised at one boundary are batched into one issue.
* **F15** (`egm-design`, lines 116-122): `apply_command` has no issue number; wrong-place commands uncovered; "edited comments return none" may drop a command edited before processing.
* **F16** (`egm-design`, line 27): G5 "Anything else" too broad; only a failing `/herd answer` line gets the restating comment.
* **F17** (`egm-design`, `egm-style`, lines 35, 114, 192): "assigned to the maintainers" has no source (CODEOWNERS, team, `herd.toml`); assignee cap 10; "so GitHub notifications apply" unverified, say no reminder is sent.
* **F18** (`egm-design`, line 89): CUJ 7 must distinguish maintainer close from orchestrator close; deleted or transferred issue.
* **F19** (`egm-design`, line 130): report `causes_answered` beside `answered`.
* **F20** (`egm-design`, line 125): budget exceeded mid-step, abort or finish?
* **F21** (`egm-structural`, lines 9, 21, 97): align section names with standard ("Problem Statement", "Proposed Architecture", "Goals & Non-Goals") if not intentional.
* **F22** (`egm-structural`, lines 13, 15): Terms and Status as run-in paragraphs; use H2 or tables.
* **F23** (`egm-structural`, lines 99-139): Technical Plan lacks sub-headings; diagram last.
* **F24** (`egm-structural`, lines 15 vs 118-122): status order differs.
* **F25** (`egm-structural`, lines 7, 179, 205): inconsistent horizontal rules.
* **F26** (`egm-structural`, lines 13, 105, 112, 126, 130, 183, 184): plain-text cross-references; use links.
* **F27** (`egm-structural`, lines 28-29, 89): `test_closed_without_answer_stays_open` has no goal.
* **F28** (`egm-style`, line 13): filler "definition to share".
* **F29** (`egm-style`, lines 13, 15, 112): `Elephant` not in Terms; gloss `held_and_awaiting`.
* **F30** (`egm-style`, lines 19, 152): overstated "median meaningless".
* **F31** (`egm-style`, line 114): "worked line" -> "example line".
* **F32** (`egm-style`, line 158): "drifts into deciding the answer" vague.
* **F33** (`egm-style`, line 196): "owner" undefined; say maintainer.
* **F34** (`egm-style`, line 183): "no comment text reaches an agent" is absolute; say "no free-text comment content".
