# PRD: Herd, an evidence-based autopilot SDLC plugin built on the Elephant-Goldfish Model

Status: Draft v2 (revised after an EGM review; the review reports and v1 are in git history, commit 3ed136e) · Date: 2026-11-22 · Author: Toni

> **Implementation status (version 0.13.4, 2026-11-25).** This PRD specifies the full product, including GitHub automation. What exists today is the local autopilot described in the [README](../README.md), the [wiki](https://github.com/Beovulfo/herd-sdlc/wiki) and the [changelog](../CHANGELOG.md): evidence harness, Stop gate, the run rules it enforces (red first, risk, frozen and verbatim human criteria, `test_budget`, `known_limits`, `coverage` and `inputs` at medium and high risk, commit before done), quick route, detection, lint hook, caveat log, adversarial pass (its six standard attacks enforced at `herd done`), `herd cancel`, the stop record (`stopped.json`), the guard hook, the opt-in `herd pr` step and the opt-in worktree start. The Triage module computes the risk floor of every task. The Arbiter and Escalation modules in `plugin/scripts/` implement the designs in `docs/designs/`, are unit tested, and are not yet wired to GitHub. The builder model must be Sonnet or stronger: Haiku is not supported for reliable results (evidence: [#31](https://github.com/Beovulfo/herd-sdlc/issues/31)). Where this PRD names `.herd/state/<feature>.json`, the local harness keeps `.herd/tasks/<slug>/` instead.

## 1. Problem

The Elephant-Goldfish Model (EGM) is a spec-driven workflow: an **Elephant** agent with full project context drafts, and **Goldfish** reviewers with no prior context check the result ([README](https://github.com/google/elephant-goldfish-model)). It covers requirements, design and design review. It does not cover build, test or release, and it needs a person to answer interviews, approve each spec section, triage every finding and merge the spec PR.

In EGM the human acts as scheduler (deciding what runs next) and judge (deciding which findings to act on). We believe agents can take over both roles, if the human keeps control of what matters: the goal, the success criteria, and a review of evidence. This is a hypothesis, not a proven fact (section 6).

**Herd** is a plugin in this repo (`herd-sdlc`) that composes EGM's skills and personas and adds orchestration, an Arbiter that judges findings, and an evidence step.

## 2. Principles

**Motto: Shift left, with autopilot.** Shift left means finding problems at the plan, before code is written, and the autopilot does the rest with evidence.

- **P1 Humans provide goals and success criteria; agents provide evidence.** Each success criterion has a `check`: a command, test or probe, and the expected result. The human reviews evidence, not process.
- **P2 Minimal start.** A one-paragraph goal is enough to start. Success criteria, constraints, examples and extra evidence sources are optional; each one the human adds raises the success rate.
- **P3 Gaps never block.** Missing criteria or checks are filled in by agents, marked `agent-proposed`, and listed under "Assumptions and gap-fills" for the human. Human-written criteria are never altered by agents. If a check cannot run, the agent writes a substitute (a test, script or proxy measure) and says so. Agents stop only for an irreversible risk or a real trade-off, never for missing detail.
- **P4 Evidence is stored, not asserted.** A criterion status is `passing`, `failing` or `unchecked`. Each `passing` or `failing` status links to an artifact (CI run, test output, commit SHA). `unchecked` criteria are listed and never counted as met.
- **P5 Every autonomous decision is reported in at most 3 lines** (decision, reason, how to override). Human overrides take precedence and re-run the affected steps.
- **P6 Untrusted input.** Issue text, comments and linked documents may carry prompt injection. Only repository maintainers can apply the `herd` label or post `/herd` commands. Agents never receive secrets.

## 3. Goals, non-goals, success metrics

**Goals (M0)**
1. Take a goal from a GitHub issue to an approved, reviewed spec with a test plan, with the human acting only at the Intent gate.
2. Replace the human's triage of findings with an Arbiter, and measure its overturn rate.
3. Record every Arbiter ruling so the human can audit it afterwards.

**Non-goals (M0)**
- Building, merging or releasing code. M0 ends with an approved spec; later phases are in section 7.
- Replacing EGM. Herd reuses EGM skills, personas, `egm-lite` and `egm-review-loop`, and adds only what is missing.
- Choosing product priorities. The human decides what enters.
- Blocking on missing detail (P3).

**Success metrics (M0 pilot).** All targets are hypotheses until a baseline exists. The first pilot task is to record that baseline by running EGM by hand on the same features (spike S2).

| Metric | Definition | Target (to validate) |
| --- | --- | --- |
| Arbiter overturn rate | Share of Arbiter rulings a human reverses when auditing (every ruling for the first 5 features, then a 25% sample) | ≤ 10% on Blocker and Major findings |
| Human touchpoints per feature | Gate approvals plus escalations answered | ≤ 2 on median |
| Human minutes per feature | Time spent at the gate and on escalations | Measured; target set after the baseline |
| Gap-fill rework | Agent-proposed criteria the human edits or rejects at the gate | Reported. A very low rate is a warning sign for rubber-stamping, not a success |
| Criteria with a runnable check | Criteria in approved specs whose status is not `unchecked` | Reported per feature |

M0 is judged on at least 20 features or 3 repositories, whichever comes first. With fewer, results are reported as anecdotal.

## 4. The human contract

| Input | Required? | Effect |
| --- | --- | --- |
| Goal (issue text; a paragraph is enough) | Yes | Starts the feature |
| Success criteria, ideally with checks | No | Human-written criteria are authoritative |
| Constraints, examples, non-goals, risk tolerance | No | Narrow the agents' assumptions |
| Extra evidence sources (datasets, dashboards, test accounts) | No | Turn `unchecked` criteria into checked ones |

**Gates by autonomy level.** M0 supports L0 and L1 only.

| Level | Intent gate (H1) | Spec merge | Release gate (H2) | Available |
| --- | --- | --- | --- | --- |
| L0 Assist | Human performs every step, as in EGM today | Human | n/a | M0 |
| L1 Supervised (default) | Every feature | Human | n/a (no release in M0) | M0 |
| L2 Gated | Every feature | Herd, unless risk is high | High risk only | After M1 |
| L3 Autonomous | High-risk features only; Lite path for the rest | Herd | High risk only | After M3 |

**H1, the Intent gate.** One PR containing the brief, the success criteria (each marked `human` or `agent-proposed`, with its check), the assumptions and gap-fills list, and the risk score. The human approves, edits or rejects it. If there is no answer the feature waits, with a reminder after 24 hours. Comments on the issue or PR are folded in at the next step.

**Escalation.** One GitHub issue, opened when a loop exceeds 3 rounds, a budget is exceeded, the Arbiter's confidence is low, or a real trade-off needs a human. The feature pauses until answered. This is the only other human touchpoint, and the metrics count it.

**Commands.** `/herd hold` pauses a feature and `/herd resume` continues it. `/herd risk <level>` sets the risk level (a human override, recorded). `/herd answer <trigger>=<n> [<trigger>=<n> ...]` answers an open escalation by choosing a numbered option for each cause. All four are maintainer-only.

## 5. M0 lifecycle

Steps 1 to 9; the only human step is 4.

| # | Step | Agent | Output | EGM reuse |
| --- | --- | --- | --- | --- |
| 1 | Intake | Triage (rules only in M0; an LLM proposal is an M1 question) | Risk (low, medium, high) in the state record | New |
| 2 | Ideate | Elephant | `concepts_brief.md` with an assumptions list | `/egm-brainstorm`, run non-interactively (spike S1) |
| 3 | Draft criteria | Elephant | Success criteria in Given/When/Then, each with a `check` | New |
| 4 | **Intent gate (H1)** | Human | Approve, edit or reject the PR | — |
| 5 | Draft spec | Elephant | `docs/designs/<feature>.md` with a test plan | `/egm-draft` without section pauses |
| 6 | Review spec | Goldfish personas | Review reports | `/egm-review` stages; fails closed if fresh contexts are unavailable |
| 7 | Resolve | Arbiter | A ruling on every finding in `decisions.md` | Non-interactive `/egm-resolve` |
| 8 | Loop | Orchestrator | Repeat 6 and 7 until no Blocker or Major finding remains, or 3 rounds, then escalate | `egm-review-loop` |
| 9 | Spec PR | Orchestrator | Spec PR with a decision summary | Human merges at L1 |

**New personas.** Only the **Arbiter** in M0, and the **Evidence Auditor** in M1. Every other reviewer is an existing EGM persona with a different rubric.

**Arbiter authority.** A fresh-context agent that receives the findings, the spec and a rubric. For each finding it accepts, contests, declines or escalates, with a one-line reason and a path or line citation. In M0 it may auto-reject only Nit findings; Blocker and Major rulings are logged and audited by sample (section 3). Where the harness allows, the Arbiter uses a different model from the Elephant; where it does not, results are reported with that caveat.

**State.** The current step is derived from GitHub (issue labels, PR status) wherever possible. A small record `.herd/state/<feature>.json` holds only what GitHub cannot: the round counter, the risk field, and the budget used. One workflow run owns a feature at a time.

**Risk floor.** In M0 Triage computes the risk from path rules and labels, with no LLM. `herd.toml` holds the path rules (for example migrations, auth, public API, billing). Agents can raise the score but never lower it below the rule floor; only a maintainer's `/herd risk` command can.

## 6. Hypotheses, alternatives, risks

**Hypotheses the pilot tests**
1. Fresh-context review works on artifacts other than specs. EGM's own workflow targets specs; M0 tests only the spec case, and later milestones extend it to plans, code and release.
2. An agent Arbiter can replace the human's triage of findings with a low overturn rate. This departs from EGM's position that review informs a human judgment.
3. A self-answered interview plus an assumptions list at H1 loses little compared with a live interview.

**Alternatives considered**

| Alternative | Why not, for now |
| --- | --- |
| Keep the human as judge but batch findings asynchronously | Still blocks on a person; kept as the fallback if the overturn rate exceeds the target |
| Deterministic rules plus a human sample instead of an LLM Arbiter | Cannot judge prose findings; used for the risk floor |
| Fork EGM | Loses upstream fixes; decide after spike S1 |
| EGM Lite plus a CI-only review | Does not test the central hypotheses |
| A custom orchestrator database | GitHub already provides labels, PR status and concurrency |
| Skip H1 and gate only at release | Misread intent is the costliest error; the gate stays |

**Risks**

| Risk | Mitigation |
| --- | --- |
| Arbiter rubber-stamps the Elephant (shared model bias) | Different model where possible; human audit; Nit-only auto-reject in M0; escalate on low confidence |
| Spec looks right but intent was misread | H1 approves checkable criteria, with agent-proposed ones marked |
| H1 approved without reading | Track gap-fill rework; a very low rate is a warning |
| Review noise | The Arbiter declines Nit findings and escalates what it cannot settle |
| Runaway cost | 3-round cap; per-feature budget in `herd.toml` (tokens, wall-clock) |
| Prompt injection through issues and comments | Principle P6: maintainers only, no secrets in agent context |
| Many features at once | One workflow run per feature; a global concurrency limit in `herd.toml` |

**Open questions**
- Spike S1 (done, `docs/spikes/s1-egm-unattended.md`): EGM skills pause for the human, so Herd depends on EGM's reviewer agents and rubrics and supplies the gate answers itself; no fork. Open: whether upstream would accept a no-pause flag.
- Where do `unchecked` criteria go after merge: a follow-up issue or a digest reminder?

## 7. Roadmap

One line per milestone; each is designed with EGM when it starts.

- **M0** Define half at L1 (this document). First, spike S1 (can EGM run non-interactively) and spike S2 (baseline: EGM by hand on 5 features).
- **M1** Build: plan, builders, code review, evidence step with a CI-based check runner. Auto-merge at L2 only once minimal rollback exists.
- **M2** Ship and operate: release gate for high risk, one thin deploy contract (deploy, health and rollback commands in `herd.toml`), weekly drift loop, daily digest.
- **M3** Multi-harness packaging, L3, golden-run tests. Size and path return with the Lite path.

File layouts, schemas (criteria, `herd.toml`, `decisions.md` lines, state record), scoring scales and CI tools go in `docs/designs/herd-*.md`, written for the milestone being built.

## 8. Constraints

- Public repository: no employer data, credentials or internal URLs in any file.
- Context isolation: Goldfish and Arbiter runs get only the artifact and its cited sources. If a fresh context cannot be provided, the step fails and escalates.
- Least privilege: agents push only to `herd/*` branches; at L1 the human merges.
- Harness: Claude Code first; others after M3.

## Sources

- [google/elephant-goldfish-model README](https://github.com/google/elephant-goldfish-model)
- [EGM architecture](https://github.com/google/elephant-goldfish-model/blob/main/docs/designs/architecture.md)
- [EGM getting started](https://github.com/google/elephant-goldfish-model/blob/main/docs/getting_started.md)
- Review of the previous draft: git history, commit 3ed136e
