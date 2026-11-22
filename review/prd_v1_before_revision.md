# PRD — Autopilot SDLC plugin built on the Elephant-Goldfish Model

Nov 22, 2026 · @Toni

## 1. The SDLC that EGM implies today

EGM is a spec-driven SDLC that is strong on the left side (idea → spec → verified spec) and thin on the right side (build → test → release → operate). Its core idea is separation of context: an **Elephant** agent that holds all project context drafts, and **Goldfish** reviewers with zero prior context check the result, so the drafter's assumptions get exposed ([README](https://github.com/google/elephant-goldfish-model)). The human makes trade-offs, triages findings and approves before code is written.

| SDLC phase | What EGM provides | Human touchpoints today | Gap for an agentic SDLC |
| --- | --- | --- | --- |
| Requirements / ideation | `/egm-brainstorm`: interview + six-lens Goldfish swarm → `concepts_brief.md` | Interview answers, agreeing the direction | Interview is synchronous |
| Design / spec | `/egm-draft`: section-by-section spec in `docs/designs/<feature>.md`, split into FeatureRange and DetailedRange | Pause and feedback after every section | Many small blocking gates |
| Design verification | `/egm-review`: Zoom-out (YAGNI/reuse), Comprehension (naive reader), Critic (scale, failure modes), Implementation Readiness (paths, signatures, tests); Synthesizer dedups findings | Choose which findings to address | Human is the judge of every finding |
| Resolution | `/egm-resolve`: work through findings, patch the spec | Resolve or reject each finding | Same |
| Approval | Spec PR for peer review | PR review and merge | Required for every feature |
| Implementation | "Ask the agent to build it"; teams plug in their own skills | Fix or retry if output is off | No plan, no task graph, no code review against spec |
| Testing | Implementation Readiness checks that tests are *specified* | Run and judge tests | No test generation or execution loop |
| Release / ops | Not covered | — | Fully missing |
| Maintenance | `/egm-drift-report` (weekly), `/egm-bootstrap` for brownfield docs, Lite path for small changes | Decide doc-vs-code per divergence | Drift is reported, never reconciled |

Three takeaways shape this PRD:

1. **The Goldfish pattern generalises.** Fresh-context verification works for any artifact, not only specs: plans, code, tests, release notes, drift. The new plugin applies it at every phase.
2. **Humans in EGM are the scheduler and the judge.** Every phase ends by yielding control to a person. To remove them we need an orchestrator (scheduler) and an arbiter (judge), not just more skills.
3. **Checked-in files are the state.** EGM keeps no runtime state beyond files, which suits headless agents running from CI. We keep that and add a small, explicit state file per feature.

## 2. Problem and opportunity

EGM proves that fresh-context review catches what the authoring agent misses, but it still needs a person at five or more synchronous points per feature. That makes the human the bottleneck: agents can work around the clock, yet a feature waits for each section approval, each findings triage and each reconciliation decision.

The opportunity is to keep EGM's verification discipline and replace the human's two roles with agents: an **Orchestrator** that schedules phases, and an **Arbiter** (itself a Goldfish) that judges findings. The human keeps only what an agent cannot own: deciding *what* to build and accepting irreversible risk.

Working name: **Herd**, a plugin in a new repository (`herd-sdlc`) that depends on EGM's skills and personas rather than forking them.

## 3. Goals, non-goals, success metrics

**Goals**

1. Take a feature from GitHub issue to production and back (drift) with no human step other than the two gates.
2. Apply Goldfish verification to every artifact: brief, spec, plan, code, tests, release.
3. Make every autonomous decision auditable after the fact, so the human reviews asynchronously instead of blocking.
4. **Evidence-based:** the human supplies goals and success criteria; agents prove progress with reproducible evidence; the human reviews evidence, not process (section 5).
5. **Minimal start, optional depth:** a one-paragraph goal is enough to start. More detail from the human raises the success rate but is never required.
6. Stay harness-agnostic like EGM: Claude Code, Codex, Gemini/Antigravity, and headless runs from GitHub Actions.

**Non-goals**

- Replacing EGM. Herd composes EGM skills and adds orchestration, arbitration and the right side of the lifecycle.
- Choosing product strategy or priorities. Intake ranks; the human decides what enters.
- Multi-repo or monorepo-wide changes in v1.
- Autonomous incident remediation beyond rollback.
- Blocking a feature because the human left something unspecified. Gaps are filled by agents and reported (principle P2).

**Success metrics** (targets to validate in the pilot)

