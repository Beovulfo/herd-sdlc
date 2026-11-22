# Goldfish Review Report: Stage 9 (implementation-readiness, codebase-details, style on DetailedRange)

**Target:** `docs/designs/herd-escalation.md` (207-277). Standard: implementation-readiness-standard. Verdict: fails the Zero-Decision Rule.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-implementation-readiness` | completed |
| `egm-codebase-details` | completed |
| `egm-style` | completed |

Counts (deduplicated): Blocker 3, Major 9, Nit 9. No corruption findings. Repo has no code to reuse (no `scripts/`, no `.github/`).

## Blocker

### R1 No event appends a cause to an open escalation - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** lines 225, 226, 232, 245
* **Discrepancy Description**: Events are `issue_opened` (with `causes`), `issue_closed`, `issue_reopened`, `comment`, label events. `replay` builds causes only from `issue_opened`, so CUJ 2 and G2 (a later trigger adds a cause) cannot be replayed; `parse_answer` validates against stale causes. `next_escalation` returns only `append`.
* **Rationale & Recommendation**: Add `cause_appended` (`issue`, `cause`) or specify body-read replay; define replace/merge/keep-first for the same trigger with different `step` or `findings`.

### R2 `answer` shape undefined; replay validation unspecified - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** lines 225, 232, 235, 247
* **Discrepancy Description**: `answer` has no shape; replay is not said to run `parse_command` and `parse_answer`. `effective_limits` needs `n` mapped to option action; `touchpoints` and `paused_seconds` need answer time; CUJ 3 needs actor and comment id. `closed_at` semantics and reopen effect undefined. Breaks phasing: `test_hold_and_escalation_independent` needs a valid answer in Phase 1 while `parse_answer` is Phase 2.
* **Rationale & Recommendation**: Specify `answer = {pairs, actor, comment_id, at}`, full state schema and per-event transitions (repeated labels, events on never-opened issues).

### R3 State cannot support "since last `herd:blocked` removal" - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** line 232, G8
* **Discrepancy Description**: State is `{labels, escalations}` only; `next_escalation` needs the time of the last removal.
* **Rationale & Recommendation**: Add a state field (e.g. `blocked_cleared_at`) and its replay update, or drop the ceiling (see Stage 8 I1).

## Major

### R4 `apply_command` cannot do what the table says - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** lines 116-123, 229
* **Discrepancy Description**: "Validate, close on valid" but no issue number or causes available; cannot reject answers on the feature issue, an answered issue or when none is open. Return shape lacks label name, issue to close, resolved option actions (`continue_round`, `retry_step`). `parse_command` returns `pairs: dict[str,int]`, so `rounds=x` and duplicate keys are lost, yet G5 needs a restating reply.
* **Rationale & Recommendation**: Pass source issue number; define `action` as a record `{kind, label|issue, ...}`; return raw strings or a `malformed` flag.

### R5 `parse_command` grammar left to implementer - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** lines 116, 228
* **Discrepancy Description**: Undefined: "first line" selection, fence syntax (backtick, tilde, indented, unclosed), quote detection, case, whitespace, trailing text (`/herd hold please`), `<trigger>` charset, duplicate keys, `/herd answer` with zero or malformed pairs.
* **Rationale & Recommendation**: Give a regex, line-selection rule and a test per case.

### R6 Reply strings and CUJ 7 reopen unowned - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** lines 89, 99, 121, 129, 195
* **Discrepancy Description**: "Already held", "not paused", "naming the open issue", hold reply, restate reply and reopen comment are paraphrases; "no action" cells do not say whether the reply is empty. Nothing handles `issue_closed` (reopen once with a comment).
* **Rationale & Recommendation**: Table of literal reply strings; add a function or assign reopen to the orchestrator.

### R7 `build_issue_body` has no template; no `TRIGGERS`/`make_cause` - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** lines 101-114, 231
* **Discrepancy Description**: No literal layout, option rendering, worked answer line, marker placement or assignment; `budget` option text needs `raise_by_pct` absent from the signature; trigger-to-options mapping exists only as prose; nothing builds a cause. No test that the marker and option numbers appear and finding text does not.
* **Rationale & Recommendation**: Add `TRIGGERS` constant, `make_cause(trigger, step, findings, raise_by_pct)`, verbatim template and the test.

### R8 `effective_limits` inputs and rounding unspecified - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`
* **Affected Scope:** lines 126, 233, 255
* **Discrepancy Description**: `base` keys (`tokens`, `minutes`, `raise_by_pct`) and base rounds 3 source not given; compounding vs additive over several answers; floor/ceil/round for floats; one test only ("rounds 4; each limit multiplied once" gives no values).
* **Rationale & Recommendation**: Define `base`, rounding rule, add a two-answer test with concrete numbers.

