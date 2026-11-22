# Consolidated Review Report: herd-escalation (round 2)

**Target:** `docs/designs/herd-escalation.md` (1-277; FeatureRange 1-206, DetailedRange 207-277)
**Preset:** Consolidated report for all review rubrics, uninterrupted.

## Reviewer Status

| Stage | Reviewer | Range | Status |
| --- | --- | --- | --- |
| 5 | `egm-zoom-out` | full | completed |
| 5 | `egm-inventive-catalyst` | full | completed |
| 6 | `egm-comprehension` | 1-206, 207-277 (no context) | completed |
| 7 | `egm-design` | 1-206 | completed |
| 7 | `egm-structural` | 1-206 | completed |
| 7 | `egm-style` | 1-206 | completed |
| 8 | `egm-zoom-out` | full | completed |
| 9 | `egm-implementation-readiness` | 207-277 | completed |
| 9 | `egm-codebase-details` | 207-277 | completed |
| 9 | `egm-style` | 207-277 | completed |

## Per-stage counts (match stage files, before cross-stage dedup)

| Stage file | Blocker | Major | Nit |
| --- | --- | --- | --- |
| `zoom_out_report.md` | 0 | 9 | 6 |
| `comprehension_report.md` | 0 | 6 | 9 |
| `critic_report.md` | 0 | 13 | 21 |
| `intermediate_zoom_out_report.md` | 0 | 4 | 8 |
| `implementation_readiness_report.md` | 3 | 9 | 9 |

Consolidated, cross-stage deduplicated: **Blocker 3, Major 19, Nit 9**.

## Blocker

* **B1 No event for appending or extending a cause on an open escalation.** Lines 24, 59, 99, 114, 225-232. CUJ 2 and G2 cannot be replayed; answers validate against stale causes; "extends that issue's cause" undefined (replace/merge/keep-first, and invalidation of a prepared answer). Fix: `cause_appended` event or body-read rule.
* **B2 `answer` shape and replay validation undefined.** Lines 225, 232, 235, 247. Needs `{pairs, actor, comment_id, at}`, full state schema and per-event transitions; Phase 1 test needs a Phase 2 function.
* **B3 State cannot support the ceiling window.** Line 232, G8. Add a `blocked_cleared_at`-style field and replay rule, or drop the ceiling (see M11).

## Major

* **M1 `overrule_arbiter` undefined for decline/escalate; `decisions.md` writer conflict.** Line 112; Arbiter line 78 sole writer and `audit` line. Define all four verdicts, name the line owner, and state effect on flip check and overturn metric.
* **M2 Answer combination undefined.** Lines 27, 65, 103-112. `rounds=1 budget=2` mixes continue and `stop`; duplicates and extras; one choice per multi-finding cause. Define precedence (`stop` wins, atomic), reject duplicates, fix CUJ 3.
* **M3 Policy-escalated findings burn up to 3 rounds and a `rounds` touchpoint.** Lines 105, 110; Arbiter CUJ 3 and G3. Document cost against median target or take human-owned findings out of the loop exit condition.
* **M4 Replay trust: tamperable body, retroactive revocation, bot identity, per-comment permission fetch.** Lines 99, 112, 114, 116, 183, 225. Make the bot ack comment the only answer event; hash or bot-comment for causes; define bot identity; say when `author_is_maintainer` is read and by whom.
* **M5 Blocked state gaps.** Lines 30, 95, 124-128, 194. Blocked time counts against wall-clock; fourth trigger not remembered or re-derived after unblock; manual `herd:blocked` while an escalation is open makes it unanswerable; manual unblock uncounted (`unblocks`) and resets the ceiling; any labeler can toggle labels.
* **M6 `herd.toml` base-branch rule missing.** Lines 106, 126, 196; Triage line 83. Limits could be raised from a `herd/*` branch.
* **M7 Orchestrator design relied on but absent.** Lines 99, 114, 185, 191. Add a Dependencies section with the minimum contract.
* **M8 Alternatives rejected "by author" without trade-off; missing alternatives.** Lines 147-171.
* **M9 No scalability limit.** Lines 187-197. Full-timeline replay each boundary, pagination, rate limits.
* **M10 Transient `step_failure` costs a touchpoint.** Line 197. One automatic retry for transient failures (needs classifier).
* **M11 M0 over-build.** Lines 30, 95, 114, 126-130, 193, 232. Ceiling (G8/CUJ 8), `repeat_of`/`rule`/`repeats`, `effective_limits` with `raise_by_pct`, and `paused_seconds` arithmetic; repeat rule stated three ways. Drop or defer; round cap and budget belong to the round-loop design.
* **M12 Terminology.** Lines 13, 15, 24, 105-112. "Cause" has two meanings; `Elephant`, `arbiter_verdict`, `held_and_awaiting` undefined.
* **M13 Unreadable `malformed` rule.** Line 110. Rewrite precisely which partial-malformed cases go to the summary.
* **M14 Closed-issue and reopen semantics.** Lines 15, 89, 125, 225. State that reopen is cosmetic and status derives from events; actor check for maintainer vs orchestrator close; unowned function; reopen once then stop.
* **M15 Stale PRD edit; inexact path.** Lines 216, 262-265. PRD line 69 already has the syntax.
* **M16 Phase exit checks vs test classes contradict.** Lines 213-215, 239, 242-255.
* **M17 `apply_command`/`parse_command` under-specified.** Lines 116-123, 228-229. No issue number, no return record, grammar open, wrong-place commands, malformed pairs.
* **M18 No issue-body template, `TRIGGERS` constant or `make_cause`; reply strings not fixed.** Lines 89, 99, 101-114, 121, 129, 231.
* **M19 `effective_limits` and `paused_seconds` boundaries and rounding unspecified.** Lines 126, 128, 233-234, 255.

