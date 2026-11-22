# Goldfish Review Report (Consolidated)

**Target:** `docs/designs/herd-coco-ideas.md` (1..End; no Detailed Implementation Plan, Stage 9 skipped)
**Preset:** Consolidated report for all review rubrics, uninterrupted, one round. Document not edited.

## Reviewer Status

| Stage | Reviewer | Status | Notes |
| --- | --- | --- | --- |
| 5 | `egm-zoom-out` | completed | did not read zoom-out-standard.md |
| 5 | `egm-inventive-catalyst` | completed | herd.py by grep only; PRD, README, criteria skill unread |
| 6 | `egm-comprehension` | completed | no GoldfishContext, by design |
| 7 | `egm-design` | completed | orchestrator passed a wrong persona path (`design.md`); reviewer used canonical `design_critic.md`; herd_triage.py unread |
| 7 | `egm-structural` | completed | GoldfishContext files unread |
| 7 | `egm-style` | completed | PRD, README, criteria skill unread |
| 8 | `egm-zoom-out` | completed | |
| 9 | (detailed-plan reviewers) | not run | skipped: no Detailed Implementation Plan |

All reviewers read their persona. Reviewers could not verify [V]/[I] claims, as instructed.

## Per-stage counts (match stage files, pre-dedup across stages)

| Stage | File | Blocker | Major | Nit |
| --- | --- | --- | --- | --- |
| 5 | `zoom_out_report.md` | 0 | 9 | 11 |
| 6 | `comprehension_report.md` | 2 | 9 | 6 |
| 7 | `critic_report.md` | 1 | 15 | 15 |
| 8 | `intermediate_zoom_out_report.md` | 2 | 4 | 4 |
| | Stage total | 5 | 37 | 36 |

Consolidated, deduplicated across stages: **Blocker 3, Major 11, Nit 15.**

## Prioritized Findings

### Blocker (3)

**C-B1 Red-first is claimed as a guard but is skill prose; waiver undefined.** Scope L24-25, L35-38, L67-68, L80. `verify()` overwrites evidence.json, `problems()` checks freshness/failing only (herd.py ~L129-185). "Record it" and "recorded waiver" have no field, gate rule or test; an agent can self-waive. Risks 1 and 2 rely on it. Rec: add a minimal stored `red` result plus gate rule plus human-set waiver shown in `report`, or call red-first advisory and remove it from mitigations. Stage rating: Blocker in Stage 8; Major in 5, 6, 7.

**C-B2 `quick` route is undefined and its refusal has no data flow.** Scope L32-38, L80. `init` calls no triage; no task.toml exists yet (build_record takes toml text; herd.py L260 only). Triage defaults to medium when the goal names no path, so dropping the path evades `high`. Unstated what quick skips (review, approval, triage); code effect is nearly just "one criterion". `init --quick` also must set `source` and handle bad `route`. Rec: state data flow and what quick drops, add a human flag or diff-size check, or reduce quick to skill guidance.

**C-B3 No Alternatives Considered, Problem Statement, or Goals & Non-Goals.** Scope whole doc, L7-16. Standard's Alternatives Rule fails a single-path spec. Rec: add the three sections; weigh criterion-level ruff/pytest, pre-commit, lint at verify, static guidance vs `herd detect`, criterion text vs `budget`/`kind`, adopting Coco directly.

### Major (11)

**C-M1 Order contradicts dependencies; numbering mismatched.** L11-16, L27-72, L34, L54, L78. Step 2 needs Step 4 hygiene lint; L78 says any order. Four Overview items vs five Steps. Rec: put hygiene lint first, align numbering.

**C-M2 Test-budget warning needs a risk value no code stores.** L43-45. `task.toml` and `validate_task` have no risk; `herd check` prints errors or `ok` only (herd.py L224-227). Rec: persist risk and add warning channel with format and test, or drop the warning.

**C-M3 `attested`/`proxy` kinds weaken the evidence guarantee.** L66, L71, L74, L80. Check `test -s` on an agent-writable file counts as `passing`; freshness undefined; editing the file stales other evidence (`fingerprint()` hashes outside .herd/); `verify` never reads `kind`. Rec: model as `unchecked` with human-supplied file under .herd/, or defer `kind`.

**C-M4 Lint hook: no circuit breaker, no gate linkage, contract untested.** L50-55. Unlike `gate` (`MAX_BLOCKS`, herd.py L26), blocks every failing edit on whole file; results never reach Stop gate; PostToolUse `timeout` must exceed `timeout_s` (Stop uses 30); read `cwd` from payload (herd.py L255); `{file}` assumes single-file lint; exit-2/JSON behaviour untested (spike first). Rec: cap or non-blocking `additionalContext`; set timeout; reuse `run_check`.

**C-M5 `typecheck` has no integration path.** L50. `verify()` runs only `task["criteria"]`; effect on evidence and gate undefined. Rec: define or cut.

**C-M6 Vacuous-check and zero-test detection have no mechanism.** L34, L54, L55, L66, L68, L80. Denylist flags legitimate `grep -q`, misses `python -c pass`/`exit 0`; "no zero-test runs" and "unmocked path" unimplemented; `init --quick` refuses but `herd check` only warns; lint repeated in two places yet cited as a mitigation. Rec: advisory only, single location, or behavioural check against a red baseline.

**C-M7 Scope too large; Step 5 contradicts autopilot rule.** L29, L42, L53, L61, L64-65, L71. 11 type files, ~15 marker types from general knowledge (L25), `lint --suggest` duplicates detect, `test_budget`/`level` consumed by nothing; `/herd:verify` asks questions and waits while skills/run says ask none. Rec: split Step 5; ship routing, lint, detect for 3-4 ecosystems; defer `kind`, `level`, type files.

