# Goldfish Review Report: Stage 8 (intermediate zoom-out)

**Target:** `docs/designs/herd-arbiter.md` (1-253)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |

Counts: Blocker 0, Major 4, Nit 5. Reviewer found no scripts/, rubrics/ or agents/ files in the repo, so nothing to reuse.

### M1 Wrong-judged Blocker/Major findings still burn the round cap - Major
* **Reviewer Lens:** `zoom-out`
* **Affected Scope:** L13, L17, L23, L36, L62; Escalation L110
* **Discrepancy:** G3 turns every decline/contest on a Blocker/Major into `escalate/policy`; it stays "open"; `policy` opens no issue (Escalation L110). Unchanged spec makes fresh Goldfish re-raise; Arbiter contests again; flip does not fire (same verdict). Loop always runs to round 3 and the `rounds` escalation costs a touchpoint against the <=2 median.
* **Recommendation:** Either have the orchestrator stop re-reviewing a finding whose id already has a `policy` escalation with unchanged quote and carry it to the spec PR summary, or record the cost as a known M0 consequence. Update CUJ 3 to say what the loop does next.

### M2 Audit sample not "every effective ruling" and dodgeable - Major
* **Reviewer Lens:** `zoom-out`
* **Affected Scope:** L25, L115, L167, L182, L219
* **Discrepancy:** G5 vs `int(id,16) % 4 == 0` after feature 5 (25%). Id is an unsalted SHA-1 of attacker-controllable text; about 4 tries pick a non-sampled id, contrary to P6.
* **Recommendation:** Fix G5 wording; mix an unpredictable value (spec hash plus orchestrator-held salt) into the hash, keeping it a pure function so G8 holds.

### M3 Overturn metric differs from PRD target - Major
* **Reviewer Lens:** `zoom-out`
* **Affected Scope:** L115; PRD section 3 (L39)
* **Discrepancy:** PRD target is <=10% on Blocker/Major; design pools all severities and splits only by `same_model`; Nit volume can dilute.
* **Recommendation:** Split by severity class or report the B/M subset.

### M4 Merge severity rule missing; re-ask rule self-contradictory - Major
* **Reviewer Lens:** `zoom-out`
* **Affected Scope:** L25, L80, L95, L217; Escalation L110
* **Discrepancy:** Same normalised text with different severities from two personas has no selection rule; a lowest-wins rule lets a Blocker become an effective decline. Check 1 (L95) re-asks on any schema break; `validate` (L217) re-asks only when all rulings are `malformed`; Escalation L110 treats "some but not all malformed" as summary items.
* **Recommendation:** Highest severity wins plus a test; pick one re-ask rule and align G5/`step_failure`.

### M5 Single-writer claim vs other writers - Nit
* **Reviewer Lens:** `zoom-out`
* **Affected Scope:** L78, L110-113
* **Discrepancy:** `herd_arbiter.py` "only writer", yet humans append `audit` lines (no tooling) and Escalation appends `{"type":"human"}` lines. `result` values undefined beyond `upheld`; `agreed_escalations` and `overturn_rate` need them; `feature_index` source undefined.
* **Recommendation:** Name who appends and how; drop "only writer"; define `result` values and `feature_index` source.

### M6 PRD divergence not carried back to the PRD - Nit
* **Reviewer Lens:** `zoom-out`
* **Affected Scope:** L34, L89-92; PRD L89, L120
* **Discrepancy:** PRD still says the Arbiter "accepts, rejects or defers" and "defers non-blocking findings to a backlog"; design drops `defer` and renames verdicts, without a PRD edit (Escalation makes one for its own change).
* **Recommendation:** Add a PRD-edit item to the file list or an Open Question.

### M7 `escalate` with `L` confidence precedence - Nit
* **Reviewer Lens:** `zoom-out`
* **Affected Scope:** L94, L101; Escalation L112
* **Discrepancy:** Check 3 gives an `escalate`+`L` ruling cause `low_confidence`, not `arbiter` (L101 reads otherwise). Escalation `overrule_arbiter` ("opposite of `arbiter_verdict`") is undefined when that verdict is `escalate`.
* **Recommendation:** Fix precedence; `low_confidence` trigger only when `arbiter_verdict` is accept/contest/decline.

### M8 Citation matching brittle; Grep/Glob purpose unclear - Nit
* **Reviewer Lens:** `zoom-out`
* **Affected Scope:** L78, L99, L235
* **Discrepancy:** "Quote appears in the cited lines" has no comparison rule; exact substring will cause spurious `citation` escalations on whitespace/lossy reads. Grep/Glob given though citations may cite only the spec path.
* **Recommendation:** State whitespace-normalised matching plus a test; drop Grep/Glob (smaller injection surface) or explain them.

### M9 Phase 1 exit check names undefined test class - Nit
* **Reviewer Lens:** `zoom-out`
* **Affected Scope:** L201, L225-226
* **Discrepancy:** `TestValidate` is not defined in the test-file description.
* **Recommendation:** Name the class or use the module-level command.
