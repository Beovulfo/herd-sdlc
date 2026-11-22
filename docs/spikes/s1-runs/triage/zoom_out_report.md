# Goldfish Review Report: Initial Zoom Out

**Target:** `docs/designs/herd-triage.md` (lines 1-198)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |
| `egm-inventive-catalyst` | completed |

## Prioritized Findings

### Blocker: Context and spec text incomplete or fragmentary - Severity: Blocker
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** L26-30, L47-51, L57-63, L80, L117-121, L158-160, L191-198
* **Description:** Non-Goals are fragments; CUJ 2 lacks heading and Given; CUJ 3 and CUJ 4 lack parts; Trust rule L80 is cut off at the herd.yaml-edit rule (security-critical); Alternative A has no rationale; target file 1 has no heading; Verification Plan is truncated and lacks ratchet and shadow-mode checks. The document is written in a telegraphic style that drops articles and connectives, so a fresh reader cannot tell what is decided.
* **Note:** Reviewer said severity drops to Nit if this is only a rendering artifact. The file read (L20-L90) confirms real missing words (for example L28, L35, L73, L75, L80), so treat as real.

### Blocker: Design not justified against the PRD in M0 - Severity: Blocker
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** L15, L21, L127-143
* **Description:** M0 supports L0/L1 only; H1 is human-required for every feature, and Rollback (L142) and shadow mode (L141) ignore the value. Nothing in M0 consumes risk, yet the design builds a floor engine, ratchet, append-only history, fail-closed fallback, retriage and hash idempotency. G3's "H1 edit-rate" metric is not in PRD section 3.
* **Fix:** Name the concrete M0 consumer, or cut to a minimal M0 and defer audit trail and ratchet to M1.

### Alternative A (rules only, no LLM) not evaluated - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** L117-121, L15, L47-51
* **Description:** Most issues name no paths and land at `medium` from rules alone. The LLM adds only the low/high distinction, which is the only injection-exposed part (P6) and drives G2, CUJ 3, sandbox, `risk_delta`, canary. Measure on the S2 baseline, or ship the LLM as advisory only.

### Floor input is untrusted issue text - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** L15, L75, CUJ 2 (L47-51)
* **Description:** Floor can only see paths the issue author names. Omitted or hidden sensitive path gives `medium`, shown at H1 before the ratchet can correct it. G1 says the floor is not lowered, not that it is correct.
* **Proposed resolution:** Code pre-computes candidate paths from a repo index and CODEOWNERS (`floor_inputs.source: repo_index`), floor = max of both. Costs: index staleness, false-positive `high`, extra code, still heuristic for new paths.

### Two stores of truth for risk - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** L63, L86, PRD section 5, Alternative C
* **Description:** Record and H1 PR value both authoritative; orchestrator must parse PR body, the cost Alt C used to reject that option. Pick one authority, for example a `/herd risk <level>` command or label.

### Ratchet vs human authority unresolved - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** L59-69, L77, L80-81
* **Description:** "Risk never goes down" (L69) and "never overwrites human-set value" (L81) collide when a human lowers at H1 and step 5 recomputes a higher floor.
* **Proposed resolution:** Scope overrides per rule (`overridden_rules: [hash]`); recompute raises only for newly matched rules; log the rest in `risk.history`. Costs: bigger schema, stable rule identity across `herd.yaml` edits.

### Ratchet is speculative scope for M0 - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** L65-69, L77
* **Description:** Depends on a real diff that exists only in M1. Adds second recompute trigger and re-opens H1, contradicting PRD "only human step is 4". Build in M1; keep `floor_inputs.source` as the seam.

### Fail closed `high` for every failure class - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** L84, G4 L22, L143
* **Description:** Transient failures (timeout, race) inflate `high`, pollute `risk_delta` and edit-rate signals.
* **Proposed resolution:** Bounded retry (for example 2) for transient failures; keep immediate fail-closed for schema and `herd.yaml` invalidity; add `cause` to `triage.status: fallback`.

### Altitude drops into implementation detail - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** L88-101, L165
* **Description:** Function signatures, full YAML schema, hash fields and unknown-key rules sit in the architecture section. Keep interfaces; move field detail to code and tests.

### Over-decomposed implementation and inconsistent verification - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** L19, L163-181, L191
* **Description:** Three scripts plus runner plus 7 fixtures for one pure function and a validator. `fixtures/` (L19) vs `fixtures/triage/` (L191). Test names cited by G2-G4 are absent from the fixture list (L180). Fixture `bad_herd_yaml` maps to no CUJ or goal. Merge floor and record modules; make every check either a fixture or a named test.

### Two writers of the record - Severity: Nit
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** L73, L63, L86
* **Description:** L73 says only the record writer writes state; L63 and L86 say the orchestrator writes. Route human override through the writer as a typed event.

### Glob dialect open; hand-rolled grammar - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`, `egm-inventive-catalyst`
* **Affected Scope:** L34, L36, L163
* **Description:** Python `fnmatch` lets `*` cross `/`, a silent floor-bypass risk. Reuse one dialect with known semantics (CODEOWNERS or gitignore-style); if CODEOWNERS covers it, drop the `herd.yaml` `floor` block to avoid duplicate sources of truth.

### Premature observability and rollout extras - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** L80, L141-143
* **Description:** `risk_delta`, token budgeting, lazy runs with hash idempotency, `/herd retriage`. Add when needed; idempotency can mean "do not overwrite an existing record".

### PRD divergence and L0 left open - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** L33, L35, L183-186
* **Description:** Close both before M0 build. Simplest default: Triage runs at L0 too.

## Reviewer process notes
* Persona file names given in the task did not exist; reviewers used `zoom_out.md` and `inventive_catalyst.md` in the same agents directory.
* Positive: the trust split (agent returns enum, code computes floor, `herd.yaml` read from base, fail closed) addresses P6 well; dropping size path is good YAGNI.