**C-M8 Detection spec incomplete.** L25, L29, L61. `?` vs `unsure`; type table not in the document; `unsure` and `scope = "affected"` outside the stated dict shape; `*.tf`, `build.gradle*` are globs; skill menu types (notebook, web app) lack markers.

**C-M9 Risks, Order and Decisions share one heading; risks are a run-on paragraph.** L76-82. Security (shell from committed config) and latency risks not explicit. Rec: split sections, list risks with mitigations.

**C-M10 Context and evidence not citable.** L4-5, L18, L20-22. "Full report in the session" is unreachable; bare URLs; existing system (task, evidence, gate, triage, risk, floor) never defined or linked. Orchestrator note: Stage 6 rated the missing system description and report reference as Blockers; downgraded to Major here because Stage 6 ran without GoldfishContext by design and a PRD/README link resolves it.

**C-M11 Naming collision and CLI surface.** L14, L53, L71, L78. `herd verify` CLI vs `/herd:verify` skill; `herd detect` appears only in Step 5 though Step 1 builds first; four new CLI forms on a hand-rolled if/elif `main()` (herd.py L217+); README and skills/run updates are one line.

### Nit (15)

- **C-N1** `level` and `kind` taxonomies overlap; contradictory combinations possible (L42, L71).
- **C-N2** `init --quick` `source` value and bad `route` handling unspecified (herd.py L23, L88; L35). Subsumed partly in C-B2.
- **C-N3** `MultiEdit`/`NotebookEdit` skipped silently (L52); document in README.
- **C-N4** `herd.toml` is on the high-risk floor list and will hold a shell command; add trust note; confirm herd_triage tolerates `[lint]` table (unchecked) (L50).
- **C-N5** Auto-accept confident detection entries, ask only for `unsure` (Step 1, 5.1).
- **C-N6** `Check:` lines lack blank lines and merge with prior text (L29-30, 38, 46, 55, 72).
- **C-N7** Inconsistent term "Step 4 lint of checks" vs "check hygiene" (L34, L54).
- **C-N8** Metadata lacks owner/reviewer; Decisions thin while real open decisions exist (L3-5, L82).
- **C-N9** "Code changes:" paragraph unstructured; L29 pseudo-signature too low-level (L29, L71).
- **C-N10** "Coco" never defined or linked (L9-10).
- **C-N11** Vague "helps a human decide how to create and check evidence", duplicated at L14 and L58.
- **C-N12** Informal or undefined wording: "rubber-stamping", "fake green", "and CI", "agent trial", "scratch-repo run" (L23, L71, L78, L80).
- **C-N13** [V] claims carry no verification note (L20-22); L52 `MultiEdit` caveat is good.
- **C-N14** `scripts.test_herd_cli` assumed to exist (L38, 46, 55, 72).
- **C-N15** L9 "all keep the core rule" asserted but `quick` and `attested` bend it.

## Traceability Matrix

| Consolidated | Stage 5 | Stage 6 | Stage 7 | Stage 8 |
| --- | --- | --- | --- | --- |
| C-B1 | S5-M2 | S6-M2 | S7-M6, S7-M7 | S8-B1 |
| C-B2 | S5-M5, S5-N9 | S6-M1 (partly), S6-M4 | S7-M8, S7-N15 | S8-B2 |
| C-B3 | | | S7-B1, S7-M1 | |
| C-M1 | S5-M7 | | S7-M3, S7-M4 | S8-B2 (part) |
| C-M2 | S5-M1 | S6-M1 | S7-M5, S7-N13 | |
| C-M3 | S5-M3 | S6-M7 | S7-M9 | S8-M1 (part) |
| C-M4 | S5-M8 | S6-M8 | S7-M11 | S8-M2 |
| C-M5 | S5-M6 | | S7-M10 | S8-M2 (part) |
| C-M6 | S5-M9 | S6-M3, S6-M4 | S7-M12 | S8-M3 |
| C-M7 | S5-M4, S5-N3, S5-N8 | | S7-M13 | S8-M1 |
| C-M8 | S5-N2 | S6-M5, S6-M6, S6-N4 | S7-M14 | |
| C-M9 | | | S7-M2 | |
| C-M10 | S5-N7 | S6-B1, S6-B2 | S7-M15 | S8-N1 |
| C-M11 | S5-N11 | S6-M9 | S7-N8 | S8-M4 |
| C-N1 | S5-N1 | | | |
| C-N2 | S5-N4 | | S7-N15 | |
| C-N3 | S5-N5 | | | |
| C-N4 | S5-N6 | | S7-N14 | |
| C-N5 | S5-N10 | | | |
| C-N6 | | | S7-N1 | |
| C-N7 | | | S7-N2 | |
| C-N8 | | S6-N6 | S7-N3, S7-N11 | S8-N2 |
| C-N9 | | | S7-N4 | S8-N4 |
| C-N10 | | S6-N1 | S7-N5 | |
| C-N11 | | | S7-N6 | |
| C-N12 | | S6-N5 | S7-N9, S7-N10, S7-N12 | |
| C-N13 | | S6-N2 | | |
| C-N14 | | S6-N3 | | |
| C-N15 | | | | S8-N3 |

Every stage finding maps to a consolidated item (S5-N8 "cheaper path" folds into C-M7; S7-N7 into C-M8; S6-N6 and S7-N3 into C-N8).