## Nit

* **N1 Test coverage gaps** (lines 242-255, 28-29, 89): thin touchpoints test, no inputs for status table, no tests for template, repeat, bot comments, non-maintainer, blocked/held answers; `test_closed_without_answer_stays_open` lacks a goal.
* **N2 `herd.toml` ownership** (lines 218, 257, 260; Triage line 67): pin creator and `[budget]` owner; keys to preserve.
* **N3 Python version and test command form** (lines 213-215, 224): state 3.13 and `tomllib` 3.11+; one command form.
* **N4 Document structure** (lines 7, 9, 13, 15, 21, 97, 99-139, 179, 205): section names vs standard, Terms/Status as run-in, no sub-headings, status order, rules, plain-text references.
* **N5 Wording** (lines 13, 19, 35, 114, 152, 158, 183, 192, 196): filler, overstatement, "worked line", "owner", absolute claim, notification claim.
* **N6 Forward references** (lines 13, 39, 126, 184, 191, 42): PRD filename, lifecycle steps, orchestrator path; "maintainer" definition to a shared place.
* **N7 Altitude and redundancy** (lines 15, 99, 112-114, 118-123, 128, 225-236): schemas in the plan, `held_and_awaiting`, three identifiers for the escalation issue.
* **N8 Minor behaviour** (lines 27, 59, 99, 112, 114, 125, 130, 192): batching, G5 "Anything else", assignee source, `causes_answered`, mid-step budget, `step` for `rounds`, duplicate keys.
* **N9 Detailed-range wording** (lines 218, 225, 229, 230, 235): "as in the table", `None`, restate return value, `touchpoints` type, "Phase 4 runs after that".

## Traceability matrix

| Consolidated | Sources |
| --- | --- |
| B1 | Z1, F13, F14, R1, C1 (partial) |
| B2 | R2, C5, Z5 |
| B3 | R3, C4, I1 |
| M1 | Z2, Z3, F5, I8, R10, C2 |
| M2 | Z6, Z13, F4, C15 |
| M3 | Z7, F6 |
| M4 | Z5, F3, C5, F34 |
| M5 | Z9, F7, F8 |
| M6 | F9 |
| M7 | F2, C9 |
| M8 | F1 |
| M9 | F10 |
| M10 | Z8 |
| M11 | I1-I4, Z10, C3 |
| M12 | F11, C2, F29 |
| M13 | F12, C6, I9 |
| M14 | C1, Z15, F18, R6 |
| M15 | Z4, R12, I10 |
| M16 | R11, C12 |
| M17 | R4, R5, Z12, F15 |
| M18 | R6, R7, R13 (part) |
| M19 | R8, R9 |
| N1 | R13, F27 |
| N2 | R14, I10 |
| N3 | R15, R21, C14, I12 |
| N4 | F21-F26 |
| N5 | F28, F30-F34, F17 (part) |
| N6 | C7, C8, C9, Z14, I11 |
| N7 | Z11, I5, I6, I7 |
| N8 | F14, F16, F17, F19, F20, C10, C11, C15 |
| N9 | R16-R20 |

## Compared with the previous round

Previous reports were not read. Observations on regression and design-vs-sibling consistency only:

* Leftover inconsistency, Arbiter: the `{"type":"human"}` line written by the orchestrator conflicts with the Arbiter design's sole-writer rule and `audit` line type (M1). Flagged independently by four reviewers; looks unresolved.
* Leftover inconsistency, Arbiter G3: policy-escalated findings stay open and drive a `rounds` escalation (M3); the Arbiter design describes them as listed for the human in the summary. Cross-design cost not stated.
* Leftover inconsistency, Triage: `herd.toml` is read from the base branch there; this design is silent (M6). Triage line 67 also says `[budget]` is owned elsewhere (N2).
* Possible regression from the recent TOML switch: Python version is referenced indirectly via Triage (N3), and the PRD `/herd answer` edit is already applied, leaving a stale plan item (M15). Both look like fixes applied in one place but not cleaned in the plan.
* Consistent with siblings: `tomllib` use, Python pin, fallback-counts-zero, `low_confidence` routing for Nits, `herd.toml` ownership of own keys.
* Whether M-level gaps in the event model (B1-B3) are new or leftover cannot be determined without the previous round.
