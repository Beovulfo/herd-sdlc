# Goldfish Review Report: Stage 7 (design, structural, style)

**Target:** `docs/designs/herd-arbiter.md` (FeatureRange, lines 1-197). Standard: feature-spec-standard. One round.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-design` | completed |
| `egm-structural` | completed |
| `egm-style` | completed |

## Prioritized Findings

1 Blocker, 14 Major, 13 Nit (after dedup).

### D-B1 `contest` on a Blocker defeats the Nit-only limit - Severity: Blocker
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 58-62, 102, 163-167, 175
* **Description:** G3 and CUJ 4 stop `decline` on a Blocker, but CUJ 3 lets `contest` on a Blocker be effective ("Elephant makes no change") with no human before merge. That is an auto-reject of a Blocker, which PRD section 5 line 89 allows only for Nit. Alternative D routes disagreement into `contest`. The citation check proves only that lines exist (see D-M6). Whether a contested Blocker/Major counts as open at loop exit is undefined.
* **Recommendation:** In M0 make `contest` on Blocker/Major non-effective (escalate or keep open for the exit test), state its open-count status, or justify the divergence from PRD line 89 in the document.

### D-M1 Reviewer-assigned severity hazard not mitigated - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 17, 24, 113
* **Description:** Problem says the label may be wrong or injected; G2 only stops the Arbiter changing it. A Blocker mislabelled or injected as Nit makes `decline` legal under G3.
* **Recommendation:** Arbiter flags severity disagreement as `escalate`, audit Nit declines for mislabels, or drop the claim.

### D-M2 Stable finding id does not deliver flip protection; scope and dedup undefined - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 36, 92, 183, 186
* **Description:** Hash of `persona|scope|normalised text` changes on rephrase or line shift, making G6 and the re-raise mitigation largely inert; the cap-of-3 acceptance describes the common case. "Scope" and dedup method undefined (exact-hash dedup would not merge rephrased or cross-persona findings).
* **Recommendation:** Define scope and dedup; use Arbiter-proposed `same_as` validated by code, or downgrade the claim and quantify cap burn.

### D-M3 Flip rule "same citation" is brittle - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 26, 109
* **Description:** Path+range comparison: one-line shift counts as new; spec edits invalidate old range.
* **Recommendation:** Compare by quote/content or spec hash at citation time; define "same".

### D-M4 G5 injection guarantee overstated - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-style` (merged)
* **Affected Scope:** lines 25, 74, 92, 173
* **Description:** "Cannot produce an `accept`" and "no other ruling changes" are model behaviours; code enforces only shape. A fixture on one model is not a guarantee; CUJ 5 claims less than G5. Prior rulings' `reason` text is second-order injection; unclear if in a data block.
* **Recommendation:** Narrow G5 to what the test shows; list residual risk in Risks; state prior rulings are data.

### D-M5 Escalate and malformed handling undefined and costly - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 25, 111, 115; PRD line 67
* **Description:** Malformed output escalates every finding with no retry; large inputs risk truncation. Escalate mechanics (GitHub issue per ruling or round, how the answer is recorded, touchpoint count) unspecified.
* **Recommendation:** Add a retry; specify escalate mechanics and worst-case escalations per feature; add an escalate CUJ.

### D-M6 Citation proof is weak - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 24, 108, 185
* **Description:** `quote` optional, so G4 reduces to a range check; omission findings have nothing to cite; G3/CUJ 3 lean on this.
* **Recommendation:** Require `quote` for `contest`; define how omissions are cited.

### D-M7 `defer` incoherent in policy and metric - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-structural` (merged)
* **Affected Scope:** lines 107, 127, open question 2
* **Description:** Check 3 rewrites `defer` on Blocker/Major to `escalate`, escalated rulings are excluded, so `defer` never appears in the Blocker/Major denominator; "defer counts as open" matters only for Nits, which the exit test ignores.
* **Recommendation:** Allow `defer` on Major, or drop it from the metric and exit test / restrict the denominator wording.

### D-M8 Audit loop not closed - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-style` (merged)
* **Affected Scope:** lines 42, 125-127, 175; PRD line 39
* **Description:** "Adds no touchpoint" asserted; auditing every ruling for 5 features costs human minutes (PRD metric). No stated action after a human overturns a ruling. 10 percent trigger is a point estimate on about 50 rulings (basis of "about 50" is unstated). Rewritten rulings lose the original verdict.
* **Recommendation:** Say audit adds no gate but adds review time; record `raw_verdict`; define post-overturn action; state a decision rule accounting for n; label 50 an assumption.

