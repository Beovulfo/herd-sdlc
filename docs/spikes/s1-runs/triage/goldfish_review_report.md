# Goldfish Annotated Review Report

**Target:** `docs/designs/herd-triage.md` (full file, 198 lines before resolve)
**Source:** `consolidated_review_report.md`. Run caveat 1 there: the false "corrupted text" findings were dropped by the synthesizer. Not re-triaged here.
**Resolver:** the Elephant (the session that drafted the design). Gate answer supplied: `auto accept`.

## Prioritized Findings & AI Suggestions

### [B1] `egm-design` - Severity: Blocker
***AI Suggestion:*** PROPOSE FIX
* ***Justification:*** Valid. G2 only covers the Triage call. Later agent commits on `herd/<feature>` can edit the record.
* ***Proposed Edit:*** Technical Plan and G2: the orchestrator recomputes `floor` and `effective` from `herd.yaml` (base branch) and `risk.history` every time it reads the record, and refuses to proceed on a mismatch. Add test `state_file_tamper_detected`.

### [B2] `egm-zoom-out` - Severity: Blocker
***AI Suggestion:*** ESCALATE
* ***Justification:*** The finding is accurate about the PRD (M0 is L0/L1, H1 is mandatory). Whether M0 should ship the audit trail and ratchet or defer them to M1 is a scope decision that no file in the repo settles. The G3 metric is not in PRD section 3.
* ***Proposed Edit:*** None. Given to the user.

### [B3] `egm-implementation-readiness` - Severity: Blocker
***AI Suggestion:*** PROPOSE FIX
* ***Justification:*** Valid. The PRD names `herd.yaml` and `.herd/state/<feature>.yaml`, so the format is fixed by the PRD.
* ***Proposed Edit:*** Use PyYAML `safe_load` as the one dependency, with the reason stated (PRD fixes YAML; stdlib has no YAML parser). Pin Python and PyYAML versions when implementing.

### [B4] `egm-implementation-readiness` - Severity: Blocker
***AI Suggestion:*** PROPOSE FIX
* ***Justification:*** Valid and security-relevant.
* ***Proposed Edit:*** Define the matcher: match by path segment, `*` does not cross `/`, `**` matches zero or more segments, no negation. List the default rule set and the label mapping (`risk:high`, `risk:medium` raise the floor to that level). Leave CODEOWNERS reuse as an Open Question.

### [B5] `egm-implementation-readiness` - Severity: Blocker
***AI Suggestion:*** PROPOSE FIX
* ***Justification:*** Valid. The either/or must be decided.
* ***Proposed Edit:*** Decide: drop size and path from M0; Triage runs at all levels including L0; PRD edit named exactly (step 1 row of the section 5 table loses size and path; section 7 M3 line gains "size and path return with the Lite path").

### [B6] `egm-implementation-readiness` - Severity: Blocker
***AI Suggestion:*** PROPOSE FIX
* ***Justification:*** Valid. The plan covers 3 files while the Technical Plan describes a workflow.
* ***Proposed Edit:*** Declare the orchestration wiring (label workflow, issue snapshot, agent prompt, comment posting, retriage, shadow mode) out of scope here and owned by the orchestrator design, and list it under Non-Goals. The plan covers the module, fixtures and PRD edit.

### [B7] `egm-implementation-readiness` - Severity: Blocker
***AI Suggestion:*** PROPOSE FIX
* ***Justification:*** Valid.
* ***Proposed Edit:*** Specify `write_record` inputs, allowlisted agent keys (`risk`, `reason`), the error boundary and the exact fallback fields.

### [B8] `egm-style` - Severity: Blocker
***AI Suggestion:*** PROPOSE FIX
* ***Justification:*** Valid.
* ***Proposed Edit:*** Add ordered phases, each with an exit check.

### [M1] `egm-zoom-out` - Severity: Major
***AI Suggestion:*** PROPOSE FIX
* ***Justification:*** Valid. The claim that most features land on `medium` is a hypothesis, not a measured fact.
* ***Proposed Edit:*** Label it a hypothesis. State that the LLM proposal is advisory until measured against the S2 baseline in `docs/spikes/s2-baseline.md`. The threshold stays an Open Question because it needs S2 data.

### [M2] `egm-inventive-catalyst` - Severity: Major
***AI Suggestion:*** ESCALATE
* ***Justification:*** The fix (floor at least `medium` unless a maintainer confirms scope) is a trade-off: it removes most of the proposal's value and strengthens Alternative A. This is a product judgment.
* ***Proposed Edit:*** None. Given to the user.

