# Goldfish Review Report: Stage 5 (zoom-out, inventive-catalyst)

**Target:** `docs/designs/herd-arbiter.md` (1-253)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |
| `egm-inventive-catalyst` | completed |

Counts: Blocker 0, Major 12, Nit 6 (18 raw findings, before cross-reviewer dedup).

## Findings

### Z1 Loop behaviour for escalated Blocker/Major undefined - Major
* **Reviewer Lens:** `zoom-out` (also `inventive-catalyst` I2)
* **Affected Scope:** L13, L24, L62, L98, L117; Escalation L105
* **Discrepancy:** Contest/decline on Blocker/Major becomes escalate/policy and stays open; first human sight is the spec PR after the loop. A wrongly raised Blocker/Major keeps looping to the round cap and then the `rounds` trigger costs a touchpoint, against the median <=2 target. Elephant behaviour on an escalated finding in the next round is not stated.
* **Recommendation:** State loop semantics: either policy/citation escalations are closed for the loop and listed in the PR ("parked"), or they stay open and the cost is accepted. Amend Escalation `rounds` row accordingly.

### Z2 Two writers of `decisions.md` - Major
* **Reviewer Lens:** `zoom-out`
* **Affected Scope:** L78, L105; Escalation L112
* **Discrepancy:** Arbiter says `herd_arbiter.py` is sole writer; Escalation has the orchestrator append `{"type":"human"}` lines to the same file. Unclear whether a `human` line counts as an audit in `overturn_rate` (`overrule_arbiter` is effectively a reversal).
* **Recommendation:** Name one writer or add the `human` line type to this schema and define its metric treatment.

### Z3 Audit line has no capture path - Major
* **Reviewer Lens:** `zoom-out`
* **Affected Scope:** L35, L115
* **Discrepancy:** Audit lines feed the headline M0 metric but audit tooling is a non-goal and nothing writes the `audit` line; hand-editing JSONL is unrealistic.
* **Recommendation:** Name a minimum mechanism (e.g. a `/herd audit <id> upheld|overturned` command or an orchestrator-parsed PR checklist).

### Z4 Overturn metric not split by severity - Major
* **Reviewer Lens:** `zoom-out` (also `inventive-catalyst` I5)
* **Affected Scope:** L115; PRD section 3
* **Discrepancy:** PRD target is <=10% on Blocker/Major; `overturn_rate` splits only by `same_model` and mixes Nit declines with Blocker/Major accepts.
* **Recommendation:** Add a severity split.

### Z5 Merged findings have undefined severity - Major
* **Reviewer Lens:** `zoom-out`
* **Affected Scope:** L80, G2
* **Discrepancy:** Id hashes normalised text only, so identical text from several personas merges; severities may differ. Taking the lower severity downgrades a Blocker to a Nit and defeats G3.
* **Recommendation:** Take the highest severity on merge; add a test.

### Z6 Flip rule does not address the stated problem - Major
* **Reviewer Lens:** `zoom-out` (also `inventive-catalyst` I1)
* **Affected Scope:** L17, L26, L74, L80, L178
* **Discrepancy:** Problem is wrongly judged findings re-raised each round. Flip fires only when the Arbiter changes its own verdict on the same quoted text; repeated verdicts or rephrased text (new id) do not fire it. Risk row at L178 overclaims. Real bounds are the 3-round cap and prior rulings as input.
* **Recommendation:** Drop flip or restate as anti-oscillation guard and fix the risk row. Alternatively key repeat detection on cited location (`quote_sha` or overlapping line range) rather than id; beware bare section-heading citations (L92) colliding for different omissions.

### Z7 Sampling claims overstated - Nit
* **Reviewer Lens:** `zoom-out` (also `inventive-catalyst` I5)
* **Affected Scope:** L25, L68, L177 vs L28, L115
* **Discrepancy:** G5 "every effective ruling is sampled" and risk row "every Nit ruling is sampled" conflict with full audit for first 5 features then 25% by id; CUJ 4 reads the same way.
* **Recommendation:** Reword the three places to match the mechanism. Also define the source of `feature_index`.

### Z8 Citation scope narrower than tools - Nit
* **Reviewer Lens:** `zoom-out`
* **Affected Scope:** L97, L99
* **Discrepancy:** Citations must be in the spec path, so contests evidenced by the PRD or code always escalate/citation, yet the Arbiter has Read/Grep/Glob over the repo.
* **Recommendation:** Restrict tools or allow an allowlist of cited paths.

