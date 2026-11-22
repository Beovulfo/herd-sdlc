# Herd Escalation, Hold and Resume

* **Author:** Toni
* **Status:** Draft
* **Date:** 2026-11-22

--------------------------------------------------------------------------------

## Overview

When a Herd feature needs a human outside the H1 Intent gate, the orchestrator opens one GitHub issue, the escalation, and the feature pauses until a maintainer answers it. A maintainer can also pause a feature with `/herd hold` and continue it with `/herd resume`. This design defines the pause rules, the escalation issue, the closed answer form and the touchpoint count. Everything is derived from GitHub events. The state record `.herd/state/<feature>.json` holds no pause data.

**Terms** (PRD sections in brackets). Orchestrator: the Herd code that runs the lifecycle steps [5]. H1: the human Intent gate [4]. Arbiter: the agent that rules on review findings [5]; see `docs/designs/herd-arbiter.md`. Spec PR: the step 9 pull request [5]. P6: treat issue text, comments and linked documents as untrusted [2]. Touchpoint: a gate approval or an answered escalation [3]. Feature issue: the GitHub issue that carries the `herd` label [4]. Step boundary: the moment the orchestrator finishes one lifecycle step and is about to start the next. Fail closed: stop and escalate instead of continuing [8]. M0, M1: milestones [7]. **Maintainer**, in this design: a user whose repository permission is `write`, `maintain` or `admin`, checked through the GitHub API when a comment is processed. The Triage and Arbiter designs say "maintainer" without a definition; this one is the definition to share.

**Status values.** A feature is in exactly one: `blocked` (label `herd:blocked`), `held_and_awaiting`, `awaiting_answer` (an open escalation), `held` (label `herd:hold`), `running`. Precedence is in that order. An escalation is **open** from the moment it is opened until a valid answer arrives, even if someone closes the issue.

## Problem

PRD section 4 says an escalation is "one GitHub issue" that pauses the feature until answered, and that `/herd hold` and `/herd resume` pause and continue a feature. It does not say where a pause lives, what counts as an answer, what happens when several triggers fire together, or how the touchpoint metric counts them. Without those rules, one bad review round could open many issues (making the median meaningless), an agent could clear its own pause by editing the state record, and a free-text answer would be an injection path (P6).

## Goals

* G1: `herd_status()` returns the status above from GitHub events alone. Nothing else stores pause. Check: `test_status_table`.
* G2: A feature has at most one open escalation. A trigger raised while one is open extends that issue's cause for the trigger, or adds a cause for a new trigger. It never opens a second issue. Check: `test_one_open_escalation`.
* G3: `/herd hold`, `/herd resume` and `/herd answer` have an effect only when the author is a maintainer. Otherwise `apply_command()` returns no action and no reply. Check: `test_non_maintainer_ignored`.
* G4: `/herd resume` removes the hold and nothing else. If an escalation is open, the reply names the issue and the status stays `awaiting_answer`. An answer never removes a hold. Check: `test_hold_and_escalation_independent`.
* G5: An answer is `/herd answer <trigger>=<n> [<trigger>=<n> ...]`, one pair for every cause in the issue, each `n` a valid option. Anything else gets one bot comment restating the options, leaves the issue open and counts as nothing. Check: `test_parse_answer`.
* G6: A touchpoint is one escalation that received a valid maintainer answer. Hold, resume, bot comments, invalid answers and a close without an answer count as zero. Check: `test_touchpoints`.
* G7: Time held or awaiting an answer is excluded from the wall-clock budget. Check: `test_paused_seconds`.
* G8: At most 3 escalation issues are opened for a feature, counting repeats, since the last removal of `herd:blocked`. When `next_escalation()` is asked for a fourth, it returns `blocked`. Check: `test_ceiling`.

## Non-Goals

* The H2 release gate, the Evidence Auditor, and deciding what the answer should be.
* Reminders. PRD section 4 gives the 24-hour reminder to H1 only. The issue is assigned to the maintainers, so GitHub notifications apply. A reminder pass is an Open Question.
* A `tradeoff` trigger. Nothing in M0 produces one.
* Auto-answer, auto-close or auto-resume on a timeout.
* A durable escalation log outside GitHub. PRD section 5 says state is derived from GitHub wherever possible, and issue, label and comment events persist there.
* The GitHub Actions workflows, the `gh` calls and the per-feature `concurrency` group (orchestrator design).
* Tamper protection for the agent-pushable record branch (M1, as in `docs/designs/herd-triage.md`).

