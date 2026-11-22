# Stage 5: Initial Zoom Out report

Target: `PRD — Autopilot SDLC plugin built on the Elephant-Goldfish Model.md` (whole file)
Reviewers: egm-zoom-out (simplicity and scope), egm-inventive-catalyst (false compromises). Both ran in fresh contexts with the three EGM pages as background.

## Zoom-out reviewer: verdict "over-scoped for a first version"

| # | Severity | Finding | Suggested direction |
| --- | --- | --- | --- |
| Z1 | Blocker | Scope: the PRD builds the full lifecycle at once (8 agents, 6 skills, 5 rubrics, 3 deploy adapters, L0-L3, digest, evidence grading). The core bet (an Arbiter can replace the human judge) is unproven. | Keep the P0/P1 roadmap but stop describing P1 internals. Build Define half plus Arbiter at L1 first. |
| Z2 | Blocker | Reinvents GitHub: custom state machine, auto-merge and "only Orchestrator merges", reminders and digest, when Actions, labels, branch protection, CODEOWNERS and required checks exist. A YAML state file can disagree with PR/issue state. | Use PR/issue labels and workflow state. Justify `.herd/state` only where GitHub cannot cover it. |
| Z3 | Major | Reuse of EGM: Code Auditor overlaps the existing Codebase Auditor; Test Critic and Release Reviewer may be rubric swaps; Arbiter is a non-interactive `/egm-resolve`. | Add a new persona only where the role truly differs (Arbiter and Evidence Auditor are the strongest cases). |
| Z4 | Major | Evidence apparatus is heavy for v1 (grades, `matrix.md`, `evidence/`, auditor re-runs). Re-running agent-written commands has security cost. Committed raw output bloats the repo. A "≥ 90% runnable check" metric invites gaming. | Start by pointing criteria at existing tests and letting CI be the evidence. Defer the grading taxonomy. |
| Z5 | Major | The PRD departs from EGM's philosophy (human judges findings) without saying so. A same-family Arbiter removes the control Goldfish exists to provide. | State the departure. Consider Arbiter auto-rejecting Nits only, with Blocker and Major left to the human. |
| Z6 | Major | Unattended auto-merge at L2 default; correlated errors across Elephant, Arbiter and auditor. "Escaped defects" is unmeasurable before release; M1 exits on completion rate only. | Make L1 (human merges) the only level in M0 and M1. Add L2 after defect and agreement data. |
| Z7 | Major | Altitude: the PRD drops into design detail (file tree, state path, 3-line report format, numeric tunings, scanners). The lifecycle diagram is an embedded object not visible in Markdown. | Move layouts, schemas and rubric lists to `docs/designs/`. |
| Z8 | Minor | Consistency: "six-lens" swarm count may not match EGM; FR-02 and FR-04 assume EGM supports non-interactive brainstorm and draft with no pauses (unverified); "Full or Lite" in FR-01 vs Lite as P1 in FR-15; fail-closed vs "where the harness allows". | Verify the EGM assumptions first, since they decide fork vs upstream. |
| Z9 | Nit | Metric targets (≤ 10% overturn, ≤ 15 min) exist before any baseline. | Label as hypotheses and add a baseline step in M0. |

## Inventive-catalyst reviewer: false compromises

| # | Severity | Compromise challenged | Proposed resolution (and cost) |
| --- | --- | --- | --- |
| I1 | Major | H1 blocks every feature, yet P2 says nothing blocks. The H1 PR is the only check on the Elephant's guesses. | Adaptive H1: low-risk, high-confidence features run Draft and Plan speculatively while H1 is pending; only merge waits. Costs wasted tokens, a "speculative" state, and pressure to rubber-stamp. |
| I2 | Major | Arbiter trust is sampled after the fact; it sees prose, not code, and shares a model family with reviewers. | Run 2+ Arbiters (different vendors), auto-accept unanimous, escalate on divergence. Require findings to cite a path or line. Feed human overturns back as golden examples. Costs more per finding. |
| I3 | Major | An LLM judges whether a check "can fail" where a mechanical oracle exists. | Red/green rule (check fails before the change, passes after) plus mutation or revert-the-diff run. LLM auditor only for the remainder. Slow on big suites; flaky tests need retry rules. |
| I4 | Major | A single state file written by every step, in the target repo, conflicts with concurrent triggers and pollutes history. | State derived from artifacts (labels, check runs, files present) with a single-writer lease per feature. |
| I5 | Major | Auto-merge safety rests on LLM risk labels; rollback is P1 while auto-merge is P0. | Deterministic path/diff risk floor in `herd.yaml` that agents can only raise; re-apply at merge time on the real diff; minimal rollback (revert PR plus feature flag) moves to P0. |
| I6 | Major | The self-answered interview is framed as "unattended vs async Q&A". | Rank open questions by cost if wrong; auto-fill cheap ones; post the top 1-3 irreversible ones as an async comment with a default applied if unanswered. |
| I7 | Nit | Per-platform deploy adapters assume Herd owns deploy logic. | One thin contract (deploy, health, rollback commands in `herd.yaml`); ship no first-party adapters. |
| I8 | Nit | Throughput metrics can be improved by suppressing escalations. | Pair each autonomy metric with a guard metric; a rising guard auto-downshifts the autonomy level (with hysteresis). |

## Overlaps between the two reviewers
- State and merge control: Z2 and I4 (use GitHub-native or derived state), Z6 and I5 (merge safety and rollback ordering).
- Arbiter authority: Z5 and I2.
- Evidence layer: Z4 and I3 (simplify vs mechanize).
- Adapters: Z1 and I7.

## Tensions to decide
- Z4 says defer the evidence grading; I3 says make evidence mechanical (red/green, mutation). Both agree the LLM-judge is the weak point.
- Z6 says L1 only until data exists; I1 says make H1 adaptive and speculative. These pull in different directions on human load.
- Z1 says cut scope; I2, I3 and I8 add mechanisms. Net scope needs a decision.
