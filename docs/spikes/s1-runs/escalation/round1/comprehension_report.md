# Goldfish Review Report: Stage 6 (comprehension, no GoldfishContext)

**Target:** `docs/designs/herd-escalation.md` (FeatureRange 1-194, DetailedRange 195-243)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-comprehension` | completed |

Counts: Blocker 0, Major 12 (Feature 8, Detailed 4), Nit 6 (Feature 3, Detailed 3). Total 18.

## Paraphrase: FeatureRange

What this proposes: When a feature needs a human decision outside H1, the orchestrator opens ONE GitHub issue (escalation) and pauses until a maintainer answers. Maintainers can also `/herd hold` and `/herd resume`. The answer is a closed numbered list (`/herd answer 1 2`), one number per cause, parsed by code only. Pause state is never in the state record; it is derived from the `herd:hold` label and open escalation issues. A touchpoint is one escalation issue with a valid maintainer answer. Paused time is subtracted from the wall-clock budget. After 3 escalation issues the feature gets `herd:blocked`.

How the existing system works per the doc: the orchestrator runs numbered lifecycle steps and checks status before each; the review loop runs up to 3 rounds; the Arbiter agent rules on findings; the Triage design owns `herd.yaml` and `risk`; the PRD defines H1/H2/P6/touchpoints/20-feature baseline; the state record holds the round counter and budget used; the orchestrator design owns Actions, `gh` calls and serialisation.

## Paraphrase: DetailedRange

What this proposes: Four phases build one stdlib-only pure Python module `scripts/herd_escalation.py` (status, resume check, command parser, answer parser, issue-body builder, `next_escalation`, `paused_seconds`, `touchpoints`), each with a unittest exit check; a test file with one test per goal/CUJ plus four extras; `herd.yaml` gets a budget block with placeholder values (created if Triage has not). No build, lint or E2E.

How the existing system works per the doc: the Triage design pins Python and PyYAML and may have created `herd.yaml`; the orchestrator design owns GitHub I/O; the functions here receive pre-shaped label, escalation and event dicts and make no `gh` calls.

## Findings: FeatureRange

### F1 `blocked` missing from G1 and paused semantics - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** line 21 vs lines 96, 214
* **Description:** G1 says four values; line 96 says blocked is never running; line 214 lists five. G1 "iff" leaves `blocked` undefined; unclear whether it counts as paused or in `paused_seconds`.
* **Recommendation:** Add `blocked` to G1 and line 96; state paused/`paused_seconds` treatment.

### F2 G4 vs CUJ 4 and table on resume - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** line 24 vs lines 64-68, 117
* **Description:** G4 says resume is "refused" with an open escalation; CUJ 4 and the table say the hold label is removed.
* **Recommendation:** Reconcile the wording.

### F3 Ceiling count off-by-one - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** line 28 vs lines 88-92
* **Description:** "after 3 issues" vs "2 answered, third trigger opens nothing"; unclear whether "repeat of #N" issues count.
* **Recommendation:** State the exact count rule.

### F4 `rounds` trigger severity differs - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** line 102 vs line 47
* **Description:** Table fires on Blocker|Major; CUJ 1 says Blocker only.
* **Recommendation:** Align.

### F5 Raised limits storage unstated - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 120, 126 vs line 11
* **Description:** "Everything derived from GitHub" but where raised round cap/budget limit lives is not stated.
* **Recommendation:** State how it is derived (e.g. count answered `rounds`/`budget` escalations).

### F6 "abandoned" and "median" undefined - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** line 124
* **Description:** Abandoned escalations and median (of what) undefined; CUJ 7 reopens closed issues, so when is one abandoned?
* **Recommendation:** Define both.

### F7 Undefined project terms - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 13, 33, 36, 37, 39, 105, 110
* **Description:** M0/M1, Triage (+fallback), H2, Evidence Auditor, step boundary, fails closed, fresh context, malformed/re-ask, record branch, round counter, "step" in (feature,trigger,step).
* **Recommendation:** Extend Terms or link PRD.

### F8 Assignee roster unknown - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 110, 35
* **Description:** Issue "assigned to the maintainers", maintainer = triage role; no source for the assignee list.
* **Recommendation:** Say how the list is obtained.

### F9 `raise_by` unit and numbering - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 103, 231
* **Description:** Unit (percent) only in Detailed range; option numbering when `raise_by` unset unclear.
* **Recommendation:** State in feature range.

### F10 Duplicate marker/bot statement - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** line 110
* **Description:** Marker/author-is-bot stated twice; repeat-issue handling implicit.
* **Recommendation:** Dedupe, make explicit.

### F11 Arbiter cause names only by pointer - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** line 108
* **Description:** Cause names and the `escalate` verdict defined only by reference to another design.
* **Recommendation:** Inline a one-line definition.

## Findings: DetailedRange

### D1 Maintainer boolean has no receiver - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** line 112 vs lines 213-221
* **Description:** Caller passes a maintainer boolean "to the functions here", but no signature except `command_of` (author_is_bot only) takes it; nothing implements or tests G3 (`test_non_maintainer_ignored`).
* **Recommendation:** Name the function taking the boolean.

### D2 Escalation dict shape incomplete - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 213, 219
* **Description:** `next_escalation` needs step/trigger per escalation but the shape has `causes[{trigger,options}]` and no `step`; `state`, `closed_without_answer`, `answered` lack values/relationship.
* **Recommendation:** Specify the full shape.

### D3 Event shape elided - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 213, 220-221
* **Description:** Shape elided with `...`; `touchpoints`/`paused_seconds` need issue number, label name, comment body or valid-answer flag, trigger (for by-trigger report, line 124), and an `issue_reopened` type (CUJ 7).
* **Recommendation:** List fields and event types.

### D4 Untestable `test_hold_does_not_stop_running_step` - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** line 226
* **Description:** "Docstring-level assertion on herd_status ordering" is not assertable; `herd_status` has no running-step concept.
* **Recommendation:** Define or drop.

### D5 Test class mapping and import path - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 201-203, 226
* **Description:** TestStatus/TestEscalation not mapped to tests; `scripts.test_herd_escalation` implies `scripts/` importable (`__init__.py`?) unstated.
* **Recommendation:** Map and state.

### D6 Phase 4 dependency on possibly absent file - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 204, 206, 212
* **Description:** Module is stdlib-only but the Phase 4 check imports `yaml` via Triage's pin; depends on a possibly nonexistent file.
* **Recommendation:** State the ordering/dependency.

### D7 No test for 140-char cut or `/herd` line rule - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** line 238
* **Description:** Despite the coverage rule, only a fencing test is added.
* **Recommendation:** Add tests or drop the rules.