## Open Questions

* Should a reminder pass exist in M0 once real escalations are seen to go stale?
* Should Triage and Arbiter adopt this design's maintainer definition (`write` or higher)?

## Critical User Journeys (CUJs)

### CUJ 1: Round cap reached

* **Given**: Round 3 of the review loop ends with an open `Blocker` or `Major`.
* **When**: The orchestrator raises trigger `rounds`.
* **Then**: One escalation is opened with options `1 one more round`, `2 proceed with the open findings listed in the spec PR`, `3 stop`. The status is `awaiting_answer`. Test: `test_one_open_escalation`, `test_status_table`.

### CUJ 2: Several triggers

* **Given**: An escalation is open for `low_confidence`.
* **When**: The orchestrator raises `budget`.
* **Then**: The issue gets a second cause, `budget`. No second issue is opened. The answer must then contain both `low_confidence=<n>` and `budget=<n>`. Test: `test_one_open_escalation`.

### CUJ 3: Maintainer answers

* **Given**: An open escalation with causes `rounds` and `budget`.
* **When**: A maintainer comments `/herd answer rounds=1 budget=2`.
* **Then**: The answer is valid. The orchestrator posts a comment recording actor, comment id and the pairs, closes the issue, and acts on the options. The touchpoint count rises by one. Test: `test_parse_answer`, `test_touchpoints`.

### CUJ 4: Resume while an answer is pending

* **Given**: The feature is held and has an open escalation.
* **When**: A maintainer comments `/herd resume`.
* **Then**: The hold label is removed, the status is `awaiting_answer`, and the reply names the open issue. Test: `test_hold_and_escalation_independent`.

### CUJ 5: Invalid answer

* **Given**: An open escalation with cause `rounds` and options 1 to 3.
* **When**: A maintainer comments `/herd answer rounds=4`.
* **Then**: One bot comment restates the options. The issue stays open. No touchpoint is counted. Test: `test_parse_answer`.

### CUJ 6: Non-maintainer command

* **Given**: Any open feature.
* **When**: A user without write permission comments `/herd hold`.
* **Then**: Nothing happens and no reply is posted. Test: `test_non_maintainer_ignored`.

### CUJ 7: Issue closed without an answer

* **Given**: An open escalation.
* **When**: Someone closes the issue with no valid answer.
* **Then**: The orchestrator reopens it with one comment. The status stays `awaiting_answer` throughout, and the touchpoint count does not change. Test: `test_closed_without_answer_stays_open`.

### CUJ 8: Fourth escalation

* **Given**: Three escalation issues have been opened since the feature last lost `herd:blocked`.
* **When**: A trigger fires and no escalation is open.
* **Then**: No issue is opened. The orchestrator labels the feature `herd:blocked` and comments. A maintainer removes the label by hand to continue, and the count restarts. Test: `test_ceiling`.

## Technical Plan

**All state comes from events.** Every function takes a list of GitHub events, replayed in order into a state: the label set, and the list of escalations with their causes, answers and open or closed status. The orchestrator fetches events with `gh` and calls `herd_status(state)` at every step boundary. It starts a step only when the status is `running`. A hold never stops a step already running; it takes effect at the next boundary, and the reply to `/herd hold` says so.

**Triggers.** A closed table. The orchestrator has no other way to open an issue.

| Trigger | Raised when | Options |
| --- | --- | --- |
| `rounds` | The review loop ends round 3 with an open `Blocker` or `Major` (including `policy`, `citation`, `flip` and other Arbiter-escalated findings) | 1 one more round, 2 proceed with the open findings listed in the spec PR, 3 stop |
| `budget` | A limit in `herd.toml` `budget` is exceeded | 1 raise every limit by `budget.raise_by_pct` percent, 2 stop |
| `low_confidence` | The Arbiter rules `escalate` with cause `low_confidence` on a `Blocker` or `Major` | 1 follow the Arbiter's original verdict, 2 overrule it, 3 stop |
| `step_failure` | A step fails closed: no fresh context, an invalid record, or every ruling `malformed` after the Arbiter's re-ask | 1 retry the step, 2 stop |

