# Goldfish Review Report: Stage 6 (comprehension)

**Target:** `docs/designs/herd-arbiter.md` (FeatureRange 1-194, DetailedRange 195-253). No GoldfishContext.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-comprehension` | completed |

Counts: Blocker 0, Major 10, Nit 5.

## Feature Paraphrase

What this proposes: Herd step 7 swaps the human who triages reviewer findings for an agent called the Arbiter. It starts with fresh context and reads the findings, the spec and a rubric. It returns one JSON ruling per finding: accept, contest, decline or escalate. Python orchestrator code then validates every ruling. Code can downgrade a ruling to `escalate` with a cause: malformed, missing, duplicate, unknown, low_confidence, policy, citation, flip or arbiter. A ruling is effective without a human only if it is `accept`, or it is `decline`/`contest` on a Nit. The Arbiter can never change severity. Every non-escalate ruling must quote spec text that code can find. A human audits a deterministic sample at spec-PR merge, and the overturn rate is measured, split by whether the Arbiter and Elephant share a model. If the overturn rate is over 10% after 5 features, Herd falls back to batched human triage.

How the existing system works, per this document: EGM has a human triage each finding, using `egm-resolve` categories (PROPOSE FIX, CONTEST, DECLINE, ESCALATE). The Herd lifecycle (PRD) has an Elephant (drafting agent) and Goldfish reviewers. Reviewers give findings a severity. The review loop is capped at 3 rounds and is owned by a separate orchestrator design. A spec PR is merged by a human at step 9. Prior designs and spikes (S1, S2) and the PRD constrain the vocabulary and log format. The `decisions.md` format is a placeholder until S2 replaces it.

## Detailed Paraphrase

What this proposes: Four phases build a stdlib-only Python module, `scripts/herd_arbiter.py`, with `finding_id`, `merge_findings`, `build_input`, `validate`, `format_lines`, `needs_audit`, `overturn_rate` and `summary`. A unittest file has one test per Goal and CUJ, plus four extra tests. A rubric file `rubrics/arbiter-v1.md` has five `Rule N:` lines. An agent definition `agents/herd-arbiter.md` grants Read, Grep and Glob. `herd.toml` gets `[arbiter] model = "inherit"`. Each phase has a runnable exit check.

How the existing system works, per this document: `herd.toml` may already exist from the Triage design. If it does not, this work creates it with only the `arbiter` table. The caller reads the config and maps `inherit` to `arbiter_model = none`. The Python version is whatever the Triage design pins. `validate` never raises. The caller re-asks the Arbiter once when every ruling is `malformed`.

## Findings

### C1 Re-ask rule ambiguous for partial malformed output - Major
* **Reviewer Lens:** `comprehension`
* **Affected Scope:** L94-95, L217
* **Discrepancy:** Technical Plan implies partial malformed ("for the affected findings"); Detailed plan re-asks only when every ruling is `malformed`. A single bad object among good ones: re-ask or not is unclear.
* **Recommendation:** State one rule (any malformed triggers re-ask, or partial failures escalate immediately).

### C2 Cause precedence when output is unparseable - Major
* **Reviewer Lens:** `comprehension`
* **Affected Scope:** L94-101
* **Discrepancy:** Check 1 emits `malformed`, then check 2 could assign `unknown`/`duplicate`/`missing` to the same findings; with unparseable output every finding is also "missing". Winning cause unclear; per-object schema failure `malformed` vs `missing` undefined.
* **Recommendation:** Say unparseable output gives all findings `malformed` and skips checks 2-6; define per-object failure cause.

### C3 Multi-failure cause (policy vs citation) - Major
* **Reviewer Lens:** `comprehension`
* **Affected Scope:** L24, L98-100
* **Discrepancy:** Check 4 turns a Blocker/Major decline/contest into `policy` before the citation is checked, so a bad-citation contest on a Blocker records `policy` only. G4/G3/CUJ 3 do not say which cause appears when several fail.
* **Recommendation:** State "first failing check wins" or record all causes.

### C4 Flip rule `prior` and `quote_sha` undefined - Major
* **Reviewer Lens:** `comprehension`
* **Affected Scope:** L82, L100
* **Discrepancy:** Unclear which `arbiter_verdict` goes into `prior` for a finding escalated last round; `escalate` rulings have no quote so prior `quote_sha` is undefined; hash input and function not defined.
* **Recommendation:** Define `quote_sha` and what `prior` holds for escalated and quote-less rulings.

### C5 Human decision and audit result values unspecified - Major
* **Reviewer Lens:** `comprehension`
* **Affected Scope:** L13, L103, L115
* **Discrepancy:** "Open" depends on a human decision, but how a human decision on an escalated finding is recorded is not stated; only `audit` lines exist, and `result` values are not listed (only `upheld` shown; `overturned` implied).
* **Recommendation:** List allowed `result` values and the encoding of human decisions on escalated findings.

### C6 `feature_index` undefined; G8 vs `needs_audit` signature - Major
* **Reviewer Lens:** `comprehension`
* **Affected Scope:** L115, L177, L219
* **Discrepancy:** "First 5 features" has no defined counter, storage or base; G8 says sampling is a pure function of the id but `needs_audit` takes `feature_index`; L177 "every Nit ruling sampled" conflicts with 1-in-4.
* **Recommendation:** Reconcile G8 and risk table with the rule; define `feature_index`.

### C7 G5 and CUJ 4 not testable as written - Major
* **Reviewer Lens:** `comprehension`
* **Affected Scope:** L25, L62, L68, L115
* **Discrepancy:** G5 "every effective ruling is sampled" contradicts 1-in-4 after feature 5; CUJ 4 outcome "valid, escalated or sampled" is not a testable result.
* **Recommendation:** Align G5 with the sampling rule; give CUJ 4 a precise expected result.

### C8 Rollout threshold has no evaluator or sample-size guard - Major
* **Reviewer Lens:** `comprehension`
* **Affected Scope:** L35, L115, L169
* **Discrepancy:** Fallback if overturn rate >10% after 5 features is automatic in wording, yet open question 2 admits minimum n is undecided, and there is no tooling or dashboard; unclear who evaluates and when.
* **Recommendation:** State the evaluator and moment; set a minimum n.

### C9 Phase exit checks reference unnamed test classes - Major
* **Reviewer Lens:** `comprehension`
* **Affected Scope:** L203-206, L226
* **Discrepancy:** Phase 1 exit check runs `TestValidate`, but the test-file section names no classes ("one test per name"). Checks are not runnable as described.
* **Recommendation:** Name the test classes in the test-file section.

### C10 `prior` cannot be rebuilt from the log - Major
* **Reviewer Lens:** `comprehension`
* **Affected Scope:** L109, L213, L217
* **Discrepancy:** `validate` needs `prior` with `quote_sha`, but the ruling log line stores the citation without the quote and the ruling shape has no `quote_sha`.
* **Recommendation:** Add `quote_sha` to the log line or specify how `prior` is derived.

### C11 "Hypothesis 2" not glossed - Nit
* **Reviewer Lens:** `comprehension`
* **Affected Scope:** L13, L17
* **Discrepancy:** P6 explained inline, "hypothesis 2" is not.
* **Recommendation:** Add a one-line gloss.

### C12 `confidence` vs `conf` naming - Nit
* **Reviewer Lens:** `comprehension`
* **Affected Scope:** L80, L92
* **Discrepancy:** Output field `confidence` and log field `conf` differ.
* **Recommendation:** Use one name or note the mapping.

### C13 S2 placeholder replacement trigger - Nit
* **Reviewer Lens:** `comprehension`
* **Affected Scope:** L37
* **Discrepancy:** S2 result "only a candidate title"; no owner or trigger for replacing the placeholder.
* **Recommendation:** Note owner or trigger.

### C14 "reject" vs `decline` wording - Nit
* **Reviewer Lens:** `comprehension`
* **Affected Scope:** L133, L34, L190
* **Discrepancy:** Alternative A says "accept, reject, defer" while the verb is `decline`.
* **Recommendation:** Short note if needed.

### C15 Config and Triage dependency unverifiable in isolation - Nit
* **Reviewer Lens:** `comprehension`
* **Affected Scope:** L204
* **Discrepancy:** `herd.toml` described only as "Config"; Triage's Python pin and herd.toml existence cannot be verified from this document alone (reviewer had no GoldfishContext).
* **Recommendation:** Cross-reference the Triage section explicitly.
