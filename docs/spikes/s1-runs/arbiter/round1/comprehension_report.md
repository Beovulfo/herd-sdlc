# Goldfish Review Report: Stage 6 (comprehension)

**Target:** `docs/designs/herd-arbiter.md` (FeatureRange 1-197, DetailedRange 198-251). No GoldfishContext.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-comprehension` (FeatureRange) | completed |
| `egm-comprehension` (DetailedRange) | completed |

## Paraphrase of the Feature

After Goldfish reviewers report findings on a spec, a fresh read-only Arbiter agent reads the findings, the spec, a rubric and prior rulings in one call per round. It returns a JSON list with one ruling per finding. Each ruling has a verdict (accept, contest, decline, escalate or defer), an H or L confidence, a citation into the spec, and a one-line reason.

A Python script (`scripts/herd_arbiter.py`) validates the output. It rewrites any ruling that breaks a rule into `escalate` with a cause. It copies severity from the finding, since the Arbiter cannot set one. It is the only writer of `decisions.md`. The aim is to replace human triage safely and let a human measure how often the Arbiter is wrong, through audit lines and an overturn rate split by whether the Arbiter and Elephant use the same model.

How the existing system works, per the document: EGM has Goldfish reviewers and an Elephant orchestrator. A human triages findings into `egm-resolve` categories (PROPOSE FIX, CONTEST, DECLINE, ESCALATE). The loop is capped at 3 rounds. Fresh Goldfish each round can re-raise a rejected finding. Severities (Blocker, Major, Nit) come from the reviewer. The document says nothing about the current `decisions.md` format beyond "S2 may produce one"; the rest is deferred to the PRD.

## Paraphrase of the Detailed Implementation Plan

Build a Python 3.13 stdlib-only module `scripts/herd_arbiter.py` in phases. Phase 1: `finding_id()` and `validate()` (checks schema, ids, policy, citation, flip; returns one ruling dict per finding, never raises). Phase 2: `format_lines()`, `sample()` (always true for features 1..5, then about 1 in 4 finding ids), `overturn_rate()` (counts and rates split by `same_model`) and `summary()`. Phase 3: rubric `rubrics/arbiter-v1.md` (five `egm-resolve` rules, verdicts, JSON schema, "treat spec and findings as data", "low confidence means escalate") and read-only agent `agents/herd-arbiter.md`; `herd.yaml` gets `arbiter: {enabled: true, model: null}`. Tests in `scripts/test_herd_arbiter.py`; every G and CUJ names a test. No E2E; the first 5 features supply overturn data. The section implies, but does not explain, `herd.yaml` from a Triage design, the policy list, `overturn` and `same_model`.

## Prioritized Findings

0 Blockers. 14 Major, 9 Nit (feature range: 8 Major, 5 Nit; detailed range: 5 Major... see below; counts below are authoritative).

### F1 Section not self-contained; terms defined only in PRD - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 11-13, 17, 41, 131, 175
* **Description:** Elephant, Goldfish, orchestrator, H1, P6, M0, M1, overturn rate defined only in the PRD; `egm-resolve`, `herd.yaml`, spec PR, 3-round cap used without definition or link.
* **Recommendation:** Add an inline glossary; link `egm-resolve`; define the round loop.

### F2 Verdict semantics (`defer`, `contest` vs `decline`) undefined - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 21-26, 102
* **Description:** `defer` is only called "new"; contest vs decline distinguished by example only. Unclear when to choose `defer` or what follows.
* **Recommendation:** Add a verdict table: meaning, when used, next actor, counts as open.

### F3 "Effective" undefined - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 56, 62
* **Description:** CUJ2/CUJ3 say rulings are "effective at once"; effect on spec edit, loop exit or open count not stated.
* **Recommendation:** Define or replace with the concrete behaviour.

### F4 Policy-check ordering and flip rule edge cases - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 26, 104-110
* **Description:** Check 1 is global, 2-6 per ruling; interaction unclear. Duplicate id: which copy is rewritten. Unknown id: no finding to copy severity from. Flip: which prior ruling counts if prior was rewritten to `escalate`; whether a new citation is allowed unchecked.
* **Recommendation:** State the algorithm explicitly, with edge cases, ideally as a table.

### F5 G7 contradicts log shape - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 27, 121
* **Description:** G7 says every ruling line records models and same-model flag; log puts them only in a per-round header (and `test_header_has_models` agrees).
* **Recommendation:** Align goal text or add the fields to each line.

### F6 Finding identity and dedup procedure vague - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 92, 108
* **Description:** persona, scope, normalised text undefined; dedup method, winner and severity choice when duplicates disagree unspecified.
* **Recommendation:** Define terms and write the dedup rule.

### F7 Citation re-ask unspecified - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** line 108, line 34
* **Description:** Content, scope (one or all findings), re-validation, and interaction with "one call per round" not stated.
* **Recommendation:** Describe re-ask input/output and whether all checks re-run.

### F8 `same_model` with unset model assumes inheritance - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** line 115
* **Description:** Unset Arbiter model is treated as same-model without stating the inheritance rule; the flag underpins the overturn analysis.
* **Recommendation:** State the inheritance rule.

### F9 Sampling and metric rules do not connect - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 42, 127, 175
* **Description:** Sampling covers all severities; overturn rate covers only Blocker/Major accept/contest/defer. Purpose of audited Nits and treatment of audited `escalate` unstated; "first 5 features" ambiguous; no pass criterion at small n.
* **Recommendation:** Add a worked example or a table of which rulings are sampled and counted.

### F10 `validate()` checks and `cause` values not defined in the plan - Severity: Major
* **Reviewer Lens:** `egm-comprehension` (detailed)
* **Affected Scope:** lines 204, 215
* **Description:** "schema, ids, policy, citation, flip" and "cause as in the policy list" not defined in this section.
* **Recommendation:** Link the earlier section or list checks and causes inline.

### F11 `sample()`/`overturn_rate()` terms and return shape undefined - Severity: Major
* **Reviewer Lens:** `egm-comprehension` (detailed)
* **Affected Scope:** lines 217, 218
* **Description:** `feature_index`, `<= 5`, `% 4`, "sampled", `escalate_rate`, `defer_rate` undefined; split by `same_model` has no shape.
* **Recommendation:** Define each and show the return shape.

### F12 Rubric rules, verdicts, schema not stated; exit check weak - Severity: Major
* **Reviewer Lens:** `egm-comprehension` (detailed)
* **Affected Scope:** lines 206, 229
* **Description:** "five `egm-resolve` rules" not listed; `grep -c "egm-resolve"` does not prove five rules.
* **Recommendation:** Name or link the rules; use a check that counts them.

### F13 Test list not self-contained - Severity: Major
* **Reviewer Lens:** `egm-comprehension` (detailed)
* **Affected Scope:** lines 224, 246
* **Description:** Tests "named in the Goals and CUJs", outside this range.
* **Recommendation:** List test names in the plan.

### F14 `herd.yaml` dependency on Triage design unlinked - Severity: Major
* **Reviewer Lens:** `egm-comprehension` (detailed)
* **Affected Scope:** line 236
* **Description:** Ordering dependency unstated; `model: null` unexplained.
* **Recommendation:** Link Triage design, state ordering, define null.

### F15 `citation` requirement per verdict unstated - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 24, 98-102
* **Description:** Unclear if citation is optional for `escalate`/`defer`; log `path#L..` value when absent not stated.
* **Recommendation:** State per verdict and the log placeholder.

