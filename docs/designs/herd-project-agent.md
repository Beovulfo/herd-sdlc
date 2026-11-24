# Herd Project Agent: ground check, learning across tasks, a graph agent that runs the task

* **Author:** Toni
* **Status:** Draft. Spike S4 done; nothing else built. The owner approved Part B as Collie's first job. A revision of Part B (one graph agent per repository) is under review on a separate branch and will replace this text when it lands.
* **Date:** 2026-11-24

--------------------------------------------------------------------------------

## Overview

Three changes that make Herd start from what a project already knows and get better with each task in it:

1. **Ground check (Part A).** `herd init` records the target repository's own knowledge base (agent instructions, README, docs, tests, CI) as evidence, and `herd verify` warns when the task ignores it: an instruction file the agent never read, or the project's own test command that no check runs.
2. **Learning across tasks (Part B).** When a task ends (`herd done`) or stops (`stopped.json`), Herd's code turns the task's records into lessons in a per-project store. The next task in that project reads them at intake. Lessons come from what Herd recorded (failed checks, refused gates, review findings, escalations, the human's criteria changes), never from an agent's summary.
3. **The Herd graph agent (Part C).** The plugin ships an agent that runs a Herd task as a graph, in the graph format of Collie, so a user's task is driven by Herd's flow and the project's lessons instead of Claude's default agent. Collie, the owner's graph agent that develops Herd and lives in its own repository, is the reference: same file layout, same node types, same gate rules, the same split of knowledge (agent file) and control flow (graph).

All three keep the existing rules: standard library only, `gh` the only external service, the CLI decides from files, git state, session logs and exit codes, a hook never breaks the session, and nothing reads the agent's wording.

**Terms.** Collie: the graph agent that develops Herd, kept outside this repository; an agent file holds its knowledge and YAML graphs its control flow, one line per node, with node types `act`, `think`, `check`, `gate`, `sub` and `end`. Knowledge base: the files in the target repository that tell a contributor how it works. Lesson: one record in the store, written by code. Store: the per-project file of lessons. Graph agent: an agent file plus a graph file, run by Collie's executor rules. Intake: step 1 of the run flow, up to `herd init` and triage.

## Problem

* Herd does not read the project it works in. `herd detect` proposes commands from ecosystem conventions ("not from docs", `scripts/herd_detect.py`). On this repository it returns nothing, while `CLAUDE.md` and `.github/workflows/ci.yml` name three commands: `python -m unittest discover -s tests -t .`, the supermarket verifier and `ruff check .`. A task whose criteria never run the project's own suite can break it and still pass `herd done`.
* Every task starts from zero. Haiku builds with Herd 0.3.1, 0.4.0 and 0.7.0 failed on the same bug class (a product refused while another side of its shelf was open). Each time the lesson reached Herd only because a human read the runs and changed Herd. Inside a user's project, the same mistake in the same module repeats until a human notices.
* The run flow is skill text read by Claude's default agent. Herd enforces most steps at `herd done`, but the order of steps, when to read a reference file, and what to do at intake are still text. The owner prefers a graph over a persona for agents (the `blackboard-reviewer` project) and code over skill text for rules (CHANGELOG 0.4.0).

## Goals

* G1: `herd init` writes `.herd/tasks/<slug>/ground.json`: for each knowledge file found, its path, size and SHA-256, and the commands found in CI workflow `run:` lines. Nothing is parsed beyond that. Check: `test_ground_records_files`, `test_ground_reads_ci_run_lines`.
* G2: At the first `herd verify`, Herd reads the main session log (as `preinit` already does for edits) and warns for each instruction file (`CLAUDE.md`, `AGENTS.md`, `README*` at the root) that no Read tool call opened. Check: `test_ground_warns_unread_instructions`.
* G3: `herd verify` warns when no criterion or attack check runs a command found in CI or proposed by `herd detect`, and the report and the PR list it under Not proven: "the project's own suite was not run". Check: `test_ground_warns_project_suite_not_run`.
* G4: `herd done` and `write_stop` add lessons to the store, from records only (see B2). Each lesson keeps its source (`herd`, `reviewer`, `human`) and the task, commit and record it came from. Check: `test_lessons_from_done`, `test_lessons_from_stop`.
* G5: The same lesson seen again increments `seen` instead of adding a row, and the report says "recurred: L7 (3rd time)". Check: `test_lesson_recurrence`.
* G6: `herd init` writes `.herd/tasks/<slug>/lessons.md` with at most 10 lessons, ranked by `seen` and recency, and prints one line naming it; at the first verify the ranking is redone with the changed files. Check: `test_lessons_ranked_and_capped`.
* G7: The store is written only by the CLI: the guard protects it during a task, like Herd's state files. Check: `test_guard_protects_store`.
* G8: The plugin ships `agents/herd-run.md` and `graphs/run.yaml` in the graph format; every `check` node in `run.yaml` names the `herd` command whose exit code decides it. Check: `test_run_graph_valid`, `test_run_graph_checks_name_commands`.
* G9: Parts A and B add at most 50 ms to `herd init` and `herd verify` on a repository with 1,000 files and 200 lessons. Check: `test_ground_and_lessons_cost`.

## Non-Goals

* Summarising the knowledge base with a model. Herd records which files exist and whether the agent opened them; understanding them stays the agent's job.
* Lessons written by the agent in free text. A summary an agent writes is a claim, not evidence (PRD P4).
* Matching words in lessons or in the agent's text to decide anything (no word lists).
* Sharing lessons across projects or machines, or any service beyond `gh`.
* Starting agents for the user. Herd provides the graph agent; how a session starts it stays the user's choice.
* Changing what `herd done` accepts. Ground and lesson warnings are advisory in this version.

## Open Questions

1. Should lessons be committed (one file per task, reviewed in the PR, shared with the team) or local only (the default below)? Committed lessons survive a fresh clone, but a lesson file written at `herd done` dirties the tree after the commit check.
2. Should a lesson that recurs 3 times raise the risk floor of the next task that touches its paths, so a review becomes mandatory?
3. Should G3 block `herd done` at medium and high risk instead of warning?
4. Is the graph agent the default for `/herd:run`, or opt-in through `herd.toml`?

## Critical User Journeys (CUJs)

### CUJ 1: The project's suite is ignored

* **Given**: A Python project whose CI runs `pytest tests/` and whose `CLAUDE.md` says "run make check before committing".
* **When**: The agent writes criteria that run only a new test file, and never opens `CLAUDE.md`.
* **Then**: The first `herd verify` prints "ground: CLAUDE.md not read" and "ground: no check runs a project command (`pytest tests/`, `make check`)". The PR lists both under Not proven. Test: `test_ground_warns_unread_instructions`, `test_ground_warns_project_suite_not_run`.

### CUJ 2: The same refusal bug, second task

* **Given**: Task `route-v1` failed its `refusal` attack twice before passing, and its reviewer reported a Major finding in `planner.py`. Both are lessons.
* **When**: Task `route-v2` runs `herd init` in the same project.
* **Then**: `lessons.md` lists both, with their source, task and record. If the refusal attack fails again in `route-v2`, the report says "recurred: L2 (2nd time)". Test: `test_lesson_recurrence`.

### CUJ 3: A stopped task still teaches

* **Given**: Task `export` stops after 3 gate blocks with criterion C2 failing 3 times in a row.
* **When**: The gate writes `stopped.json` with reason `escalated`.
* **Then**: The store gets a lesson of kind `escalation` naming C2's text (the human's words) and the failing check command. Test: `test_lessons_from_stop`.

