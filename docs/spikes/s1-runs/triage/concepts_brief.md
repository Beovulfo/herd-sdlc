# Herd Triage

* **Author:** Toni
* **Date:** 2026-11-22
* **Status:** Brainstorm output, input to `/egm-draft`. Reviewed by 7 Goldfish lenses (design, codebase-details, zoom-out, comprehension, implementation-readiness, structural, inventive-catalyst).

## Summary

Triage is step 1 of the Herd lifecycle (PRD section 5). An agent reads a GitHub issue and proposes a risk level (low, medium, high), a size (S, M, L) and a path (Full or Lite). Code, not the agent, combines that proposal with a floor taken from path rules in `herd.yaml` (for example migrations, auth, public API, billing) and writes the result to `.herd/state/<feature>.yaml`. The orchestrator and Arbiter read the record. The human sees the risk on the H1 Intent gate PR.

The reviewers agree the core is sound: a deterministic floor, a proposal-only agent, no secrets in context. They also agree the concept has one real hole (what the floor matches at intake) and several unstated rules that must be decided before drafting.

## Problem

- Every later step needs a risk level, and the H1 gate needs one to show the human.
- Today the human decides this by hand. An LLM can propose it, but an LLM reading untrusted issue text can be steered (prompt injection), so something outside the LLM must set a lower bound.

## Proposed approach

1. A trigger (maintainer applies the `herd` label) snapshots the issue body and stores its hash.
2. The Triage agent gets the issue body and `herd.yaml` only. It has no write tools, no network, no secrets. It returns enums for risk, size and path plus a one-line reason, validated against a schema.
3. Orchestrator code computes the floor from `herd.yaml` and writes the record. The agent never writes the file.
4. The H1 PR shows proposed risk, floor, final risk and the rule that fired, in 3 lines or fewer (PRD P5).
5. The floor is a ratchet: it is recomputed when new path information appears (the spec at step 5), and it can only raise risk.

Proposed record shape (for `/egm-draft` to settle):

```yaml
schema_version: 1
feature: <feature>
issue: { number: 0, body_hash: "<hash>" }
triage: { status: ok, run_id: "<id>", at: "<timestamp>" }   # ok | failed | fallback
risk:
  proposed: medium
  floor: high
  floor_rules: ["migrations/**"]
  floor_inputs: { paths: [], source: issue_text }
  herd_yaml_hash: "<hash>"
  effective: high            # computed as max(proposed, floor), or a logged human override
  history: []                # append-only: actor, from, to, time
size: M
path: Full
```

## Findings from the review, merged and ranked

### Blockers

1. **The floor has nothing to match at intake.** Path rules match file paths, but at step 1 no diff or spec exists. The only input is issue text, which is untrusted and often names no paths ("users cannot log in after reset"). A floor fed by issue keywords or an agent's guess is not deterministic, and an injected "this touches nothing sensitive" defeats it. Raised by design, comprehension, zoom-out, structural, implementation-readiness, inventive-catalyst, codebase-details.
   * Resolution direction: define the floor input explicitly and make risk a ratchet. At step 1 use maintainer-applied labels and paths named in the issue. At step 5 recompute from files the draft spec names. In M1 recompute from the real diff. Risk only goes up. A rise re-opens H1 or adds a line to the spec PR. Unmatched or unknown input defaults to medium, not low. State the known miss rate at intake.
2. **No stated owner of the final value.** Triage "proposes", the floor "cannot be lowered", and both land in one field. If the agent writes the file, an injected issue controls its own bound.
   * Resolution direction: keep `proposed`, `floor` and `effective` as separate fields. Code computes `effective = max(proposed, floor)`. Only that code writes the record. Triage returns schema-checked enums only.
3. **No audit trail, so the success metric cannot be computed.** With one risk value, nobody can tell whether "high" came from the agent, a rule or a human, and an H1 edit overwrites the proposal. The edit-rate metric and the floor check both need the original data.
   * Resolution direction: append-only `risk.history`, the fields in the record above, and the metric formulas written into the PRD with their denominator (features reaching H1).

### Major

4. **Human lowers risk below the floor: undefined.** PRD P5 says human overrides win; PRD section 5 says the floor is never lowered. Pick one rule. Candidates: the floor binds agents only and a human may lower it with a logged `override` (who, from, to), or lowering requires a separate reviewed `herd.yaml` change. The H1 PR should refuse or flag a below-floor edit with a message naming the rule.
5. **Floor rule grammar is undefined.** Needed: glob lists, one per risk level, highest wins, no negation, no rule DSL in M0. Include one worked `herd.yaml` example and schema validation at load. Check whether CODEOWNERS globs already cover the sensitive paths.
6. **`herd.yaml` can lower its own floor.** Read it from the base branch, never the feature branch. Treat edits to `herd.yaml` as a floor-matching path (high). A missing or invalid file fails closed to high, with a loud warning. An absent rules block uses a default rule set, not an empty one.
7. **Issue text is mutable and untrusted after labeling.** Pin the body hash at label time. Re-triage only on a maintainer `/herd retriage`. Never overwrite a human-set value on re-run. Render the agent's one-line reason as inert quoted data. Downstream agents read enums, not the reason. Never copy raw issue text into the record or logs.
8. **Failure behavior is undefined.** On timeout, malformed output, schema failure, invalid `herd.yaml` or a race, default to risk high, path Full, `triage.status: fallback`, and say so on the PR and with an issue comment so the feature does not stall silently.
9. **State record lifecycle.** Which branch holds it, who commits, and what happens at intake when no `herd/*` branch exists yet (agents only push `herd/*`). Cheapest option: create the branch at intake. Also decide authority after H1 (suggest: the human-edited PR value, written once by the orchestrator) and how abandoned or rebased features are cleaned up.
10. **Schema versioning.** Add `schema_version` on day one. Readers tolerate unknown keys and preserve them on write. A missing or older version escalates, not guesses. Fix enum spellings now. An unknown enum fails closed to high.
11. **Edit-rate metric is ambiguous.** A low rate can mean good triage or rubber-stamping (PRD already warns about this for gap-fill rework). Report separately: edits up vs down, edits to Triage proposals vs overrides of floor-forced values. Under-triage (human raises) is weighted worse than over-triage. A near-zero rate is a warning. With about 20 features, state the error bars. Baseline against the S2 hand runs.
12. **Observability gaps.** Add a correlation key (`feature` plus workflow run id) to each step's writes. Count Triage tokens and time against the "budget used" field. Track a `risk_delta` signal (proposal below floor) as an injection and under-rating indicator.
13. **Rollout and rollback.** Features already open have no record: run Triage lazily, never block (P3), idempotent by issue body hash. Ship in shadow mode first (Triage and floor results shown at H1, Arbiter ignores them) until agreement is measured on the 5-feature baseline. Rollback means ignoring `.herd/state`, with a manual fallback of the human setting risk on H1.