### Z9 `overrule_arbiter` opposite verdict and default model - Nit
* **Reviewer Lens:** `zoom-out` (also `inventive-catalyst` I6)
* **Affected Scope:** L241; Escalation L107, L112
* **Discrepancy:** "Opposite verdict" defined only for accept/contest, but `low_confidence` can arise on a decline. Default `model = "inherit"` makes `same_model` true by default, weakening the PRD "different model where the harness allows" mitigation.
* **Recommendation:** Define opposite for decline; default to a different model where supported, fall back to `inherit`.

### Z10 Detailed plan altitude and check order rationale - Nit
* **Reviewer Lens:** `zoom-out`
* **Affected Scope:** L94, L195-221
* **Discrepancy:** Plan lists nine signatures, `int(id,16) % 4`, SHA-1 truncation, 140-char cut; consistent with siblings so not a defect. `low_confidence` check precedes `policy`, so a low-confidence contest on a Major opens an issue while a confident one only goes to the summary; no rationale given.
* **Recommendation:** Trim `finding_id`, `format_lines`, `needs_audit` to a sentence each; add a one-line rationale for check order.

### I3 Low confidence treated alike for every verdict - Major
* **Reviewer Lens:** `inventive-catalyst`
* **Affected Scope:** L97, L119 (rule 5); Escalation L107
* **Discrepancy:** `L` on `accept` (the safe direction) is escalated, spending a touchpoint where risk is lowest. Check order puts `low_confidence` before `policy`, so an `L` decline on a Blocker opens an issue instead of going to the summary.
* **Recommendation:** Escalate low confidence only for decline/contest; keep `L` accept effective and always sampled; move `policy` ahead of `low_confidence` for Blocker/Major. Keep Arbiter and Escalation cause tables in step.

### I4 Cross-contamination in one call vs G5 claim - Major
* **Reviewer Lens:** `inventive-catalyst`
* **Affected Scope:** G5 L25, Alternative C L145-149, Risks L183
* **Discrepancy:** G5 says an injected finding can affect only its own ruling, but all findings share one context; code does not enforce it and one fixture is the only test. Cost argument is weak since the spec dominates the prompt.
* **Recommendation:** Split into two calls (Blocker/Major vs Nit), sharing the prefix via caching where available; at minimum reword G5 to what is enforced.

### I5 Sampling steerable and mis-split - Major
* **Reviewer Lens:** `inventive-catalyst`
* **Affected Scope:** G8 L28, L115, G5 L25, L177
* **Discrepancy:** Sampling is deterministic from the id, which derives from reviewer-controlled text, so a reviewer can steer whether it is sampled. `feature_index` has no defined source; metric lacks a severity split; wording conflicts (see Z7).
* **Recommendation:** Salt the hash with an orchestrator-only salt (version recorded); audit every effective Nit decline; add severity split; fix wording.

### I6 Shared-model bias default and target - Major
* **Reviewer Lens:** `inventive-catalyst`
* **Affected Scope:** L41, L176, L241
* **Discrepancy:** `model = "inherit"` makes `same_model` true on every run, disabling the PRD mitigation. The open question targets the wrong verdict: bias shows as decline/contest (already blocked on Blocker/Major); exposed path is the effective Nit decline.
* **Recommendation:** Default to a different model where supported; under `same_model` widen sampling to all effective Nit declines instead of restricting accept.

### I7 Re-ask scope inconsistent - Nit
* **Reviewer Lens:** `inventive-catalyst`
* **Affected Scope:** L95 vs L217; Escalation L110
* **Discrepancy:** L95 says one re-ask for the whole round on schema break; L217 re-asks only when every ruling is `malformed`. Partial malformed output gets no re-ask.
* **Recommendation:** Re-ask only the affected ids, cap at one retry, update L95; `build_input` needs an id-subset parameter.

### I8 No rule for under-labelled severity - Nit
* **Reviewer Lens:** `inventive-catalyst`
* **Affected Scope:** L119, L177, L203
* **Discrepancy:** A Blocker mislabelled Nit becomes an effective decline sampled at 25%; rubric has no rule to `escalate` when harm exceeds the label.
* **Recommendation:** Add rubric rule 6 ("worse than label -> escalate") and update the Phase 3 `grep -c "^Rule [1-5]:"` check to 6.
