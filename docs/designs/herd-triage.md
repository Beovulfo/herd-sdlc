# Herd Triage

* **Author:** Toni
* **Status:** Draft
* **Date:** 2026-11-22

--------------------------------------------------------------------------------

## Overview

Triage is step 1 of the Herd lifecycle (PRD section 5). When a maintainer applies the `herd` label to an issue, Triage computes a risk level (`low`, `medium`, `high`; order `low < medium < high`) from path rules in `herd.toml`, and writes it to `.herd/state/<feature>.json`. In M0 Triage is deterministic code with no LLM. The orchestrator and the Arbiter read the record, and the human sees the risk on the H1 Intent gate PR.

**Terms** (all in the PRD): Arbiter, orchestrator, H1 (section 4); P6 (section 2); autonomy levels L0 to L3 (section 4); milestones M0 to M3 (section 7).

## Problem

Every later step needs a risk level, and H1 needs one to show the human. A person sets it by hand today. A lower bound must come from outside any LLM, because an LLM that reads untrusted issue text can be steered by that text (P6). At intake there is no diff or spec, only issue text that may name no paths. Hypothesis, not yet measured: most issues name no path, so the floor is `medium` for most features. M0 tests that hypothesis with rules only. An LLM proposal is an M1 question.

## Goals

* G1: `effective` is never below `floor`, unless a human override is recorded in `risk.override`. Check: `python3 -m unittest scripts/test_herd_triage.py` passes `test_floor_hit`, `test_no_path`, `test_low_label`, `test_label_raises`.
* G2: A human override records actor login, comment id, old value, new value and time in `risk.override`. Check: `test_override_recorded`.
* G3: Any failure to compute a floor gives `effective: high` and `status: fallback` with a `cause`. Check: `test_fallback_cases`.

## Non-Goals

* An LLM risk proposal, a state-file tamper check and race handling: M1. In M0 the value is display-only at H1, where a human reads it, so a forged value is visible to that human. The record sits on an agent-pushable branch; this gap is accepted for M0 and listed in Risks.
* Ratchet recomputation after intake, append-only history, edit-rate metrics, shadow mode and `/herd retriage`: M1.
* Size and path (Full or Lite): they return with the Lite path in M3. No M0 step reads them.
* Orchestration wiring: the label-triggered workflow, issue snapshot, comment posting, and creating the `herd/<feature>` branch. The orchestrator design owns these; this design covers the floor, the record and the writer.
* A rule language in `herd.toml` beyond lists of globs.

## Open Questions

* Can existing CODEOWNERS globs seed the default rule set?
* Which M1 mechanism protects the record: a bot-only ref, a CI diff check, or recompute from a trusted source?
* What edit rate at H1 counts as a warning after 20 features?

## Critical User Journeys (CUJs)

### CUJ 1: Issue names a sensitive path

* **Given**: `floor.high` contains `migrations/**`; the issue body names `migrations/0001_init.sql`.
* **When**: The maintainer applies the `herd` label.
* **Then**: `floor: high`, `effective: high`, `floor_rules: ["migrations/**"]`. Test: `test_floor_hit`.

### CUJ 2: Issue names no path

* **Given**: The issue body names no path and carries no `risk:*` label.
* **When**: Triage runs.
* **Then**: `floor: medium`, `floor_inputs.source: default`. The H1 PR shows the floor is the default. Test: `test_no_path`.

### CUJ 3: Maintainer confirms low risk

* **Given**: The issue names no path matching a rule and carries `risk:low`, applied by a maintainer.
* **When**: Triage runs.
* **Then**: `floor: low`. A matching rule still wins over the label. Tests: `test_low_label`, `test_label_raises`.

### CUJ 4: Human lowers risk below the floor

* **Given**: `floor: high`, `effective: high`.
* **When**: A maintainer comments `/herd risk medium`.
* **Then**: `effective: medium` and `risk.override` holds the actor login, comment id, `from: high`, `to: medium` and time. The orchestrator comments naming the overridden rule. Test: `test_override_recorded`.

### CUJ 5: Triage cannot compute a floor

* **Given**: `herd.toml` on the base branch is missing, is invalid TOML, or has an unknown key inside `floor`, or the writer raises. Other top-level keys (for example `arbiter`, `budget`) belong to other designs and are ignored.
* **When**: Triage runs.
* **Then**: `effective: high`, `status: fallback`, `cause` is one of `herd_toml`, `error`. The orchestrator comments so the feature does not stall silently. Test: `test_fallback_cases`.

