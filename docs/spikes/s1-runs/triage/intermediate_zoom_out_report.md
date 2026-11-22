# Goldfish Review Report: Intermediate Zoom Out

**Target:** `docs/designs/herd-triage.md` (lines 1-198)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |

Verdict: pass with Major fixes. Context sufficient; the root problem (steerable LLM risk proposal, needs an outside-LLM floor) is clear and matches PRD P6 and the PRD risk-floor paragraph. Reviewer verified with Grep that the file is not truncated or garbled (earlier Blockers about missing text in stage 5 came from a lossy read view and do not stand). No existing code in the repo to reuse (greenfield).

## Prioritized Findings

### Duplicated, unclear ownership of state writes - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** L63, L73, L86, L163-171
* **Description:** L73 says record writer is the only writer; L86 and CUJ 4 have the orchestrator writing. G2/G3 are unenforced if the orchestrator writes directly. Fix: orchestrator calls the record writer.

### Scope ambiguity: retriage, lazy runs, race - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** L29, L81, L84, L141
* **Description:** Non-Goal bars automatic re-run; `/herd retriage` is manual and has no CUJ, test or fixture. "Triage runs lazily" is unspecified in the plan. "Race" has no definition or test. Define each or cut it.

### Unresolved PRD divergence hedged in the plan - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** L33, L183-186, PRD L77
* **Description:** Open Question says decide before build, yet file 6 already edits the PRD "or restores them in this design". Make the call (drop size and path, per L26) and state it unconditionally.

### G1 verification path and file layout inconsistent - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** L19, L45, L180, L191
* **Description:** `fixtures/` vs `fixtures/triage/`; CUJ 1 "fixture in `scripts/triage_check.py`" reads wrong. G2-G4 name test cases (`agent_cannot_set_floor`, `history_append_only`, `failure_defaults_high`, `human_override_logged`, `ratchet_only_up`) that do not map to the seven fixtures; `triage_check.py` is described as a fixture loader only.

### Speculative fields and signals - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** L98, L143
* **Description:** `risk_delta` has no consumer; `run_id`, correlation key, `herd_yaml_hash`, `failed` status unused in M0. Alternative C's rejection reason does not require a separate state record plus a PR value, which adds two-store drift. Keep only fields a named reader uses.

### Injection CUJ contradicts itself on the reason field - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** L57, L82, L88-101, L106
* **Description:** CUJ 3 stores a one-line reason as inert data; L82 says raw issue text is never copied; the schema has no reason field. Decide whether the reason is stored and where. The grep check is weak.

### Default rule set vs CODEOWNERS - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** L36, L80, L161
* **Description:** If CODEOWNERS seeds defaults, new `floor` globs and hard-coded examples may be unnecessary (reuse win). Resolve before M0.

### Labels have no mapping to floor levels - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** L75-77, L165
* **Description:** `floor(paths, labels, rules)` takes labels but `herd.yaml` holds only glob lists.

### Borderline low altitude - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** L165, L168
* **Description:** Function signatures and a three-script split for about 100 lines; one module plus a test would do.

### Speculative canary and edit-rate threshold - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** L37, L147-150
* **Description:** Golden-set canary correctly parked in Future Improvements; threshold does not block M0.

### Idempotency in Rollout conflicts with manual-only retriage - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** L81, L141
* **Description:** "Idempotent by issue body hash" is a behavior requirement and belongs in the Technical Plan.

### Non-Goals wording and Rollback conflict with PRD - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** L24-26, L142, PRD L91
* **Description:** "Size and path (Full or Lite)" reads as three items. Rollback "ignore `.herd/state`" drops round counter and budget the PRD assigns to the record.

## Positives
Agent/code split, fail-closed defaults, up-only ratchet and shadow-mode rollout are minimal and match P6.