### D-M9 Alternatives section fails the Alternatives Rule - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-structural` (merged)
* **Affected Scope:** lines 143-167
* **Description:** Every rejection is "Rejected by author" without a linked issue/discussion/PR; A cites the S1 spike unlinked; C's cost is "a large multiple" unquantified. All four are minor variants; central choices (code-enforced vs prompt-only, LLM Arbiter vs deterministic rules plus human sample, batched human triage, human confirmation of Blocker contest, different-model requirement) have no alternative.
* **Recommendation:** Restate as technical trade-offs, link S1, quantify C, add missing alternatives or cross-reference PRD section 6.

### S-M1 "Does not fork `egm-resolve`" contradicts `defer` - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 102, 148
* **Description:** Verdicts are said to map to `egm-resolve`, yet `defer` has no EGM equivalent; Alternative A rejects new vocabulary for forking.
* **Recommendation:** Say four of five map; state how `defer` is counted in handoff counts, or drop the claim.

### S-M2 "reject" used though no verdict is named reject - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 40, 182, 193 vs 102
* **Description:** PRD says "accepts, rejects or defers"; design verdicts differ.
* **Recommendation:** Use verdict names; note once that PRD "reject" maps to `contest` and `decline`.

### S-M3 Unsupported assertions - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 154, 160
* **Description:** "Model confidence is poorly calibrated" has no source; "a large multiple of token cost" no number.
* **Recommendation:** Cite evidence or recast as a decision ("M0 has no data to set a threshold"); give the multiple.

### T-M1 Risks table misses injection and scalability - Severity: Major
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** lines 178-187
* **Description:** Standard requires failure modes, security, scalability limits. Injection only in NFR and G5; no row for one call carrying whole spec plus findings (context size, truncation, spec drift).
* **Recommendation:** Add both rows.

### N1 H1 term reference wrong; terms incomplete - Severity: Nit
* **Reviewer Lens:** `egm-structural`, `egm-style`, `egm-design`
* **Affected Scope:** line 13
* **Description:** H1 defined only in PRD section 4 (not 1); collides with Markdown H1; "orchestrator" not defined in PRD section 1; S1, S2, `egm-resolve` not covered.
* **Recommendation:** Cite section 4, write "Intent gate (H1)", add or link missing terms.

### N2 `unknown`/`duplicate` ids lack severity/persona and keep-rule - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 21, 25
* **Recommendation:** Specify log fields for unknown ids and which duplicate is kept.

### N3 G8 "append-only" unenforced and mixes concerns - Severity: Nit
* **Reviewer Lens:** `egm-design`, `egm-style`
* **Affected Scope:** lines 28, 125, 127
* **Description:** Only sampling determinism tested; nothing stops the Elephant editing `decisions.md`. G8 omits the first-5-features full audit; "declined Nits do not vanish" is figurative.
* **Recommendation:** Add enforcement/test or soften; state the rule; say declined Nits are audited at the same rate.

### N4 "same family" vs `same_model` equality - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 40, 115
* **Recommendation:** Align the definitions.

### N5 Cost NFR has no token estimate - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 173-176
* **Recommendation:** Add a rough token budget (3 rounds plus re-ask).

### N6 G7 says every ruling line records models; header holds them - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** lines 21, 28, 117-121
* **Recommendation:** Reword G7 to "every round header".

### N7 CUJ 7 breaks Given/When/Then and has no test - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** lines 82-86
* **Recommendation:** Move to Non-Goals or add "Test: n/a (orchestrator design)".

### N8 Unnumbered trailing rule in Policy checks - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** line 111
* **Recommendation:** Make it item 7 or mark it separate.

### N9 Heading "Technical Plan (Architecture)" - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** line 88
* **Recommendation:** Use "Proposed Architecture".

### N10 Open Questions placed before CUJs - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** lines 38-42
* **Recommendation:** Move after Risks and Mitigations.

### N11 S2 "candidate title" unclear - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** line 36
* **Recommendation:** Link the spike or state what item 3 is.

### N12 Filler wording and repeated "Rejected by author" - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 17, 149, 155, 161, 167
* **Recommendation:** Rewrite as "Three risks: ..."; drop the prefix and state the rationale.

### N13 Subjective pros in Alternatives - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 147, 153, 165
* **Recommendation:** Give concrete properties instead of "Simple to read", "Fine-grained".