Arbiter causes other than `low_confidence` on a `Blocker` or `Major` go to the spec PR summary (Arbiter design) and open no issue. Some `malformed` rulings short of all of them are such summary items. A `low_confidence` ruling on a `Nit` goes to the summary too, so it costs no touchpoint. A Triage fallback is a comment and counts zero. `stop` is always the last option and labels the feature `herd:blocked`.

**Cause.** One cause per trigger per issue: `{trigger, step, findings, options}`. `findings` lists finding ids and may be empty. `step` is the lifecycle step number. `options` is a list of `{n, label, action}` with `action` one of `continue_round`, `proceed_open`, `stop`, `raise_budget`, `follow_arbiter`, `overrule_arbiter`, `retry_step`. For `overrule_arbiter`, the Elephant acts on the opposite of the Arbiter's `arbiter_verdict` (`accept` becomes a contest, `contest` becomes an accept); the orchestrator appends a `{"type":"human", ...}` line with the finding id, the choice, actor and comment id to `decisions.md`.

**Escalation issue.** `build_issue_body(feature, causes)` fills a fixed template with no model call, so an over-budget feature cannot overspend to report itself. Contents: the feature issue number, each cause with its numbered options, and the answer syntax with a worked line. Finding text and reasons are not included, only ids. The issue has the label `herd:escalation` and never the `herd` label. Its first line is a hidden marker `<!-- herd:escalation v1 feature=<n> -->`, trusted only when the issue author is the bot. It is assigned to the maintainers. A trigger whose `(feature, trigger, step)` matches an earlier answered escalation opens a new issue with `repeat_of` set, and counts as a touchpoint again.

**Commands.** `parse_command(body, author_is_bot, edited)` takes the first line of the comment that is outside code fences and not quoted (starts with `>`), and matches one of `/herd hold`, `/herd resume` or `/herd answer ` followed by one or more `<trigger>=<n>` pairs. Bot-authored and edited comments return none. Commands go on the feature issue, except `/herd answer`, which goes on the escalation issue. `apply_command(state, command, is_maintainer)` returns `{action, reply}` as in this table:

| Command | `running` | `held` | `awaiting_answer` | `held_and_awaiting` | `blocked` |
| --- | --- | --- | --- | --- | --- |
| `/herd hold` | add label | reply "already held" | add label | reply "already held" | no action |
| `/herd resume` | reply "not paused" | remove label | reply naming the open issue | remove label, reply naming the issue | no action |
| `/herd answer` | no action | no action | validate, close on valid | validate, close on valid; the hold stays | no action |

**Blocked.** `herd:blocked` is set by the ceiling or by a `stop` answer. A maintainer removes it by hand, which makes the status follow the other rules and restarts the ceiling count.

**Effective limits.** The round cap is `3 + k`, where `k` is the number of answered `rounds` escalations whose answer was `continue_round`. Each limit in `herd.toml` `budget` is multiplied by `(1 + raise_by_pct / 100)` for each answered `budget` escalation whose answer was `raise_budget`. `effective_limits(state, base)` computes both from events, so no counter is stored. `budget_used` stays in the record and belongs to the round loop design.

**Pause time.** `paused_seconds(events, now)` returns the total length of the union of intervals during which the feature had `herd:hold` or an open escalation, so overlapping intervals count once. The orchestrator subtracts it from elapsed wall-clock time. Token limits are not reduced.

**Touchpoints.** `touchpoints(state)` returns `{opened, answered, open, repeats, rule: 1}` for one feature. `rule` is the version of the counting rule and is printed in the report, so the 20-feature baseline stays comparable (PRD section 3). Aggregation across features and the median belong to the report code in the orchestrator design.

```text
GitHub events --> replay --> state --> herd_status, next_escalation, apply_command,
                                       effective_limits, touchpoints   (all pure)
        |
 orchestrator: checks status before each step; opens, appends, closes; applies answers
        |
 feature issue: herd:hold, herd:blocked        escalation issue: herd:escalation
```

## Alternatives Considered

### Alternative A: A `paused` field in the state record

* **Pros**: One read.
* **Cons**: An agent can push to the record's branch and clear its own pause, and it duplicates GitHub.
* **Reason for Rejection**: Rejected by author: it breaks P6. The same gap applies to `budget_used` until the M1 tamper check.