### Minor and scope

14. **Size and path have no M0 consumer.** Only risk is read by the Arbiter and H1. Path (Lite) matters at L3 only, after M3, and size has no named reader. Zoom-out, comprehension and structural each recommend dropping size, and probably path, from M0 or marking them informational and unconsumed. If kept: define Full, Lite, S, M, L in one line each, add an allowed-combinations table (for example high risk forces Full), and never let size set a budget (injected "L" would be a cost-DoS; budget stays capped by the `herd.yaml` maximum).
15. **Two stores for risk** (state file and H1 PR). Name one override route: edit the value in the H1 PR. Humans do not hand-edit the state file.
16. **Should Triage run at L0?** Open.
17. **Reuse:** the S1 run-log shape is the only reusable artifact found in `docs/` and `review/`. No existing code to reuse.

### Inventive resolutions (contradictions resolved, with costs)

| Contradiction | Resolution | Cost |
| --- | --- | --- |
| Deterministic floor vs sparse intake information | Risk ratchet recomputed at steps 1, 5 and M1; "low" needs positive evidence | More medium ratings at H1; re-gate churn when risk rises mid-flight; needs stored history |
| Triage proposes vs record is treated as fact | Agent emits three enums; orchestrator code owns the record and the floor | A thin orchestrator layer and a schema to version |
| P5 (human wins) vs floor never lowers | Floor binds agents only; human lowering allowed but logged | An audit field; possible rubber-stamp path. In M0 risk gates little, so consider recording without acting until L2 |
| Low edit rate: good triage or rubber-stamping | Golden-set canary in CI (known-risk and injected issues); read edit rate only next to canary pass rate | Golden-set upkeep; model updates shift results |
| "No secrets" vs "needs repo context" | Read-only checkout, no credentials, no write or network tools | None found |

## Alternatives considered

* **Rules only, no LLM in M0:** the floor alone gives a deterministic risk with no injection surface. Rejected as the sole design because the floor is sparse at intake, but it is the fallback if the proposal adds little (measure the proposal vs floor agreement in shadow mode).
* **Risk only, drop size and path in M0 (zoom-out's minimal cut):** LLM proposes a risk enum, code takes the max with the floor, H1 shows proposed, floor and final. Strong candidate for M0.
* **Keep risk only in the PR body, no state field:** removes the drift hazard but loses the history needed for the metric and for the Arbiter to read it without parsing a PR.

## Success measures

* **Floor rule (deterministic, CI gate):** a fixture table of path list to expected floor, plus a golden set of 10 to 20 issues, including injected ones, where `effective` must never fall below the floor. A schema check rejects any record with `effective` below `floor` unless a logged human override exists.
* **H1 risk edits (reported, not a target):** count by direction and by source (agent proposal vs floor-forced), with the denominator and a sampled audit, as for the Arbiter overturn rate.

## Out of scope

* Builders, release gating, and cost estimation beyond the `herd.yaml` budget.
* A rule language for `herd.yaml` beyond globs, precedence and highest-wins.
* Re-evaluating the floor against a real diff (M1). The concept only needs to state that the floor will be re-run then.

## Key Decisions & Staging Next Steps

Decisions to settle in `/egm-draft` (each has a recommended direction above):

1. What the floor matches at intake, and where it is re-evaluated (steps 1, 5, M1). Default for unmatched input.
2. Human override below the floor: allowed with a log, or not.
3. Whether size and path ship in M0 or are deferred.
4. Where the state file is committed and which value is authoritative after H1.
5. Failure default (high, Full, `fallback`) and the re-triage rule (`/herd retriage`, human values never overwritten).
6. Shadow-mode period and the agreement threshold for letting the Arbiter act on Triage output.

Staging suggestion: (a) deterministic floor, schema and record writer with their CI checks; (b) the LLM proposal in shadow mode; (c) wire the H1 PR display and metrics; (d) ratchet re-evaluation at step 5.

Open questions: Should Triage run at L0? Do CODEOWNERS globs already cover the sensitive paths? What exact edit-rate warning threshold applies at 20 features?

## Reviewer status

| Reviewer | Status |
| --- | --- |
| `egm-design` | completed |
| `egm-codebase-details` | completed |
| `egm-zoom-out` | completed |
| `egm-comprehension` | completed |
| `egm-implementation-readiness` | completed |
| `egm-structural` | completed |
| `egm-inventive-catalyst` | completed |

Caveat: several reviewers noted the PRD and persona text arrived partly garbled or truncated in their reads, so some line references and a few inferred points (for example the exact BRAINSTORM output format) should be checked against the source files.
