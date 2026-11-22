# Stage 5 Report: zoom-out and inventive-catalyst

**Target:** `docs/designs/herd-coco-ideas.md` (1..End, DetailedRange N/A)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |
| `egm-inventive-catalyst` | completed |

Notes: zoom-out did not read zoom-out-standard.md and did not re-check line numbers with Grep. Inventive-catalyst read herd.py by grep only and did not read the PRD, README or skills/criteria/SKILL.md.

## Findings (deduplicated; Z = zoom-out, I = inventive-catalyst)

### Major (9)

- **S5-M1 Step 3 relies on a risk value no code stores (L43).** Z1. `task.toml` has no risk field; `validate_task` ignores risk; `herd check` has no warning channel. Persist risk and add warnings, or drop the warning and keep budget guidance in the criteria skill (smaller).
- **S5-M2 Red-first is described as a guard but is only skill prose (L24-25, L36, L67, L80).** Z2, I1. `verify`, `gate`, `problems()` never record or check a red run. Risks 1 and 2 mitigations depend on it. "Record it" (Step 5.5) and "recorded waiver" (Risk 5) have no schema or gate rule. Either store a baseline in evidence.json with a gate check plus waiver, or declare it advisory and remove it from mitigations.
- **S5-M3 `attested` and `proxy` kinds weaken the evidence guarantee (L66, L71).** Z3. Check `test -s evidence/<id>.md` is agent-writable and exit 0 counts as `passing`; "freshness" undefined; contradicts "unautomatable stays `unchecked`". Model as `unchecked` with human-supplied file, or drop `attested`; keep `proxy` as a text label and drop `kind`.
- **S5-M4 Step 5 contradicts the autopilot rule and is speculative (L64-65).** Z4. skills/run says do not ask clarifying questions; verify flow asks up to 5 and waits. 11 per-type files, `herd detect`, and `kind` serve an unrun flow. Declare `/herd:verify` a separate human-in-the-loop skill, or split Step 5 into its own plan.
- **S5-M5 `quick` route undefined and code effect near-empty (L32-38).** Z5. Does not say whether quick overrides review for medium risk (triage defaults medium); only real code effect is "exactly one criterion". Define what ceremony is dropped or drop `route`/`--quick`.
- **S5-M6 `typecheck` has no integration path (L50).** Z6. `verify()` runs only `task["criteria"]`. Inject as synthetic criterion (changes evidence shape) or cut it.
- **S5-M7 Order contradicts dependencies (L34, L78).** Z7. Step 2 depends on Step 4 hygiene lint; L78 says "2, 3, 4 in any order".
- **S5-M8 Lint hook: no circuit breaker, no gate linkage, timeout unspecified (L50-55, Risk 3).** Z8, I2. Unlike `gate` (`MAX_BLOCKS`), blocking on pre-existing errors can loop; lint results never reach the Stop gate; PostToolUse `timeout` must exceed `timeout_s` (Stop uses 30, lint default 20); resolve root from hook `cwd`. Prefer non-blocking `additionalContext`, or reuse counter pattern; optionally record last result per file for `verify`.
- **S5-M9 Vacuous-check detection is a brittle denylist shared by two features (L34, L54, Step 5.4).** I3, Z9. `grep` is a legitimate assertion; `echo ok`, `true && true`, zero-test runs slip through; Step 5.4 "no zero-test runs" has no mechanism. Make warn-only and not a `--quick` refusal condition; or judge by behaviour (red baseline, zero-test output markers).

### Nit (11)

- **S5-N1 Overlapping `level` and `kind` taxonomies (L42, L71).** Z10, I6. `probe/manual` vs `proxy/attested`; contradictory combinations possible. One field, or list allowed combinations.
- **S5-N2 `herd detect` output shape inconsistent (L25, L29).** Z11. Dict lacks `unsure`/`scope`; monorepo `scope = "affected"` undefined.
- **S5-N3 Detection too broad for v0.2.** Z12. About 15 marker types with fixtures; ship pyproject, package.json, Cargo.toml, go.mod first.
- **S5-N4 Quick-init details missing (L34).** Z13. `init` must set `source` (validate_task C1, herd.py L88); needs flag parsing; new triage coupling.
- **S5-N5 `MultiEdit`/`NotebookEdit` skipped silently (L52).** Z14. Document it.
- **S5-N6 `herd.toml` is on the high-risk floor list and will hold an edit-time shell command (L50).** Z15. State the effect and add a trust note in README.
- **S5-N7 "Full report in the session" is unrecoverable (L18).** Z16. Link or inline the driving findings.
- **S5-N8 Cheaper path unstated.** Z17. Ship lint (no typecheck/hygiene) plus budget as skill text first; routing, kind and verify skill later.
- **S5-N9 `quick` floor check enforced only at `init`.** I4. Editing `route = "quick"` later bypasses it; have `validate_task` recheck, or accept.
- **S5-N10 Confirm ceremony for high-confidence detection entries.** I5. Auto-accept confident entries, ask only for `unsure` (depends on S5-M9).
- **S5-N11 Docs gap.** I. `herd detect` absent from Step 1 file list; README commands table and skills/run step 1 need `quick` and `detect`; docs listed last.

## Counts

Blocker 0, Major 9, Nit 11.
