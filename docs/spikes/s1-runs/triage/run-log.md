# S1 run 1: Triage (risk, size, path, risk floor)

Executor: Claude Code, EGM plugin v0.1.1, reading `skills/*/SKILL.md` and following it in one thread.
Human turns during the run: 0 (after the instruction "yes go ahead").
Rule: every gate is answered by the Elephant from PRD text only. No other human input.

## egm-brainstorm

### Step 1 interview (self-answered, source: PRD sections 2, 4, 5, 6)

| Interview question (SKILL.md Step 1.2) | Self-answer | PRD source |
| --- | --- | --- |
| Problem solved | Step 1 of the lifecycle must set risk, size and path before any other agent runs. Without it, no step knows whether a feature takes the Full or Lite path or needs more review. | s5 row 1 |
| Consumer | The orchestrator and the Arbiter read the result from `.herd/state/<feature>.yaml`. The human sees risk on the H1 PR. | s4 H1, s5 State |
| Hard constraints | Triage output is a proposal. `herd.yaml` path rules set a floor that Triage cannot lower. No secrets in agent context. Issue text is untrusted. | s5 Risk floor, P6 |
| Edge cases / out of scope | Out: builders, release gating, cost estimation beyond the `herd.yaml` budget. Edge: issue text asks the agent to lower the risk (injection). Edge: a feature touches no path rule. | s3, P6 |
| Today | A human decides ad hoc. EGM has no triage step. | s1 |
| Success measure | Deterministic checks on the floor rule. Reported rate of human edits to risk at H1. | s3, s4 |

### Gate answers

| Gate (SKILL.md) | Answer supplied | Reason |
| --- | --- | --- |
| Step 1.3 readiness | `Review with Goldfishes` | Hypothesis anchored from PRD. |
| Step 2 synthesizer | Spawned `egm:egm-synthesizer`, 7 reviewers, mode BRAINSTORM | Completed, no reviewer failed. `concepts_brief.md` written (12538 bytes), 17 findings, 2 Blockers. |
| Step 3 iterate | `Accept the recommended direction for every Key Decision, drop size and path from M0` | Zoom-out cut; PRD has no M0 reader for them. Human lowering below floor allowed and logged (P5). |
| Step 4 handoff | `Proceed to egm-draft` | Equivalent to the "Proceed egm-draft" option. |

Stalls: none in this skill. Note: Step 3 asks the user how to address objections, so the Elephant had to decide; the decisions are recorded above and are the only judgment calls.
Observation: the synthesizer reported the SKILL.md Step 2 template as partly garbled when read; the brief structure was rebuilt from the legible parts.

## egm-draft

Context file: `concepts_brief.md` (Priority 1 intake). Output: `docs/designs/herd-triage.md`.

| Gate (SKILL.md) | Answer supplied | Reason |
| --- | --- | --- |
| Section approval, each of 4 sections | `Approve [section] and proceed` | No inline comments exist, so the gate has nothing to apply. Deviation: all sections were written in one pass, not one per turn. |
| Rule 13, author decides architecture | Elephant chose the brief's recommended direction for each of the 6 Key Decisions | The skill says never to pick for the author and to re-present the gate; unattended, no author exists. This is the main human-substitution point and the Arbiter's future job. |
| Step 6.1 contradiction audit | One contradiction found: the draft drops size and path, the PRD lists them | The skill says stop and ask the user. Not stopped: recorded as the first Open Question in the design and as file 6 in the plan. |
| Step 6.2 save location | `Save to detected directory: docs/designs/` | CLAUDE.md names it. |
| Step 6.3 index | No `SITEMAP.md` or `README.md` in `docs/designs/`, nothing registered | |

Stalls: Step 6.1 and rule 13 both say stop and wait. Both would block a driver that cannot yield a turn.
Check: `ls -la docs/designs/herd-triage.md`.

## egm-review (consolidated preset, uninterrupted)

| Gate | Answer supplied | Reason |
| --- | --- | --- |
| Step 2 preset | `Consolidated report for all review rubrics` | Only preset with no checkpoints. |
| Step 3 split | Automatic (standard layout, L=154) | No gate hit. |
| Stage 7 and 9 review loop | Single round, no `egm-review-loop` | Time; the loop was not exercised, so its round cap is untested. |

