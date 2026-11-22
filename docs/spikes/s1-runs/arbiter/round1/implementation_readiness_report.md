# Goldfish Review Report: Stage 9 (implementation readiness, codebase details, style)

**Target:** `docs/designs/herd-arbiter.md` (DetailedRange, lines 198-251). Standard: implementation-readiness-standard. Verdict (readiness): NOT READY.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-implementation-readiness` | completed |
| `egm-codebase-details` | completed |
| `egm-style` | completed |

## Prioritized Findings

2 Blocker, 10 Major, 4 Nit (after dedup; highest severity kept on merge). Absent paths (`scripts/`, `rubrics/`, `agents/`) are marked Create/Modify and not flagged; no reuse candidates exist in the repo.

### R-B1 No function owns the orchestrator work - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details` (Major)
* **Affected Scope:** lines 210-219 vs 90, 92, 36, 108
* **Description:** Technical Plan says `herd_arbiter.py` builds input, validates, applies policy and is the only writer of `decisions.md`. Target Files list only `finding_id`, `validate`, `format_lines`, `sample`, `overturn_rate`, `summary`. Missing: input assembly (order, data-block delimiters, dedup), the citation re-ask (`validate` is pure and never raises, so cannot re-ask), parsing prior rulings from `decisions.md`, appending to `decisions.md`, computing `same_model`, reading `herd.yaml`, producing audit lines, entry point.
* **Recommendation:** Add the functions with signatures and call sequence, or state they belong to the orchestrator design and name the interface this module exposes.

### R-B2 "stdlib only" conflicts with reading `herd.yaml` - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** lines 212, 239, 115
* **Description:** Module needs `arbiter.model` and `arbiter.enabled` from `herd.yaml`; the standard library has no YAML parser. Who reads the file and who supplies the Elephant model is undecided.
* **Recommendation:** Pass values as arguments, or add a dependency with a stated reason.

### R-M1 Data shapes and citation rules undefined - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** lines 108, 125, 215
* **Description:** Keys of `findings` dicts (is `id` precomputed; persona/scope/text/severity), returned ruling dict, `prior[id]` structure (last round only?), `header` keys. Line numbers 1-based/inclusive, `start > end`, quote matching (substring or normalised), path compare, "same citation" for flip, flip when prior was `escalate`, SHA-1 input encoding, `|`/newline replacement.
* **Recommendation:** Specify each shape and rule in the plan.

### R-M2 Policy-check edge cases unspecified - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** line 215, policy checks 1-3
* **Description:** Per-ruling schema errors vs whole-output `malformed`; unknown verdict/confidence; duplicate id handling; `unknown` id has no severity to copy; citation requirement for `defer`/`contest`/`escalate` (line 24).
* **Recommendation:** State behaviour for each case, as a table.

### R-M3 `format_lines` under-specified; nothing produces audit lines - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** lines 28, 216
* **Description:** Header keys, escape characters, whether 140 cap includes a truncation marker, citation field for `escalate`, hash and length for `rubric=` and `spec_sha=`, date format, append-only guarantee, and the producer of `audit|...` lines.
* **Recommendation:** Specify the format fully and add an audit-line writer.

### R-M4 `sample` and `overturn_rate` semantics ambiguous - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style` (nit on 1-based)
* **Affected Scope:** lines 217-218
* **Description:** Source and base of `feature_index` (1-based?), return shape "split by `same_model`", `n == 0`, denominators of `escalate_rate`/`defer_rate`, which ruling an audit line binds to when an id repeats across rounds, no line parser for `summary`/`overturn_rate`.
* **Recommendation:** Define each, add a parser function.

### R-M5 `summary` has no exact format - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** lines 62, 219
* **Description:** CUJ 3 requires a "Contested Blocker and Major findings" section; heading and layout not given; what `test_contest_listed_in_summary` asserts is unstated.
* **Recommendation:** Give the exact heading and layout.

### R-M6 Test plan is names without cases - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** lines 204, 221-224
* **Description:** No class layout (Phase 1 runs `TestValidate`), no inputs/expected. `test_injected_finding_fixture` cannot test model behaviour offline; must say it feeds fabricated output to `validate`. No tests for `finding_id` normalisation, unset-model `same_model`, re-ask, `n == 0`, audit binding.
* **Recommendation:** Add a test / input / expected table and class layout.

### R-M7 Rubric rule count inconsistent and exit check not checkable - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style` (nit)
* **Affected Scope:** lines 131, 206, 226-229
* **Description:** Line 229 says five `egm-resolve` rules plus low confidence; Phase 3 says "5 rules"; line 131 lists a different five and omits "A wish to contest is not evidence"; one `egm-resolve` rule ("You wrote the document") does not apply to the Arbiter. `grep -c "egm-resolve"` counts lines, not rules.
* **Recommendation:** Name the exact rules and count; give a per-rule grep exit check.

### R-M8 "Every G and CUJ names a test" is false for CUJ 7 - Severity: Major
* **Reviewer Lens:** `egm-style` (verified by Grep: `Test:` lines exist only for CUJ 1-6)
* **Affected Scope:** lines 82-88, 224, 246
* **Recommendation:** Add a test name or narrow to "Goals G1-G8 and CUJ 1-6"; spell out "G".

### R-M9 Agent file and `herd.yaml` in no phase's exit check; ordering dependency - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** lines 200-206, 231-239
* **Description:** Frontmatter (name, description, tools) unspecified; how `arbiter.model` is applied and how "no inherited project instructions" is achieved unstated; rubric injected by the script (line 92) yet agent "points to" it; `herd.yaml` created by Triage design, no ordering or fallback; `rubrics/` is a new directory.
* **Recommendation:** Specify the file, add to a phase with an exit check, add prerequisite or fallback.

### R-M10 Inconsistent test commands - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness` (Major), `egm-codebase-details`, `egm-style` (Nit)
* **Affected Scope:** lines 204-205, 244
* **Description:** Module form `scripts.test_herd_arbiter` vs path form `scripts/test_herd_arbiter.py`; module form needs `scripts` importable (maybe `scripts/__init__.py`).
* **Recommendation:** Use the module form; state whether `__init__.py` is needed.

### R-N1 "Python 3.13" unsourced - Severity: Nit
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** line 212
* **Recommendation:** Confirm against the repo or relax.

### R-N2 Vague wording in plan - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 215, 224, 227, 236, 239
* **Description:** "set as in the policy list" has no referent; "inline generic findings"; "outside the data blocks"; Triage design file unnamed; `model: null` meaning unstated; redundant mention of `test_accept_written`, `test_contest_listed_in_summary`.
* **Recommendation:** Reference the cause list by section, say "inline fixture findings, no external files", name the Triage design path, state null means harness default, list only `test_reason_escaped` as the addition.

### R-N3 Redundant "5"/"five" numerals - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 206, 229
* **Recommendation:** Use one form (folded into R-M7 fix).

### R-N4 No round-trip integration test - Severity: Nit
* **Reviewer Lens:** `egm-codebase-details`
* **Affected Scope:** line 247
* **Description:** `format_lines` output feeds `overturn_rate` and `summary` with no test covering the round trip.
* **Recommendation:** Add one round-trip test.
