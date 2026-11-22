# Herd Escalation and hold/resume

* **Author:** Toni
* **Date:** 2026-11-22

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

## Overview

Escalation is how Herd asks a human for help. One GitHub issue is opened when a review loop passes 3 rounds, the per-feature budget is exceeded, the Arbiter's confidence is low, or a real trade-off needs a human. The feature stays paused until a maintainer answers. Apart from the H1 Intent gate, this is the only human touchpoint, and the metrics count it (median at most 2 per feature, H1 included).

`/herd hold` and `/herd resume` let a maintainer pause and continue a feature by hand. Both are maintainer-only. Under principle P6, issue text, comments and linked documents are untrusted input.

Consumers: the maintainer who answers, the orchestrator that pauses and resumes, and the touchpoint metric. Only `gh` is used as an external service.

## Analysis

All seven reviewers agree on the core shape. They differ on a few details, listed under Open questions.

**1. Pause has no defined home (Blocker, raised by five lenses).** The PRD says the feature "pauses", and `/herd hold` also "pauses" it, but no design says what a pause is or where it lives. The state record `.herd/state/<feature>.yaml` sits on a branch an agent can push to (Triage accepts this gap for M0). A pause flag in that file could be cleared by an agent. Reviewers converge on deriving pause from GitHub only: paused = a maintainer-applied `herd:hold` label OR an open escalation issue. Hold and escalation are two independent facts, not one state machine. The record gets no pause keys. The orchestrator re-reads GitHub at each step boundary. Dissent: zoom-out and the observability lens would accept a small `paused` field as a cache or fallback, and implementation-readiness wants the safer state (paused) to win if label and record disagree.

**2. Several triggers at once: one open issue per feature (Blocker/Major, all lenses).** The Arbiter emits one `escalate` ruling per finding, with nine causes (missing, duplicate, unknown, policy, citation, malformed, flip, low_confidence, arbiter). Without a rule, one bad round gives many issues and the touchpoint median is meaningless. Rule: at most one open escalation issue per feature. A new trigger while one is open is appended to it (comment plus a cause list) and never opens a second issue. Findings in one round are batched into one issue.

**3. The mapping from triggers to causes is undefined (Blocker).** The PRD names four triggers. The Arbiter design routes `policy` rulings to the spec PR summary, not an issue, but says cap exhaustion "escalates with their ids". Triage says the orchestrator "escalates" on a `herd_yaml` fallback or a rejected `schema_version`. PRD section 8 says a missing fresh context "fails and escalates". Reviewers want a closed table: trigger, cause value, whether it opens an issue. Suggested triggers: `rounds`, `budget`, `low_confidence`, `tradeoff`, plus `step_failure` for fail-closed cases. The Arbiter cause stays as a detail field and is reused verbatim, not redefined. Triage fallback comments are not escalations and count as zero touchpoints. Which Arbiter causes open an issue is for the owner to decide (see Open questions).

**4. "Answered" must be defined (Blocker).** Free text cannot drive code, and an LLM reading a comment as an instruction is a P6 injection surface. Reviewers converge on a closed answer form: the issue body lists numbered options per cause (for example continue with one more round, raise budget by N, stop the feature, human takes over), and a maintainer replies with a choice. Deterministic code checks the commenter's role from the GitHub API at processing time and parses the option. Free text beyond the option is passed to agents only as a delimited data block. A reply that matches no option gets one bot comment restating the options, the feature stays paused, and nothing is counted. Closing the issue without an answer is not an answer. The accepted answer records actor, comment id and a content hash, so a later edit does not change what the feature acts on (reuse the shape of Triage's `risk.override`). Dissent: zoom-out prefers a lighter rule (maintainer comment, then close) over a new command. A dedicated `/herd answer <option>` command adds a command the PRD does not list, so it is a PRD change to flag to the owner.

**5. Hold and resume semantics (Major).** Hold and escalation compose without a state machine:

| Command or event | While running | While held | While escalated | Held and escalated |
| --- | --- | --- | --- | --- |
| `/herd hold` | add label, effective at next step boundary | no-op, "already held" | add label | no-op |
| `/herd resume` | no-op reply | clear hold | refuse, "answer #N first" | clear hold only, still waiting on #N |
| maintainer answer | not applicable | not applicable | clear escalation | clear escalation, still held |

Resume with no answer is refused with a comment. An answer never clears a hold, and resume never clears an escalation. There is no force option in M0. A hold never kills a step already running; it takes effect at the next boundary, and the reply says so.

**6. Non-maintainer commands (Major).** Reuse Triage's applier-role check (one shared `is_maintainer` function, role from the GitHub API at processing time, not from comment text). A command is the first line of a comment, exact match, outside quotes and code fences, from a non-bot author, and edits do not re-fire it. Reviewers split on the reply: the design lens wants no comment at all (an Actions run and a reply are a spam and probing vector), while comprehension and the observability lens want exactly one fixed reply. Either way, a non-maintainer command does no work and counts as nothing. Finding text quoted in an escalation issue must be fenced, cut to 140 characters (as the Arbiter does for `reason`), never linked or mentioned, and must not be able to look like a `/herd` command. The escalation issue must never carry the `herd` label, which starts a feature.