Result: 5 stages ran in order, 7 reviewer types, none failed. 8 Blockers, 15 Majors, Nits. Files: `zoom_out_report.md`, `comprehension_report.md`, `critic_report.md`, `intermediate_zoom_out_report.md`, `implementation_readiness_report.md`, `consolidated_review_report.md`.
Stalls: none from gates. Defect found: the Read tool returned a lossy view that dropped short words, so reviewers raised false "corrupted text" findings; the synthesizer dropped them after grep checks. The reviewers may misjudge other findings for the same reason.

## egm-resolve

| Gate | Answer supplied | Reason |
| --- | --- | --- |
| Step 4 resolution gate | `auto accept` | Yields zero tools in the skill. The driver supplied the reply from the run rule. |

Result: `goldfish_review_report.md` written. 8 Blockers and 15 Majors classified: 19 PROPOSE FIX, 3 ESCALATE (B2, M2, M4), 1 partial CONTEST (M13). All PROPOSE FIX items applied to `docs/designs/herd-triage.md` (198 lines to rewritten file). ESCALATE items were not fixed; recorded as Open Questions.
Not run: the re-audit after fixes (cap is 1). The revised design has not been re-reviewed.
Check: `ls docs/spikes/s1-runs/triage/`.

## Escalations answered (human, after resolve)

| Item | Human answer | Applied |
| --- | --- | --- |
| B2, M4 M0 scope | Floor plus display value only; ratchet and history to M1 | Design: ratchet, history, CUJ 5 removed; `risk.override` replaces `risk.history`; M1 note added |
| M2 floor input trust | Accepted: floor `medium` unless maintainer `risk:low` | Design Floor section, CUJ 2 |
| PRD conflict | Design is right | PRD: step 1 row, state line, M3 line, commands line edited |

Human turns in S1 run 1: 1 escalation answer (3 items). Not re-reviewed after these edits.

## Round 2 review (revised design, fresh reviewers, 1 round)

Output: `round2/` (5 stage reports plus `consolidated_review_report.md`). Result: 4 Blockers, 12 Majors, nits. Round 1 had 8 Blockers and 15 Majors. Not run: `egm-resolve` on round 2.
Stall: the synthesizer returned "not complete" while its stage 5 reviewers were still running, and had to be resumed by the harness notification. A driver must wait on background children, not trust the first hand-back.

## Round 2 resolve (human decision, then Elephant)

Human answer: "yes defer" to: defer G5 (tamper check) and race handling to M1, rules-only M0. Applied by rewriting `docs/designs/herd-triage.md`.
Disposition of round 2 findings: 1 deferred to M1 (Non-Goals, Risks); 3 path extraction fixed (regex, normalisation); 4 pinned (Python 3.13, `PyYAML==6.0.4`, from `pip index`); 2, 5, 15, 16 fixed (signatures in plan only, fixtures replaced by inline unittest cases, phases); 6, 7, 8, 9 removed with the agent, shadow mode, rollback narrowed; 10 override stores login and comment id; 11, 12, 13, 14, 17 fixed or dropped. `egm-resolve` "auto accept" was applied by hand, not by running the skill's gate. Round 3 review not run.
PRD edited again: step 1 agent column, risk floor paragraph.
Verification not run: the design describes code that does not exist yet.

## Verdict, run 1 (Triage)

Pass criterion: each of 4 steps produced its artifact with zero human turns. Met: `concepts_brief.md`, `docs/designs/herd-triage.md`, consolidated review reports (rounds 1 and 2), `goldfish_review_report.md`.
Human turns after "go ahead": 2 answers (3 escalated items, then "defer"). Both were scope decisions the Arbiter would face, not gate prompts.
Gates that needed a driver answer: brainstorm readiness, step 3 iterate, step 4 handoff; draft section approvals, architecture choice (rule 13), contradiction audit (6.1), save location; review preset; resolve "auto accept".
Gaps in EGM as shipped: rule 13 and 6.1 say stop and wait; resolve yields zero tools; `egm-review-loop` and its 3-round cap not exercised; synthesizer hand-back can precede its children; Read tool can mislead reviewers (drops short words).
Open: Round 3 review of the rules-only design not run.