### [M3] `egm-inventive-catalyst` - Severity: Major
***AI Suggestion:*** PROPOSE FIX
* ***Justification:*** Valid. The write rules contradict each other.
* ***Proposed Edit:*** One writer (the module) called with typed events (`triage`, `human_override`, `ratchet`). Automatic events never lower `effective`. After a human override, a ratchet recomputation does not change `effective`; it appends a `floor_exceeds_override` history entry. A ratchet rise re-opens H1 at most once per feature.

### [M4] `egm-zoom-out` - Severity: Major
***AI Suggestion:*** ESCALATE
* ***Justification:*** Same scope decision as B2.
* ***Proposed Edit:*** None. Given to the user with B2.

### [M5] `egm-zoom-out` - Severity: Major
***AI Suggestion:*** PROPOSE FIX
* ***Justification:*** Valid. Two authorities force the orchestrator to parse a PR body.
* ***Proposed Edit:*** The record is the single authority. The H1 PR displays it. A human override is a maintainer-only `/herd risk <level>` command that calls the writer. This adds one command to PRD section 4; noted in Open Questions.

### [M6] `egm-inventive-catalyst` - Severity: Major
***AI Suggestion:*** PROPOSE FIX
* ***Justification:*** Valid.
* ***Proposed Edit:*** Retry transient failures once; fail closed at once for schema or `herd.yaml` invalidity. Record `cause` in `triage.status: fallback`. Define "race" as two writes with the same base record hash.

### [M7] `egm-design` - Severity: Major
***AI Suggestion:*** PROPOSE FIX
* ***Justification:*** Valid. G1 and "Arbiter ignores" read as a contradiction.
* ***Proposed Edit:*** Clarify: the record is always written and G1 always holds; shadow mode only means the Arbiter does not read it. Cite `docs/spikes/s2-baseline.md` and name the agreement measure. Threshold stays an Open Question.

### [M8] `egm-design` - Severity: Major
***AI Suggestion:*** PROPOSE FIX
* ***Justification:*** Valid.
* ***Proposed Edit:*** Add a short Risks and Mitigations table.

### [M9] stage 7 and 9 reviewers - Severity: Major
***AI Suggestion:*** PROPOSE FIX
* ***Justification:*** Valid.
* ***Proposed Edit:*** Use `fixtures/triage/` everywhere. Add a CUJ-to-fixture table. Runner takes one argument and prints one line per fixture.

### [M10] `egm-implementation-readiness` - Severity: Major
***AI Suggestion:*** PROPOSE FIX
* ***Justification:*** Valid.
* ***Proposed Edit:*** Give signatures and level order in the plan.

### [M11] `egm-zoom-out` - Severity: Major
***AI Suggestion:*** PROPOSE FIX
* ***Justification:*** Valid. Three scripts and a runner for a small module is over-decomposed.
* ***Proposed Edit:*** One module `scripts/herd_triage.py` and one test file `scripts/test_herd_triage.py`.

### [M12] `egm-style` - Severity: Major
***AI Suggestion:*** PROPOSE FIX
* ***Justification:*** Valid.
* ***Proposed Edit:*** G2 mechanism: the agent output is parsed against an allowlist (`risk` enum, `reason` string, nothing else); any other key is rejected.

### [M13] `egm-structural` - Severity: Major
***AI Suggestion:*** CONTEST (part), PROPOSE FIX (part)
* ***Justification:*** Contest "Rejected by author": `egm-draft` `SKILL.md` step 4.3 requires `Rejected by author: [technical rationale]` and bars only `Rejected by maintainer` without a link. The heading level of `### Future Improvements` is valid.
* ***Proposed Edit:*** Change `### Future Improvements` to `##`. Keep the rejection wording.

### [M14] `egm-comprehension` - Severity: Major
***AI Suggestion:*** PROPOSE FIX
* ***Justification:*** Comprehension gap; not contested.
* ***Proposed Edit:*** Add a short Terms list with PRD section references.

### [M15] `egm-comprehension` - Severity: Major
***AI Suggestion:*** PROPOSE FIX
* ***Justification:*** Valid.
* ***Proposed Edit:*** Define "known input": at least one path named or one `risk:*` label. A labelled issue with no paths is unknown, so `medium`.

### Nits - Severity: Nit
***AI Suggestion:*** DECLINE, except two
* ***Justification:*** Wording nits are not worth a pass. PROPOSE FIX for two: remove the undefined `failed` status value; reword the Non-Goals size and path line.