**7. Same cause escalated twice (Major).** A repeat usually means the earlier answer did not take, and it burns the touchpoint budget. Reviewers agree an answered cause must not re-ask silently. Mechanisms proposed: a dedupe key of (feature, trigger, step), not finding ids, because ids change when a reviewer rephrases (Arbiter Risks); a repeat is opened as "repeat of #N" linking the prior answer, and still counts as a touchpoint; a ceiling on escalations per feature (suggested 2 or 3), after which the feature is parked as failed or blocked instead of asking again. The design must also say whether an answer resets the round counter or adds a fixed number of rounds. A budget escalation must carry a new limit or a stop, or the resumed feature trips the same budget immediately.

**8. Budget while paused (Major).** If wall-clock counts paused time, a feature that waited days for an answer re-escalates the moment it resumes. Budget accounting must exclude time held or waiting on an escalation, computed from GitHub timestamps (label events, issue created and closed). Tokens stay the hard limit. Creating the issue must use a fixed template and make no model call, so an over-budget feature cannot overspend while reporting it.

**9. Reminders (Major, with dissent).** The PRD gives H1 a 24-hour reminder and says nothing for escalations. Zoom-out says M0 needs none: assign the issue to maintainers and let GitHub notifications work, and add reminders when the first escalation goes stale. The other lenses want one scheduled GitHub workflow that lists open escalations in one query, reminds at 24 hours, repeats a bounded number of times (suggested one more at 72 hours, or every 48 hours to a cap of 3), then applies a `herd:stalled` label. No auto-close, no auto-answer, no default decision. Reminders are bot comments, count as zero touchpoints, and are never new issues. Due-ness comes from the issue created time and a hidden bot marker, not a stored timer. No reminder fires while only a hold is waiting. Waiting consumes no run: the run exits on pause and a comment event or the scheduled check restarts it.

**10. Touchpoint metric (Blocker/Major).** One counting rule, defined once, versioned so the 20-feature pilot baseline stays comparable: a touchpoint is one escalation issue that received a valid maintainer answer, derived from GitHub. A repeat counts again. Hold, resume, reminders, clarification replies, and an issue closed without an answer count as zero. Report opened, answered and abandoned escalations by cause, the repeat rate, and held time next to the median, so holds are not a hidden touchpoint. Time to answer is wall time and must not be labelled "human minutes". The PRD limits the record to round counter, risk and budget used, so the count is derived from GitHub (and optionally an append-only log), not a stored counter. The S2 baseline table is blank, so there is no baseline to compare to yet.

**11. Shared record ownership (Blocker for implementation).** Triage, the round loop and Escalation all write `.herd/state/<feature>.yaml`. Triage's `write_record` takes a whole record and rejects an unknown or missing `schema_version`. No design yet owns the round counter and budget keys. Rule: each feature owns its own top-level key, read-modify-write touches only that key, new keys are optional on read (a Triage-only record means "no escalation"), and rollback of Escalation leaves other keys intact. Triage treats an unknown `herd.yaml` key as a fallback, so adding a budget key to `herd.yaml` needs a coordinated Triage change.

**12. Concurrency (Major).** A label event, a comment event, a cron check and a running review can start together. Use one GitHub Actions `concurrency` group per feature (cancel-in-progress false) for all event types. Command handlers only flip a label and post a reply, and never write the record. The owning run honours the hold at the next step boundary. Handlers are idempotent by comment id. GitHub state is written first, the record second, so a lost record write is repaired by reading GitHub. Triage defers race handling to M1, so Escalation cannot lean on it.

**13. Observability (Major).** One function, `herd_status(feature)`, returns running, held, awaiting_answer or both, with the cause. It is the single answer to "why is this feature idle" and gets a unit test that no step starts unless the status is running. Every command gets a recorded outcome (accepted, rejected_not_maintainer, rejected_bad_state, ignored_edited). Optionally extend the Arbiter's `decisions.md` (JSON Lines) with `escalation`, `answer`, `hold`, `resume`, `reminder` lines carrying feature, run id, round, causes, issue number, actor and comment id. The issue body carries a hidden marker comment with feature, trigger and a version, trusted only when the issue author is the bot, plus a small fenced machine block with `version: 1` that ignores unknown keys. Command location: commands go on the feature issue, answers on the escalation issue, linked both ways.

**14. Contradictions and the Ideal Final Result (inventive lens).** The reviewer named five tensions and resolved each without a new store. Pause versus touchpoint cost: key the escalation by feature, not by trigger (segmentation plus intermediary). Maintainer authority versus untrusted prose: make the answer a structured option, validated by code (extraction plus inversion). Pause versus silent stalls: a bounded, idempotent reminder pass that signals a stall instead of adding touchpoints (self-service). Two pause sources versus "state derived from GitHub": pause is a pure derived predicate, never stored. Frequent `low_confidence` and `policy` causes versus the touchpoint target: report escalate rate by cause and tune by hand, with no auto-adapting thresholds in M0. Ideal Final Result: one escalation issue per feature per answered cause set, holding the causes and a closed option list. A maintainer answers it once. Code checks the role and parses the answer. Pause, reminders and the touchpoint count are all derived from GitHub, with only round counter, risk and budget in the record, and the same cause with the same evidence never asks twice.