### CUJ 4: A user runs a task with the Herd graph agent

* **Given**: The plugin is installed and the user starts a session with the Herd agent as the main agent (Part C, C3).
* **When**: The user gives a goal.
* **Then**: The agent follows `graphs/run.yaml`: ground check, lessons, criteria, red, build, break it, review, verify, done. Each `check` node passes only on the named `herd` command's exit code, and each gate stops for the user. Test: `test_run_graph_checks_name_commands`.

## Design

### Spike S4 (do first, before any code)

Confirm on the current Claude Code and record in `docs/spikes/s4-project-agent.md`:

1. That Read tool calls appear in the main session log as `tool_use` blocks with `name: "Read"` and `input.file_path`, like the Edit calls `_edited_files` reads.
2. That a plugin agent can be the main agent: `claude --agent <name>` and the `agent` setting both exist (`claude --help`, Claude Code 2.1.330); unknown is whether a plugin-scoped name (`herd:herd-run`) is accepted, and whether a project's `.claude/settings.json` can set it.
3. That `git rev-parse --git-common-dir` gives the same folder from the main checkout and from every linked worktree.

Do not guess these (CLAUDE.md, Writing). If one fails, change this design before writing code.

**Result** ([`s4-project-agent.md`](../spikes/s4-project-agent.md), Claude Code 2.1.330): all three hold, with one change to A2. `CLAUDE.md` is loaded by Claude Code itself and recorded as an `instructions` attachment, not a Read, so A2 counts those files as read. `--agent herd:herd-reviewer` and the project `agent` setting both made the plugin agent the main agent, so C3 needs no subagent fallback.

