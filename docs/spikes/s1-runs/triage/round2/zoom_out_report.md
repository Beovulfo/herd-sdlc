# Stage 5 Report: zoom-out and inventive-catalyst

**Target:** `docs/designs/herd-triage.md` (lines 1-222)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed (verified raw text via Grep, no corruption findings; did not read the PRD) |
| `egm-inventive-catalyst` | completed (caveat: did not Grep raw file; PRD path not found by it; line refs from lossy view, findings 1-2 should be checked against raw text) |

## Zoom-out findings

### Z1 Tamper check is self-referential - Major
* **Scope:** lines 25, 68-72, 100, 112-113
* G5 recomputes `effective` from `herd.yaml` and `risk.override`, but `risk.override` lives in the record on an agent-pushable `herd/*` branch. An agent commit can forge an override and verification passes. Needs an authoritative source outside the file (maintainer comment timeline, or record on base branch). Breaks P6.

### Z2 Record lacks inputs verification needs - Major
* **Scope:** lines 25, 89, 110-111
* `floor` depends on labels (`risk:low/medium/high`) but `floor_inputs` stores only `paths` and `source`. Recompute with today's `herd.yaml` gives false tamper alarms after rule changes. Pin inputs and/or `herd.yaml` hash, or decide that a changed rule set legitimately re-floors.

### Z3 Altitude drop: Python signatures in design body - Major
* **Scope:** line 190
* State interfaces (agent allowlist, writer events, verifier); leave signatures to implementation.

### Z4 LLM M0 value unproven - Major
* **Scope:** lines 17, 128-132, 89
* Hypothesis is most features floor at `medium`, so `max(proposed, floor)` rarely differs. Agent, injection surface, allowlist parser and shadow rollout are built to test it, while the writer, verifier and race handling are built either way. Consider rules-only first, agent later behind same schema. Alternative A is rejected only "by author".

### Z5 Concurrency machinery premature - Nit
* **Scope:** lines 91, 162
* Base-record-hash race check and retry assume concurrent writers, yet a single orchestrator calls the writer. Justify or drop; `race` also adds a `triage.cause` value.

### Z6 Glob matcher reuse not examined - Nit
* **Scope:** lines 89, 160, 38
* Custom segment-glob semantics; check `pathlib.PurePath.full_match` (3.13) or an existing library. CODEOWNERS (open question, line 38) is the obvious reuse; a parallel rule set will drift.

### Z7 Rollback is not a rollback - Nit
* **Scope:** line 153
* Ignoring `.herd/state` drops round counter and budget fields. Move fields first or state as a Rollout precondition.

### Z8 Phase 4 exit check weak - Nit
* **Scope:** line 183 (edits at line 210)
* `grep -n "size" PRD*.md` cannot confirm the three listed edits (section 5 row, M3 line, `/herd risk` command). Check them directly.

Passes: context and root-problem focus, agent proposes with deterministic floor bound (P6), disciplined non-goals, strong CUJ-to-fixture mapping.

## Inventive-catalyst findings

### I1 Agent-editable record, detection recomputes from the record's own inputs - Major
* **Scope:** lines 25, 68-72, 100, 102-114, 190
* Agent can edit `floor_inputs.paths` to `[]` or forge `override: {actor: human}` and the record recomputes cleanly. Nothing enforces "humans override via `/herd risk`".
* **Resolution (extraction):** authoritative record on base branch or a bot-only ref; derive human override from comment author plus `/herd risk` comment; recompute `floor` from issue snapshot matched to `body_hash`.
* **Liabilities:** second write identity or protected ref; stale reads from feature branch; GitHub API and comment retention become dependencies.
* Overlaps Z1.

### I2 Who extracts paths at intake; low unreachable without label - Major
* **Scope:** lines 17, 22, 50-54, 89, 119, 163, 190
* Floor needs `paths`, but G2 limits agent output to `risk` and `reason`. No step names who extracts paths. A proposed `low` never takes effect without a maintainer `risk:low` label, so the agent only contributes medium to high.
* **Resolution (segmentation):** agent emits untrusted candidate path list plus risk enum; deterministic code globs the list (injection can only omit paths = same as blind `medium`). Or use a deterministic regex extractor in M0. Name the owner and add a fixture.
* **Liabilities:** bigger injection surface; wrong paths over-escalate; regex misses prose.

### I3 Every failure cause falls to `high` - Nit
* **Scope:** lines 24, 91, 95, 98
* Timeout, malformed and benign race all set `effective: high`; race fallback could clobber a human-set value (conflicts with line 95).
* **Resolution (cushioning):** for `timeout`, `malformed`, `race` fall back to `effective = floor` with `triage.status: fallback`; keep `high` for `herd_yaml`, `schema`, unknown enum; re-read and re-apply on race.

### I4 Rollback couples to unrelated state - Nit
* **Scope:** lines 100, 153
* **Resolution (segmentation):** put `risk` and `triage` in their own file or top-level key owned by the Triage writer. Needs coordination with orchestrator design. Overlaps Z7.

### I5 `herd.yaml` edit rule has no M0 enforcement point - Nit
* **Scope:** lines 94, 159
* Triage runs at intake with no diff; step 5 ratchet deferred to M1. Mark rule as M1 or add M0 enforcement (e.g. CI check failing `herd/*` PRs that touch `herd.yaml`).

No false compromise detected: floor/proposal split, allowlist parsing, single writer with base-hash check, Alternatives A to C.

## Notes
* Both reviewers reported the persona path `agents/egm-*.md` did not exist; actual files are `agents/zoom_out.md` etc. Reviews proceeded.
