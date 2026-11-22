# Goldfish Review Report: Stage 5 (zoom-out, inventive-catalyst)

**Target:** `docs/designs/herd-arbiter.md` (full file, lines 1-251)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |
| `egm-inventive-catalyst` | completed |

## Prioritized Findings

No Blockers. 7 Major, 7 Nit (zoom-out: 3 Major, 5 Nit; catalyst: 4 Major, 2 Nit).

### Z1 Scope creep: 8 goals and 6 policy checks for M0 - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 21-28, 104-111, 204-205
* **Description:** G6 (flip rule), `duplicate`/`unknown` id causes, `policy` rewrite for `defer`, and citation re-ask each add code paths and tests. PRD asks only for Nit-only auto-reject, low-confidence escalation, logged rulings.
* **Recommendation:** Keep schema, `missing` ids, Nit-only decline, citation resolution, log. Cut or defer flip rule and re-ask unless justified by a pilot failure. The 3-round cap already bounds the cost (lines 183, 186).

### Z2 PRD drift on `defer`/`contest`; contest on a Blocker bypasses Nit-only rule - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`, `egm-inventive-catalyst` (merged with C1)
* **Affected Scope:** lines 62, 102, 107, 110-113, 125, 127, 184-185, 215
* **Description:** PRD section 5 gives accept/reject/defer and says the Arbiter may auto-reject only Nit findings in M0 (PRD line 89). `contest` is effective on Blocker and Major (CUJ 3), so a Blocker can be auto-rejected; G3 blocks only the verb `decline`. `defer` is unmapped to EGM (line 102), contradicting Alternative A's "no fork" rationale. `defer` is forbidden on Blocker/Major (line 107) yet counted in the overturn numerator for them (line 127).
* **Recommendation:** State that the design amends the PRD, or make contest on Blocker/Major provisional (shown first in the PR summary, not stopping the loop). Audit 100% of contest/defer on Blocker/Major and sample the rest; report overturn per stratum. Decide whether `defer` exists in M0.

### Z3 Metric and sampling diverge from PRD; audit machinery built despite non-goal - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 34, 127, 175, 205, 217
* **Description:** PRD (line 39) audits every ruling for first 5 features, then 25%. Design uses id mod 4, not stratified. `overturn_rate()`, `summary()` and `audit|` lines are built while "audit tooling and dashboards" is a non-goal (line 34). Fallback "overturn exceeds 10 percent after first 5 features" conflicts with PRD's 20 features / 3 repos judgement (PRD line 45); ~50 rulings give too wide an interval.
* **Recommendation:** Human marks overturns in the PR and computes the rate by hand for M0, or drop the non-goal. Align the fallback trigger with the PRD.

### C2 Round-burn from re-raised rejected Blocker named but not resolved - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** Problem statement, Risks row "Rejected Blocker re-raised every round", G6, CUJ 6, CUJ 7
* **Description:** Mitigation (stable id, prior rulings, flip rule) stops only the Arbiter flipping, not the re-raise or its round cost. CUJ 6 says a same-verdict repeat is "kept", while the loop exit counts open Blockers; the design never says whether a repeated contested Blocker counts as open.
* **Recommendation:** Orchestrator code keeps a settled set of contested/declined ids keyed to a hash of the cited region; a re-raise with unchanged region is auto-carried and not counted open. Prefer code suppression over telling Goldfish prior rulings. Invalidate on spec change.

### C3 One malformed object discards the whole round - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** Policy check 1, G5
* **Description:** Any schema failure escalates every finding, burning the round and a human touchpoint (hits the "<=2 touchpoints" metric). Citation failure gets one re-ask; malformed output gets none.
* **Recommendation:** Validate each ruling independently and escalate only broken or missing ids; give whole-output malformation the single re-ask. Treat a run with schema errors plus an accept as suspect. Prompt-prefix caching weakens the Alternative C cost objection.

### C4 Unstable finding id disables the flip rule - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`, `egm-zoom-out` (Z7 merged)
* **Affected Scope:** line 92, line 186, G6, Risks row "Finding id changes when a reviewer rephrases"
* **Description:** id is a hash of persona|scope|normalised text; rephrasing or another persona raising the same issue yields a new id, bypassing flip rule, repeated-finding defence and prior-rulings input. This is the exact failure path of C2. 8 hex chars (32 bits) is unjustified.
* **Recommendation:** Optional Arbiter `same_as: <prior id>` validated by code (id exists, persona/scope match, flip and citation rules still apply), or code-side near-duplicate matching. If G6 stays, state the limitation in G6 itself.

### Z4 Altitude drop to code-level detail - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 92, 204-205, 215, 217-220
* **Description:** Function signatures, `int(finding_id, 16) % 4`, SHA-1 first-8-hex algorithm in an architecture doc.
* **Recommendation:** Keep `validate()` and `format_lines()` interfaces; drop `sample`/`overturn_rate` bodies.

### Z5 Config surface depends on an unwritten design - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 115, 131, 175, 236
* **Description:** `arbiter.enabled` and `arbiter.model` go into `herd.yaml` created by the Triage design; `enabled` has no off-path behaviour and the PRD defines none.
* **Recommendation:** Drop `enabled` until the fallback exists or define its behaviour.

### Z6 Pipe-delimited log format is speculative - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 36, 118-125, 187
* **Description:** Escaping, 140-char cap and trailing-field parser for a format S2 will replace.
* **Recommendation:** Use JSON Lines; removes escaping logic and `test_reason_escaped`.

### Z8 Re-ask cost and citation-check strength unstated - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 108, 131, 174, 185
* **Description:** Unclear whether the re-ask counts against the 3-round cap or token budget. Rubric says a contest must be checkable by evidence, but code only verifies the citation exists.
* **Recommendation:** State both; do not let the citation check read as stronger than it is.

### C5 Citation-equality in flip rule is brittle to line shifts - Severity: Nit
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** Policy check 5
* **Description:** Comparison by path and line range; Elephant edits shift lines so legitimate re-rulings escape or same-quote cases wrongly escalate.
* **Recommendation:** Compare by `quote` text or hash of the cited region against `spec_sha`; require `quote` for reversal comparisons.

### C6 Injection claim stronger than design (accept path) - Severity: Nit
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** NFR Security, G5, CUJ 5
* **Description:** Elephant applies accepted fixes from raw finding text, so injected text reaches an editing agent unvetted; G5 covers only Arbiter output.
* **Recommendation:** Accepted ruling carries a validated one-line `fix` description (length-limited, no URLs/commands), applied instead of raw text; keep it a description, not a patch, to preserve "Arbiter only rules".