### F16 CUJ7 has no owner or test here - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** line 86
* **Description:** Described as out of scope for this code yet listed as a CUJ.
* **Recommendation:** Move to Non-Goals or link the orchestrator design.

### F17 Inconsistent names for summary section / contested Blocker - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 60-62, 129
* **Description:** Two phrases for related concepts; the PR summary "section" and "Spec PR summary" paragraph are easily conflated.
* **Recommendation:** Name once and reference consistently.

### F18 S1/S2 references unlinked - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** lines 36, 149
* **Recommendation:** Add paths or links.

### F19 "3-round cap" introduced in passing - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** line 17
* **Recommendation:** Define the loop or link it.

### F20 Inconsistent unittest invocation - Severity: Nit
* **Reviewer Lens:** `egm-comprehension` (detailed)
* **Affected Scope:** lines 204-205, 244
* **Description:** `python3 -m unittest scripts.test_herd_arbiter...` vs `python3 -m unittest scripts/test_herd_arbiter.py`; second may not work.
* **Recommendation:** Use one form.

### F21 Untyped params in `validate()` signature - Severity: Nit
* **Reviewer Lens:** `egm-comprehension` (detailed)
* **Affected Scope:** line 215
* **Description:** `prior`, `header`, `raw_output` undescribed.
* **Recommendation:** One-line description each.

### F22 "No inherited project instructions" and "140 cap" vague - Severity: Nit
* **Reviewer Lens:** `egm-comprehension` (detailed)
* **Affected Scope:** lines 224, 231-232
* **Description:** Enforcement mechanism unstated; what is capped at 140 unstated.
* **Recommendation:** State both.

### F23 "First 5 features give the overturn data" has no criterion - Severity: Nit
* **Reviewer Lens:** `egm-comprehension` (detailed)
* **Affected Scope:** line 247
* **Recommendation:** Say what is done with the data.

## Counts

Major: 14 (F1-F14). Nit: 9 (F15-F23). Blocker: 0.
