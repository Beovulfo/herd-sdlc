# Goldfish Review Report: Stage 8 (intermediate zoom-out)

**Target:** `docs/designs/herd-escalation.md` (1-277)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |

Counts: Blocker 0, Major 4 (I1-I4), Nit 8 (I5-I12). Reuse check: no existing code in repo; `tomllib` consistent with Triage and Arbiter. Alternatives A-F judged sound.

## Major

### I1 3-issue ceiling is speculative machinery - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 30, 95, 232, 251 (G8, CUJ 8, `next_escalation`, `test_ceiling`)
* **Discrepancy Description**: Needs a "since last `herd:blocked` removal" window and counter reset in replay. PRD already caps rounds at 3 and has a budget; M0 has 4 triggers each bounded; overlaps `repeat_of` and the repeat-burns-touchpoints risk.
* **Rationale & Recommendation**: Drop G8, CUJ 8 and ceiling-path `blocked`; keep `blocked` only for `stop`. Add the ceiling in M1 if data shows runaway repeats.

### I2 `repeat_of` and versioned touchpoint rule without evidence of need - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 114, 130, 193
* **Discrepancy Description**: `touchpoints` returns `{opened, answered, open, repeats, rule: 1}` and repeat matching on `(feature, trigger, step)`; G6 needs only `answered`.
* **Rationale & Recommendation**: Return the answered count; drop `repeat_of`, `repeats`, `rule`; version when the rule first changes.

### I3 `effective_limits` and `raise_by_pct` leak layering - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 126, 255, 260
* **Discrepancy Description**: Derives limits from replay with a multiplicative per-answer raise, adding a config key, function and test for a feature the PRD does not request. Round cap `3+k` and budget belong to the round-loop design (line 126 says `budget_used` does).
* **Rationale & Recommendation**: Offer `budget`: continue (one more allowance owned by round-loop design) or stop; leave `continue_round` to the orchestrator.

### I4 `paused_seconds` interval arithmetic may be unnecessary - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 128, 184, 250 (G7)
* **Discrepancy Description**: Orchestrator exits on pause and bills no run, so measuring active step time excludes pause for free; interval-union over hold and escalation intervals may be redundant.
* **Rationale & Recommendation**: Measure active step time or defer G7.

## Nit

* **I5** (lines 15, 99, 118-123): `held_and_awaiting` as a fifth status inflates the command table; two booleans plus `blocked` give the same behaviour.
* **I6** (lines 112-114, 225-236): altitude; event/cause schemas, 7-value `action` enum, marker format and signatures; consolidate schemas, trim plan to components and data flow.
* **I7** (line 114): hidden marker, `herd:escalation` label and event `kind` identify the same thing three ways; pick the label with bot-author check.
* **I8** (line 112, 202): `decisions.md` human line conflicts with Arbiter sole-writer rule (Arbiter line 78, only `header`/`ruling`/`audit` types) and own Future Improvements; add `human` type to Arbiter `format_lines` or drop.
* **I9** (lines 105, 110): partial-`malformed` rule vague; Arbiter causes `policy`, `citation`, `flip`, `missing`, `unknown`, `malformed`, `arbiter`, `low_confidence`; state precisely which partial cases go to the summary.
* **I10** (lines 213-216, 260, 262-265): PRD line 69 already has the new `/herd answer` syntax so the edit and Phase 4 grep are stale; Triage line 67 says `budget` is owned elsewhere, name `[budget]` ownership once.
* **I11** (line 13, Open Question 2): fold the "maintainer" definition into one shared place such as PRD terms.
* **I12** (lines 213-215): test command form `python3 -m unittest scripts.test_herd_escalation...` vs Triage `python3 -m unittest scripts/test_herd_triage.py`; pick one (dotted form relies on namespace packages, fine on 3.13).

Summary from reviewer: stripping I1-I4 removes about a third of functions and tests without losing a PRD requirement; resolve the `decisions.md` writer conflict (I8) before build.
