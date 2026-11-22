# Goldfish Review Report: Stage 9 (implementation-readiness + codebase-details + style, DetailedRange)

**Target:** `docs/designs/herd-escalation.md` (lines 195-243), standard `implementation-readiness-standard`

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-implementation-readiness` | completed |
| `egm-codebase-details` | completed |
| `egm-style` | completed |

Counts: Blocker 3 (readiness 3), Major 16 (readiness 8, codebase-details 6, style 2), Nit 19 (readiness 5, codebase-details 4, style 10). Total 38 (not deduplicated across reviewers). Readiness verdict: plan NOT ready; a fresh engineer would have to make several design choices. Notes marked "context only" and "KEEP/no change" are not counted. Codebase-details: repo has no `scripts/` or `herd.yaml`, both correctly marked Create/Modify.

## Findings: egm-implementation-readiness

### R-B1 Data shapes cannot support `next_escalation` - Severity: Blocker
* **Affected Scope:** lines 213, 219, 233 (rule at line 110)
* **Description:** Escalation shape `{number, state, closed_without_answer, causes:[{trigger, options}], answered}` has no `step` though the repeat rule keys on `(feature, trigger, step)`. `state` values unlisted; `closed_without_answer` and `answered` overlap and line 214 defines "open" by a third notion; `options` item shape undefined; `repeat_of` when several earlier answered issues match undefined.
* **Recommendation:** One exact schema with allowed `state` strings and `options` item shape; state which issue wins for `repeat_of`.

### R-B2 Ceiling ambiguous and unresolved in plan - Severity: Blocker
* **Affected Scope:** line 219 vs line 28 (G8), line 92 (CUJ 8)
* **Description:** G8 blocks a 4th issue; CUJ 8 blocks the 3rd after 2 answered. Plan says only "ceiling of 3"; count basis (open, abandoned, repeat), comparison (`>=2` vs `>=3`) and branch order (append to open issue vs ceiling) unstated; `test_ceiling` cannot be written.
* **Recommendation:** State exact comparison and count basis; order branches (append if open, else blocked at limit, else open); align G8 and CUJ 8.

### R-B3 Event schema hides everything with `...` - Severity: Blocker
* **Affected Scope:** lines 213, 220-221
* **Description:** `{type, at, actor_is_maintainer, ...}`. `paused_seconds` and `touchpoints` need label name, feature-vs-escalation issue, issue number, comment id and body; deciding whether a closing comment is a valid answer needs the escalation's causes, which events do not carry.
* **Recommendation:** Define every field per event type; define how an event links to an escalation and how "valid answer" is derived (recorded field, or events joined with escalations).

### R-M1 No function implements the command table - Severity: Major
* **Affected Scope:** lines 215-216, 114-118
* **Description:** `command_of` has no maintainer parameter; return strings unnamed; `can_resume(status)` gets no issue number for "name the issue"; nothing yields action and reply per status (already held, no-ops, add label, close issue, still held); maintainer boolean never consumed though `test_non_maintainer_ignored` needs it.
* **Recommendation:** Add `apply_command(status, cmd, is_maintainer, open_issue_number) -> {action, reply}` with exact action tokens and reply templates.

### R-M2 `command_of` parsing underspecified - Severity: Major
* **Affected Scope:** line 216 (vs line 112)
* **Description:** First line of comment vs first line outside fences; quote syntax, fence syntax (``` and ~~~, unclosed), number tokenisation (separators, negative, leading zero, empty), trailing text after `/herd hold`, case sensitivity, bot/edited `None` all unspecified.
* **Recommendation:** Exact algorithm or regex plus accept/reject table.

### R-M3 `parse_answer` and `build_issue_body` inputs/outputs - Severity: Major
* **Affected Scope:** lines 217-218, 110
* **Description:** `build_issue_body(feature, causes)` has no finding text, reason or step although line 110 requires the 140-char cut, fencing, `/herd` filtering; template never written; truncation marker, embedded fences, newlines, `/herd` line start unspecified; restated-options reply format, duplicate numbers, empty list unspecified.
* **Recommendation:** Literal template and sanitiser steps; add finding text to cause shape; give reply template.

### R-M4 No function builds options per trigger - Severity: Major
* **Affected Scope:** lines 100-106, 219
* **Description:** `budget` option 1 only if `raise_by` set; `tradeoff` 2 to 3 options plus last `stop`; `stop` last everywhere; unknown-trigger handling undefined.
* **Recommendation:** Add `options_for(trigger, raise_by_set, tradeoff_options) -> list`, closed trigger set as a constant, unknown trigger raises `ValueError`.

### R-M5 `paused_seconds` and `touchpoints` semantics undefined - Severity: Major
* **Affected Scope:** lines 220-221, 124
* **Description:** Interval open/close events, reopened issue (CUJ 7), clipping at `now`, `herd:blocked` time, rounding, by-trigger split, repeat rate, `abandoned`, and the file rendering the report are all undefined.
* **Recommendation:** Define each term and return shape; name the report file.