### Alternative B: One issue per trigger or per finding

* **Pros**: Simple to open.
* **Cons**: One bad round gives many issues, so the touchpoint median says nothing.
* **Reason for Rejection**: PRD section 4 says an escalation is one issue; this design reads it as one open issue per feature.

### Alternative C: Free-text answers read by an agent

* **Pros**: Flexible.
* **Cons**: An agent reading a comment as an instruction is an injection surface, and it drifts into deciding the answer.
* **Reason for Rejection**: Rejected by author: closed options parsed by code.

### Alternative D: Closing the issue is the answer

* **Pros**: No answer syntax to learn.
* **Cons**: Closing carries no choice and is easy to do by accident.
* **Reason for Rejection**: Rejected by author: a close stays "no answer".

### Alternative E: `/herd resume` overrides an open escalation

* **Pros**: Lets a maintainer unblock quickly.
* **Cons**: Skips the human decision and corrupts the touchpoint count.
* **Reason for Rejection**: Rejected by author: there is no force option in M0.

### Alternative F: A default answer after a timeout

* **Pros**: A feature never waits.
* **Cons**: The agent decides a trade-off the PRD says needs a human, and the touchpoint count then hides the decision.
* **Reason for Rejection**: PRD section 4: the feature pauses until answered.

--------------------------------------------------------------------------------

## Non-Functional Requirements

* **Security**: P6 applies to every comment and issue body. The maintainer check runs through the GitHub API when the comment is processed. Only trigger names and option numbers in an answer are parsed, and no comment text reaches an agent.
* **Cost**: The issue is built with no model call. Waiting uses no run: the run exits on pause and a comment event restarts it (orchestrator design).
* **Rollout**: Open features have no escalations, so they are `running` until a trigger fires. Rollback: remove the `herd:*` labels and ignore escalation issues.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Label, comment and a running step at once | The orchestrator design serialises per feature; handlers are idempotent by comment id |
| Maintainers miss an escalation | Assigned to maintainers; Open Question on reminders |
| A repeat cause burns touchpoints | `repeat_of` link and the ceiling of 3 |
| A user with write permission applies or removes `herd:hold` | Accepted: write permission is the maintainer definition; GitHub logs label events |
| Closing and reopening loops | One comment per reopen; count stays zero; no auto-answer |
| `raise_by_pct` set too high by the owner | It lives in `herd.toml`, set by the owner; an answer only chooses whether to apply it |
| Transient `step_failure` costs a touchpoint | Accepted; the retry option is option 1 |

## Future Improvements

* A bounded reminder pass at 24 and 72 hours, then a `herd:stalled` label.
* A durable escalation log in `decisions.md`.
* A `tradeoff` trigger with agent-supplied options.

--------------------------------------------------------------------------------

## Detailed Implementation Plan

### Phases

| Phase | Work | Exit check |
| --- | --- | --- |
| 1 | `replay()`, `herd_status()`, `parse_command()`, `apply_command()` | `python3 -m unittest scripts.test_herd_escalation.TestStatus` passes |
| 2 | `parse_answer()`, `build_issue_body()`, `next_escalation()` | `python3 -m unittest scripts.test_herd_escalation.TestEscalation` passes |
| 3 | `effective_limits()`, `paused_seconds()`, `touchpoints()` | `python3 -m unittest scripts.test_herd_escalation` passes (all tests) |
| 4 | `herd.toml` `budget` key; PRD edit | `python3 -c "import tomllib; print(tomllib.load(open('herd.toml','rb'))['budget'])"` prints a dict with `tokens`, `minutes`, `raise_by_pct`; `grep -n "answer <trigger>" PRD*.md` matches one line |

Whichever of the Triage, Arbiter and Escalation designs is built first creates `herd.toml`; the others modify it. Phase 4 runs after that.

### Target Files to Create/Modify

#### 1. `scripts/herd_escalation.py` (Create)