**Existing-code reuse.** The repo has docs only: no `scripts/`, no `herd.yaml`, no `.herd/`. Reuse by convention: Triage's atomic tmp-file plus rename record writer and its `human_override` event shape; the Arbiter's `decisions.md`, 140-character plain-text rule and finding-id scheme; Python stdlib, `unittest`, pure functions that never raise, with the orchestrator doing the `gh` calls. Suggested pure functions: one that builds the issue body from the cause list, and `can_resume(...)`.

## Goals vs. Non-Goals

* **In-Scope Goals:**
  * One open escalation issue per feature, with a cause list, appended to on new triggers.
  * A closed trigger table that reuses Arbiter causes and states which open an issue.
  * A closed answer form, checked by code, with a defined result for ambiguous, missing and non-maintainer answers.
  * `/herd hold` and `/herd resume`, maintainer-only, with the state table above.
  * Pause derived from GitHub (label plus open issue), never stored in the record.
  * A same-cause repeat rule and a per-feature escalation ceiling.
  * Budget accounting that excludes paused time.
  * One touchpoint counting rule, derived from GitHub.
  * Bounded reminders (or an explicit decision to defer them).
  * Key ownership, optional-on-read keys and rollback for the shared state record.
* **Out-of-Scope Non-Goals:**
  * The H2 release gate and the Evidence Auditor.
  * Deciding what the answer should be.
  * Auto-answer, auto-close or auto-resume on timeout.
  * A cause taxonomy beyond the Arbiter's, plus the few new triggers.
  * A maintainer roster in `herd.yaml`, a dashboard, or a touchpoint counter store.
  * Tamper protection for the agent-pushable branch (deferred to M1, as in Triage).
  * Any external service other than `gh`.

## Alternatives Weighed

* **One issue per trigger or per finding.** Rejected: the touchpoint median would become meaningless, and the PRD says one issue.
* **A `paused` field in the state record.** Rejected as the source of truth: an agent can write that branch and clear its own pause, and it duplicates GitHub. Kept only as a possible non-authoritative cache (observability lens), where GitHub wins if they disagree.
* **One merged pause state machine (running, held, escalated).** Rejected: hold and escalation are independent causes, so a derived predicate is simpler. Zoom-out proposed a single `paused: null | hold | escalation` field instead; rejected for the same agent-write reason.
* **Free-text answers interpreted by an LLM.** Rejected: that is a P6 surface and edges into deciding the answer.
* **Treating issue close as the answer.** Rejected: close carries no choice and is easy to do by accident. It stays "no answer", so the feature stays paused.
* **Letting `/herd resume` override an open escalation.** Rejected: it bypasses the human touchpoint and corrupts the metric. No force option in M0.
* **Dedupe by finding ids.** Rejected: ids change when a reviewer rephrases. Use (feature, trigger, step).
* **A reminder scheduler in M0.** Contested, not rejected. Zoom-out says defer it; the other lenses want a bounded scheduled check. Left as an open decision.
* **A separate `/herd answer` command.** Open: it is the cleanest closed form but is a PRD change.

## Key Decisions & Staging for Next Steps

Settled enough to carry into `/egm-draft`:

1. Pause is derived from GitHub: `herd:hold` label (maintainer-applied) OR open escalation issue. It is never stored in the record.
2. At most one open escalation issue per feature, with a cause list, batched per round.
3. Hold and escalation clear independently. Resume refuses while an escalation is open.
4. The answer is a closed option chosen by a verified maintainer. Free text is data only.
5. Touchpoint = one escalation issue with a valid maintainer answer. Everything else counts as zero. The rule is versioned.
6. Budget accounting excludes paused time. A budget answer must name a new limit or stop.
7. The record changes only under the feature's own key, optional on read.

Open questions for the owner (carry into the draft as decisions):

* Which Arbiter causes open an issue, and which only ride the spec PR summary (`policy` in particular)?
* Command form for the answer: a new `/herd answer <option>` (PRD change) or maintainer comment plus close?
* Is there a `stop` or `abandon` option in M0? The PRD has no cancel command.
* Reminders: none in M0, or one scheduled check with a stated cadence and cap?
* Repeat handling: ceiling of 2 or 3 per feature, and what happens at the ceiling (failed or blocked)?
* Does an answer reset the round counter or add a fixed number of rounds?
* Non-maintainer commands: no reply at all, or one fixed reply?
* Should `herd:hold` and `herd:escalation` (plus `herd:stalled`) be the label names, and how are they created and permission-limited?
* Does the touchpoint metric also read an append-only log, or only GitHub state?
* What does the metric do with an issue closed with no valid answer, or reopened?