## Technical Plan (Architecture)

**Inputs.** The orchestrator passes the writer the issue number, the issue body, the labels with their appliers, and the text of `herd.toml` read from the base branch. The writer does no network or git calls.

**Path extraction.** One regular expression over the issue body: tokens of letters, digits, `.`, `_`, `-` containing at least one `/`, or ending in a known extension from `herd.toml` (`path_extensions`, default `py, ts, js, sql, toml, json, md`). Each token is normalised: strip a leading `./`, collapse `//`, keep case, and drop any token that contains `..` or starts with `/`. Case is significant, because the rules are case-sensitive. The extractor misses paths written in prose ("the auth module"), so the rate of unknown input is known to be high. That is why unknown input gives `medium`.

**Floor.** `herd.toml` has two lists of globs, `floor.high` and `floor.medium`, plus optional `path_extensions`. Matching uses `PurePosixPath.full_match` (Python 3.13): `*` does not cross `/`, `**` matches zero or more segments, no negation. The highest matching level wins. Labels `risk:high` and `risk:medium` raise the floor to that level. `risk:low` counts only when a maintainer applied it, and lowers the floor to `low` only when no rule matched. With no rule match and no label, the floor is `medium`. The default rule set, used when `herd.toml` has no `floor` block: `high` for `migrations/**`, `auth/**`, `billing/**`, `herd.toml`; `medium` for `api/**`. A `herd.toml` edit counts as touching a `high` path, so a feature that edits it floors at `high` once a diff exists (M1); at intake the extractor sees it only if the issue names it.

**Effective value.** `effective = floor`, unless `risk.override` is set, in which case `effective = override.to`. Only the `human_override` event sets `risk.override`, and a later `triage` event for the same feature never changes an existing override.

**Failure.** The writer catches every exception from parsing and matching and writes `effective: high`, `status: fallback`, `cause`. It never leaves a partial file: it writes a temporary file in the same directory and renames it.

**Authority.** The record is the single authority for risk. The H1 PR displays it. Humans override only with `/herd risk <level>`, issued by a maintainer (PRD section 4, P6). `herd.toml` is read from the base branch, never the feature branch. Readers ignore unknown keys and preserve them on write. A record with a missing or older `schema_version` is rejected with an error the orchestrator escalates. The writer treats any value outside the three levels as `high`.

```json
{"schema_version": 1, "feature": "<feature>", "issue": 0,
 "status": "ok", "cause": null,
 "risk": {"floor": "high", "floor_rules": ["migrations/**"],
          "floor_inputs": {"paths": ["migrations/0001_init.sql"], "source": "issue_text"},
          "effective": "high", "override": null}}
```

`status` is `ok` or `fallback`. `cause` is `herd_toml` or `error` when `status` is `fallback`, else null. `source` is `issue_text`, `label` or `default`. `override` is null or `{actor, comment_id, from, to, time}`.

```text
issue + label + herd.toml (base branch)
        |
  extract paths --> floor (rules, labels) --> medium if no input
        |
  writer: events triage, human_override --> .herd/state/<feature>.json
        |
  orchestrator, Arbiter, H1 PR (display)
```

## Alternatives Considered

### Alternative A: Add an LLM risk proposal in M0

* **Pros**: Reads issue prose that names no path; could separate `low` from `high` where rules cannot.
* **Cons**: Adds an injection surface, an allowlisted output contract, retry and race handling, and a rollout, before any evidence that it changes the outcome. Most floors are `medium`, so the proposal can raise nothing the floor does not already catch.
* **Reason for Rejection**: Rejected by author: M0 first measures how often the rules alone land on `medium`. If that rate hides real risk differences, the proposal returns in M1.

### Alternative B: Agent writes the risk value directly

* **Pros**: One field, no writer.
* **Cons**: An injected issue controls its own lower bound.
* **Reason for Rejection**: Rejected by author: it breaks P6.

### Alternative C: Risk only in the PR body, no state field

* **Pros**: No second store.
* **Cons**: The Arbiter must parse a PR body, and an override has no stable, structured home.
* **Reason for Rejection**: Rejected by author: the Arbiter reads the state record by design (PRD section 5, State).

--------------------------------------------------------------------------------

## Non-Functional Requirements