### Part A: ground check

**A1. What is recorded.** At `herd init`, from the project root, `ground.json` holds:

```json
{"at": "...", "files": [{"path": "CLAUDE.md", "bytes": 2210, "sha256": "...", "kind": "instructions"}],
 "ci_commands": ["python -m unittest discover -s tests -t ."], "detect": ["pytest"]}
```

Kinds, by path only: `instructions` (`CLAUDE.md`, `AGENTS.md`, `.github/copilot-instructions.md`), `readme` (`README*` at the root), `docs` (`docs/**/*.md`, at most 50, listed not read), `contributing` (`CONTRIBUTING*`), `ci` (`.github/workflows/*.y*ml`, `.gitlab-ci.yml`), `tests` (the top-level test folders `herd detect` already knows). CI commands are the text after `run:` on single-line `run:` entries; multi-line blocks are recorded as the workflow path only. This reads the repository's files, not the agent's text.

**A2. Read check.** At the first `herd verify`, Herd collects the `file_path` of every Read call in the session logs since `herd init` (same walk as `_edited_files`, subagent logs included), plus every `files[].path` of an `attachment` line of type `instructions` (how Claude Code records the `CLAUDE.md` files it loads itself, spike S4). An `instructions` or `readme` file not in that set is a warning. Reading through Bash (`cat`) is not seen: a known limit, like `preinit`.

**A3. Suite check.** If neither `ci_commands` nor `detect` is empty and no criterion `check` or attack `check` contains one of those commands as a substring, `herd verify` warns once. Substring on commands, not on prose.

**A4. Output.** One summary line in `herd verify` (`ground: 4 files, 1 not read; project suite run`), the details in the report and the PR under Not proven.

### Part B: learning across tasks

**B1. Store.** `<git-common-dir>/herd/lessons.json`, shared by every worktree of the clone, never committed, kept when a worktree is removed (spike S4, item 3). Shape:

```json
{"lessons": [{"id": "L7", "key": "attack:refusal:planner.py", "kind": "attack-failed",
  "text": "refusal attack failed: python3 -m unittest tests.test_refusal", "source": "herd",
  "paths": ["src/planner.py"], "tasks": ["route-v1", "route-v2"], "commit": "abc1234",
  "first": "...", "last": "...", "seen": 2}]}
```

Writes take the same file lock as `git worktree add` (0.3.1), so parallel tasks do not lose lessons. At most 200 lessons; the lowest `seen`, then the oldest, are dropped first.

**B2. Extraction, by code only.** Each kind, its source record and its `key` (the dedupe identity):

| Kind | From | Key | Text |
| --- | --- | --- | --- |
| `attack-failed` | an attack command that failed at any verify before passing (new: `verify` appends failing attack names to `history.json`) | attack name + changed paths | attack name and command |
| `criterion-escalated` | `fails.json` reaching 3 | criterion text hash | the criterion text and check command |
| `review-finding` | hook-recorded review notes, lines starting `Blocker` or `Major` | path in the line | the reviewer's line, quoted |
| `human-change` | `human-change` notes | criterion id + text hash | the human's words |
| `stopped` | `stopped.json` | reason + first problem | reason and problems |
| `guard` | `guard` notes | rule | the rule denied |
| `late-red` | a `late-red` note | task | "code before red first" |
| `open-limit` | `open` notes left at `herd done`, and `known_limits` | text hash | the text, quoted |
| `check-command` | criterion and attack commands passing at `herd done` | command | the command |

The table is fixed in code. Text is copied from the record, never rewritten. Lines starting `Blocker`/`Major` follow the reviewer's own output format (`agents/herd-reviewer.md`), not a word list.

**B3. Intake.** `herd init` writes `lessons.md` in the task folder: up to 10 lessons, one line each (at most 200 characters), with id, source, `seen` and task, and `check-command` lessons listed as "commands that worked here before". It prints `lessons: 10 of 37 for this project, read .herd/tasks/<slug>/lessons.md`. At the first verify, lessons whose `paths` share a folder with the changed files move to the top and the file is rewritten. A2's read check covers `lessons.md` too.

**B4. Recurrence.** When a task adds a lesson whose `key` exists, `seen` goes up and the report and the PR say "recurred: L7 (3rd time)". This count, per project, is the measure of whether learning works (see Not proven).