### R-M6 Test plan lacks cases and assertions - Severity: Major
* **Affected Scope:** lines 223-226
* **Description:** No inputs/expected outputs per test; no test-to-class mapping (`TestStatus`, `TestEscalation`, third class for Phase 3); `test_hold_does_not_stop_running_step` is not a test; `test_status_table` needs all 5 values incl. `blocked` while G1 lists 4.
* **Recommendation:** Fixtures and expected values per test; assign classes; fix or drop the non-test; state `blocked` precedence.

### R-M7 `herd.yaml` change unsafe and underspecified - Severity: Major
* **Affected Scope:** lines 204-206, 228-231
* **Description:** Triage creates `herd.yaml` and `requirements.txt` (`PyYAML==6.0.4`). If Phase 4 runs first and creates a `budget`-only file, Triage's `floor` key and the PyYAML dependency are missing. `raise_by: 50` is a percentage but option 1 exists only if `raise_by` is set while the placeholder always sets it; applies to both `tokens` and `minutes`? compounding?
* **Recommendation:** State dependency order (Phase 4 requires Triage `herd.yaml` and `requirements.txt`) or who merges; settle `raise_by` semantics.

### R-M8 File boundary incomplete - Severity: Major
* **Affected Scope:** lines 208-231, 126, 120, 160
* **Description:** PRD amendment (line 160) not in file list; `budget_used` ownership (line 126) and round-cap change (line 120) have no file.
* **Recommendation:** Name orchestrator ownership explicitly; exact write allowlist.

### R-N1 Python version restated - Severity: Nit
* **Affected Scope:** line 206
* **Recommendation:** Write "Python 3.13 or later" (herd-triage.md line 171).

### R-N2 Timestamp format - Severity: Nit
* **Affected Scope:** line 213
* **Description:** ISO 8601 UTC; `Z` suffix and offsets acceptance unstated (`fromisoformat` handles `Z` on 3.11+).
* **Recommendation:** State it.

### R-N3 Namespace-package import form - Severity: Nit
* **Affected Scope:** line 201
* **Description:** Works only if `scripts` is importable as namespace package; Triage uses the same form, so consistent.
* **Recommendation:** No change needed.

### R-N4 `malformed` cause list - Severity: Nit
* **Affected Scope:** line 108 vs herd-arbiter.md line 25
* **Recommendation:** Reconcile cause lists.

### R-N5 New tests not tied to a CUJ - Severity: Nit
* **Affected Scope:** lines 226, 239
* **Description:** `test_command_in_code_fence_ignored`, `test_edited_comment_ignored`, `test_issue_body_fences_finding_text` unmapped; line 239 claims every goal and CUJ names a test.
* **Recommendation:** Add mapping.

## Findings: egm-codebase-details

### C-M1 Maintainer boolean has no signature - Severity: Major
* **Affected Scope:** lines 213-221, 25, 112
* **Description:** G3 and `test_non_maintainer_ignored` need non-maintainer commands to do nothing; line 112 says the caller passes a boolean "to the functions here", but `command_of` has only `author_is_bot` and `edited`, `can_resume` only `status`; no function implements the hold/answer rows.
* **Recommendation:** Add `author_is_maintainer` to `command_of` (None when false) or add `apply_command(status, command, is_maintainer) -> {action, reply}`.

### C-M2 Shapes cannot support the functions - Severity: Major
* **Affected Scope:** lines 213, 218, 219
* **Description:** No `step`; `build_issue_body` lacks finding text and `raise_by` (option 1 exists only if `raise_by` set); event shape ends `...`; `state` values not given; `closed_without_answer`/`answered`/`state` overlap; line 214 redefines "open" in prose.
* **Recommendation:** Exact dict schemas for escalation, cause (`trigger`, `step`, `reason`, `options`) and event (per `type`); pass `raise_by` or prebuilt options.

### C-M3 `herd_status` values disagree - Severity: Major
* **Affected Scope:** line 214 vs lines 21, 96
* **Description:** G1 and `test_status_table` name four values; line 96 says `herd:blocked` is never running; line 214 returns five.
* **Recommendation:** Add `blocked` to G1 and the table; define precedence over `held` and `awaiting_answer`.

### C-M4 `touchpoints()` return does not match report - Severity: Major
* **Affected Scope:** line 221 vs line 124
* **Description:** Report needs opened/answered/abandoned by trigger, repeat rate, total paused time; return is `{answered, abandoned, opened, repeats, touchpoint_rule}`. "Abandoned" undefined; line 62 reopens closed-without-answer issues.
* **Recommendation:** Define abandoned, give exact return shape, say which function produces the report.