| Metric | Definition | Target |
| --- | --- | --- |
| Human touchpoints per feature | Gate approvals + escalations answered | ≤ 2 on median |
| Human minutes per feature | Time spent at gates and on escalations | ≤ 15 on median |
| Autonomous completion rate | Features merged with no escalation | ≥ 70% of low/medium-risk |
| Escaped defects | Bugs traced to a Herd change within 30 days | No worse than the repo's human baseline |
| Arbiter agreement | Sampled Arbiter decisions a human would overturn | ≤ 10% |
| Spec drift | Open drift items older than 2 weeks | 0 |
| Criteria with a runnable check | Criteria whose evidence is `strong` (a re-runnable check) | ≥ 90%; the rest are labelled `weak` or `none`, never hidden |
| Gap-fill acceptance | Agent-filled gaps the human leaves unchanged at H1 | ≥ 80% |

## 4. Users and the minimal human contract

The primary user is a **tech lead or product engineer** who owns a repository and wants features delivered without supervising each step. Secondary users are **reviewers and auditors** who inspect decisions after the fact.

**What the human provides.** Only the first row is required.

| Input | Required? | Effect |
| --- | --- | --- |
| Goal (issue text, a paragraph is enough) | Yes | Starts the feature |
| Success criteria, ideally with how to check each one | No | Human-written criteria are authoritative; agents never edit them, only add checks to them |
| Constraints, examples, non-goals, risk tolerance | No | Narrow the Elephant's assumptions and raise the success rate |
| Extra evidence sources (dashboards, datasets, test accounts) | No | Upgrade `weak` evidence to `strong` |

The human can add detail at any time by commenting on the issue or PR. The Orchestrator folds it in at the next step.

The human contract is fixed and short:

| Gate | When | What you see | What you do | Default if no answer |
| --- | --- | --- | --- | --- |
| H1 Intent gate | Every feature, after Ideate | `concepts_brief.md` + success criteria with checks (each marked `human` or `agent-proposed`) + a short **Assumptions and gap-fills** list + risk score, in one PR | Approve, edit or reject the PR | Waits; reminder after 24 h |
| H2 Release gate | Only when Triage or Release Reviewer scores risk **high** (data migrations, auth, public API, billing, irreversible infra) | Release PR with diff summary, test evidence, rollback plan | Approve or hold | Waits; never auto-releases |
| Escalation | A loop exceeds 3 rounds, budget exceeded, Arbiter confidence is low, or a real trade-off needs a human (never for missing detail or missing evidence) | One GitHub issue with the disagreement and options | Pick an option or comment | Feature paused |

Everything else is asynchronous: a daily digest lists decisions made, and you can interrupt any feature by commenting `/herd hold` on its issue.

## 5. Agent-native lifecycle

&#91;embedded content: Herd lifecycle · 13 steps, 2 human gates\]

**Evidence-based principles**

- **P1 Criteria are checkable claims.** Each success criterion has a `check`: a command, test, query or probe, an expected result, and an evidence grade.
- **P2 Gaps never block.** If the goal, criteria or checks are missing or vague, the Elephant drafts them from the issue, repo and linked docs, labels them `agent-proposed`, and lists them under "Assumptions and gap-fills" at H1. The same applies later: if a check cannot run, the agent builds a substitute (a new test, a script, a fixture, a proxy metric) and says so. The agent stops only for an irreversible risk or a real trade-off.
- **P3 Evidence has grades, not a pass/fail wall.** `strong` = re-runnable check, output stored. `weak` = proxy or partial check (e.g. static analysis instead of a load test). `none` = cannot be checked by agents; a manual step is requested from the human, and the feature proceeds meanwhile. A `weak` or `none` criterion is reported, never silently counted as met.
- **P4 Evidence is stored, not asserted.** Each feature keeps `docs/designs/<feature>/evidence/`: raw check output, commit SHA, timestamp, and `matrix.md` mapping each criterion to its evidence and grade. Agents may claim a criterion is met only by pointing to an artifact.
- **P5 Fresh-context audit of evidence.** An Evidence Auditor Goldfish re-runs the checks and judges whether the evidence proves the criterion (a test that asserts nothing fails the audit). Failures go back to the Builder as gaps to fix, not to the human.
- **P6 Concise decision reports.** Every autonomous decision, gap-fill and downgrade is reported in at most 3 lines (decision, why, how to override) in the digest and PR description. Human overrides rewrite the criterion or check and re-run the affected steps.

Read it top to bottom: Define turns an issue into an approved, verified spec; Build turns the spec into reviewed code; Ship and operate releases it and feeds drift back as new issues. You appear only at the two highlighted gates.

