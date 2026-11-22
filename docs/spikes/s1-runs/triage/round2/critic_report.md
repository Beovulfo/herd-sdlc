# Stage 7 Report: design, structural, style (one round)

**Target:** `docs/designs/herd-triage.md` (lines 1-173). Standard: feature-spec-standard.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-design` | completed |
| `egm-structural` | completed (Grep omitted long lines 11 and 89, not audited by this reviewer) |
| `egm-style` | completed |

All three verified raw text via Grep; no corruption findings.

## Blocker

### B1 Tamper check trusts attacker-controlled data - Blocker
* **Lens:** design (also zoom-out Z1/I1 in Stage 5, comprehension 2, 7)
* **Scope:** lines 25, 70-72, 100, 105-113
* Record lives on agent-pushable `herd/*` branches. Recompute of floor/effective uses `herd.yaml` plus `risk.override` and `floor_inputs`, both fields in the same record. Agent can forge `override: {actor: human}` or blank `floor_inputs.paths`.
* **Fix:** take override from authenticated source outside the file (maintainer comment event or append-only log); re-derive `floor_inputs` from the `body_hash` snapshot; add fixtures for forged override and forged paths.

## Major

### M1 "Only the record writer writes the record" not enforced - Major
* **Lens:** design | **Scope:** lines 87, 100
* No mechanism named (path-restricted token, CODEOWNERS/branch rule, signed commits). G2 constrains only the Triage agent. Specify enforcement or state G5 detection is the only control.

### M2 Alternatives weak, attribution unlinked - Major
* **Lens:** design, structural, style | **Scope:** lines 126-144
* "Rejected by author:" on A, B, C without linked discussion (standard disallows). A's reason is a learning goal, not a trade-off. C's "override must be auditable" is a bare assertion. No alternative stores record outside the agent-writable repo (check-run, protected branch, separate store). Heading "Reason Rejection" should be "Reason for Rejection". Drop attribution prefix or link.

### M3 LLM value has no success criterion - Major
* **Lens:** design | **Scope:** lines 39-40, 132, 152
* Shadow-mode exit and edit-rate thresholds open with no owner or deadline; no testable condition for Arbiter reading the record or falling back to rules only.

### M4 Rollback not viable - Major
* **Lens:** design | **Scope:** line 153
* Round counter and budget fields need storing elsewhere first, no owner or plan.

### M5 Path extraction from untrusted text unspecified - Major
* **Lens:** design | **Scope:** lines 17, 46, 54, 89, 111
* Who extracts, how (regex, markdown, URLs), evasion handling ("the billing module", code fences, encoded paths). CUJ 1 and G1 depend on it. Add fixtures.

### M6 Override identity weak - Major
* **Lens:** design | **Scope:** lines 23, 66, 31
* `actor: human` only. Record GitHub login and comment ID. Who may run `/herd risk` and whether lowering a high floor needs more than one maintainer is deferred to orchestrator design but trust model depends on it.

### M7 `reason` is an injection and leak channel - Major
* **Lens:** design (comprehension 3) | **Scope:** lines 22, 60, 96, schema 102-114
* LLM output from untrusted text stored and shown at H1/PR; "no issue body text" unenforced; "quoted inert data" undefined. Specify plain-text rendering, no links or markdown, charset and length check. Schema has no `reason` key although CUJ 3 stores it.

### M8 Shadow mode contradicts G5 and Overview - Major
* **Lens:** design (also style: "G1 always holds" overstated) | **Scope:** lines 11, 25, 152
* Overview and G5 say orchestrator reads record and refuses on mismatch; Rollout says Arbiter does not read it in shadow mode. Unstated whether tamper check blocks during shadow and what risk source Arbiter uses. Line 152 "G1 always holds" should read "`effective >= floor` holds except under a recorded `risk.override`" (G1 line 21, CUJ 4 lines 62-66).

### M9 Failure rules inconsistent - Major
* **Lens:** style | **Scope:** lines 91, 98, 151
* L98 omits the outcome of a `race` that fails after its single retry; L151 "transient" undefined. State race outcome; replace "transient" with "timeout or malformed output". (Design nit 12: a race failing closed to `high` during a human override would silently defeat it.)

### M10 Open Question not a question - Major
* **Lens:** style, structural | **Scope:** lines 35-40
* L40 "**Edit-rate warning threshold** after 20 features." is fragmentary, lacks colon used on 37-39, not a decision question. L37 is a deferral duplicating L30 and L168. Rewrite as question or drop.

## Nit

* **N1** Risks and mitigations (155-164) is H3 under NFR; standard lists it as its own section. Promote to H2 (structural).
* **N2** Rule at line 146 between Alternatives and NFR; use rules consistently or remove (structural).
* **N3** Label style: "Reason Rejection" and Pros/Cons bold convention differs from G1-G5 bullets (structural).
* **N4** Lines 93-96: list after bold label lacks blank line (structural).
* **N5** Line 76: trailing whitespace in table header (structural, style).
* **N6** No scalability limit in NFR or risk table; add row or declare out of scope (structural, lines 148-164).
* **N7** Labels: who may apply `risk:*` labels (triage role can apply any); conflicting `risk:low` plus `risk:high` handled only implicitly (design, lines 89, 163-164).
* **N8** Human override persists silently if `herd.yaml` later raises floor; say whether orchestrator re-notifies (design, lines 91, 95).
* **N9** Line 100 "escalates" for missing/old `schema_version` undefined vs unknown enum "fails closed to `high`"; fixture `old_schema_version.yaml` is under G4 (style, comprehension). Unknown-key preservation on write lets agents stash data (design).
* **N10** Line 160: case sensitivity of path matching undecided; case fixture has no expectation (design).
* **N11** `body_hash` written but unconsumed except via B1 fix (design, lines 37, 105).
* **N12** Line 151: no token or latency cap on agent call; body unbounded (design).
* **N13** Line 89 "keeps the agent's proposal from lowering anything" vague; state `effective = max(proposed, floor)` (style).
* **N14** Line 131 repeats L17 hypothesis (style).
* **N15** Line 169 "read next to the canary pass rate" vague; state the decision it drives (style).
* **N16** Line 11 parenthetical repeats L30; move or drop (style).
