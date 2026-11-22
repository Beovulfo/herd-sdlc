# Stage 6 Report: comprehension

**Target:** `docs/designs/herd-triage.md` (lines 1-222; no GoldfishContext)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-comprehension` | completed (raw text verified via Grep, no corruption findings; read only the design) |

## What proposes

When a maintainer labels an issue `herd`, a read-only LLM agent proposes a risk level (`low`, `medium` or `high`). Separately, a deterministic floor is computed from path globs in `herd.yaml` on the base branch and from `risk:*` labels. A record writer stores `effective = max(proposed, floor)` in `.herd/state/<feature>.yaml`. A human can lower `effective` only via a `/herd risk <level>` comment, logged in `risk.override`. Any failure or tampering resolves to `high` (fail closed) or a refusal to proceed. M0 delivers only the floor and a display value; the ratchet and history are deferred to M1.

## How existing system works, per this document

Today a person sets risk by hand (line 17). The PRD, which is external, defines the lifecycle steps, the H1 gate, the Arbiter, the orchestrator and principles P3 and P6. The document does not describe the orchestrator's current behaviour; it says only that a separate "orchestrator design" owns the label workflow, snapshot, agent prompt, comments and rate limits (line 31). A reader can state what Triage will do, but not how the existing system hands it an issue or a feature branch.

## Findings

1. **Major.** Lines 117-123, 22, 31, 111: source of the floor's input paths. `floor(paths, labels, rules)` needs paths from issue text; the agent may return only `risk` and `reason` (line 22); snapshot is delegated to the orchestrator design (line 31). `floor_inputs.paths` is empty in the sample record. Extraction owner and method (regex, agent, other) unstated.
2. **Major.** Lines 25, 70-72, 111: can the G5 tamper check be bypassed. Unstated what recompute reads for paths and labels. Paths live in the agent-editable record (line 100); labels are not in the record. If recompute trusts `floor_inputs`, an agent can empty it. Forged `risk.override` vs real human one is not distinguished.
3. **Major.** Line 60 vs schema lines 102-114: CUJ 3 says `reason` is stored (max 200 chars, inert); schema has no `reason` key. Line 96 says downstream reads the enum, not the reason. Storage and readers unclear.
4. **Major.** Lines 30-31, 37, 152, 168: undefined terms. "Ratchet", "step 5", "edit-rate metric", "shadow mode". Line 37 says edit-rate metric is "not in PRD section 3". "Ratchet" is both Non-Goal and Future Improvement. Shadow mode half-defined (line 152); unclear whether orchestrator G5 check also waits.
5. **Major.** Lines 31, 164: "the orchestrator design" cited as owner with no link or filename.
6. **Major.** Line 100 vs line 83: "A missing or older `schema_version` escalates" does not say to what (`high`, human, comment). Next sentence says unknown enum "fails closed to `high`"; fixture `old_schema_version.yaml` is under G4 (`high`). Conflict.
7. **Major.** Lines 87, 100: where the record lives and who commits it. On `herd/*` branches (agent-pushable, premise of CUJ 5) yet only the writer writes it. Unclear who commits, how a later agent commit is told apart, and whether the record is on the feature branch while `herd.yaml` is read from base.
8. **Nit.** Line 94: "An edit to `herd.yaml` counts as touching a `high` path", but no diff exists at intake (line 17); when it applies is unclear.
9. **Nit.** Lines 91, 98: `race` as `triage.cause`; retry-once outcome on second failure unstated; Failure paragraph names retry only for timeout and malformed.
10. **Nit.** Line 89: label combinations (`risk:high` plus `risk:low`; `risk:low` on a medium-rule match) not spelled out.
11. **Nit.** Lines 13, 152, 222: P3 and P6 barely glossed; "EGM" never expanded; PRD cited by section number, filename only at line 207.
12. **Nit.** Line 153: round counter and budget fields absent from sample schema; unclear what is lost on rollback.
13. **Nit.** Line 190: `base_hash` / "base record hash" undefined (record file hash or base commit?).
