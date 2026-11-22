# Goldfish Review Report: Stage 5 (zoom-out, inventive-catalyst)

**Target:** `docs/designs/herd-escalation.md` (1-277)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |
| `egm-inventive-catalyst` | completed |

Counts (deduplicated): Blocker 0, Major 9, Nit 6.

## Prioritized Findings

### Z1 No event for appending a cause to an open issue - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 24, 99, 114, 225
* **Discrepancy Description**: Event model has no event for a cause added after the issue opens (CUJ 2 `append`). Breaks G1 (derive from GitHub events alone); `parse_answer` answer set undefined after append; `test_one_open_escalation` and CUJ 2 unimplementable.
* **Rationale & Recommendation**: Add a `cause_appended` event (bot comment with hidden marker) or specify body edit plus replay. Pick one.

### Z2 Overrule semantics undefined for decline/escalate verdicts - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`, `egm-inventive-catalyst`
* **Affected Scope:** lines 107, 112
* **Discrepancy Description**: Only `accept` and `contest` have an opposite. A `low_confidence` cause can wrap `decline` or `escalate` (Arbiter check 3), so "follow" and "overrule" are meaningless or circular.
* **Rationale & Recommendation**: Replace with concrete outcomes ("apply finding as written" / "dismiss finding") or define the mapping for all four verdicts.

### Z3 Orchestrator writes `decisions.md`, violating Arbiter sole-writer invariant - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 112; Arbiter design (Technical Plan, Roles); Future Improvements
* **Discrepancy Description**: Arbiter design says `herd_arbiter.py` is the only writer of `decisions.md`; this design has the orchestrator append a `human` line. Also contradicts own Future Improvements ("durable escalation log in decisions.md").
* **Rationale & Recommendation**: Add an Arbiter-side writer function or drop the line; the GitHub ack comment already holds the audit trail.

### Z4 Stale PRD edit work in plan - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 216, 262-265 (Target File 4, Phase 4 grep check)
* **Discrepancy Description**: PRD line 69 already reads `/herd answer <trigger>=<n> [<trigger>=<n> ...]`; the plan item is a no-op.
* **Rationale & Recommendation**: Delete the PRD item and that part of Phase 4; keep the `herd.toml` `[budget]` check.

### Z5 Retroactive revocation of processed answers via replay - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** Technical Plan "All state comes from events", `parse_command`, lines 99, 116, 225
* **Discrepancy Description**: Replay reads `edited` and `author_is_maintainer` from each human comment. A later edit or permission loss makes replay drop an already-acted answer, flipping status and touchpoint count retroactively. Needs a per-comment API fetch on each replay.
* **Rationale & Recommendation**: Make the bot ack comment (actor, comment id, pairs) the only answer event replay reads; do maintainer/edited checks once at processing time. Liabilities: ack becomes a critical write needing idempotent retry keyed by comment id; bot identity check becomes load-bearing.

### Z6 One choice per cause for all findings - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** Triggers, Cause, G5; lines 105-107, 112
* **Discrepancy Description**: `low_confidence` may cover several findings but allows one option; the `decisions.md` human line records a finding id, implying per-finding decisions the syntax cannot express.
* **Rationale & Recommendation**: Allow `<trigger>` or `<trigger>:<finding-id>` keys, bare trigger as default. Cost: parser and test complexity.

### Z7 Rounds escalation duplicates spec PR review - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`, `egm-zoom-out`
* **Affected Scope:** rounds row, CUJ 1, line 110; Arbiter G3; PRD step 8
* **Discrepancy Description**: Policy-escalated Blocker/Major findings stay open, so the loop runs to the round-3 cap and then opens a `rounds` issue whose option 2 is "proceed with open findings listed in the spec PR". Costs up to 3 rounds plus a touchpoint for a routine Arbiter outcome; cost not stated in Risks.
* **Rationale & Recommendation**: Carry human-owned findings straight to the spec PR summary outside the loop exit condition (needs PRD step 8 and Arbiter clarification), or count rounds option 2 as the merge review; at minimum document the cost in Risks.

### Z8 Transient step_failure costs a human touchpoint - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** step_failure row; Risks line 197
* **Discrepancy Description**: Retry is only a human option; flaky failures cost a touchpoint.
* **Rationale & Recommendation**: One automatic retry for transient failures; deterministic fail-closed cases stay immediate (PRD section 8). Needs a classifier and budget accounting.

### Z9 Manual `herd:blocked` removal unrecorded and bypasses ceiling - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`, `egm-zoom-out`
* **Affected Scope:** lines 95, 124, 130, 194; CUJ 8
* **Discrepancy Description**: Manual removal of `herd:blocked` is a human intervention counting zero (flatters median) and resets the ceiling count (G8). Any labeler, including triage role, can toggle `herd:hold`/`herd:blocked`; the stated risk is understated.
* **Rationale & Recommendation**: Add `unblocks` to `touchpoints()` output (derivable from `label_removed`); check actor on label events or state any labeler can toggle; add to Risks.

### Z10 Repeat and rule-version fields speculative - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 114, 130, 193
* **Discrepancy Description**: `repeat_of` is metadata only (ceiling of 3 already bounds repeats); `rule: 1` is read by nothing.
* **Rationale & Recommendation**: Drop both until a second counting rule exists.

### Z11 Altitude: implementation detail in Technical Plan - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 128, 225-233
* **Discrepancy Description**: Full event schema, signatures and `paused_seconds` interval-union detail are implementation-level.
* **Rationale & Recommendation**: Keep status precedence, trigger and command tables; leave signatures to code and tests.

### Z12 Command routing unclear - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 116, 122, 229
* **Discrepancy Description**: `/herd answer` valid only on the escalation issue but `apply_command(state, command, is_maintainer)` has no issue kind; `author_is_maintainer` is both an event field and a parameter.
* **Rationale & Recommendation**: Add issue kind or state the orchestrator filters first; keep one source for maintainer status.

### Z13 Stop vs continue precedence in mixed answers - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 27, 110
* **Discrepancy Description**: Answer mixing `stop` with a continue option (e.g. `rounds=1 budget=2`) has no stated precedence; line 110 implies stop wins.
* **Rationale & Recommendation**: State it in G5 or CUJ 3.

### Z14 "Maintainer" definition shared by three designs - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 13, Open Question 2
* **Discrepancy Description**: Definition (`write`/`maintain`/`admin`) is sound but Triage and Arbiter use the term undefined.
* **Rationale & Recommendation**: Move it to one shared place (PRD glossary).

### Z15 Bot reopening a maintainer-closed issue - Severity: Nit
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** CUJ 7; line 89
* **Discrepancy Description**: Closing is treated as an error to fight; a maintainer wanting to abandon has no signal except `stop`.
* **Rationale & Recommendation**: Reopen once; on second close with no answer, comment pointing at `stop` and stop reopening.

### Notes
* Inventive-catalyst found no false compromise in: events-only state (Alt A), closed answer syntax (Alt C), no-model-call issue body, independent hold and escalation (G4), no timeout auto-answer (Alt F). No corruption findings.
* Cross-design: consistent with Triage and Arbiter on `herd.toml` ownership, Python pin, fallback-counts-zero, low_confidence-on-Nit routing. Conflicts: Z3 (sole writer), Z2/Z7 (Arbiter verdict set and G3).
