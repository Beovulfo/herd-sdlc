# Stage 8 Report: intermediate zoom-out

**Target:** `docs/designs/herd-coco-ideas.md` (whole file, DetailedRange N/A)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |

Verdict (reviewer): scope too big for one plan; several claimed safeguards do not exist in code.

## Findings

### Blocker (2)

- **S8-B1 Red-first is the main defence against `quick` abuse but is prose only (L80, L35, L38, L68).** skills/run step 3 says run `herd verify` once; `verify()` (herd.py L129-149) writes only latest evidence.json; `problems()` (L175-185) checks freshness and failing only. "Record it" and "recorded waiver" have no schema, field, gate rule or test. Add an explicit step (store `red` result, one gate rule, waiver field) or remove the claim and rely on the `high` refusal.
- **S8-B2 `--quick` floor lookup has no data flow (L34), and Step 2 depends on Step 4 (L34 vs L78).** `herd_triage.build_record` is called only at herd.py L260 in a separate subcommand; `init` has no triage call and no task.toml exists yet (build_record takes toml text). State the data flow. L34 forward-references "Step 4 lint of checks" while L78 says 2, 3, 4 are order-independent.

### Major (4)

- **S8-M1 Scope and YAGNI.** Four features plus a 14-type detector from one session's research. Cut Step 5 to `herd detect` plus one generic SKILL.md; ship 3-4 ecosystems (L29, tagged [I] at L25); drop `herd lint --suggest` (L53, duplicates detect); defer `test_budget` and `level` (free text in criteria skill suffices); defer `kind` (`proxy`/`attested` add a second evidence model, under-specified at L74; `unchecked` already exists, herd.py L138-141, gate L183).
- **S8-M2 Lint hook adds an always-on failure path (L50-52, L55).** exit-2 and JSON options untested against current Claude Code; run a spike first. Implementation-level weeds (quoting, 2000-char tail, timeout). `{file}` assumes the lint command accepts one file. `typecheck` "runs at verify" changes `verify()` semantics (evidence schema, gate), unlisted.
- **S8-M3 Vacuous-check lint is trivially bypassed and flags legitimate `grep -q` (L34, L54, L55, L66).** Make advisory or drop; the lint is repeated in skill and `herd check`; pick one.
- **S8-M4 CLI surface growth (L53, L71).** `herd lint`, `lint --suggest`, `herd detect`, `--quick` added to a hand-rolled if/elif `main()` (herd.py L217+); README/command-table updates only one line (L78).

### Nit (4)

- **S8-N1** "Full report in the session" is a dangling reference (L18).
- **S8-N2** "Decisions" (L82) has two items while real open decisions exist (waiver, `typecheck` placement, quick-vs-triage wiring).
- **S8-N3** L9 "all keep the core rule" is asserted but `quick` waiving red and `attested` bend it.
- **S8-N4** L29 pseudo-signature and field list is low-level for a plan.

Reuse check (reviewer): reuse `herd_triage` (imported herd.py L19) for floor; `run_check` (L120) and `validate_task` (L72) are the extension points; `herd lint` should reuse `run_check`. No existing detection code found.

Suggested minimum v0.2 (reviewer): `--quick` plus real red-first recording, plain-text test-budget line in criteria skill, post-edit lint hook after a spike, detect for a few ecosystems; defer `kind`, level enums, type files.

## Counts

Blocker 2, Major 4, Nit 4.
