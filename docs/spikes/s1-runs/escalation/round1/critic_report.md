# Goldfish Review Report: Stage 7 (design + structural + style, FeatureRange)

**Target:** `docs/designs/herd-escalation.md` (lines 1-194), standard `feature-spec-standard`, one round

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-design` | completed |
| `egm-structural` | completed |
| `egm-style` | completed |

Counts: Blocker 0, Major 10 (design 7, structural 1, style 2), Nit 19 (design 6, structural 5, style 8). Total 29 (not deduplicated across reviewers). The style reviewer's "KEEP" note on line 183 is not a finding and is not counted.

## Findings: egm-design

### D1 `herd:blocked` contradicts "pause is derived" - Severity: Major
* **Affected Scope:** lines 21, 28, 96, 120
* **Description:** G1 says paused iff `herd:hold` or open escalation. Line 96 says `herd:blocked` is "never `running`"; G8 and the `stop` answer set it. After `stop` the issue is closed and no hold label exists, so `herd_status` (four values) has no fit. No one clears `herd:blocked`; every dead end is permanent.
* **Recommendation:** Add a fifth status `blocked` or fold the label into G1; state the unblock path; add a test.

### D2 G8 vs CUJ 8 ceiling - Severity: Major
* **Affected Scope:** lines 28, 88-92, 182
* **Description:** G8 blocks the fourth issue, CUJ 8 blocks the third. Unclear if abandoned, reopened or "repeat of #N" issues count; unclear how a ceiling of 3 fits the PRD median <=2 target.
* **Recommendation:** Pick one number, define what counts.

### D3 `rounds` trigger cannot settle open policy findings - Severity: Major
* **Affected Scope:** lines 102, 108; herd-arbiter.md lines 62, 98
* **Description:** Arbiter turns declines/contests on Blocker/Major into `escalate` with cause `policy`, decided by a human at the spec PR. Here such findings route to `rounds` at the cap with only "one more round" or "stop"; another round cannot resolve them, so touchpoints burn to the ceiling and the feature is `blocked`.
* **Recommendation:** Add option "proceed to the spec PR with open findings listed" or exclude `policy`-only findings from `rounds`.

### D4 Arbiter causes not mapped consistently - Severity: Major
* **Affected Scope:** lines 104-108
* **Description:** `malformed` omitted from the non-escalating list; `step_failure` covers malformed after re-ask, but the Arbiter design makes it a per-finding `escalate` cause. `low_confidence` has no severity filter, so one Nit pauses the feature. "As the Arbiter design says" is overbroad (its summary lists every `escalate`, `low_confidence` included).
* **Recommendation:** Give `malformed` an explicit route; restrict `low_confidence` to Blocker/Major or justify the Nit case against the touchpoint target.

### D5 Cause and answer semantics undefined - Severity: Major
* **Affected Scope:** lines 22, 25, 56, 104, 120
* **Description:** "Cause" could mean trigger or finding; order of numbers in `/herd answer 1 2` undefined; behaviour when a cause is appended (CUJ 2) after an answer is posted but before processing undefined; line 120 gives actions only for `rounds`, `budget`, `stop` (missing `step_failure` retry, `low_confidence` 1 and 2, `tradeoff`).
* **Recommendation:** Define cause as a `(trigger, step or finding id)` pair with fixed order; bind answers to the cause list at answer time or reject as stale; write an action per option.

### D6 Raised cap and budget have no home - Severity: Major
* **Affected Scope:** lines 120, 126, 185
* **Description:** Answers raise round cap and budget, but line 126 says the design owns nothing in the record except `budget_used`. `raise_by` is one value for two limits (`tokens`, `minutes`). Line 126 self-contradicts.
* **Recommendation:** Define effective cap/budget as base plus answered escalations; split `raise_by` per limit.

### D7 "Maintainer" = triage role has spending and verdict authority - Severity: Major
* **Affected Scope:** lines 35, 112, 183
* **Description:** Triage is the lowest role that can label and close issues; PRD P6 says "repository maintainers". Risk table accepts it for hold/resume only, but triage can answer `budget`, `rounds` and overrule an Arbiter verdict. Triage design never defines "maintainer".
* **Recommendation:** Require write or higher for `/herd answer`, or document the acceptance; define once, share across designs.

### D8 G4 vs command table - Severity: Nit
* **Affected Scope:** lines 24, 117
* **Description:** G4 says resume with open escalation is "refused"; table and CUJ 4 say the hold is removed and the reply names the issue.
* **Recommendation:** Reword G4 to "resume never clears an escalation".

### D9 Alternative D stale - Severity: Nit
* **Affected Scope:** line 160
* **Description:** PRD already lists `/herd answer <n>` (PRD line 69); the new part is the multi-number form.
* **Recommendation:** Say the PRD needs `<n> [<n> ...]`.

### D10 Rejection rationales cite authority; missing alternatives - Severity: Nit
* **Affected Scope:** lines 142, 148, 154, 160, 166
* **Description:** "Rejected by author" / "The PRD says" instead of trade-offs. Missing alternatives: timeout default (a non-goal; give a one-line rejection) and a protected/signed state flag.
* **Recommendation:** Restate trade-offs; add the two alternatives.

### D11 Answer/close ordering race - Severity: Nit
* **Affected Scope:** lines 62, 86, 120
* **Description:** Answer recorded "in the closing comment" while a close without answer is reopened (CUJ 7); if the bot closes first, its own close triggers the reopen. `touchpoints()` should read the bot record comment, and needs maintainer role per event since roles can change.
* **Recommendation:** State record comment is posted before close; state which comment `touchpoints()` reads; pass role per event.

### D12 Command parsing unclear - Severity: Nit
* **Affected Scope:** line 112
* **Description:** "First line outside quote and code fences" vague; `/herd answer` on a non-escalation issue unspecified; reply vs silence for no-op cases unspecified (G3 covers only non-maintainers).
* **Recommendation:** Specify.

### D13 Human-minutes metric unsourced; repeat key undefined - Severity: Nit
* **Affected Scope:** lines 110, 124; PRD line 41
* **Description:** Paused time is "not human minutes", so the PRD "Human minutes per feature" metric is unmeasured. `step` in `(feature, trigger, step)` is undefined for `rounds` and `budget`.
* **Recommendation:** Say deferred or replaced; define `step` for those triggers.

## Findings: egm-structural

### S1 "Rejected by author" fields carry no rationale (A, C, D, E) - Severity: Major
* **Affected Scope:** lines 140-166
* **Description:** A and C state a trade-off; D and E give none in the field (reasoning only in Cons; D's field states the cost of the chosen path). Standard requires concrete trade-offs and bars unlinked maintainer attribution.
* **Recommendation:** Drop attribution; state the trade-off in each field; link a decision record if one exists.

### S2 Section name differs from standard - Severity: Nit
* **Affected Scope:** line 94
* **Description:** Standard calls it "Proposed Architecture"; here "Technical Plan".
* **Recommendation:** Rename or add pointer.

### S3 Sub-topics are bold run-in labels - Severity: Nit
* **Affected Scope:** lines 96-126
* **Description:** Eight sub-topics are not H3 headings and cannot be linked.
* **Recommendation:** Promote to H3.

### S4 Data-flow diagram placement - Severity: Nit
* **Affected Scope:** lines 128-134
* **Description:** Last item in Technical Plan; most useful at the top.
* **Recommendation:** Move up.

### S5 Inconsistent horizontal rules - Severity: Nit
* **Affected Scope:** lines 7, 168, 193
* **Description:** One after metadata, one before Non-Functional Requirements only, one trailing.
* **Recommendation:** Use consistently or drop.

### S6 Traceability gaps - Severity: Nit
* **Affected Scope:** lines 21-28, 86
* **Description:** CUJ 7 cites `test_closed_without_answer_stays_paused`, not listed under any Goal; G6 covers the case but cites only `test_touchpoints`.
* **Recommendation:** Add the test to G6 or add a Goal.

### S7 Terms nested in Overview; Open Questions early - Severity: Nit
* **Affected Scope:** lines 13, 39-42
* **Description:** Dense Terms paragraph; Open Questions precede CUJs and plan. Optional.
* **Recommendation:** Terms H3; move Open Questions after Risks.

## Findings: egm-style

### Y1 Claims about the PRD do not match the PRD - Severity: Major
* **Affected Scope:** lines 17, 160
* **Description:** Line 17 says the PRD does not say what counts as an answer; PRD section 4 (line 69) defines `/herd answer <n>`. Line 160 says the command is "added to PRD section 4"; it is already there. Real delta: multiple numbers, one per cause.
* **Recommendation:** Say the PRD defines `<n>` and this design extends it; narrow line 17; fix the PRD to match.

### Y2 `herd:blocked` outside the pause definition - Severity: Major
* **Affected Scope:** lines 13, 21, 96
* **Description:** G1 and line 13 define paused without `herd:blocked`; line 96 says blocked is never `running`; `herd_status` returns only four values. After G8 or `stop` the stated rules give `running`.
* **Recommendation:** Add `herd:blocked` to the definition or add a fifth status; name it in `test_status_table`.

### Y3 "Everything is derived from GitHub state" overclaims - Severity: Nit
* **Affected Scope:** line 11
* **Description:** `budget_used` lives in the record (line 126).
* **Recommendation:** "Pause and touchpoint state is derived from GitHub."

### Y4 Subjective phrasing - Severity: Nit
* **Affected Scope:** lines 17, 147
* **Description:** "making the median meaningless", "the touchpoint median says nothing".
* **Recommendation:** "inflating the touchpoint count per feature".

### Y5 "goes stale" undefined - Severity: Nit
* **Affected Scope:** line 33
* **Recommendation:** Name a threshold (e.g. open more than 24 hours).

### Y6 Redundant sentence - Severity: Nit
* **Affected Scope:** line 110
* **Description:** "Its author is the bot" repeats the earlier clause.
* **Recommendation:** Drop it.

### Y7 Awkward sentence - Severity: Nit
* **Affected Scope:** line 124
* **Recommendation:** "Paused time is wall-clock time, not human minutes."

### Y8 Wordy, self-contradicting state-record sentence - Severity: Nit
* **Affected Scope:** line 126
* **Recommendation:** "The record keeps the PRD's round counter (`rounds`) and `budget_used`. This design adds no other key."

### Y9 "the human decides in the open spec PR" unclear - Severity: Nit
* **Affected Scope:** line 174
* **Recommendation:** Name the decision or drop the clause.

### Y10 "exceed the intent" vague - Severity: Nit
* **Affected Scope:** line 185
* **Recommendation:** "exceed the owner-set limit".
