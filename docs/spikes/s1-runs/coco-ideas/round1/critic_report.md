# Stage 7 Report: design, structural, style (one round)

**Target:** `docs/designs/herd-coco-ideas.md` (1..End, DetailedRange N/A). Standard: feature-spec-standard.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-design` | completed (orchestrator gave a nonexistent persona path `agents/design.md`; reviewer used canonical `design_critic.md` and the standard; did not read herd_triage.py or skills/criteria/SKILL.md) |
| `egm-structural` | completed (did not read GoldfishContext files; structural pass from standard and target) |
| `egm-style` | completed (did not read PRD, README, criteria skill; herd.py by grep only) |

Raw counts before dedup: design 1B/9M/7N, structural 1B/4M/5N, style 0B/5M/10N.

## Findings (deduplicated; D = design, S = structural, Y = style)

### Blocker (1)

- **S7-B1 No Alternatives Considered, Problem Statement, or Goals & Non-Goals (whole doc).** D1, S1. The standard's Alternatives Rule fails a single-path spec. Candidates to weigh: criterion-level ruff/pytest instead of a hook; pre-commit; static per-type guidance instead of `herd detect`; criterion text instead of `budget`/`kind`; adopting Coco directly; lint at `verify` time rather than PostToolUse. Only `Deferred:` (L74) hints at non-goals.

### Major (15)

- **S7-M1 Problem Statement and Goals/Non-Goals sections missing (L7-16).** S2, D1. Overview lists features but not what is broken or for whom.
- **S7-M2 Risks section shares a heading and is a run-on paragraph (L76-82).** S3. Split into Implementation Order, Risks & Mitigations, Decisions; list risks with mitigations; security (shell injection, config trust) and scalability/latency not explicit.
- **S7-M3 Overview numbering (4 items) mismatches body (5 Steps) (L7-16, L27-72).** S4, D12, Y. "Items 3 and 4" means Steps 4 and 5; Step 1 not an Overview item.
- **S7-M4 Order contradicts dependencies (L34, L54, L78).** S5, Y3, D11. Step 2 needs Step 4 hygiene lint; L78 says "any order".
- **S7-M5 Test-budget warning needs a risk value no code stores (L43-45).** D2. `task.toml` and `validate_task` have no risk; triage only prints (herd.py ~258-261); `herd check` has no warning channel (L224-227); `--quick` refusal needs triage inside `init`.
- **S7-M6 Red-first claimed as enforced, is skill prose only (L24, L36-37, L67, L80).** D3, Y1. `verify` overwrites evidence.json each run (herd.py ~148) so a red run is lost; "record it" has no field or gate rule; L24 "Herd already runs verify" should read "the run skill instructs".
- **S7-M7 Waiver is an undefined escape hatch (L80 risk 5).** D4, Y. No schema, step, or limit on who sets it; an agent can self-waive. Specify field, human-set, shown in `report`, or move to Deferred.
- **S7-M8 `quick` limit is soft (L34, L37, L80).** D5. Triage defaults to medium with no path in goal text, so dropping the path avoids `high`; "one-file change" is prose only. Add a human flag or diff-size check, or call it a soft limit.
- **S7-M9 `attested` is not safe or defined (L66, L80).** D6, Y. `verify` never reads `kind`; freshness undefined; agent can write the file; `fingerprint()` hashes everything outside .herd/ so editing it stales other evidence. Put under .herd/ or define freshness and authorship rule.
- **S7-M10 `typecheck` has no defined effect (L50).** D7. Failing result, criterion, or side output; feeds gate or not. Define or cut from v0.2.
- **S7-M11 Lint hook can loop, no circuit breaker (L51-52).** D8. `gate` has `MAX_BLOCKS` (herd.py L26); lint blocks every failing edit, whole-file not diff. Cap, or use non-blocking `additionalContext`; read `cwd` from payload (herd.py L255); hooks.json `timeout` above `timeout_s`; glob relative to root.
- **S7-M12 Hygiene lint and zero-test guard have no mechanism; risk 2 overclaims (L34, L54, L68, L80).** D9, Y2. Denylist flags legitimate `grep -q`, misses `python -c pass`/`exit 0`; "no zero-test runs" and "at least one unmocked path" unimplemented and untested; lint is advisory yet cited as mitigation. Narrow wording or define rule.
- **S7-M13 Scope heavy for a minimal plan (L29, L42, L61, L71).** D10. About 15 marker types from general knowledge (L25), 11 type files, overlapping `level` and `kind`, `test_budget` consumed by nothing. Ship routing and lint with a few types; defer the rest.
- **S7-M14 Detection spec incomplete (L25, L29).** Y4, D13. `?` vs `unsure` terminology; type table not in the document; `unsure`/`scope` outside the stated dict shape; `*.tf`, `build.gradle*` are globs.
- **S7-M15 Evidence not citable: "full report in the session" (L18).** Y5, D16, S7. No path or link; bare URLs; [V]/[I] legend only inline.

### Nit (15)

- **S7-N1** `Check:` lines lack blank lines and merge into prior paragraph/list item (L29-30, 38, 46, 55, 72). S6.
- **S7-N2** Inconsistent term "Step 4 lint of checks" vs "check hygiene" (L34, L54). S8, Y.
- **S7-N3** Metadata has no owner/reviewer; Status needs update after review (L3-5). S9.
- **S7-N4** "Code changes:" paragraph in Step 5 has no sub-structure (L71). S10.
- **S7-N5** "Coco" never defined or linked (L9, L10, filename). Y.
- **S7-N6** Vague "helps a human decide how to create and check evidence" (L14), repeated at L58. Y.
- **S7-N7** "workspace files" and `scope` undefined (L29). Y.
- **S7-N8** `herd detect` subcommand appears only in Step 5 but Step 1 is built first and `lint --suggest` depends on it (L53, L71). Y.
- **S7-N9** Informal "rubber-stamping is visible" (L71). Y.
- **S7-N10** "and CI" vague (L78). Y.
- **S7-N11** Decisions section thin (L82). Y.
- **S7-N12** "Fake green" jargon, define once (L23, L80). Y.
- **S7-N13** Warning output path in `herd check` needs format and test (L45). D14.
- **S7-N14** Config trust: `[lint] command` runs shell from committed file; confirm herd_triage tolerates new `[lint]` table (unchecked) (L50). D15.
- **S7-N15** `init --quick` must set `source` (herd.py L23, L88 allowed values); behaviour on bad `route` unspecified (L35). D17.

## Counts

Blocker 1, Major 15, Nit 15.