* **Type / Scope**: Python module, standard library only, on the Python version the Triage design pins. Pure functions; no `gh` calls and no file writes.
* **Proposed Changes**: An event is a dict with `type` and `at` (ISO 8601 UTC string), plus the fields for its type: `label_added` and `label_removed` (`label`); `issue_opened` (`issue`, `kind` of `feature` or `escalation`; for an escalation also `causes` and `repeat_of`); `issue_closed` and `issue_reopened` (`issue`); `comment` (`issue`, `id`, `body`, `author`, `author_is_bot`, `author_is_maintainer`, `edited`). `replay` yields a state `{labels: set, escalations: list}`, each escalation `{number, causes, repeat_of, opened_at, closed_at, answer}` where `answer` is the first valid maintainer answer or none. An escalation is open while `answer` is none.
  * `replay(events: list[dict]) -> dict`.
  * `herd_status(state: dict) -> str`: the precedence in Overview.
  * `parse_command(body: str, author_is_bot: bool, edited: bool) -> dict | None`: `{name: hold | resume | answer, pairs: dict[str, int]}`.
  * `apply_command(state: dict, command: dict, is_maintainer: bool) -> dict`: `{action, reply}` as in the table; `action` is `add_label`, `remove_label`, `close_issue` or none.
  * `parse_answer(pairs: dict[str, int], causes: list[dict]) -> tuple[bool, str]`: valid only when the keys equal the triggers in `causes` and each value is an option number; otherwise the restating reply.
  * `build_issue_body(feature: int, causes: list[dict]) -> str`.
  * `next_escalation(state: dict, trigger: str, step: int) -> dict`: `{action: append | open | blocked, repeat_of: int | None}`. Order: if an escalation is open, `append`; else if 3 or more were opened since the last `herd:blocked` removal, `blocked`; else `open`, with `repeat_of` set when an answered one matches `(trigger, step)`.
  * `effective_limits(state: dict, base: dict) -> dict`: `{rounds, tokens, minutes}`.
  * `paused_seconds(events: list[dict], now: str) -> int`.
  * `touchpoints(state: dict) -> dict`.

#### 2. `scripts/test_herd_escalation.py` (Create)

* **Type / Scope**: `unittest`, standard library only. Inline generic events. `TestStatus` holds the status, command and parsing tests; `TestEscalation` the rest.
* **Proposed Changes**:

| Test | Input | Expected |
| --- | --- | --- |
| `test_status_table` | five label and escalation combinations | `blocked`, `held_and_awaiting`, `awaiting_answer`, `held`, `running` |
| `test_one_open_escalation` | open escalation, trigger `budget` raised | `append`; with none open: `open` |
| `test_non_maintainer_ignored` | `/herd hold`, `is_maintainer=False` | action none, reply empty |
| `test_hold_and_escalation_independent` | held and open, `/herd resume`; then valid answer while held | status `awaiting_answer`; then `held` |
| `test_parse_answer` | `rounds=1 budget=2`; `rounds=4`; `rounds=1` with two causes | valid; invalid with restating reply; invalid |
| `test_touchpoints` | one valid answer, one invalid, one close without answer | `answered` is 1 |
| `test_paused_seconds` | overlapping hold and open escalation | the union length, counted once |
| `test_ceiling` | three issues opened, none open; then label removal | `blocked`; then `open` |
| `test_closed_without_answer_stays_open` | open, close, no answer | status `awaiting_answer`; `answered` is 0 |
| `test_command_in_code_fence_ignored` | command inside fences or a quote | none |
| `test_edited_comment_ignored` | `edited=True` | none |
| `test_effective_limits` | one `continue_round` answer, one `raise_budget` answer | rounds 4; each limit multiplied once |

#### 3. `herd.toml` (Modify; Create if absent)

* **Type / Scope**: Config.
* **Proposed Changes**: Add a `[budget]` table with `tokens = 500000`, `minutes = 60`, `raise_by_pct = 50`. The values are placeholders for the owner to set, not a recommendation.

#### 4. PRD (Modify)

* **Type / Scope**: Docs, the file at the repo root whose name starts with `PRD`.
* **Proposed Changes**: In section 4, Commands: change `/herd answer <n>` to `/herd answer <trigger>=<n> [<trigger>=<n> ...]`.

### Verification Plan

* **Build**: none.
* **Unit Tests**: `python3 -m unittest scripts.test_herd_escalation`.
* **Static Analysis & Linting**: none required in M0.
* **Test Coverage Requirement**: every goal and CUJ above names a test in the table.
* **E2E/Integration**: none in this design. The orchestrator design owns the GitHub flow.

--------------------------------------------------------------------------------

*Drafted with EGM*
