# Goldfish Review Report: Stage 9 (implementation-readiness, codebase-details, style)

**Target:** `docs/designs/herd-arbiter.md` (195-253), standard `implementation-readiness-standard`.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-implementation-readiness` | completed |
| `egm-codebase-details` | completed |
| `egm-style` | completed |

Counts (raw): Blocker 5, Major 21 (readiness 9, codebase 9, style 3), Nit 14 (readiness 3, codebase 4, style 7). Verdict from readiness: not ready to implement. Codebase-details confirmed sound: no scripts/, agents/, rubrics/, herd.toml in repo yet (all marked Create/Modify); Triage pins Python 3.13; `python3 -m unittest scripts.test_herd_arbiter` works via namespace package; `tomllib` Phase 4 check and `int(id,16) % 4` valid.

## Findings: implementation-readiness (R)

### R1 Flip check cannot be built from the spec - Blocker
* **Affected Scope:** L100, L110-111, L213, L217
* **Discrepancy:** `prior` is `{arbiter_verdict, quote_sha}` but the log line stores no quote or hash; ruling shape has no `quote_sha`/`quote`; hash algorithm and normalisation unstated; no function turns `decisions.md` lines into `prior`.
* **Recommendation:** Add `quote_sha` (with algorithm) to ruling and log line; add `load_prior(lines, id)` or state the orchestrator builds it.

### R2 Citation resolution undefined - Blocker
* **Affected Scope:** L92, L95, L99, L217
* **Discrepancy:** 0- vs 1-based lines, inclusive/exclusive range, line joining, whitespace/case normalisation, path comparison, valid omission-heading quote all unspecified.
* **Recommendation:** Pin each (e.g. 1-based inclusive, newline join, substring after whitespace collapse).

### R3 Re-ask rule contradicts check 1 - Blocker
* **Affected Scope:** L95, L217
* **Discrepancy:** Check 1 re-asks on invalid JSON or any schema-breaking object; L217 only when every ruling is `malformed`. "Affected" findings undefined when an object has missing/invalid id; re-ask prompt unspecified.
* **Recommendation:** One trigger (e.g. `validate` returns a flag, or re-ask on any `malformed`); specify the prompt.

### R4 Header never built - Blocker
* **Affected Scope:** L103, L108, L217-218
* **Discrepancy:** `format_lines(rulings, header)` takes a header no function constructs; nothing computes `same_model`; `rubric_sha`/`spec_sha` algorithm unstated.
* **Recommendation:** Add `build_header(round, arbiter_model, elephant_model, rubric, spec)` with a test; name the hash.

### R5 Audit and metric functions lack usable inputs/outputs - Blocker
* **Affected Scope:** L110, L113, L115, L220-221
* **Discrepancy:** Audit lines keyed only by `id`, ids repeat across rounds/features; `result` values not enumerated; `agreed_escalations` has no value; "split by `same_model`" shape undefined; `n=0` behaviour unstated; `summary(lines)` cannot mark audit-sample members without `feature_index`.
* **Recommendation:** Add `feature` and `round` keys to ruling and audit lines; enumerate `result` values; give exact return shapes; add `feature_index` to `summary`.

### R6 `merge_findings` severity/scope on merge - Major
* **Affected Scope:** L80, L214
* **Discrepancy:** Which severity and `scope` survive when personas differ is undefined.
* **Recommendation:** Highest severity wins; define scope.

### R7 `build_input` delimiters and prior section format - Major
* **Affected Scope:** L82, L167, L216
* **Discrepancy:** Data-block delimiters and handling of delimiter text inside spec/finding undefined; a finding could close the block and defeat the injection defence; prior-rulings section format unstated.
* **Recommendation:** Define tokens; escape or reject input containing them.

### R8 Policy checks ambiguous - Major
* **Affected Scope:** L24, L94-101
* **Discrepancy:** Duplicate: both copies or second only? Arbiter `escalate` position in order (an `escalate`+`L` could be `arbiter` or `low_confidence`); whether `severity` is copied at the end; `escalate` with invalid citation exempt from check 5 (L24 implies yes).
* **Recommendation:** Specify each.

### R9 No append function or file path for `decisions.md` - Major
* **Affected Scope:** L114, L218
* **Discrepancy:** "Only writer" but `format_lines` only returns lines; file location (per feature/round, `.herd/`) never given.
* **Recommendation:** Add `append_lines(path, lines)`; fix the path.

### R10 Reason cut and plain-text rule unplaced - Major
* **Affected Scope:** L113, L226
* **Discrepancy:** Whether the 140-char cut is in `validate` or `format_lines` unstated; "never as a link" has no mechanism.
* **Recommendation:** Assign to a function and specify.

### R11 Agent file under-specified - Major
* **Affected Scope:** L233-236, L241
* **Discrepancy:** No frontmatter keys; no mechanism for "no inherited project instruction files"; how `model = "inherit"` reaches the agent definition unstated.
* **Recommendation:** Give exact frontmatter and output-contract text.

### R12 Tests not tied to phases - Major
* **Affected Scope:** L201, L223-226
* **Discrepancy:** `TestValidate` named in Phase 1 exit check but not in the test spec; phase that creates the file unstated.
* **Recommendation:** List classes and assign tests to phases.

### R13 Test plan lacks assertions and coverage - Major
* **Affected Scope:** L225-226
* **Discrepancy:** No cases for `low_confidence`, unknown/duplicate ids, citation sub-cases, check order, `needs_audit` boundary, `build_input` order/delimiters, merge severity; injection fixture asserts nothing definable.
* **Recommendation:** Table of test, input, expected; define fixture assertion.

### R14 `herd.toml` creation ownership fragile - Major
* **Affected Scope:** L206, L238, L241
* **Discrepancy:** Triage and Escalation also "create if absent"; Triage treats missing file as error; Phase 4 check never verifies the agent file.
* **Recommendation:** State build order; add an agent-file exit check.

### R15 `feature_index` undefined - Nit
* **Affected Scope:** L219
* **Recommendation:** State 1-based, caller-supplied.

### R16 Python version deferred to Triage - Nit
* **Affected Scope:** L212
* **Recommendation:** Restate "3.13 or later".

### R17 Rubric rule text not verbatim - Nit
* **Affected Scope:** L231
* **Recommendation:** Give each `Rule N:` line.

## Findings: codebase-details (CB)

### CB1 Unknown/duplicate/missing ids have no defined output - Major
* **Affected Scope:** L96-97, L217
* **Discrepancy:** `validate` "one ruling per finding"; unknown id has no finding to attach to (dropped or extra ruling?); which duplicate kept unstated; G1 leaves the shape to the implementer.
* **Recommendation:** State returned rulings and ids for each case.

### CB2 Re-ask condition contradicts itself - Major
* **Affected Scope:** L96, L217
* **Discrepancy:** Partial schema break re-asks under L96 not L217; zero findings edge case under "every"; second output replacing the first and use of same `prior` unstated.
* **Recommendation:** One rule and a detection mechanism.

### CB3 `prior` cannot be rebuilt from log - Major
* **Affected Scope:** L105-110, L213, L217
* **Discrepancy:** Same as R1; also `quote_sha`, `rubric_sha`, `spec_sha` hash algorithms unspecified (only id SHA-1/8 hex given).
* **Recommendation:** Add `quote_sha` to ruling/log; name e.g. `hashlib.sha256` and normalisation; add `prior_from_lines(lines)`.

### CB4 Merged finding severity undefined - Major
* **Affected Scope:** L80, L213
* **Recommendation:** Highest wins (Blocker > Major > Nit).

### CB5 Citation resolver under-specified - Major
* **Affected Scope:** L99, L217
* **Discrepancy:** Numbering base, end inclusivity, start > end, line join, exact vs normalised match, multi-line quotes, trailing newlines.
* **Recommendation:** Pin choices.

### CB6 Arbiter-issued `escalate` path through checks - Major
* **Affected Scope:** L99-101
* **Discrepancy:** No required quote, may carry `L`, may differ from prior `accept`; unclear whether it hits check 3 or 6 rather than `arbiter`.
* **Recommendation:** State it skips checks 3-6 or give its order position.

### CB7 Log and metric functions lack data - Major
* **Affected Scope:** L103, L109-110, L115, L213, L218-220
* **Discrepancy:** Ruling shape lacks `round`; `format_lines` header is the only source; `needs_audit(feature_index)` contradicts G8 (id-only); no audit-line creator; `result` values; `overturn_rate` must join rulings to headers by round but audit lines lack round; no function computes `same_model`/header/hashes; return shape and `n=0`.
* **Recommendation:** Round in audit lines or key by (round, id); enumerate results; `build_header`; return shapes; align `needs_audit` with G8 or amend G8.

### CB8 Test plan below the Escalation design's bar - Major
* **Affected Scope:** L201, L223-226
* **Discrepancy:** Names only; Escalation has classes and input/expected tables; untested causes, check order, `needs_audit` 5/6 boundary, `summary`; fixture cannot exercise an agent; import style (`scripts.herd_arbiter`) unstated.
* **Recommendation:** Table of test, input, expected, class.

### CB9 Agent file under-specified - Major
* **Affected Scope:** L233-236, L241
* **Discrepancy:** No frontmatter; no exclusion mechanism for inherited instructions though repo has a root CLAUDE.md; `inherit` path unclear.
* **Recommendation:** Exact frontmatter and exclusion mechanism, or accept the limit.

### CB10 `herd.toml` ownership differs across designs - Nit
* **Affected Scope:** L206, L238
* **Discrepancy:** Triage "Create" with no other tables; if Triage built after the Arbiter a literal Create clobbers `[arbiter]`.
* **Recommendation:** Triage entry "Create if absent, else Modify", or state build order.

### CB11 Normalisation not exact - Nit
* **Affected Scope:** L80, L214
* **Discrepancy:** strip/`lower()` vs `casefold`; `" ".join(s.split())` not named; affects ids.
* **Recommendation:** Specify exactly.

### CB12 Phase 3 `grep -c "^Rule [1-5]:"` weak - Nit
* **Affected Scope:** L203
* **Discrepancy:** Passes an otherwise empty rubric; fails if rule lines indented or in a code block; does not check verdict set, schema, data-block rule.
* **Recommendation:** Strengthen the check.

### CB13 Phase 4 lacks coexistence check - Nit
* **Affected Scope:** Phase 4
* **Discrepancy:** No check that `floor`/`budget` tables survive when modifying `herd.toml`.
* **Recommendation:** Add one.

## Findings: style (SD)

### SD1 Re-ask condition L217 vs L95 - Major
* **Affected Scope:** L95, L217; Escalation L108
* **Discrepancy:** Escalation uses "every ruling malformed after the re-ask", matching L217 only.
* **Recommendation:** State the same condition in both; say how the caller detects partial breaks.

### SD2 "the prompt in the order above" has no referent - Major
* **Affected Scope:** L216, L221
* **Discrepancy:** Order is at L82; `summary` says nothing about content.
* **Recommendation:** Name "Technical Plan, Input: rubric, spec, prior rulings, findings"; point `summary` to "Spec PR summary".

### SD3 Ruling shape under-specified and inconsistent - Major
* **Affected Scope:** L88, L109, L213
* **Discrepancy:** `conf` vs `confidence`; `verdict` vs `arbiter_verdict` meaning; `cause` values not listed; `type` and `round` absent from the shape and from `format_lines` inputs.
* **Recommendation:** One sentence on each of the four points.

### SD4 `overturn_rate` shape and `test_round_trip` parse - Nit
* **Affected Scope:** L110, L220, L226
* **Discrepancy:** "each split by `same_model`" undefined; `result` values; `test_round_trip` covers "parse" but no parser listed.
* **Recommendation:** Define shape; name the parser.

### SD5 Python version via Triage - Nit
* **Affected Scope:** L206, L212, L224
* **Recommendation:** Write "Python 3.13 or later".

### SD6 `herd.toml` creator wording - Nit
* **Affected Scope:** L206, L238
* **Discrepancy:** Escalation L218: whichever design builds first creates it.
* **Recommendation:** "Modify; Create if absent"; reword "only the `arbiter` table" as "at least".

### SD7 Agent-file sentence vague - Nit
* **Affected Scope:** L235
* **Recommendation:** Separate tools from context rule; name rubric path and JSON contract.

### SD8 Cryptic Type/Scope entry - Nit
* **Affected Scope:** L231
* **Recommendation:** "Rubric text, which is placed outside the data blocks in the prompt".

### SD9 E2E line is a pilot measurement - Nit
* **Affected Scope:** L249
* **Recommendation:** "E2E/Integration: none in this design"; point to PRD section 3.

### SD10 "(TOML has no null)" aside - Nit
* **Affected Scope:** L241
* **Recommendation:** Keep; reword as separate sentence.
