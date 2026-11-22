# Goldfish Review Report: Implementation Readiness

**Target:** `docs/designs/herd-triage.md` (DetailedRange, lines 154-198). Standard: `implementation-readiness-standard`.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-implementation-readiness` | completed |
| `egm-codebase-details` | completed |
| `egm-style` | completed |

Repo is greenfield (no scripts, fixtures or herd.yaml), so every file is a Create. All three reviewers found the range intact (no truncation).

## Prioritized Findings

### stdlib only cannot parse YAML - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`
* **Affected Scope:** L158, L165, L170-171, L175, L178-180
* **Description:** `herd.yaml`, the state record and fixtures are YAML; Python stdlib has none. Plan must choose PyYAML, a hand parser, or JSON/TOML (`tomllib` is stdlib). Also pin a minimum Python version.

### Glob dialect and default rule set undefined - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`
* **Affected Scope:** L34, L75, L161, L165
* **Description:** `fnmatch`, `pathlib` match and `glob.translate` (3.13+) differ on `**`. "Document the default rule set" never lists it, a security-relevant default the implementer would invent. Label handling is unspecified (labels vs globs). `herd.yaml` schema covers only `floor` although L140 and PRD L121-123 mention budget and concurrency keys. State which of `migrations/**`, `auth/**`, `billing/**` are real defaults and their levels.

### PRD edit is an either/or - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`
* **Affected Scope:** L33, L183-186
* **Description:** "move size and path to Future Improvements, or restore them" breaks the Zero-Decision Rule and is an unresolved Open Question. The PRD has no "Future Improvements" section; the target line (PRD L77) and destination are unnamed. Pick one, name exact lines and text.

### File list does not cover the Technical Plan behavior - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** L163-176 vs L71-113
* **Description:** Nothing creates or changes: label-triggered workflow or entry point, `/herd retriage` handler, issue snapshot and hash (algorithm unspecified), agent definition or prompt with read-only restrictions, comment posting, orchestrator H1 write and override path, step 5 recompute, shadow mode, `risk_delta`, correlation key. Add files and steps or mark out of scope for this plan.

### `triage_record.py` has no interface - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`
* **Affected Scope:** L171, L86
* **Description:** No input channel (CLI, stdin, call), no "any error" boundary, no description of writing to `herd/<feature>`, producing `run_id` and `at`, detecting agent-supplied fields, `schema_version` escalation, or append-only enforcement on existing files. "Fail closed to `high` and `fallback`" does not say which field or value. "The record shape above" names no section.

### No phasing or checkpoints - Severity: Blocker
* **Reviewer Lens:** `egm-style`, `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** L154-194
* **Description:** Flat file list. Suggested order: floor logic plus fixtures and checker; record writer; check runner; workflow and agent wiring in shadow mode; `herd.yaml`; PRD edit. Each phase needs an exit check.

### `triage_floor.py` signatures and rules underspecified - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`
* **Affected Scope:** L165-166
* **Description:** No types for `paths`, `labels`, `rules`, or `effective()` return; level order (low<medium<high) unstated; "unknown input" ambiguous (empty, partially matched, None, unrecognized level); `history` format and human-entry validation undefined (actor must be `human`? `to` equals new level?); ratchet never-lowers is not an explicit behavior. Add exact signatures and a rule table.

### Fixture contract and check-runner invocation inconsistent - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`
* **Affected Scope:** L19, L45, L175-181, L191
* **Description:** `fixtures/` vs `fixtures/triage/`; no-argument load (L175) vs directory argument (L191); output "failing only" (L176) vs "one line per fixture" (L191). `*.yaml` glob despite seven known names (L180): list exact paths. Fixture schema, handling of non-deterministic `run_id` and `at`, and "generic content only" are undefined. CUJ 1 says fixture is "in `scripts/triage_check.py`".

### Test coverage does not match CUJs and goals - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`
* **Affected Scope:** L19-22, L69, L180, L193
* **Description:** G2-G4 test names (`agent_cannot_set_floor`, `history_append_only`, `failure_defaults_high`, `human_override_logged`, `ratchet_only_up`) match no fixture (`human_override`, `ratchet_up`, `failure_default`). No fixture for the first two; `bad_herd_yaml` ties to no CUJ. Missing edge cases: unknown enum fails closed, older `schema_version` or missing record, body-hash idempotency, retriage not overwriting human value, `herd.yaml` read from base branch, label-based match. Injection assertion mechanism undefined. Add a CUJ-to-fixture table.

### E2E and shadow-mode step not runnable - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`
* **Affected Scope:** L194
* **Description:** No procedure, command, output location, agreement metric or pass threshold. "S2" is undefined in range; `docs/spikes/s2-baseline.md` exists and should be cited. M0/M1 boundary for the ratchet (L77) is not stated.

### Type/Scope entries mix file type and behavior - Severity: Nit
* **Reviewer Lens:** `egm-style`, `egm-codebase-details`
* **Affected Scope:** L160, L167, L174, L185
* **Description:** Move behavior and signatures to Proposed Changes; a short pseudocode block per script is the cheapest fix.

### Minor clarity items - Severity: Nit
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`
* **Affected Scope:** L158, L160, L183, L190, L192, L198
* **Description:** Say whether `herd.yaml` exists today and how the `floor` block lands on the base branch; say whether example rules are committed or docs only; confirm the em-dash PRD filename matches the repo file exactly; "Build: n/a"; "no linter configured" (and whether `py_compile` is expected); drop "Drafted with EGM" footer unless the template requires it.
