# Stage 7: Critic report

Target: whole PRD. Reviewers (fresh contexts): egm-design, egm-structural, egm-style.
Verdicts: design critic **fails** the feature-spec standard (3 blockers, 7 majors, 3 nits). Structural reviewer: **does not conform** until an Alternatives section exists (1 blocker, 5 majors, 5 nits). Style reviewer: 4 blockers, 10 majors, 9 nits (no standard supplied; it ran persona-only).

Line numbers refer to the PRD as reviewed.

## Blockers (merged, deduplicated)

| ID | Finding | Sources |
| --- | --- | --- |
| K1 | **No "Alternatives Considered" section.** The standard requires rejected options with concrete reasons. Candidates: human judge with async batching vs Arbiter; Arbiter as deterministic rules plus human sample; fork vs depend on EGM; GitHub-native state vs a custom state file; skip H1 and rely on H2; use EGM Lite plus a CI-gated review. | Design 1, Structural 1 |
| K2 | **Arbiter trust model.** An LLM judges findings from the same model family with no independent ground truth; "fresh context" is not independence. The "different vendor where the harness allows" hedge has no fallback. The 10% audit is after the fact, with no remediation (revert or reopen) and no justification for the sample size. | Design 2, Style 11 |
| K3 | **Gaps never block plus auto-merge.** Agent-invented criteria are checked by agent-built evidence and graded by the same kind of model. `weak` and `none` criteria do not block merge (FR-11). The only control is H1, and the "≥ 80% gap-fill acceptance" metric rewards rubber-stamping. Suggested fix: an evidence floor (for example, no auto-merge if any criterion is `none` or agent-only), an adversarial check on agent-proposed criteria, and treating acceptance as a risk signal. | Design 3, Zoom-out Z6 |
| K4 | **Unrendered lifecycle diagram.** The "13 steps" are never enumerated; "highlighted gates" cannot be read; the steps don't map to FR-01 to FR-17. Replace with a numbered list or Mermaid diagram. | Structural 2, Design 14, Style 4, Comprehension C2 |
| K5 | **Contradictory human-touchpoint claims.** Goal 1 says two gates; escalation is a third; H1 is "every feature" yet L3 says "H1 only for high risk" while H2 is the high-risk gate; Lite skips H1; "only the Orchestrator merges" vs L0/L1 human merges; "≤ 2 touchpoints" leaves no room for H1+H2 plus an escalation. Define one gate-by-level matrix and make Goal 1, metrics and FRs consistent with it. | Design 10, Style 3, Comprehension C10 and C18 |
| K6 | **Central premise stated as proven.** "EGM proves..." and "The Goldfish pattern generalises" are not supported; the EGM README says the workflow targets software specs and "a review does not replace tests or human judgment". Restate as a hypothesis with a named pilot metric. | Style 1 and 2 |

## Majors