### C-M5 Phase 4 exit check can fail; file boundary ambiguous - Severity: Major
* **Affected Scope:** lines 204-206, 208-231
* **Description:** Check runs `import yaml`; the "create with only budget" fallback creates no `requirements.txt` or PyYAML pin (Triage creates it, herd-triage.md line 165, not on this plan's list). "Modify; Create if the Triage design has not made it" is not one action for a write allowlist.
* **Recommendation:** State which design lands first; add `requirements.txt` as Create-if-absent with the same pin or make Phase 4 depend on Triage Phase 3.

### C-M6 Two tests underspecified - Severity: Major
* **Affected Scope:** line 226
* **Description:** `test_hold_does_not_stop_running_step` not testable (`herd_status` stateless over labels); `test_issue_body_fences_finding_text` has no inputs/outputs, 140-char cut and `/herd` rule not given as cases; no test-to-class mapping.
* **Recommendation:** Concrete input/expected output per test; list tests per class.

### C-N7 Reply texts and command strings - Severity: Nit
* **Affected Scope:** lines 215-216
* **Description:** `can_resume` reply texts not given; command strings (`hold`, `resume`, `answer`) not named; empty `list[int]` for hold/resume not stated.

### C-N8 Count basis for ceiling - Severity: Nit
* **Affected Scope:** line 219, G8, CUJ 8
* **Description:** All issues or only answered; does an open issue count.

### C-N9 Python version - Severity: Nit
* **Affected Scope:** line 206
* **Recommendation:** Restate 3.13 or later instead of "the version Triage pins".

### C-N10 `budget_used` has no owner - Severity: Nit
* **Affected Scope:** line 126
* **Description:** Claimed record key, but no target file or function reads or writes it.
* **Recommendation:** Name the owner or drop the claim.

## Findings: egm-style

### Y-M1 `test_hold_does_not_stop_running_step` cannot fail - Severity: Major
* **Affected Scope:** lines 226, 238
* **Description:** Name claims behaviour; description is a "docstring-level assertion on `herd_status` ordering", which asserts nothing; line 238 counts it toward coverage.
* **Recommendation:** State the real assertion (e.g. `herd_status(['herd:hold'], [])` returns X) or rename.

### Y-M2 `herd_status` order and "open" ambiguous - Severity: Major
* **Affected Scope:** line 214 vs 213, 226
* **Description:** Five statuses listed in an order that looks like precedence but is not stated; line 226 relies on "ordering". "Open unless closed with a valid answer" conflicts with `closed_without_answer`/`answered` fields.
* **Recommendation:** Add "evaluated in this order"; name the fields that decide open.

### Y-N3 Line 213 run-on with `...` - Severity: Nit
* **Affected Scope:** lines 213, 225
* **Recommendation:** Split into a short list; replace `...` with per-type fields or a pointer to the Design section.

### Y-N4 `can_resume` lacks condition - Severity: Nit
* **Affected Scope:** line 215
* **Recommendation:** E.g. `(True, reply)` only when status is `held`, otherwise `(False, reply)`.

### Y-N5 `command_of` return undefined - Severity: Nit
* **Affected Scope:** line 216
* **Recommendation:** "Returns `(command, numbers)`, or `None` when the author is a bot, the comment was edited, or no command is found."

### Y-N6 `parse_answer` return tuple - Severity: Nit
* **Affected Scope:** line 217
* **Recommendation:** "`(True, '')` when valid, `(False, reply)` otherwise."

### Y-N7 "Inline generic events" vague - Severity: Nit
* **Affected Scope:** line 225
* **Recommendation:** "event dicts built inline in each test, with no external fixtures".

### Y-N8 Test names point outside range - Severity: Nit
* **Affected Scope:** line 226
* **Recommendation:** Link the Goals and CUJs section; verify the names exist.

### Y-N9 Redundant caveat - Severity: Nit
* **Affected Scope:** line 231
* **Recommendation:** "The values are placeholders; the owner sets them."

### Y-N10 Duplicate create-file instruction - Severity: Nit
* **Affected Scope:** lines 206, 228
* **Recommendation:** Keep line 206; shorten line 228.

### Y-N11 "M0" undefined; build/lint lines collapse - Severity: Nit
* **Affected Scope:** lines 235-237
* **Recommendation:** Drop "M0" or define it; "Build and lint: none."

### Y-N12 Phase 4 exit check is a visual check - Severity: Nit
* **Affected Scope:** lines 201-204
* **Description:** Exit checks are otherwise concrete (KEEP). Phase 4 prints `budget` without asserting `tokens`, `minutes`, `raise_by`; "passes (all tests)" on line 203 slightly redundant.
* **Recommendation:** Reword to an assertion.

(Reviewer item 13, `standard library only` vs PyYAML in Phase 4: no change needed; not counted.)