### R9 `paused_seconds` boundaries unstated - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** line 234
* **Discrepancy Description**: Hold interval from `label_added` to `label_removed`, open to `now`; escalation interval ends at answer `at`, not `closed_at` (close without answer reopens); `label_added` has no `issue` field so only feature-issue labels may count; int rounding.
* **Rationale & Recommendation**: State each boundary and rounding.

### R10 `decisions.md` human line has no owner - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** line 112; Arbiter line 78
* **Discrepancy Description**: No function writes it; Arbiter design says `herd_arbiter.py` is the only writer and its format is a placeholder pending S2.
* **Rationale & Recommendation**: Pure `build_decision_line` here with `herd_arbiter.py` as writer, or amend Arbiter; state exact JSON fields.

### R11 Phase exit checks vs test-class split contradict - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-style`, `egm-implementation-readiness`
* **Affected Scope:** lines 213-215, 239, 242-255
* **Discrepancy Description**: `TestStatus` holds "status, command and parsing tests" so `test_parse_answer` (Phase 2) lands in Phase 1; `TestEscalation` ("the rest") holds `test_touchpoints`, `test_paused_seconds`, `test_effective_limits` (Phase 3), so the Phase 2 check cannot pass.
* **Rationale & Recommendation**: Add a Class/Phase column or exact `-k` lists; say `parse_command` tests; state import form and whether `scripts/__init__.py` is needed.

### R12 PRD edit stale; path not exact - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-implementation-readiness`
* **Affected Scope:** lines 216, 262-265
* **Discrepancy Description**: PRD line 69 already has `/herd answer <trigger>=<n> [<trigger>=<n> ...]`; Phase 4 grep passes before any work. Target described as "name starts with `PRD`"; the standard requires exact repo-relative paths (file has spaces and an em dash).
* **Rationale & Recommendation**: Drop or mark done; otherwise name exact file and current text.

## Nit

* **R13** (lines 242-255): test gaps: `test_touchpoints` asserts only `answered` (add `opened`, `open`, `repeats`); `test_status_table` and the "five combinations" test (line 244) list no inputs or outputs; no tests for `build_issue_body`, `repeat_of`, bot-authored comments, non-maintainer answer, answer while `blocked`/`held`, first-valid-answer-wins.
* **R14** (lines 218, 257): `herd.toml` "whichever design is built first creates it" is conditional; pin the creator or record build order; state keys to preserve (`floor`, `arbiter`).
* **R15** (line 224): "the Python version the Triage design pins" is indirect; state 3.13 (Triage line 167) and that `tomllib` needs 3.11+.
* **R16** (line 229): "as in the table" names no table; cite the Overview command table.
* **R17** (line 225): "answer is the first valid maintainer answer or none" ambiguous; write "or `None`" and use a field table for the seven event shapes.
* **R18** (line 230): "otherwise the restating reply" does not state the return; spell out `(False, <reply text>)`.
* **R19** (line 235, 249): `touchpoints()` return type not declared; add `-> dict` and keys.
* **R20** (line 218): "Phase 4 runs after that" vague; say Phase 4 needs `herd.toml` to exist.
* **R21** (lines 213-215 vs Triage 196): test command form differs from Triage (dotted vs path); pick one.
