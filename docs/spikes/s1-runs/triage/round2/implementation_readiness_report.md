# Stage 9 Report: implementation-readiness, codebase-details, style

**Target:** `docs/designs/herd-triage.md` (lines 174-222). Standard: implementation-readiness-standard.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-implementation-readiness` | completed (verdict: fails Zero-Decision Rule) |
| `egm-codebase-details` | completed (verified against repo and PRD) |
| `egm-style` | completed |

All verified raw text via Grep; no corruption findings kept. Two candidate findings dropped as likely Read-view lossiness: "G4's own text is partly garbled" (IR 5) and "size or path reads oddly" (IR 11).

## Blocker

### R1 `floor()` semantics undefined - Blocker
* **Lens:** implementation-readiness, style | **Scope:** line 190 (also 119)
* `labels` use not stated (only the `risk:low` label in the risks table, line 163). Glob algorithm unspecified (`fnmatch`, `pathlib`, custom `**`; does `migrations/**` match `migrations/a/b.sql`). Normalisation order and case-fold not placed. Precedence when `high` and `medium` both match not stated. No-match return level unclear. "`medium` for unknown input" (L190, L119) conflicts with G4/L100 fail-closed to `high`; "unknown input" undefined.
* **Fix:** state algorithm, normalisation order, precedence, default level, label role; list exact inputs yielding `medium`, route all other bad input through `write_record` fail-closed to `high`.

### R2 `write_record` and `verify_record` underspecified - Blocker
* **Lens:** implementation-readiness, codebase-details | **Scope:** line 190
* `event` values and per-event `payload` shape, `base_hash` bytes and algorithm, where retry lives and what is raised, atomic write mechanism, feature-to-path mapping, who computes `effective`, `floor_rules`, `floor_inputs`, where the 200-char `reason` cap is enforced, how callers signal `timeout`/`malformed`, exception type, old/missing `schema_version` and unknown-enum behaviour, unknown-key preservation, which `triage.cause` is set on lost race, whether `effective()` returns `override.to`, what `floor_inputs` holds (`paths`, `labels`). No function loads and validates `herd.yaml` from base.
* **Fix:** full signatures, exception classes, numbered steps per function.

### R3 No step produces `paths` - Blocker
* **Lens:** implementation-readiness | **Scope:** line 190
* Extraction not specified; who sets `floor_inputs.source` unknown (CUJ 2). Declare out of scope with a caller contract or specify extraction. (Same gap as zoom-out Z4/I2, comprehension 1, design M5.)

### R4 Version pin deferred, no manifest - Blocker
* **Lens:** implementation-readiness, style | **Scope:** line 189
* "Pin the Python and PyYAML versions when implementing". No exact versions, no manifest (`requirements.txt` or `pyproject.toml`) in the Target Files list. PyYAML itself is justified (PRD fixes YAML format).

## Major

### R5 Phase 4 and Target File 5 describe PRD edits already applied - Major
* **Lens:** codebase-details (contradicted by implementation-readiness 8) | **Scope:** lines 183, 207-210
* Codebase-details found all three edits already in the PRD (row 1 output line 77, M3 line 136, `/herd risk` in section 4 line 69). Implementation-readiness found the edit text not exact (no before/after strings, M3 and section 4 placement vague). Synthesizer note: the two lenses disagree on state; either way the plan is wrong. Mark the file as already modified or drop it, otherwise supply exact before/after strings.
* Phase 4 exit check `grep -n "size" PRD*.md` matches unrelated lines (e.g. PRD line 136) and cannot be scoped to "section 5 step 1 row" (style Major). Use a row-scoped check.

### R6 Fixture schema cannot express listed fixtures - Major
* **Lens:** codebase-details, implementation-readiness | **Scope:** lines 197-200 vs 76-83
* Fixture keys `paths, labels, rules, proposed, expected` insufficient for `tampered_record`, `human_override`, `old_schema_version`, `unknown_enum`, `bad_herd_yaml`, `failure_default` (need prior record, event, actor, raw YAML text, simulated failure). Shape of `expected` not given; creating phase for non-floor fixtures not given; `fixtures/triage/` has no repo-root anchor or loading logic. Add an example per fixture kind.

### R7 Phase exit checks do not cover goals - Major
* **Lens:** codebase-details, implementation-readiness | **Scope:** lines 180-183, 192-195, 83, 160, 217
* Phase 2 names only `failure_defaults_high`; `bad_herd_yaml`, `unknown_enum`, `old_schema_version` are in no phase. Path-normalisation fixtures (L160) are in neither table nor phase. "Every CUJ goal named fixture test" (L217) not backed. `-k floor` may select nothing without fixed test names (e.g. `test_floor_hit`, `test_no_path`). Phase 1 uses fixture names, Phase 2 test names: use test names only.

### R8 `herd.yaml` default rules referenced, not written - Major
* **Lens:** implementation-readiness | **Scope:** lines 202-205
* "The default rule set above" points to prose; no literal YAML; `floor.high`/`floor.medium` format not shown. Header says "Modify... Create if absent" though file is absent (it is a Create). Phase 3 ordered after code that needs the rules. Default set must contain `herd.yaml` as `high`; created on main or via PR not stated.

### R9 Phasing gaps - Major
* **Lens:** implementation-readiness | **Scope:** lines 176-183
* Phase 2 exit needs `herd.yaml` loading and fixtures from Phase 3. No phase wires `.herd/state/` creation. pytest import of `scripts/herd_triage.py` needs `conftest.py`/`__init__.py`/`sys.path` rule, none named.

### R10 Verification step not actionable and violates write allowlist - Major
* **Lens:** implementation-readiness, style | **Scope:** lines 212-218
* "Record `proposed` against the human value" has no procedure, format or pass criterion; threshold is an Open Question. Writes `docs/spikes/s2-baseline.md`, not in Target Files. Line 217 "table above" is wrong (CUJ-to-fixture table is near line 83); name the section. Line 218 "shadow-mode run" undefined in range.

## Nit

* **RN1** Lines 214, 216: combine "Build: none" and "Static analysis: none required" into one line; state no formatter added.
* **RN2** Line 190 `labels` parameter unused by Technical Plan floor rules except line 163 (covered by R1).
* **RN3** Line 190 `effective(proposed, floor, override)`: say whether result is `override.to` when override exists (covered by R2).
* **RN4** Header line 185 "Create/Modify" marking satisfies plan-marking rule; no action.