**B5. Human control.** `herd lessons` lists the store; `herd lessons --drop L7 --reason "..."` removes one and keeps the reason. The guard denies `--drop` while a task is active, so only a session outside a task (the human's) can drop one. Lesson text is shown as data, quoted, with its source: a reviewer's or a past agent's words never become instructions.

### Part C: the Herd graph agent

**C1. Files in the plugin.** `agents/herd-run.md` (knowledge: Herd's hard rules, the writing rules, how to read `ground.json` and `lessons.md`) and `graphs/run.yaml` (control flow), in Collie's format, with a copy of its executor rules and validator shipped in the plugin. Collie is the reference: a graph per job, `check` nodes that route on evidence, gates only a human opens, a `learn` node, sources for every rule. The plugin keeps its own copy of the validator and a test, so it does not depend on Collie.

**C2. The run graph.** The nodes follow the run skill's steps: `stopped` (a `Stopped` record with a `Next`), `ground` (read `ground.json`'s instruction files and `lessons.md`), `route` (quick or standard), `init`, `criteria`, `red`, `gate_high` (gate at high risk), `build`, `break_it`, `review`, `verify`, `pr`, `done`, `report`. Every `check` node names its command, for example `red_ok: {type: check, cmd: "herd verify", expect: "fails", pass: gate_high, fail: criteria}`. The skill keeps only what a graph cannot say, and shrinks by what moves (one of Collie's recurring corrections).

**C3. How a session loads it.** Spike S4 showed a plugin agent can be the main agent. The README says `claude --agent herd:herd-run`, and `herd setup` can offer to write `{"agent": "herd:herd-run"}` into the project's `.claude/settings.json` (asked, never silent). `/herd:run` in a session on the default agent keeps working from the skill.

**C4. Project knowledge is data.** Herd does not write agent files into the user's repository. The per-project part (ground check, lessons) lives in files the graph agent reads at its `ground` node, so the agent definition stays the plugin's, reviewed and versioned, while the project's knowledge grows.

## Order

1. Spike S4 (done).
2. Part B first, built by Collie through its `change.yaml` graph as its first autonomous job (the owner's choice, 2026-11-24). B1 to B5 in one release.
3. Part A, advisory warnings only, after Part B.
4. Part C after A and B, with a benchmark leg: the run graph agent against the run skill, same model, same input.

## Alternatives Considered

| Alternative | Why not, for now |
| --- | --- |
| An agent writes "what I learned" at `herd done` | A claim, not evidence; it can be wrong, flattering or an injection. Records are already there |
| A model summarises the knowledge base at init | Costs tokens every task, and the summary is not checkable. Recording files and checking reads is free |
| Trail Code for shared memory (`docs/backlog.md`) | Node install and machine-wide hooks; unconfirmed CLI. Kept in the backlog |
| Lessons in `.herd/` of the task's worktree | Lost when the worktree is removed; not shared between parallel tasks |
| Writing a project agent `.md` into the user's `.claude/agents/` | Changes the user's repository without asking and forks Herd's rules per project; C4 keeps knowledge as data |

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Lessons pile up and become noise | 10 shown, 200 kept, ranked by recurrence and path; human drop |
| A lesson carries an injected instruction (reviewer or old agent text) | Shown quoted with its source; never changes checks or gates; text copied, not composed |
| Stale lessons about code that changed | Each keeps its commit; paths that no longer exist rank last |
| Read check is gamed by opening files without using them | Accepted: it proves less than reading, more than nothing; listed as a known limit |
| Cost per task | G9: under 50 ms; `lessons.md` under about 600 tokens |
| Parallel tasks write the store at once | File lock, as `git worktree add` already uses |

## Not proven

* That an agent shown lessons repeats fewer mistakes. Measure it: a benchmark of three related tasks in one project, run in order, with the store on and off, 6 runs each, Haiku and Sonnet; compare recurrences (B4), gate blocks, review rounds and hidden-verifier scores, mean and standard deviation.
* That the read check means the agent used what it read.
* That a graph agent follows the run flow better than the skill text; Part C ships only after its benchmark leg.
* That the B2 keys are stable enough across tasks to count a recurrence.

## Context and sources

* The owner's requests for this design: learning from each task "is super important"; Herd "should always use as input the knowledge base available in the repository where herd is working"; the graph agent is the reference for project agents, and users load it to run their tasks instead of a default agent (2026-11-24).
* The graph format: the owner's `blackboard-reviewer` project, which Collie follows.
* Records reused: `notes.jsonl` kinds (`NOTE_KINDS` in `scripts/herd.py`), `fails.json`, `stopped.json`, hook-recorded reviews, `_edited_files` (session-log walk), the worktree file lock (CHANGELOG 0.3.1).
* [`herd-guardrails.md`](herd-guardrails.md) for the hook and guard rules this builds on.