| Agent | Sees | Job | Replaces in EGM |
| --- | --- | --- | --- |
| Orchestrator | Feature state file only | Moves a feature between steps, enforces budgets, opens escalations | You as the scheduler |
| Triage | Issue + repo map | Scores risk (low/medium/high) and size; picks Full or Lite path | You choosing Lite |
| Elephant | Full project context + `<project>-elephant` skill | Writes brief, spec, plan | Same role, no per-section pauses |
| Goldfish reviewers | The artifact + sources it cites | EGM personas, plus new Code Auditor, Test Critic, Release Reviewer | Extended to code and release |
| Arbiter | Fresh: findings + spec + rubric | Accepts or rejects each finding with a written reason | Your triage in `/egm-resolve` |
| Builder | One task + its spec section | Code and tests on a branch per task | "Ask the agent to build it" |
| Evidence Auditor | Fresh: criteria + evidence + check definitions | Re-runs checks, grades evidence, flags checks that cannot fail | Your judging of test results |
| Release | CI and deploy config | Canary, health checks, rollback | Not covered |
| Drift warden | `docs/designs/` + code | Weekly drift: PR for doc-side fixes, issue for code-side | Your doc-vs-code decision |

## 6. Functional requirements

P0 = needed for the first pilot; P1 = needed for general release.

| ID | Step | Requirement | Priority |
| --- | --- | --- | --- |
| FR-01 | Intake | Watch issues labelled `herd`; Triage writes risk (low/medium/high), size and Full/Lite path into the state file | P0 |
| FR-02 | Ideate | Run `/egm-brainstorm` non-interactively: the Elephant answers its own interview from issue, repo and linked docs, and lists open questions in the brief | P0 |
| FR-03 | Intent gate | Open one PR with `concepts_brief.md`, success criteria (Given/When/Then) each with a `check` and grade, the "Assumptions and gap-fills" list and the risk score; block until merged | P0 |
| FR-03a | Gap-fill | If criteria or checks are missing, the Elephant proposes them (marked `agent-proposed`); human-written criteria are never altered; absence of detail never blocks | P0 |
| FR-04 | Draft | Run `/egm-draft` without per-section pauses; output spec + test plan in `docs/designs/<feature>.md` | P0 |
| FR-05 | Review spec | Run `/egm-review` tiers in fresh subagents; fail closed if fresh contexts are unavailable, as EGM does | P0 |
| FR-06 | Resolve | Arbiter (fresh context) rules on every finding: accept, reject or defer, with a one-line reason, written to `decisions.md` | P0 |
| FR-07 | Loop control | Review → resolve repeats until no blocking findings or 3 rounds; then escalate | P0 |
| FR-08 | Plan | Turn the DetailedRange into a task graph (`plan.yaml`): tasks, files, dependencies, tests per task; Goldfish checks coverage of every acceptance criterion | P0 |
| FR-09 | Implement | One Builder per task in an isolated worktree; tests written first from the test plan; one PR per task | P0 |
| FR-10 | Review code | Goldfish Code Auditor compares diff to spec section; Test Critic checks tests prove the criteria; CI, lint, SAST and secret scan must pass | P0 |
| FR-10a | Evidence | Run each criterion's check, store output under `evidence/`, update `matrix.md`; Evidence Auditor re-runs and grades; unmet or `weak` criteria loop back to the Builder, which adds tests or probes to close the gap | P0 |
| FR-10b | Evidence report | Post an evidence summary on every PR: per criterion, status (passing / failing / stale), grade, link. This is what the human reviews | P0 |
| FR-11 | Merge | Auto-merge when all checks pass, no criterion is `failing`, and risk is not high. `weak` or `none` criteria are listed in the merge note | P0 |
| FR-12 | Release gate | For high risk, open a release PR with the evidence matrix and rollback plan; wait for approval | P0 |
| FR-13 | Release | Pluggable deploy adapter: canary, health checks, automatic rollback on failure | P1 |
| FR-14 | Observe | Weekly `/egm-drift-report`; doc-side drift fixed by auto-PR, code-side drift filed as a new `herd` issue | P1 |
| FR-15 | Lite path | Small or low-risk changes skip Ideate and the Intent gate; spec is a short change note, still Goldfish-reviewed | P1 |
| FR-16 | Brownfield | On install, run `/egm-bootstrap` and generate the `<project>-elephant` context skill | P1 |
| FR-17 | Audit | Daily digest of decisions, costs and escalations as an issue comment or Slack message | P1 |

## 7. Repository structure (`herd-sdlc`)

The layout mirrors EGM so the same harness manifests work, and EGM is pulled in as a dependency.