* **Security**: P6 applies. Triage needs no secrets. The record is agent-writable in M0 (see Non-Goals).
* **Cost**: No LLM call and no network call.
* **Rollout**: Features already open have no record; Triage runs for them when labelled, without blocking (P3).
* **Rollback**: Delete `.herd/state/<feature>.json` fields under `risk`; the human sets risk with `/herd risk`. The PRD also assigns the round counter and budget fields to the record, so those live under their own keys and rollback touches only `risk`.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Agent commit on `herd/<feature>` edits `floor` or `effective` | Accepted in M0: the value is display-only at H1. M1 adds a check (Open Questions) |
| Glob mis-specified lets a sensitive path through | Fixed matcher semantics, one test per rule form |
| Extractor misses paths written in prose | Unknown input gives `medium`; `risk:high` label raises it |
| `herd.toml` drifts from the code layout | Default rule set; PRD weekly drift loop (M2) |
| `medium` carries little signal | Accepted: M0 measures this, see Alternative A |
| Label applied by a non-maintainer | The orchestrator passes the applier; only maintainer `risk:low` counts |

## Future Improvements

* LLM risk proposal, tamper check, ratchet at step 5 and from the real diff, append-only history (M1).
* Golden-set canary in CI: known-risk issues, including injected ones.
* Size and path, with the Lite path (M3).

--------------------------------------------------------------------------------

## Detailed Implementation Plan

### Phases

| Phase | Work | Exit check |
| --- | --- | --- |
| 1 | `extract_paths()`, `floor()` | `python3 -m unittest scripts.test_herd_triage.TestFloor` passes |
| 2 | `build_record()`, `apply_override()`, fallback and atomic write | `python3 -m unittest scripts.test_herd_triage` passes (all tests) |
| 3 | `herd.toml` example | `python3 -c "import tomllib; d=tomllib.load(open('herd.toml','rb')); print(sorted(d['floor']))"` prints `['high', 'medium']` |

### Target Files to Create/Modify

#### 1. `scripts/herd_triage.py` (Create)

* **Type / Scope**: Python module, Python 3.13 or later (3.13 for `PurePosixPath.full_match`), standard library only. `herd.toml` is read with `tomllib` and the record is read and written as JSON, so there is no dependency.
* **Proposed Changes**: Four public functions.
  * `extract_paths(body: str, extensions: list[str]) -> list[str]`: returns normalised paths as described in Path extraction.
  * `floor(paths: list[str], labels: dict[str, str], rules: dict) -> tuple[str, list[str], str]`: `labels` maps a label name to its applier's role (`maintainer` or `other`). Returns level, matched rules and source (`issue_text`, `label` or `default`).
  * `build_record(feature: str, issue: int, body: str, labels: dict[str, str], herd_toml: str) -> dict`: calls the two functions above; on any exception returns the fallback record. Never raises.
  * `apply_override(record: dict, level: str, actor: str, comment_id: int, now: str) -> dict`: sets `risk.override` and `risk.effective`; rejects a level outside the three.
  * `write_record(path: str, record: dict) -> None`: writes JSON to a temporary file in the same directory, then renames it.

#### 2. `scripts/test_herd_triage.py` (Create)

* **Type / Scope**: `unittest` file, standard library only.
* **Proposed Changes**: Tests `test_floor_hit`, `test_no_path`, `test_low_label`, `test_label_raises`, `test_override_recorded`, `test_fallback_cases` (missing file, invalid TOML, unknown key inside `floor`, exception in matching), plus `test_other_top_level_keys_ignored`, plus `test_path_normalisation` (`./a`, `a//b`, `..`, leading `/`, case) and `test_triage_keeps_override`. Inputs are inline literals with generic paths.

#### 3. `herd.toml` (Create, repo root)

* **Type / Scope**: Config.
* **Proposed Changes**: Contents:

  ```toml
  path_extensions = ["py", "ts", "js", "sql", "toml", "json", "md"]

  [floor]
  high = ["migrations/**", "auth/**", "billing/**", "herd.toml"]
  medium = ["api/**"]
  ```

### Verification Plan

* **Build**: none.
* **Unit Tests**: `python3 -m unittest scripts/test_herd_triage.py`.
* **Static Analysis & Linting**: none required in M0.
* **Test Coverage Requirement**: every CUJ has at least one named test (CUJ 1 `test_floor_hit`; 2 `test_no_path`; 3 `test_low_label`, `test_label_raises`; 4 `test_override_recorded`; 5 `test_fallback_cases`).
* **E2E/Integration**: none in this design; the orchestrator design owns the label-to-record flow.

--------------------------------------------------------------------------------

*Drafted with EGM*
