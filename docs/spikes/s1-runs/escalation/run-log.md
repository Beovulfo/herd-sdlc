# S1 run 3: Escalation issue and /herd hold, /herd resume

Executor: Claude Code, EGM plugin v0.1.1. Same rules as runs 1 and 2: gates answered from PRD text only.

## egm-brainstorm: self-answered interview (PRD s4 Escalation and Commands, s5, s6, P6)

| Question | Self-answer |
| --- | --- |
| Problem | The only non-H1 human touchpoint. When a loop exceeds 3 rounds, a budget is exceeded, the Arbiter's confidence is low, or a real trade-off needs a human, the feature must pause and a human must be asked, once, in one place. |
| Consumer | The maintainer who answers; the orchestrator that pauses and resumes the feature; the metrics (touchpoints per feature count escalations). |
| Hard constraints | One GitHub issue per escalation. Feature pauses until answered. `/herd hold` and `/herd resume` maintainer-only (P6). Comment and issue text untrusted. GitHub (`gh`) only. State derived from GitHub where possible; state record holds only what GitHub cannot. |
| Edge cases | Several triggers at once; hold during an escalation; resume with no answer; non-maintainer posts the command; escalation raised twice for the same cause; answer is ambiguous; reminder timing (PRD says 24h for H1 only). |
| Out of scope | Release gate (H2), Evidence Auditor, deciding what the answer should be. |
| Today | EGM has no escalation: the human is always in the loop. |
| Success | Touchpoints per feature <= 2 median (s3); every pause has exactly one open escalation or hold; no feature runs while paused. |

Gate answers: readiness `Review with Goldfishes`.
Step 2 synthesizer: 7 reviewers completed, `concepts_brief.md` written (17534 bytes; 5 Blockers or Majors flagged as such, 10 open questions for the owner).
Step 3 gate answers by the Elephant (the brief's 10 open questions, judgment calls):
1. Only `low_confidence`, `rounds`, `budget`, `tradeoff` and `step_failure` open an issue. Other Arbiter causes ride the spec PR summary (Arbiter design) and become `rounds` if open at the cap.
2. Answer form: `/herd answer <n>` from a maintainer, closed options. PRD commands line edited.
3. Every issue has a `stop` option.
4. No reminders in M0 (issue assigned to maintainers; PRD gives the 24h reminder to H1 only).
5. Ceiling: 3 escalations per feature, then label `herd:blocked`, no more issues.
6. An answer to `rounds` adds 1 round.
7. Non-maintainer commands: no reply.
8. Labels `herd:hold`, `herd:escalation`, `herd:blocked`; label permission is the GitHub triage role.
9. Metric derived from GitHub events only.
10. Issue closed without a valid answer: not an answer; the bot reopens it, counts zero.
Step 4 handoff: proceed to egm-draft.
Cross-design conflict found while drafting: Triage treated any unknown `herd.yaml` key as a fallback, which would break the Arbiter's `arbiter` key and an Escalation `budget` key. Fixed in `docs/designs/herd-triage.md` (ignore other top-level keys). PRD edited: `/herd answer`.

## egm-draft
Output `docs/designs/herd-escalation.md`, one pass, no per-section gates. Same stall points: rule 13 (author picks architecture) and step 6.1 (contradiction audit). The audit found one contradiction against the brief: the brief's "no reminders" was a dissent; kept as Non-Goal and Open Question.
Placeholder values flagged in the design: `herd.yaml` `budget` numbers.

## egm-review (consolidated, uninterrupted, 1 round)
Output `round1/`: 10 reviewer runs, none failed. 3 Blockers, 22 Majors, 12 grouped Nits (deduplicated); raw 3/57/59. Defect: reviewers have no write tool, so the synthesizer wrote the stage files from returned findings; counts matched this time.

## egm-resolve
Gate `auto accept` supplied by the driver; applied by rewriting `docs/designs/herd-escalation.md` (243 to 281 lines). No finding needed a human decision; the human was not asked.
PROPOSE FIX applied: CB1 (ceiling: 3 issues opened since last `herd:blocked` removal, branch order), CB2 and CB3 (events and escalation shapes, one source for "answered"), CM1 (`blocked` status, exit, precedence), CM2 (G4 reworded), CM3 (limits derived from answers), CM4 (one cause per trigger, option actions, `human` line in `decisions.md`), CM5 (all malformed is `step_failure`), CM6 (Nit low_confidence to summary; option "proceed with open findings"), CM7 (maintainer = write or higher, shared definition as Open Question), CM8 (PRD claim reworded; PRD command line edited to `<trigger>=<n>` pairs), CM9 (trade-offs, Alternative F), CM10 to CM13 (`apply_command`, parsing algorithm, template contents, return shapes, test table, non-test dropped), CM14 and CM15 (ordering, PRD file), CM16 to CM18 (status order, terms, severity), CM20 (trigger-keyed answer), CM22 (`tradeoff` dropped).
CONTEST (checkable evidence in the repo): CM19 durable log: PRD section 5 "State ... derived from GitHub wherever possible". CM21 reminders: PRD section 4 gives the 24h reminder to H1 only. Both stay Non-Goals.
Not run: round 2 review. The Arbiter design now lacks a `human` line type; it says "readers ignore unknown keys", so no edit made.