```
herd-sdlc/
├── .claude-plugin/ .codex-plugin/ .gemini/   # harness manifests, as in EGM
├── plugin.json                             # declares dependency on egm@egm
├── skills/
│   ├── herd_orchestrate/   # state machine, budgets, escalation
│   ├── herd_triage/        # risk + size scoring, Full/Lite path
│   ├── herd_plan/          # spec -> plan.yaml task graph
│   ├── herd_build/         # TDD builder per task
│   ├── herd_release/       # deploy adapter calls, rollback
│   └── herd_digest/        # daily decision digest
├── agents/                 # new Goldfish personas
│   ├── arbiter.md
│   ├── code_auditor.md
│   ├── test_critic.md
│   ├── evidence_auditor.md
│   └── release_reviewer.md
├── resources/standards/    # rubrics: plan, code, test, release, risk
├── .github/workflows/      # headless runners: on issue, on PR, weekly drift
├── adapters/deploy/        # GitHub Environments, Cloud Run, Kubernetes
├── templates/herd.yaml     # per-repo config: autonomy level, budgets, gates
├── docs/designs/           # Herd's own specs (dogfooded)
└── tests/                  # golden-run fixtures per step
```

In each target repository Herd writes only: `herd.yaml`, `docs/designs/<feature>/` (brief, spec, `plan.yaml`, `decisions.md`, review reports, `evidence/`) and `.herd/state/<feature>.yaml`, the single source of truth for which step a feature is in.

## 8. Non-functional requirements and autonomy levels

- **Context isolation:** Goldfish and Arbiter runs get only the artifact and its cited sources; the harness must prove a fresh context or the step fails closed.
- **Resumable and idempotent:** every step reads and writes `.herd/state/<feature>.yaml`, so a crashed or rescheduled run continues from the last completed step.
- **Budgets:** per-feature caps on tokens, wall-clock time and CI minutes in `herd.yaml`; exceeding one pauses the feature and escalates.
- **Least privilege:** Builders push only to `herd/*` branches; only the Orchestrator can merge, and never to protected branches when risk is high. Secrets never enter agent context.
- **Auditability:** every Arbiter ruling, auto-merge and rollback is a line in `decisions.md` with the model, inputs hash and reason.
- **Harness-agnostic:** skills run in any harness EGM supports; GitHub Actions is the reference headless runner.

Autonomy is configurable per repository, so teams can start cautious and move up as Arbiter agreement proves out:

| Level | Human gates | Who merges | Typical use |
| --- | --- | --- | --- |
| L0 Assist | EGM as today: every step | Human | Evaluation |
| L1 Supervised | H1 + every PR review | Human | First weeks on a repo |
| L2 Gated (default) | H1 + H2 for high risk | Herd | Normal operation |
| L3 Autonomous | H1 only for high risk; Lite path for the rest | Herd | Internal tools, docs, low-risk services |

## 9. Risks, open questions, milestones

**Risks**

| Risk | Mitigation |
| --- | --- |
| Arbiter rubber-stamps the Elephant (shared model bias) | Use a different model or vendor for Arbiter and Goldfish where the harness allows; sample 10% of rulings for human audit |
| Spec looks right but intent was misread | H1 approves testable acceptance criteria, not prose; Test Critic ties every test to a criterion |
| Review noise (EGM itself warns reviews produce a lot of feedback) | Arbiter defers non-blocking findings to a backlog instead of looping on them |
| Runaway cost from loops | Hard round limit (3) and per-feature budgets |
| Agent-invented criteria misread the intent | Gap-fills are listed explicitly at H1 and marked `agent-proposed`; the human can edit any line, and edits take precedence |
| Gameable or vacuous checks (tests that cannot fail) | Evidence Auditor re-runs checks and tries to break them; grades make weak evidence visible |
| Unsafe auto-merge | Risk scoring by two independent agents (Triage, Release Reviewer); high always gated |

**Open questions**

- Depend on EGM as a plugin dependency, or vendor pinned copies of its skills?
- Can the brainstorm interview run unattended without losing quality, or should H1 include a short async Q&A?
- How is a `none`-grade criterion (needs human judgment or production data) tracked after merge: a follow-up issue, or a digest reminder?
- Which deploy adapter goes first: GitHub Environments or a cloud target?

**Milestones**

1. **M0 — Define half:** Intake → Draft → Review → Resolve with Arbiter, on L1. Exit: Arbiter agreement measured on 20 features.
2. **M1 — Build half:** Plan, Builders, code review, auto-merge on L2. Exit: ≥ 70% of low/medium-risk features merged without escalation.
3. **M2 — Ship and operate:** release adapter, rollback, weekly drift loop, digest.
4. **M3 — Public release:** multi-harness packaging, L3, docs and golden-run tests.

**Sources**

- [google/elephant-goldfish-model — README](https://github.com/google/elephant-goldfish-model)
- [EGM architecture](https://github.com/google/elephant-goldfish-model/blob/main/docs/designs/architecture.md)
- [EGM getting started](https://github.com/google/elephant-goldfish-model/blob/main/docs/getting_started.md)
