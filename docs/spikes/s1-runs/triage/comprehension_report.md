# Goldfish Review Report: Comprehension Test

**Target:** `docs/designs/herd-triage.md` (FeatureRange 1-153, DetailedRange 154-198). Reviewer had no GoldfishContext and no document standard.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-comprehension` | completed |

## What proposes (FeatureRange, lines 1-153)

When a maintainer labels an issue `herd`, an LLM agent proposes a risk level (low, medium or high). Separate code computes a minimum risk ("floor") from path-glob rules in `herd.yaml`. That code writes `effective = max(proposed, floor)` to `.herd/state/<feature>.yaml`, and the agent never writes the floor or effective fields. Risk can only ratchet up as more path information arrives, such as the spec at step 5. Only a human override at the H1 gate can lower it, and each change is logged in `risk.history`. Any failure produces `effective: high` with `triage.status: fallback`. The rollout starts in shadow mode. The size path from the PRD is dropped.

## How the system works per this document (DetailedRange, lines 154-198)

The plan adds a `floor` block to `herd.yaml` and three Python standard-library scripts. `triage_floor.py` holds the pure floor and effective functions. `triage_record.py` is the validating, append-only writer that fails closed to high. `triage_check.py` runs the fixtures in `fixtures/triage/` and exits 0 only if all pass. There are seven fixtures, and the PRD gets edited to drop the size path. Beyond that the reader could not paraphrase the section, because the heading for item 1 and the Verification Plan (lines 191-198) are corrupted. The reader cannot tell how the agent call, the label trigger, or the orchestrator and Arbiter integration get built, or which test cases are verified and how. The detailed plan creates no agent prompt, no workflow or trigger, and no `/herd retriage` handler. It also has no file for the ratchet, the human-override path, or the comment posting.

## Prioritized Findings

### Item 1 (`herd.yaml`) heading and Type/Scope cut off - Severity: Blocker
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** L158-160
* **Description:** Create vs Modify is unknowable; L160 starts mid-word ("Scope**:").

### Verification Plan truncated - Severity: Blocker
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** L188-198
* **Description:** Fragments only ("scripts/triage_check.py fixtures/triage/` 0", "CUJ", "shadow-mode", stray "EGM*" at L198). No runnable steps, no mapping of tests to G1-G4 or shadow-mode agreement.

### CUJ 4 title, Given and When missing - Severity: Blocker
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** L59-62 (Then at L63)
* **Description:** Human override trigger and who edits the H1 PR are unclear.

### Alternative A title and Pros/Cons/Rejection missing - Severity: Blocker
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** L117-121
* **Description:** Only "proposal adds little over floor" survives; the reason the LLM is kept is not stated.

### Non-Goals, CUJ 3 Then, Trust rule fragments - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** L26-29, L57, L80-81
* **Description:** At least two non-goals are lost. CUJ 3 Then is cut after "one-line". Trust rule "An edit `herd.yaml` `herd.yaml`" has no verb or outcome; which hash goes with the label is unclear.

### Undefined project terms - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** L11, L15, L19-22, L141
* **Description:** Herd lifecycle, PRD section 5, H1 Intent gate, Arbiter, orchestrator, P3, P6, S2 baseline, M0/M1/M3, L0, Full/Lite, step 5, H1 edit rate. PRD named but not linked. Add glossary or links.

### Actors and trigger unstated - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** L11, L73, L112
* **Description:** The doc never says what runs the flow (Action, bot, CLI) or where the agent runs; the plan creates no workflow file connecting scripts to the trigger.

### Path inconsistency for fixtures - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** L19, L45, L191
* **Description:** `fixtures/` vs `fixtures/triage/`; CUJ 1 says the fixture lives "in `scripts/triage_check.py`", contradicting item 5.

### Floor `medium` vs `low` rule self-inconsistent - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** L75, L48-51
* **Description:** Unclear whether "known" means a non-empty path list, and whether a labelled issue with no paths counts as known.

### Record authority before and after H1 unclear - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** L86-87, L129
* **Description:** Record created at intake yet H1 PR value authoritative; drift handling undefined (L129 rejects PR-only storage). "Escalates instead guessing" does not say to whom.

### PRD divergence decision status ambiguous - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** L33, L183-186
* **Description:** Open Question says decide before build; item 6 already edits the PRD.

### `triage.status: failed` undefined - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** L92, L22
* **Description:** `ok | failed | fallback` listed, but only `ok` and `fallback` are described.

### Garbled sentences - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** L140, L143, L149
* **Description:** "Size cannot set budget"; `risk_delta` and "budget used" undefined; "read edit rate only next canary pass rate" unparseable.

### Function signature conjunction missing; fixture naming mismatch - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** L165, L180, L69
* **Description:** "floor(...) `effective`(...)" lacks conjunction. `ratchet_up` vs `ratchet_only_up`; `bad_herd_yaml` maps to no CUJ or goal; "Fixtures generic content only" undefined.

### Undefined `/herd retriage` and correlation key - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** L80, L143
* **Description:** Named without definition or place in the file plan.
