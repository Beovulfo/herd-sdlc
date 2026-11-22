# Goldfish Review Report: Stage 7 (design, structural, style)

**Target:** `docs/designs/herd-arbiter.md` (1-194), standard `feature-spec-standard`, one round.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-design` | completed |
| `egm-structural` | completed |
| `egm-style` | completed |

Counts (raw, before cross-reviewer dedup): Blocker 0, Major 12 (design 7, structural 1, style 4), Nit 18 (design 7, structural 3, style 8).

## Findings: design (D)

### D1 Policy-escalated Blocker/Major cannot close the loop - Major
* **Reviewer Lens:** `design`
* **Affected Scope:** L23, L62, L98, L105-117; Escalation L105
* **Discrepancy:** Contest/decline on Blocker/Major becomes `escalate/policy`, open until a human decides, but the only human look is the spec PR after the loop. Next round's Goldfish likely re-raise; the Arbiter likely re-contests; repeat is not a flip. Every wrong Blocker/Major runs to the round cap and triggers a `rounds` escalation, against the PRD <=2 touchpoint median; the design never says so.
* **Recommendation:** State loop treatment (non-blocking for termination, or a human decision path before the cap).

### D2 Sampling claims contradict each other - Major
* **Reviewer Lens:** `design` (also `style` S2)
* **Affected Scope:** L25, L115, L177
* **Discrepancy:** G5 "every effective ruling is sampled"; risk row "every Nit ruling is sampled"; L115 samples 25% after feature 5. Mislabelled Blocker-as-Nit or bad accept unseen 75% of time.
* **Recommendation:** Correct G5 and the risk row to the real rule; state the accepted residual miss rate.

### D3 No recording path for audit/human decisions - Major
* **Reviewer Lens:** `design`
* **Affected Scope:** L13, L35, L78, L105-111, L115; Escalation L112
* **Discrepancy:** `herd_arbiter.py` is declared sole writer, audit tooling is a non-goal, yet audit lines and escalated-finding human decisions must be appended; Escalation has the orchestrator append `{"type":"human"}` lines. No record carries a human decision on a policy escalation.
* **Recommendation:** Define the writer(s) and allowed `result` values; reconcile "only writer" with Escalation.

### D4 Merged findings: severity undefined - Major
* **Reviewer Lens:** `design`
* **Affected Scope:** L80, G2, G3
* **Discrepancy:** Same normalised text from several personas merges but severities may differ; G2/G3 rely on the copied severity.
* **Recommendation:** Take the highest severity; test it.

### D5 Arbiter read scope and exfiltration - Major
* **Reviewer Lens:** `design`
* **Affected Scope:** L78, L113, L167, L182; PRD section 8
* **Discrepancy:** Unrestricted Read/Grep/Glob vs PRD limit "the artifact and its cited sources". An injected finding could make it read arbitrary repo files and emit content in `reason`, printed in the PR summary of a public repo; 140-char truncation does not prevent it. Security NFR and injection risk row omit this path.
* **Recommendation:** Restrict reads to spec and rubric (or pass them in the prompt and drop tools); add the risk.

### D6 Single-call injection containment asserted, not shown - Major
* **Reviewer Lens:** `design` (also `style` S1, `inventive-catalyst` I4)
* **Affected Scope:** L25, L66-68, L149
* **Discrepancy:** G5 says an injected finding affects only its own ruling, but all findings share one context; Alternative C concedes cross-contamination; the fixture cannot prove containment against a live model.
* **Recommendation:** Reword G5; define the fixture as a recorded-output replay; say sampling is the only control.

### D7 Severity mislabelling has no mitigation beyond sampling - Major
* **Reviewer Lens:** `design` (also `inventive-catalyst` I8)
* **Affected Scope:** L151, L177
* **Discrepancy:** Real Blocker labelled Nit is effectively declined, unseen 75% of the time; Arbiter has no signal to give.
* **Recommendation:** Add a `severity_dispute` flag that cannot change severity but forces `escalate` (or rubric rule 6).

### D8 Alternatives rationale thin; missing alternatives - Nit
* **Reviewer Lens:** `design` (also `structural` T1)
* **Affected Scope:** L137, L143, L149, L155
* **Discrepancy:** "Rejected by author" without a link; B rests on an unsupported hypothesis. Missing: semantic persona-independent finding id, escalate-all default, rule-based Nit pre-filtering.
* **Recommendation:** Drop attribution, state technical reasons; add or dismiss the missing alternatives.

### D9 Flip scope ambiguous - Nit
* **Reviewer Lens:** `design`
* **Affected Scope:** L100
* **Discrepancy:** "Prior round" is immediate or any earlier? A prior `escalate` compared with a later `accept` counts as differing and triggers flip, probably unintended.
* **Recommendation:** State scope; exclude prior `escalate`.

### D10 Duplicate-id handling unspecified - Nit
* **Reviewer Lens:** `design`
* **Affected Scope:** L96
* **Discrepancy:** Not stated which duplicate ruling is rewritten (both or second).
* **Recommendation:** Specify.

### D11 Contest evidence outside spec cannot resolve - Nit
* **Reviewer Lens:** `design` (also `zoom-out` Z8)
* **Affected Scope:** L99, L119
* **Discrepancy:** Rubric rule 1 asks for evidence the reviewer could read; citation check allows only the spec path, so a PRD-based contest always becomes `escalate/citation`.
* **Recommendation:** Align rule and check.

### D12 No size/cost bound per call - Nit
* **Reviewer Lens:** `design`
* **Affected Scope:** L115, L168-169, L183
* **Discrepancy:** No bound on findings or spec size or token estimate; truncated output yields a malformed round and a re-ask that likely truncates again; dedup does not mitigate "many findings".
* **Recommendation:** Cap findings per call or chunk.

### D13 `feature_index` counter and gameable sampling - Nit
* **Reviewer Lens:** `design`
* **Affected Scope:** L115
* **Discrepancy:** Counter location unstated; `int(id,16) % 4` depends on Goldfish-controlled text, so injected text can choose a non-sampled id.
* **Recommendation:** Define counter; salt the hash.

### D14 Overturn metric does not match PRD section 3 - Nit
* **Reviewer Lens:** `design` (also `style` S4, `zoom-out` Z4)
* **Affected Scope:** L7, L39-42, L115
* **Discrepancy:** PRD: <=10% on Blocker/Major; design pools Nit declines with accepts and splits only by `same_model`.
* **Recommendation:** Also split by severity.

## Findings: structural (T)

### T1 "Rejected by author" attribution - Major
* **Reviewer Lens:** `structural`
* **Affected Scope:** L137, L143, L149, L155
* **Discrepancy:** Standard forbids attributing a rejection to a maintainer without a link to their issue/discussion/PR. Alternative A links a spike path only; B, C, D restate cons rather than give rationale.
* **Recommendation:** Drop "by author"; state the concrete trade-off; link any person-based rejection.

### T2 Technical Plan heading and run-in labels - Nit
* **Reviewer Lens:** `structural`
* **Affected Scope:** L71
* **Discrepancy:** Siblings title it "Technical Plan (Architecture)"; standard requires Proposed Architecture. Section is bold run-in labels, not H3.
* **Recommendation:** Match sibling heading; promote labels to H3.

### T3 Dense Terms paragraph - Nit
* **Reviewer Lens:** `structural`
* **Affected Scope:** L13
* **Discrepancy:** Glossary plus effective/open definitions in one paragraph.
* **Recommendation:** Bulleted list or Terms subsection.

### T4 Code fence labels - Nit
* **Reviewer Lens:** `structural`
* **Affected Scope:** L84-90, L105-111
* **Discrepancy:** L84 says "A JSON list" but the example is one object; log block fenced `text` though JSON Lines.
* **Recommendation:** Fix wording; use `json`/`jsonl`.

## Findings: style (S)

### S1 Unsupported isolation claim - Major
* **Reviewer Lens:** `style`
* **Affected Scope:** L25, L68, L149, L182
* **Discrepancy:** G5/CUJ 4/risk row claim per-finding isolation; one shared call contradicts it (Alternative C says untested).
* **Recommendation:** Rewrite as known risk limited by schema validation and policy checks, detected by sampling; state what `test_injected_finding_fixture` asserts.

### S2 Contradictory sampling claims - Major
* **Reviewer Lens:** `style`
* **Affected Scope:** L25, L115, L177
* **Discrepancy:** See D2.
* **Recommendation:** One statement everywhere: every ruling for first 5 features, then 1 in 4 by id.

### S3 Sampling does not "cover" residual risk - Major
* **Reviewer Lens:** `style`
* **Affected Scope:** L167
* **Discrepancy:** Sampling occurs at merge after the Elephant applied the fix; detects some cases, prevents none.
* **Recommendation:** Reword to say so.

### S4 Overturn metric differs from PRD - Major
* **Reviewer Lens:** `style`
* **Affected Scope:** L42, L115, L169; PRD section 3
* **Discrepancy:** See D14; no stated deviation rationale.
* **Recommendation:** Report Blocker/Major separately or state the deviation.

### S5 `defer` dropped vs PRD - Nit
* **Reviewer Lens:** `style`
* **Affected Scope:** L34; PRD L89, L121
* **Discrepancy:** PRD says Arbiter "accepts, rejects or defers"; design drops `defer` without citing the PRD departure.
* **Recommendation:** Cite the PRD sections departed from.

### S6 "valid, escalated or sampled" - Nit
* **Reviewer Lens:** `style`
* **Affected Scope:** L68
* **Discrepancy:** "Valid" undefined; "sampled" not a ruling outcome.
* **Recommendation:** "is `escalate`, or passes all policy checks and is in the audit sample".

### S7 Vague wording at L48 and L62 - Nit
* **Reviewer Lens:** `style`
* **Affected Scope:** L48, L62
* **Discrepancy:** "cited lines show where it belongs" vague; "a Blocker finding the Arbiter judges wrong" states the conclusion as the Given.
* **Recommendation:** Name the condition and the answering spec line.

### S8 Harness behaviour stated as fact - Nit
* **Reviewer Lens:** `style`
* **Affected Scope:** L103
* **Discrepancy:** "an agent with no configured model inherits the Elephant's" unsupported.
* **Recommendation:** Cite source or write "assumed".

### S9 Unverified opinion in Alternative E - Nit
* **Reviewer Lens:** `style`
* **Affected Scope:** L153
* **Discrepancy:** "Matches how a human would triage".
* **Recommendation:** Concrete benefit or "Mirrors EGM manual triage".

### S10 Subjective "Simple to read" - Nit
* **Reviewer Lens:** `style`
* **Affected Scope:** L135
* **Recommendation:** Drop or state the reader decision supported.

### S11 Risk row mitigation mismatch - Nit
* **Reviewer Lens:** `style`
* **Affected Scope:** L183
* **Discrepancy:** "Many findings in one call" mitigated by one call/dedup does not address the risk.
* **Recommendation:** Name a cap or mark accepted.

### S12 `escalate` as ruling and cause - Nit
* **Reviewer Lens:** `style`
* **Affected Scope:** L22, L92, L101
* **Discrepancy:** Consistent but could state that `verdict` is always `escalate` after rewrite and `cause` explains why (optional).
* **Recommendation:** One clarifying sentence.