| ID | Finding | Sources |
| --- | --- | --- |
| M1 | **EGM dependency unverified.** FR-02 (non-interactive brainstorm), FR-04 (draft without pauses) and the cross-plugin dependency `egm@egm` are assumed, not shown. The "six-lens" count conflicts with EGM's "7-lens" and the PRD lists four review tiers vs EGM's five stages. Settle the plugin-dependency vs vendor question early; the PRD also states the decision as settled ("rather than forking") while listing it as open. | Design 4, Style 12 and 20, Structural 6, Zoom-out Z8 |
| M2 | **No threat model.** Prompt injection through issue text, linked docs and PR comments; who may apply the `herd` label or `/herd hold`; secrets in the CI where Builder code runs; agent-added dependencies; risk scoring that an attacker controls through the issue text. "Secrets never enter agent context" has no mechanism. | Design 5, Structural 5, Style 10, Comprehension C13 |
| M3 | **No cost model or concurrency policy.** No default budgets, no per-feature token, CI-minute or dollar estimate, no parallel-feature or rate-limit behaviour. The "≤ 15 human minutes" target is unsupported. | Design 6 |
| M4 | **State and concurrency design.** `.herd/state/<feature>.yaml` has no schema, locking or race behaviour, and conflicts with human edits. The Orchestrator is a single point of failure. Parallel per-task PRs have no merge order, rebase policy or integration-test story. | Design 7, Comprehension C2 and C9, Inventive I4 |
| M5 | **Release safety ordering.** Auto-merge (FR-11, P0) precedes rollback (FR-13, P1) and FR-12 has no defined release path in the pilot. Risk rubric is informal; medium risk deploys automatically. Make rollback a prerequisite of L2 and define a deterministic path-based risk floor. | Design 8, Inventive I5, Comprehension C11 |
| M6 | **Metrics.** "≥ 70% autonomous completion" can be raised by loosening escalation; no baselines; M0's 20 features are too few for a 10% overturn threshold; "Arbiter agreement" actually measures overturn rate; no measuring mechanism for several metrics. | Design 9, Style 9, Comprehension C12 |
| M7 | **Problem statement is untested.** No data shows human waiting is the bottleneck vs spec quality. Goal 5 ("minimal start") conflicts with FR-02 (Elephant answers its own interview). Lite path assumed definable without evidence. | Design 11 |
| M8 | **Schemas and contracts missing**: criterion, `check`, `matrix.md`, `concepts_brief.md` fields, `herd.yaml` keys, `plan.yaml`, `decisions.md` line format, risk/size scales, "blocking finding", "stale", "confidence". | Comprehension C1 to C5, C8, Style 8 |
| M9 | **Structure.** Sub-sections faked with bold labels; Goals, Risks and Architecture content bundled into compound headings or split across Sections 5, 7 and 8; Risks table lacks security and scalability rows. | Structural 3 to 5 |
| M10 | **Overclaims and hedges in mitigations.** "Two independent agents" for risk scoring is unproven; "tries to break them" has no method; "never auto-releases" needs a stated enforcement. | Style 10 and 11 |
| M11 | **Milestone vs goal.** Goal 1 ("to production and back") is only met at M2, but the PRD doesn't say so. | Style 13 |
| M12 | **Undefined EGM terms** and buzzwords ("Autopilot", "Agent-native", "success rate") with no metric. | Comprehension C14, Style 7 |
| M13 | **Style claims without support**: "strong on the left, thin on the right", "five or more synchronous points" (not derived). | Style 5 and 6 |
| M14 | **Terminology drift**: Release vs Release Reviewer; Lite path vs EGM Lite; gate/step/touchpoint; Define/Build/Ship vs step names. | Style 12 |

## Nits (grouped)

- Priorities: FR-01 expects Lite selection at P0 while FR-15 (Lite) is P1; FR-10a and FR-12 are P0 but FR-13 is P1; FR-03a, FR-10a and FR-10b break sequential IDs. P0/P1 are not defined in Section 3.
- Naming: `herd_*` underscores vs EGM's hyphenated skill names; `resources/standards/` vs EGM's `resources/document_standards/`, so "mirrors EGM" is inaccurate; `plugin.json` at root vs `.claude-plugin/`.
- Voice: "you" and "Your triage" in a requirements document; filler ("fixed and short", "Read it top to bottom"); "Typical use" and "Normal operation" without criteria.
- Document hygiene: bare code fence, no Status field, byline format, headings numbered inconsistently, Problem statement after the analysis section, cross-references by number without anchors, the EGM architecture link path should be confirmed.
- P3: whether a manual step counts toward human touchpoints.
- Kept as correct: FR-05 "fail closed" matches the EGM README; the Section 1 EGM behaviour claims match the README.

## Cross-stage note
Stage 5's scope-cutting findings (Z1, Z2, Z4, Z6) and Stage 7's hardening findings (K2, K3, M2 to M5) pull in opposite directions. The resolution step needs a scope decision first: a smaller v1 reduces the schema and threat-model work needed.
