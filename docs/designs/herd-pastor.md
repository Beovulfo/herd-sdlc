# Herd Pastor: an opt-in graph agent that coordinates Herd agents on your project and learns

* **Author:** Toni
* **Status:** Draft v5, revised after two EGM rounds. Rewritten from v4 (commit c63fb51) on the owner's M4 decisions of 2026-11-24. The agent lives in a kennel repository, never in the product repository. It coordinates headless Herd agents from GitHub, learns for itself through stacked pull requests, files feedback for Herd, and can be driven from a phone. "Changes from v4" lists what v5 drops and why. EGM review round 1 (design, implementation readiness, scope, code accuracy, comprehension) found 3 Blockers and 27 Majors; round 2 (implementation readiness, code accuracy) found 0 Blockers and 13 Majors. This revision answers both. Spike S5 is done, spike S6 is planned, nothing is built. Supersedes Parts B and C of [`herd-project-agent.md`](herd-project-agent.md); its Part A (ground check) stays there.
* **Date:** 2026-11-24
* **Tracking:** issue #33, milestone "M4 Graph agents in Herd", draft PR #25.

--------------------------------------------------------------------------------

## Overview

Herd offers, as an opt-in feature, a **pastor**: a graph agent that works on one project for one human. `herd pastor new` writes it into the human's **kennel**, a git repository of agents with agent-kennel's layout, as `plugins/<name>/`. The product repository gets no file from it.

A new pastor starts from a **baseline**: the setup the owner's agent Collie uses to build Herd (graphs, gates, agent roster, GitHub tracking, milestone reports), written as rules without the owner's private context. From then on it learns from its own human:
* its **Learner** turns the human's corrections into rules in the pastor's agent file, as stacked pull requests the human merges;
* problems it meets in Herd become **customer-feedback** issues on Beovulfo/herd-sdlc.

At work the pastor is a **coordinator**:

1. An Opus session reads the plan from GitHub: the project board, milestones and issues.
2. It spawns headless Sonnet or Haiku sessions with the herd-sdlc plugin, one per issue, in parallel, and passes each one its issue, milestone and context.
3. It accepts a session's work only when Herd's `herd done` evidence and a pull request in the right milestone exist.
4. It reports to its human in the milestone format.
5. It stops for the human at design, merge and release gates.

After setup it runs under Claude Code's Remote Control, so the human can drive it from the Claude mobile app.

**M4** is herd-sdlc's milestone "M4 Graph agents in Herd". It closes when this feature is proven on a new project: the pastor Magpie, made for a new repository Beovulfo/picturebook, passes the acceptance in D9. Picturebook's own product, a visual pull-request review, is Magpie's ongoing work after M4.

The owner's words for the coordinator (2026-11-24): "the way you are working for this porject Collie, is what -i would like the graph agents we want to build next as a feature in herd-sdlc behave --> they are Opus models that control the work and spawn agents in parallel when needed and are able to update on the progress to the human, they should act as kwnoledgable coordinators and pass to the headless agents the right context and plugins. All the coding agents spawn by these graph agents must use herd-sdcl plugin for all the development lifecycle".

Herd's existing rules still apply:
- standard library only, and `gh` is the only external service;
- decisions are made from files, git state, session logs and exit codes, never by matching the agent's wording;
- a hook never breaks the session.

### Terms

Herd's own:
- **Herd task**: one change run by `/herd:run`, kept in `.herd/tasks/<slug>/` on branch `herd/<slug>`. `.herd/active` names the open task and is removed by `herd done`.
- **`evidence.json`**: the result of each success criterion's check, written by `herd verify`. **`evidence.md`**: the report `herd done` writes when it accepts the task.
- **`stopped.json`**: written when a task stops without `herd done`. `herd done` later sets its `resolved_at`; a stop without it is **unresolved**.
- **Guard**: Herd's PreToolUse hook. During a task it denies edits to Herd's files and irreversible commands such as `git push`.
- **Done gate**: the code in `herd done` and the Stop hook that refuses a task whose evidence is missing, stale or failing.

This design's:
- **Graph agent**: an agent whose file holds its knowledge (rules, each with its source) and who follows graphs, YAML files of steps, one node per line. D3 gives the format, from agent-kennel's `graphs/README.md`, which is private.
- **Gate node**: a graph node where the agent stops and asks its human, and goes on only after the human's explicit reply. Not the same as the done gate.
- **Kennel**: a git repository holding graph agents as Claude Code plugins, `plugins/<name>/`, listed in its `.claude-plugin/marketplace.json`. The owner's kennel is agent-kennel. Below, `<kennel>` is the kennel's checkout path and `<market>` the `name` in its `marketplace.json` (`agent-kennel`).
- **Pastor**: a graph agent made by `herd pastor new` for one product repository.
- **Product repository**: the repository the pastor works on; its **checkout** is the local folder of its main working tree.
- **Headless session**: `claude -p "<request>"`, a session with no human, started by the pastor's `bin/spawn`.
- **Spawn record**: the JSON file `bin/spawn` writes for each session (D5).
- **Learner**: the pastor's learning agent, `plugins/<name>/agents/learner.md`.
- **Customer-feedback issue**: an issue on Beovulfo/herd-sdlc with the label `customer-feedback`. The label exists: "Feedback on Herd filed by a graph agent from a user's project".
- **EGM**: the Elephant-Goldfish Model, the design review method of the egm plugin: fresh-context reviewer agents each read the design from one angle.

## Changes from v4

| v4 | v5 | Why |
| --- | --- | --- |
| The pastor is `.claude/agents/<name>.md` in the product repository, shared or local | `plugins/<name>/` in a kennel | The owner: the agent lives in agent-kennel, never in the product repository |
| A SessionStart hook asks on every new session whether to use or create a pastor; an ON/OFF switch silences it | No hook, no switch: nothing happens until the human runs `herd pastor new` | The feature is opt-in. It also removes the only per-session cost Herd added |
| `herd note --correction` records the human's words inside a Herd task | The Learner records corrections in the kennel | The human talks to the coordinator. A headless session has no human messages to quote |
| The lessons store from task records (v4 D5), its guard rules (v4 D6), a committed shared copy | Not in this design; Open Question 1 | The M4 bar does not need them, and the shared copy would put a file in the product repository |
| One `run` graph that replaces `/herd:run` | A `coordinate` graph above Herd; every coding session still runs `/herd:run` | The owner: all coding agents use the herd-sdlc plugin for the whole lifecycle |
| Random pet names | `--name` is required | Every pastor so far was named by its human; one less table in code |

## Problem

* **Coordination is a person's job today.** Collie shows that an Opus coordinator can run several Herd sessions at once and track them in GitHub. It works only in herd-sdlc, for the owner, with rules the owner taught it over three days. Every other project starts from zero.
* **Without code, coordination rules slip.** Collie's `spawn` refuses an issue without a milestone and refuses work that skipped Herd. It was built after the headless session that wrote herd-sdlc PR #28 (a benchmark docs change) committed without `herd init` or `herd done`. A generic agent without that code would repeat the mistake.
* **Herd hears about its problems only from the owner.** When Herd blocks or misleads an agent in another project, nobody files it.
* **Agents do not keep what their human taught them.** Collie's agent file holds rules from the owner's corrections, each with a source. A new agent has no such file and no Learner to keep one.

## Goals

* **G1 Create in the kennel only.** `herd pastor new --name N --kennel DIR --repo OWNER/NAME --checkout PATH` writes `plugins/<N>/` in DIR from the template (D1), and appends `{"name": "<N>", "source": "./plugins/<N>", "description": "<N>, a Herd pastor for OWNER/NAME", "category": "development"}` to `plugins` in DIR's `.claude-plugin/marketplace.json`. PATH is the product's checkout, which may not exist yet. It refuses when:
  * DIR is not a git checkout or has no `.claude-plugin/marketplace.json` (it names the file a kennel needs);
  * DIR is inside PATH, or PATH inside DIR;
  * `plugins/<N>/` exists, or N does not match `[a-z][a-z0-9-]{1,30}`.

  It writes nothing outside DIR. Check: `test_pastor_new_writes_kennel_plugin` (files of D1 and the marketplace entry), `test_pastor_new_writes_nothing_in_product_repo` (the checkout's `git status --porcelain` is empty after the run), `test_pastor_new_refuses_nested`, `test_pastor_new_refuses_existing_name`, `test_pastor_new_refuses_non_kennel`.
* **G2 A baseline from the owner's setup, without the owner's private context.** The template's agent file has D4's sections. Every rule line (a line matching `^\s*[-*] ` under a `## ` section other than `## Learnt rules`) ends with a source tag matching `\[(baseline: [^\]]+|human \d{4}-\d{2}-\d{2}[^\]]*|evidence: [^\]]+)\]$`. The template's text holds none of these: `/Users/`, `/home/`, an email address (`[\w.+-]+@[\w-]+\.[\w.]+`), the word `\bToni\b`, or `Beovulfo` except in `Beovulfo/herd-sdlc`. The template's graphs pass D3's checks. Check: `test_template_rules_have_sources`, `test_template_privacy`, `test_template_graphs_valid`.
* **G3 Setup behind a gate.** The `setup` graph (D3) creates the GitHub side only after `gate_setup`:
  * the repository when it does not exist, with its license, a `CLAUDE.md` with Herd's rules, a CI workflow that runs the checks the human named, and a `herd.toml` with `[pr] open = true` (Herd's `herd pr` opens a pull request only when that is set or `--yes` is given);
  * the clone at the checkout path;
  * the labels and the private project board with D5's fields;
  * the first milestones.

  It writes `owner`, `project` and `checkout` into `plugins/<name>/pastor.json`. Check: `test_template_setup_side_effects_gated`. In the Magpie test: `gh project view <n> --owner Beovulfo --format json` shows D5's fields.
* **G4 Parallel work from the board.** `bin/pick` prints the Queued issues, other than `role:design` ones, whose `Depends on:` issues are all Done and whose `Touches:` paths share no leading path component sequence with a Running issue's (`src/a` and `src/a/b` overlap; `src/a` and `src/ab` do not). The issue body lines match `^Depends on: #\d+(, #\d+)*$` and `^Touches: \S+(, \S+)*$`; an issue without a `Touches:` line overlaps everything. `bin/spawn` starts one headless session per issue (D5). It refuses:
  * an issue without a milestone;
  * an issue already labelled `status:running`, or claimed by another coordinator;
  * a coding or small-fix request that does not start with `/herd:run`;
  * a worktree on the default branch;
  * a worktree whose `.herd/active` names a task, unless the request continues that slug (D5).

  Check: `test_pick_skips_blocked_overlapping_and_design`, `test_spawn_refuses_issue_without_milestone`, `test_spawn_refuses_running_issue`, `test_spawn_refuses_request_without_herd_run`, `test_spawn_refuses_default_branch`, `test_spawn_allows_continuation`, `test_spawn_command_loads_herd`.
* **G5 Accept only Herd-made work.** `bin/spawn check --issue N` finds the worktree and slug in the newest spawn record for N. It exits 0 only when all of these hold:
  * `.herd/tasks/<slug>/evidence.md` exists (written by `herd done`);
  * every result in `evidence.json` is `passing`;
  * `stopped.json` is absent or has `resolved_at`;
  * `.herd/active` does not name the slug;
  * a pull request from `herd/<slug>` exists and its body says `Closes #N`;
  * at least one CI check ran on it and all passed. While any check is still pending, it exits 3 and changes nothing; the coordinator's `wait` node runs it again every 5 minutes, and after 60 minutes pending counts as a failure.

  On success it then sets the pull request's milestone to the issue's (`gh pr edit --milestone`), makes it a draft (`gh pr ready --undo`), fills the spawn record's end time and cost, and sets the issue to Review. Herd's `herd pr` opens a ready PR with no milestone, so this step is code. On failure it sets the issue to Blocked and comments why. Check: `test_spawn_check_finds_slug_from_record`, `test_spawn_check_needs_herd_done`, `test_spawn_check_needs_closes_line`, `test_spawn_check_refuses_no_ci`, `test_spawn_check_sets_milestone_and_draft`.
* **G6 Milestone reports from data.** `bin/report` prints one block per open milestone from `gh` data, in D5's format. The coordinator prints it after every `spawn check`, passed or failed, at every gate, and when the human types `status`; never on a timer. Check: `test_report_milestone_blocks` (D5's fixture to D5's example, byte for byte), `test_report_names_every_pr`.
* **G7 The human decides design, merge, release and feedback.** In the template's graphs, every node that merges, tags, releases, opens a learning pull request or files an issue on another repository has `side_effect: true` and is reached only through a gate. A design runs as an Opus side session that stops at its own gate and returns the question. Check: `test_template_graphs_valid` (D3 rule 5), `test_template_external_actions_gated` (every node whose `does` names `merge`, `tag`, `release`, `bin/feedback --file` or `bin/learn-pr` has `side_effect: true`; the check reads the template's own text, written by Herd).
* **G8 Learning for itself, as stacked pull requests.** `bin/learn-check --base B` exits 0 only when, for the diff from B to the working tree:
  * it touches only `plugins/<name>/agents/<name>.md`, `plugins/<name>/graphs/*.yaml` and `plugins/<name>/.claude-plugin/plugin.json`;
  * `plugin.json`'s `version` is higher than at B, so installed copies update;
  * every graph passes D3's checks;
  * every added rule line in the agent file ends with a source tag;
  * every quoted phrase (text in double quotes) in an added agent-file line is found in a message the human typed (D7).

  `bin/learn-pr --topic T --start` creates a worktree `<kennel>/runs/<name>/learn/<T>` on a new branch `learn/<T>`, and the Learner edits only there, so the kennel's own checkout, which the pastor reads live, never changes branch. `bin/learn-pr --topic T` then runs `learn-check --base <base>` in that worktree, commits, and pushes. The base is the newest open learning branch (the open kennel pull request with a `learn/` head that was created last), or from `main` when none is open. It opens a pull request whose base is that branch, so learning pull requests stack; each bumps `plugin.json`'s version from its own base, so they merge in order without conflict. It refuses to push `main`, to force-push, or to merge: the human merges the stack. Check: `test_learn_check_allowed_paths`, `test_learn_check_needs_version_bump`, `test_learn_check_needs_source_tag`, `test_learn_check_quote_must_be_typed`, `test_learn_check_rejects_peer_and_tool_text`, `test_learn_pr_stacks_on_newest_open`, `test_learn_pr_from_main_when_none_open`, `test_learn_pr_never_pushes_main`.
* **G9 Learning for Herd.** `bin/feedback --draft --issue N` builds a customer-feedback issue body from Herd's records only (D8); `bin/feedback --file --issue N` rebuilds the same body and files it. The body has the literal lines `filed-by: <name>` and `feedback-key: <key>`. It holds no file content, diff or path from the product repository except `.herd/tasks/<slug>/` record names. `--file`, after `gate_feedback`, runs `gh issue list -R Beovulfo/herd-sdlc --label customer-feedback --state open --search "feedback-key: <key>"`. It comments on a match, or opens a new issue with the label. Check: `test_feedback_body_from_records_only`, `test_feedback_body_has_filed_by_and_key`, `test_feedback_dedups_by_key`, `test_feedback_label_and_repo`.
* **G10 No cost for those who do not opt in.** No new hook and no change to what `herd done` accepts. `herd pastor new` is the only new Herd command. Check: `test_hooks_unchanged` (the hook events and commands in `hooks/hooks.json` equal 0.12.1's), and the existing suite passes.
* **G11 Drive it from a phone.** The last step of `setup`, after its gate, starts `claude remote-control --name <Name> --spawn same-dir --permission-mode <mode> --settings <kennel>/plugins/<name>/remote.json`, detached, in the product's checkout. The human then drives the pastor from the Claude mobile app or claude.ai/code, and the terminal session that ran `setup` ends.
  * `herd pastor new` writes `remote.json`: settings that make a new Remote Control session open as the pastor with the herd-sdlc and kennel plugins loaded. Which keys do that is not verified (spike S6, item 4), and the build does not rely on them before the spike passes.
  * The permission mode is the human's choice at `gate_setup`, with `default` proposed.
  * `setup` writes the server's PID and the reattach command (`claude remote-control -c`, in the same folder) into run state.

  Check: `test_pastor_new_writes_remote_settings` (blocked on S6 item 4), `test_template_remote_start_gated`. In the Magpie test: a session named `Magpie` is listed in the app, and asked "who are you?" it answers as Magpie and names `herd` among its plugins.
* **G12 The Magpie test meets the M4 bar** (CUJ 6, D9). Check: `examples/pastor-m4/accept.py --kennel K --name magpie --repo Beovulfo/picturebook` exits 0 only when each line of D9's acceptance table holds, and prints the evidence for each. Its own tests, `test_accept_m4_*`, run it on fixture spawn records, session logs and `gh` output.

## Non-Goals

* Putting any agent file, graph, lesson or run state in the product repository.
* Enforcing the graph. The pastor follows it as text. What is enforced is code: `bin/spawn`, `bin/spawn check`, `bin/learn-check`, `bin/learn-pr`, Herd's done gate and guard.
* Fetching the template from agent-kennel, which is private. The template ships in the herd-sdlc plugin.
* Creating a kennel. `herd pastor new` needs an existing one.
* Upgrading an existing pastor when the template changes. `pastor.json` records the template version for a later version to compare.
* Lessons learnt from Herd's task records (v4 D5). See Open Question 1.
* Designing picturebook's product here. Magpie designs it in picturebook, through its own design gate (CUJ 6). D9 only seeds its first milestone.

## Open Questions

1. Should v4's lessons store (lessons from Herd's task records, shown at `herd init`) come back as its own design after M4, without the committed shared copy? Default: yes, as a separate design that works for any agent.
2. The M4 bar says the human gets reports "without asking", while Collie's rule since 2026-11-24 is to report only when the owner types `status`. G6 reports on events (each accepted or refused session, each gate) and on `status`, never on a timer. Is that the intended meaning? Default: yes.
3. The M4 bar needs at least one customer-feedback issue, which needs a real Herd problem in Magpie's run. If none happens, should M4 wait for one, or count a recorded run with no Herd problem? Filing feedback only to meet the bar is not allowed. Default: report it at the gate and let the owner decide.
4. Should `bin/feedback` file without a gate under a standing approval? Default: no. The body goes to a public repository and may describe a private project.
5. The agent file and `pastor.json` hold the kennel's absolute path, which a public kennel would publish. Default: allowed; a kennel is expected to be private.

### Decided by the owner (2026-11-24)

* The feature is opt-in. The agent lives in agent-kennel (`plugins/<name>/`, with its own Learner and run state), never in the product repository.
* The baseline comes from the owner's projects: Collie's setup.
* Two kinds of learning: for itself (Learner), and for Herd (customer-feedback issues on Beovulfo/herd-sdlc, label `customer-feedback`).
* The coordinator is an Opus session that plans from GitHub and spawns headless Sonnet or Haiku agents with the herd-sdlc plugin, one per issue. It reports in the milestone format and stops at design, merge and release gates.
* The first test is Magpie, for Beovulfo/picturebook: public, MIT, herd-sdlc's rules, its own private project "Picturebook". Its first priority, P1, is a visual pull-request review (D9).
* Learnings reach the kennel as stacked pull requests the human merges, for every graph agent and its Learner: "I approve the commit, next time create stacked PRs and i will merge them, lets make this the normal flow to update learnings with any graph agent, (include it in the PASTOR design)" (the owner, relayed verbatim by Collie, 2026-11-24 15:35 UTC). This replaces direct pushes to the kennel's `main`. Collie's own setup follows it since agent-kennel commit 1a7e442. G8.
* M4's scope: "the idea is that magpie will keep working on the Picture Book and you will close M4 as soon as you proof that Pastor can work on new projects and magpie works correctly with herd-sdlc" (relayed verbatim by Collie, 15:50 UTC). M4 closes on D9's acceptance. Picturebook's product bars are Magpie's ongoing work. After M4, Collie fixes the pastor feature only from Magpie's customer-feedback issues.
* Remote Control after setup: "is it possible to incliude in the pastor design that when you create and setup the first time to Magpie, then you spawn a headless session with RC (remote control) so i can control it thorugh my cellphone?" (relayed verbatim by Collie, 15:45 UTC). G11.

## Critical User Journeys (CUJs)

### CUJ 1: A human creates a pastor

* **Given**: Herd is installed. The human has a kennel checkout at `~/kennel` and a product repository `acme/shop` cloned at `~/shop`.
* **When**: The human runs `herd pastor new --name juniper --kennel ~/kennel --repo acme/shop --checkout ~/shop`.
* **Then**: Herd writes `~/kennel/plugins/juniper/` and a `juniper` entry in the marketplace. It prints the next steps: commit the kennel, `claude plugin marketplace add ~/kennel` (once per kennel), `claude plugin install juniper@<market>`, then `claude --agent juniper:juniper` in `~/shop`. `git status` in `~/shop` is empty. Test: `test_pastor_new_writes_kennel_plugin`, `test_pastor_new_writes_nothing_in_product_repo`.

### CUJ 2: The first session sets up GitHub

* **Given**: Juniper is installed at user scope (the default of `claude plugin install --scope`), and `pastor.json` has no board yet.
* **When**: The human starts `claude --agent juniper:juniper` in `~/shop` and gives a goal.
* **Then**: Juniper runs `setup`. At `gate_setup` it shows the labels, the board and its fields, the CI workflow, the milestones it proposes (each named by its outcome, with a measurable bar), and the Remote Control permission mode. On the human's yes it creates them, starts Remote Control, and ends the terminal session. Test: `test_template_setup_side_effects_gated`.

### CUJ 3: Two issues in parallel

* **Given**: The board has issues #4 and #5 Queued in milestone "M1 Checkout works offline", with no dependency between them and disjoint `Touches:` paths.
* **When**: Juniper reaches `pick` in `coordinate`.
* **Then**:
  1. `bin/pick` prints both.
  2. `bin/spawn coding --issue 4 ...` and `bin/spawn small-fix --issue 5 ...` start two headless sessions, each in its own worktree with the herd-sdlc plugin, and set both issues to Running with Session and Branch filled.
  3. Juniper waits on the two PIDs and keeps answering the human.
  4. When #4's session ends, `bin/spawn check --issue 4` finds `evidence.md`, passing evidence, PR #6 from `herd/offline-cache` with `Closes #4`, and green CI. It puts PR #6 in M1 as a draft and sets #4 to Review.
  5. Juniper prints `bin/report`.

  Test: `test_pick_skips_blocked_overlapping_and_design`, `test_spawn_check_sets_milestone_and_draft`.

### CUJ 4: A session fails in Herd, and Herd hears about it

* **Given**: #5's session ended without `herd done`. Its `notes.jsonl` holds a `guard` note: the guard denied a write the task needed, and `stopped.json` says the task stopped.
* **When**: `bin/spawn check --issue 5` exits 1 and sets #5 to Blocked. Juniper prints `bin/report`.
* **Then**:
  1. At `triage` Juniper quotes the `guard` note and judges that Herd caused it.
  2. `bin/feedback --draft --issue 5 --record guard:1` prints a body with the Herd version and the denied command, taken from the task's `guard` note.
  3. At `gate_feedback` the human says yes. `bin/feedback --file` opens a `customer-feedback` issue on Beovulfo/herd-sdlc, or comments on the open one with the same key.
  4. Juniper sends #5 again with a sharper request that continues slug `export`, at most twice.

  Test: `test_feedback_body_from_records_only`, `test_feedback_dedups_by_key`, `test_spawn_allows_continuation`.

### CUJ 5: The human corrects the pastor

* **Given**: During the run the human types "always put the issue number in the branch name". An earlier learning pull request from `learn/report-format` is still open.
* **When**: Juniper sends the correction to its Learner.
* **Then**:
  1. The Learner adds the rule `Put the issue number in the branch name: "always put the issue number in the branch name" [human 2026-11-24]` to `juniper.md` and bumps `plugin.json`'s version.
  2. `bin/learn-check` finds the quote in a line the human typed, and passes.
  3. At `gate_learn` the human approves. `bin/learn-pr --topic branch-names` commits on `learn/branch-names`, cut from `learn/report-format`, and opens a kennel pull request based on it.
  4. The human merges the stack. Sessions started after the merge and a `claude plugin update` have the rule.

  Test: `test_learn_check_quote_must_be_typed`, `test_learn_pr_stacks_on_newest_open`.

### CUJ 6: The Magpie test

* **Given**: The owner's kennel is agent-kennel. Beovulfo/picturebook does not exist yet.
* **When**: The owner runs `herd pastor new --name magpie --kennel ~/Documents/beovulfo/agent-kennel --repo Beovulfo/picturebook --checkout ~/Documents/beovulfo/picturebook`, commits and installs it, runs `claude` once in an empty `~/Documents/beovulfo/picturebook` folder to trust it, and starts Magpie there with the goal "P1 Visual PR review".
* **Then**:
  1. Magpie's `setup` creates, at its gate, the public repository (MIT, a `CLAUDE.md` with herd-sdlc's Rules, CI), the clone, and the private project "Picturebook". It then moves to Remote Control.
  2. From the phone, Magpie designs P1 through a design side session and stops at `gate_design`.
  3. After the owner approves, it runs at least two issues in parallel and reports.
  4. It files any Herd problem as feedback and opens a learning pull request with what the owner taught it.
  5. `examples/pastor-m4/accept.py` passes (D9).

## Design

### D1. Where things live

| Path | Holds | Written by |
| --- | --- | --- |
| `<kennel>/plugins/<name>/.claude-plugin/plugin.json` | `{"name": "<name>", "version": "0.1.0", "description": ...}`; the plugin name makes the agent `<name>:<name>` | `herd pastor new`; the Learner bumps `version` |
| `<kennel>/plugins/<name>/agents/<name>.md` | the pastor's knowledge: baseline rules (D4), then learnt rules | `herd pastor new`, then the Learner |
| `<kennel>/plugins/<name>/agents/learner.md` | the Learner (D4) | `herd pastor new` |
| `<kennel>/plugins/<name>/graphs/{setup,coordinate,design}.yaml` | the control flow (D3) | `herd pastor new`; graph fixes by the Learner |
| `<kennel>/plugins/<name>/bin/{spawn,pick,report,feedback,learn-check,learn-pr}` | the code that enforces the coordination rules | `herd pastor new` |
| `<kennel>/plugins/<name>/pastor.json` | `{"name", "repo", "checkout", "owner", "project": <board number or null>, "kennel": <path>, "template": 1}` | `herd pastor new`, then `setup` |
| `<kennel>/plugins/<name>/remote.json` | the settings Remote Control starts new sessions with (G11) | `herd pastor new` |
| `<kennel>/runs/<name>/state.json` | run state: `{"graph", "at_node", "path", "nodes", "waiting": {"gate", "question", "issue", "session_id"} or null, "remote": {"pid", "reattach"} or null}` | the pastor after every node; `bin/spawn check` fills `waiting`; `setup` fills `remote` |
| `<kennel>/runs/<name>/spawn/`, `learn/` | spawn records and session logs; learning worktrees. All of `runs/` is git-ignored by the kennel | `bin/spawn`, `bin/learn-pr` |
| the product's checkout and worktrees | its code, `CLAUDE.md`, CI, and Herd's `.herd/` task folders as today | `setup` once, then the headless Herd sessions |

The template lives in the herd-sdlc plugin as `templates/pastor/`. `herd pastor new` copies it and fills `{name}`, `{repo}`, `{kennel}`, `{checkout}` and the Herd version with `string.Template`. The `bin/` scripts are Python standard library only, like Herd, and read every machine- or person-specific value from `pastor.json`: owner, kennel and checkout. Each script has the kennel path filled in as a constant and always reads `{kennel}/plugins/<name>/pastor.json` and `{kennel}/runs/<name>/`, never paths relative to itself, because the installed copy in the plugin cache can be stale. The agent file tells the pastor to call `{kennel}/plugins/<name>/bin/<script>`. Collie's `spawn` hard-codes its GitHub account and kennel path; the template does not. Their tests live in herd-sdlc, in `tests/test_pastor_template.py`, with a fake `gh` on `PATH`, because the template ships with Herd.

The pastor is started with `claude --agent <name>:<name>` in the product's checkout, or by Remote Control (G11). The agent file names its kennel checkout by absolute path. Claude Code runs the installed copy from its plugin cache, which can be older than the kennel (agent-kennel's `graphs/README.md`, rule 7), so the pastor reads its live files from the kennel.

### D2. Herd's side

* `herd pastor new` (G1) is a subcommand in `scripts/herd.py`, about 80 lines: argument checks, the copy, the marketplace entry. It needs no task and touches no Herd state.
* `templates/pastor/` ships in the plugin folder.
* `examples/pastor-m4/accept.py` is the M4 acceptance script (D9). It is not part of the template, because only M4 needs it.
* No hook, no change to `herd done` or the guard (G10).

### D3. Graph format, checks and the template's graphs

The format is agent-kennel's. Each graph is a YAML file with `name`, `start` and `nodes`, one node per line, `  <id>: {type: ..., does: "...", <edge>: <id>, ...}`. Types:
* `act` does one thing, `think` is a judgment;
* `check` has `pass` and `fail` edges;
* `gate` has `approve`, `edit` and `skip` edges, and an optional `standing` field that only the human adds;
* `sub` runs another graph, `end` reports.

Other keys are `max`, the loop bound (default 2), `on_exhausted`, `side_effect: true`, `parallel` (independent reads a node may do at once) and, for `sub`, `graph`. Two rules are the pastor's own, not agent-kennel's: at a gate whose question offers numbered options, the human's reply is carried into the next node as the human's own words, and `approve` means "go on with the chosen option".

The checks, from agent-kennel's `graphs/validate.py` (61 lines), which the template copies into `bin/` as part of `learn-check`:
1. `start` names a node.
2. Every edge names a node.
3. Every type is one of the six.
4. On each node line, the counts of `{` and `}` match.
5. A `side_effect: true` node is entered only from a gate, from another side-effect node, or through a check's `fail` edge (a retry of the same approved action).
6. Every node is reachable, and an `end` node is reachable.

The rules the pastor follows as text: start at `start` and never skip or reorder nodes; write run state after every node; at a gate, stop for the human's explicit reply. A design side session saves the gate as `waiting`, ends, and returns its question as its final message. `bin/spawn check` copies that question from the session's `result` line into the coordinator's run state, so the side session never writes into the kennel.

`coordinate.yaml`. It passes checks 1 to 6, run with agent-kennel's `validate.problems`.

```yaml
name: coordinate
start: ground
nodes:
  ground:        {type: act, does: "Read this agent file, pastor.json, bin/report, open PRs and runs/<name>/; resume an unfinished run", next: plan}
  plan:          {type: think, does: "Turn the request into issues, each in a milestone and on the board, with Depends on: and Touches: lines; no work without an issue", next: design_needed}
  design_needed: {type: check, does: "A Queued issue labelled role:design has no approved design", pass: design, fail: pick}
  design:        {type: act, does: "bin/spawn design --issue N; the Opus side session runs design.yaml and returns its gate question", next: gate_design}
  gate_design:   {type: gate, ask: "Approve the design before code? (doc link, open findings) On skip the issue is set Blocked", approve: pick, edit: design, skip: report}
  pick:          {type: act, does: "bin/pick: Queued issues, not role:design, whose dependencies are Done and whose Touches: overlap no Running issue", next: spawn}
  spawn:         {type: act, does: "bin/spawn coding|small-fix --issue N for every picked issue at once; each request starts with /herd:run and carries the issue, milestone and context", next: wait}
  wait:          {type: act, does: "Wait on the PIDs bin/spawn printed, in the background; answer the human meanwhile; take finished sessions one at a time", next: accept}
  accept:        {type: check, does: "bin/spawn check --issue N exits 0 for this finished session", pass: report, fail: report_refused}
  report_refused: {type: act, does: "Print bin/report", next: triage}
  triage:        {type: think, does: "Is the cause the issue, the request, or Herd? Quote the record that shows it", next: herd_cause}
  herd_cause:    {type: check, does: "triage quoted a Herd record (a herd exit code, stopped.json, a guard denial) as the cause", pass: feedback, fail: retry}
  feedback:      {type: act, does: "bin/feedback --draft --issue N builds the issue body from Herd's records", next: gate_feedback}
  gate_feedback: {type: gate, ask: "File this customer-feedback issue on Beovulfo/herd-sdlc? (body shown)", approve: file_feedback, skip: retry}
  file_feedback: {type: act, side_effect: true, does: "bin/feedback --file --issue N --record R: a new issue, or a comment on the open one with the same key", next: retry}
  retry:         {type: check, does: "The refused issue can run again with a sharper request", pass: spawn, fail: gate_stuck, max: 2, on_exhausted: gate_stuck}
  gate_stuck:    {type: gate, ask: "One question with 2 or 3 numbered options", approve: pick, skip: report}
  report:        {type: act, does: "Print bin/report", next: more}
  more:          {type: check, does: "This request's milestones have Queued or Running issues", pass: pick, fail: gate_merge, max: 20, on_exhausted: gate_merge}
  gate_merge:    {type: gate, ask: "Merge these PRs? Each has green CI and accepted evidence; default no", approve: merge, skip: gate_release}
  merge:         {type: act, side_effect: true, does: "Merge the approved PRs one by one, updating the next branch each time; set their issues Done", next: gate_release}
  gate_release:  {type: gate, ask: "Tag and release? Version and changelog shown; default no", approve: release, skip: learn}
  release:       {type: act, side_effect: true, does: "Tag and publish the approved release", next: learn}
  learn:         {type: act, does: "Send every correction and weak point of this run to the Learner; it drafts the change and runs bin/learn-check", next: gate_learn}
  gate_learn:    {type: gate, ask: "Open a learning PR in the kennel with these changes? (diff shown)", approve: learn_pr, skip: close}
  learn_pr:      {type: act, side_effect: true, does: "bin/learn-pr --topic T: commit on learn/T cut from the newest open learning branch or main, push it, open a PR stacked on that base; never push main, never merge", next: close}
  close:         {type: end, does: "Path taken; issues, PRs and milestones; feedback filed; learning PRs; what is not verified"}
```

`setup.yaml`:

```yaml
name: setup
start: ground
nodes:
  ground:        {type: act, does: "Read pastor.json, gh auth status, whether the repository and the checkout exist, and the human's goal", next: propose}
  propose:       {type: think, does: "Propose labels, board fields (D5), CI checks, milestones named by outcome with a measurable bar, and the Remote Control permission mode (default proposed)", next: gate_setup}
  gate_setup:    {type: gate, ask: "Create these on GitHub and start Remote Control? (everything listed)", approve: create, edit: propose, skip: close}
  create:        {type: act, side_effect: true, does: "Create the repository if missing (license, CLAUDE.md, CI), clone it to the checkout, labels, board, fields, milestones; write owner, project and checkout to pastor.json", next: remote}
  remote:        {type: act, side_effect: true, does: "Start claude remote-control detached in the checkout with remote.json; write its PID and the reattach command to run state", next: created}
  created:       {type: check, does: "gh repo view, gh project view and gh api milestones show what was approved, and the Remote Control PID is alive", pass: close, fail: create, max: 2, on_exhausted: close}
  close:         {type: end, does: "What exists now, with links; the Remote Control session name; end this terminal session"}
```

`design.yaml`, run by the design side session in the issue's worktree:

```yaml
name: design
start: ground
nodes:
  ground:        {type: act, does: "Read the issue, its milestone, the product's CLAUDE.md, docs/designs/ and open PRs", next: design}
  design:        {type: think, does: "Write docs/designs/<slug>.md: Overview, Problem, Goals each with a named check, Non-Goals, Open Questions, CUJs, Design, Alternatives, Risks, Not proven", next: review}
  review:        {type: act, does: "Fresh-context review with the EGM reviewers when the egm plugin is loaded, otherwise one reviewer agent; list Blocker, Major, Nit", next: review_ok}
  review_ok:     {type: check, does: "No Blocker or Major left and every goal has a named check", pass: commit, fail: design, max: 2, on_exhausted: commit}
  commit:        {type: act, does: "Commit the design on the issue's branch, locally; no push", next: gate_design}
  gate_design:   {type: gate, ask: "Approve this design? (the doc's text, open findings)", approve: push, edit: design, skip: close}
  push:          {type: act, side_effect: true, does: "Push the branch and open a draft PR in the issue's milestone saying Closes #N", next: close}
  close:         {type: end, does: "On a gate: save it as waiting and return its question as the final message; otherwise report the PR"}
```

The side session first returns at `gate_design` with the design's text. The coordinator shows it to the human and resumes the same session with the human's exact words, as agent-kennel's rule for side sessions says, through `bin/spawn design --issue N --resume <session_id> --request FILE` (`claude -p --resume <session_id>`, the id taken from `waiting` in run state); on a yes the session pushes and opens the draft pull request.

### D4. The baseline

The template's agent file holds the sections below. Each rule ends with `[baseline: collie 2026-11-24]` and states the rule in plain words, with no quote from the owner's sessions. The owner's quotes stay in the private kennel, in Collie's file.

* **How you run:** the graphs and their rules (D3); read your live agent file in `{kennel}` first.
* **Hard rules:**
  * never work on the default branch;
  * draft pull requests only, each in its milestone;
  * never merge, tag or release without the human's words in this session;
  * never run blocking work in your own session: spawn it or run it in the background;
  * the coordinator runs on Opus and hands bounded work to Sonnet or Haiku;
  * evidence before claims: quote the command output;
  * do exactly what was asked;
  * no credentials or private data in any file.
* **Coordination:** GitHub is the plan, with no plan kept elsewhere. No work starts without an issue in a milestone and on the board. Each spawned request names its issue, milestone and impact. Wait on PIDs, never on process names. One coordinator at a time: after `setup`, that is the Remote Control session.
* **Reports:** `bin/report`, on events and on `status` only.
* **Roster:** D5.
* **Learning:** send each correction and weak point to the Learner at once. Rules come only from the human's typed words or from quoted evidence. Learnings go out through `bin/learn-pr` as stacked kennel pull requests; never push the kennel's `main`, never merge.
* **Herd feedback:** when a refused session's records show Herd as the cause, draft a customer-feedback issue.
* **Learnt rules:** empty at creation; the Learner fills it.

`learner.md` is Collie's Learner with the pastor's name and paths. Its remit: write rules into the pastor's file, fix weak points in the pastor's graphs, bump `plugin.json`'s version, and open every change through `bin/learn-pr`. A graph fix passes D3's checks in `learn-check` and the human's review of the pull request. A rule from session evidence instead of the human's words carries `[evidence: <what>]` and no quote.

### D5. Roster, spawning, board and reports

| Role | Model | Started by | For |
| --- | --- | --- | --- |
| coordinator | Opus | the human: `claude --agent <name>:<name>`, then Remote Control | plans, decides, gates, reports |
| design | Opus | `bin/spawn design`: the same agent in a side session | designs; returns at its gate |
| coding | Sonnet + Herd | `bin/spawn coding` | any change to the product |
| small-fix | Haiku + Herd | `bin/spawn small-fix` | one or two files, low risk, no design |
| research | Sonnet | the Agent tool, read-only | analysis before a decision; Agent-tool subagents cannot load plugins, so they never develop |

**`bin/spawn coding|small-fix|design --issue N --request FILE [--worktree DIR] [--slug S] [--design] [--budget USD] [--resume ID]`.**
* Without `--worktree`, it creates one: `git -C <checkout> worktree add --detach <checkout>/.claude/worktrees/<issue>-<role> origin/<default>`, after `git fetch`, where `<default>` is `gh repo view --json defaultBranchRef`. `herd init` then makes `herd/<slug>` from there. With `--worktree`, the worktree is a continuation's.
* The request comes from FILE. A coding or small-fix request starts with `/herd:run`, and its goal line ends with `Closes #N`, because `herd pr` puts the `herd init` goal in the PR body. `bin/spawn` adds a header naming the issue, its milestone and the milestone's description.
* A continuation passes `--slug S`, and the request names S. When `.herd/active` in DIR names S, the request must not ask for `herd init`, which refuses an existing task; when DIR is on a new `herd/S` branch with no task yet, it must contain `herd init S`. A design session is refused in a worktree with an active task. These are Collie's rules.
* The command line is Collie's: `claude -p "<request>" --model <claude-sonnet-5-5 | claude-haiku-5-5 | claude-opus-5-5> --plugin-dir <herd> [--plugin-dir <egm> for role design or --design] --setting-sources project --permission-mode dontAsk --allowedTools "Bash,Read,Write,Edit,MultiEdit,Glob,Grep,Agent,Skill" --max-budget-usd <budget> --output-format stream-json --verbose`. The design role adds `--agent <name>:<name>` and puts `--plugin-dir <kennel>/plugins/<name>` first, so the side session runs the live pastor.
* Default budgets are Collie's: coding 15, small-fix 3, design 20 USD.
* `<herd>` is the highest version folder under `~/.claude/plugins/cache/*/herd/` whose `.claude-plugin/plugin.json` has `"name": "herd"`, compared by number; `<egm>` the same under `*/egm/`. With no herd, `bin/spawn` refuses and says to install herd-sdlc. Unlike Collie's, which reads only `cache/herd-sdlc/herd/`, this works for any marketplace name.
* It starts the process detached (`subprocess.Popen` with `start_new_session=True`, stdin from `/dev/null`), as Collie's does. Output goes to `runs/<name>/spawn/<issue>-<role>-<stamp>.jsonl`, errors to `.err` (Collie's names the file by slug or worktree).
* It writes the spawn record `runs/<name>/spawn/<issue>-<stamp>.json`: `{"issue", "role", "model", "worktree", "slug", "pid", "log", "started", "herd": <version>}`. `spawn check` adds `ended` (the log's last line time), `cost` (`total_cost_usd` from the stream's final `result` line), `session_id` (from the same line) and `check` (exit code and reasons). The record is new in the pastor; Collie's `spawn` labels the issue, sets board fields, comments and prints an info line, but writes no record file.
* It refuses a worktree on the default branch (Collie's refuses only `main`).
* It sets the issue to Running, with Session (PID and log path) and Branch.

When the session gave no `--slug`, `spawn check` takes the slug from the worktree: the one `.herd/tasks/*` folder whose `herd/<slug>` branch is the worktree's current branch.

**Board fields** (Collie's): Status (Queued, Running, Blocked, Review, Done), Role, Model, Branch, Session, Progress (percent), ETA (text, set by the coordinator, an estimate) and Size (a number from 1 to 10, set at `plan`). Issues carry the labels `status:*`, `role:*` and `claimed-by:<name>`. `bin/spawn` sets Running, `spawn check` sets Review or Blocked, the merge sets Done.

**Report format.** For this fixture (the `gh` JSON in `tests/fixtures/pastor/report.json`): milestone "M1 Checkout works offline", description "Bar: the cart survives 10 offline reloads", issues #4 (Review, Size 6, PR #6 draft), #5 (Blocked, Size 2, no PR, branch `herd/export`) and #7 (Queued, Size 4, ETA "~20 min"). `bin/report` prints:

```text
M1 Checkout works offline
   Bar: the cart survives 10 offline reloads
   [####------]  1 of 3 in review or done
   ✓ #4 Cache the cart        ##################  PR #6 draft
   ✗ #5 Export orders         ######              no PR yet: herd/export
   ⏸ #7 Retry on reconnect    ............        ~20 min (estimate)
   ⚠ #5 blocked: evidence.md (written by `herd done`)
```

* The state marks are text symbols: U+2713 Review or Done, U+25B6 Running, U+23F8 Queued, U+2717 Blocked, U+26A0 the risk line.
* The bar has 3 cells per Size point, at least 5 and at most 30: `#` for an issue in Review or Done, `.` for Queued, and Progress percent of `#` for Running.
* The milestone bar has 10 cells, filled by issues in Review or Done over all issues.
* A pull request shows as `PR #n draft`, `PR #n open` or `PR #n merged <7-character SHA>`.
* Running and Blocked bars are filled by the Progress percent, rounded down (#5 has Progress 100).
* The milestone bar rounds up (1 of 3 fills 4 cells).
* Issue titles are padded to the longest title in the block plus 2 spaces, and bars to 30 plus 2.
* `spawn check` comments on a refusal as `spawn check: <slug> refused: <reason>; <reason>`. The risk line is `#<n> blocked: <first reason>`.
* Fixture shape: `{"milestones": [{"number", "title", "description", "issues": [{"number", "title", "status", "size", "progress", "eta", "branch", "prs": [{"number", "state", "isDraft", "mergeCommit"}], "last_check"}]}]}`, the result of the one GraphQL query plus `gh pr list`. The expected output is `tests/fixtures/pastor/report.txt`.

### D6. Code-enforced versus text rules

| Rule | Enforced by |
| --- | --- |
| No work without an issue in a milestone | `bin/spawn` refuses |
| Coding sessions use Herd | `bin/spawn` refuses a request without `/herd:run` and always passes the herd-sdlc `--plugin-dir` |
| Accept only Herd-made work, in the milestone, as a draft | `bin/spawn check` (G5) |
| No two sessions on one task or on files one owns | `bin/pick` (`Touches:`), `bin/spawn` (Running issues, `.herd/active`) |
| Learnt rules only from the human's words or evidence, via a stacked PR | `bin/learn-check`, `bin/learn-pr` (G8) |
| Feedback carries records, not product content | `bin/feedback` builds the body (G9) |
| Merge, release, feedback and learning PRs need the human | gate nodes, and D3 check 5 in `test_template_graphs_valid`. The graph is followed by the agent as text |
| Report format | `bin/report` |
| Report timing (events, `status`) | text only: no hook can tell an event from idle time. `accept.py` measures it for M4 |
| One coordinator at a time | text only; `bin/spawn`'s Running and claimed-by refusals stop two coordinators from taking the same issue |

The `Depends on:` and `Touches:` lines are fields that `plan` writes into issues in a fixed format, read by a fixed pattern. They are the pastor's own data format, not a reading of its wording.

### D7. The quote check

A quoted phrase counts when it is found in a message the human typed, compared the way Herd's verbatim rule compares (`_squash` and `_quotes` in `scripts/herd.py`: NFKC, case-folded, punctuation and markup removed, whole words only), in a session log of this product: `~/.claude/projects/<folder>/*.jsonl`. Claude Code names `<folder>` after the checkout's absolute path; the exact encoding is to be confirmed by spike S6 item 5. `<system-reminder>` blocks are removed before comparing.

A line counts as the human's when it is one of:
* a `user` line with `origin.kind` equal to `human` (from v4's D8 research; unverified until S6 item 5), or with `promptSource` equal to `queued` (Collie's Learner);
* an `attachment` line of type `queued_command` with `origin.kind` equal to `human`;
* a `queue-operation` line with `operation` equal to `enqueue`: a message typed while the agent was working, as Collie's Learner found (`learner.md`, agent-kennel).

Lines from peer sessions, task notifications and tool results never count, and neither do headless `claude -p` logs, where the pastor's human never types. A phone message through Remote Control must count; whether it is logged as one of these shapes is S6 item 5.

These shapes come from v4's D8 research on Claude Code 2.1.330 (a desktop session's log and `claude -p`) and from Collie's Learner. Herd's code does not read them today; its verbatim rule for human criteria (CHANGELOG 0.10.0, `human_unquoted` in `scripts/herd.py`) compares against `request.md` and `human-change` notes. `learn-check` reuses only its comparison.

### D8. Feedback body and cost

**Feedback body.** `bin/feedback --draft --issue N` reads issue N's newest spawn record and, in its worktree, `.herd/tasks/<slug>/`: `stopped.json` (`reason`, `detail`, `problems`), the `guard` notes in `notes.jsonl` (each a denied command or path), and `evidence.json`. It reads no session log. The coordinator picks one record at `triage`, passed as `--record stopped|guard:<n>|evidence`. `<what>` is `stopped: <reason>`, `guard denied: <command or path>` or `failing: <criterion id>`, and `<text>` is that record's text. It prints:

```text
Herd <version>: <what> in a pastor's task

<text, at most 1,000 characters>

- Herd: <version>, Claude Code <version>, Python <version>, <OS>
- Records: .herd/tasks/<slug>/stopped.json, evidence.json
- filed-by: <name>
- feedback-key: F<first 10 hex digits of SHA-1 of "<version>|<what>|<first line of text>">

---
<the pastor's one-line summary>
```

The title is the first line. `test_feedback_body_from_records_only` builds a fixture task whose changed files hold a unique string and asserts the body lacks it.

**Cost.**
* Herd: no new hook, no new work per tool call or per task (G10). `herd pastor new` runs once per pastor.
* Per issue: one headless session, capped by `--max-budget-usd`. The spawn record holds the real cost, and `accept.py` prints the mean per issue for M4.
* Coordinator: one Opus session. It runs no tests or long commands itself (baseline hard rule).
* `gh` calls: `bin/report` makes one GraphQL query per board plus one `gh pr list`; `bin/spawn check` makes about five calls per issue (PR, checks, edit, ready, labels).

### D9. The Magpie test

**Setup**, at Magpie's `gate_setup`: Beovulfo/picturebook, public, MIT license, a `CLAUDE.md` with herd-sdlc's Rules section, a CI workflow, Herd's labels, the private project "Picturebook" with D5's fields, and milestone "P1 Visual PR review".

**P1, the test project's first goal (not an M4 exit criterion).** Magpie designs it in picturebook, at its own `gate_design`. The owner's brief for that design:
* One pull-request comment that GitHub renders itself: Mermaid diagrams for the map of changed modules and the changed flows, alert boxes (`> [!WARNING]`, `> [!CAUTION]`) as attention marks, and inline comments on the risky lines, posted as one review through `POST /repos/{owner}/{repo}/pulls/{n}/reviews` with `comments[]`.
* Accuracy, in code: every element cites `path:start-end` ranges in the diff. A visual with a citation outside the diff, or one that leaves out a changed file, is refused and not posted.
* Speed bar: 3 pairs of closed herd-sdlc pull requests, text review against visual review, the order alternating. The visual review takes at most half the time, with the same or a better score on a 5-question quiz written by a separate agent that never sees the visual.

**M4 acceptance, `examples/pastor-m4/accept.py`:**

| Bar | Evidence the script prints |
| --- | --- |
| At least 2 headless Herd sessions ran in parallel from the board | two spawn records whose `started` to `ended` intervals overlap, each with `check` exit 0 |
| Each ends with `herd done` evidence and a PR in its milestone | per issue: the `evidence.md` path, the PR number, its milestone equal to the issue's, `Closes #N` in its body |
| Milestone-format reports without asking | in the coordinator's session logs, for each `bin/spawn check` tool call, a `bin/report` tool call follows before the next human message, and that message is not `status` |
| At least 1 learning PR for Magpie | a kennel PR from a `learn/` branch whose commits touch only G8's allowed paths under `plugins/magpie/`, with `bin/learn-check` exit 0 on it |
| At least 1 customer-feedback issue | `gh issue list -R Beovulfo/herd-sdlc --label customer-feedback --search "filed-by: magpie"` returns at least one (Open Question 3) |
| Driven from a phone (G11) | the Remote Control PID in run state is alive, and the owner confirms the `Magpie` session answered as Magpie (by hand: the app is outside the script's reach) |

M4 closes when `accept.py` exits 0 and the owner confirms the phone session. Magpie then keeps working on picturebook on its own.

### Spike S6 (planned, before any code)

1. A headless session started by `bin/spawn` (`--permission-mode dontAsk`, cwd the product worktree) cannot write into the kennel checkout. Expected from Claude Code's working-directory rule, not tried. If it can, `bin/spawn` adds a deny rule for the kennel path.
2. `claude --agent magpie:magpie`, for a plugin installed at user scope from a local kennel, makes Magpie the main agent (S4 showed a plugin agent as the main agent; S5 showed its scoped `agent_type`, `egm:egm-style`).
3. On a scratch pull request: a comment with Mermaid and an alert box renders, and a review with multi-line `comments[]` posts.
4. `claude remote-control --settings remote.json`, started in the checkout, opens new sessions as the pastor with herd-sdlc and the kennel plugin loaded. `claude remote-control --help` (2026-11-24, this machine) shows `--name`, `--spawn same-dir|worktree|session`, `--permission-mode`, `--settings` (read once, at start), `-c` (reattach to the session last recorded for this folder within about 4 hours) and `--session-id`. It shows no `--agent` and no `--plugin-dir`, so the agent and the plugins must come from settings. Which keys work (`agent`, `enabledPlugins`, `extraKnownMarketplaces`) is the question. If none works, G11 falls back to the human choosing the agent in the app, and the owner hears about it at the design gate of the build.
5. Real session-log lines for D7, recorded as test fixtures: a terminal message, a message typed mid-turn, and a message from the phone through Remote Control; and the project-folder name for a checkout path.

## Order

1. Spike S6.
2. `templates/pastor/` with its `bin/` scripts and tests, `herd pastor new`, `examples/pastor-m4/accept.py` and its tests, a README section, a CHANGELOG entry and a version bump. No hook changes (G10).
3. Create Magpie in agent-kennel and run CUJ 6 until `accept.py` passes.
4. After M4: Collie fixes the pastor feature only from Magpie's customer-feedback issues.

## Alternatives Considered

| Alternative | Why not, for now |
| --- | --- |
| v4: the pastor in the product repository's `.claude/agents/` | The owner's decision: never in the product repository |
| One plugin agent shipped in herd-sdlc for every project | It cannot learn per human without writing into Herd's plugin cache, which every upgrade replaces |
| A Herd hook that enforces the coordinator's graph | A hook sees tool calls, not the agent's plan. The rules that matter are code in `bin/` |
| Feedback filed by the headless coding sessions | They see one task and have no human to approve the filing. The coordinator sees why a session was refused |
| Feedback triggered by matching words in logs (for example "Traceback") | A word list on text. The coordinator quotes a record, and code builds the body |
| Learnings pushed to the kennel's `main` under a standing approval | The owner replaced it with stacked pull requests the human merges |
| `bin/` scripts inside `scripts/herd.py` | They make `gh` project and PR calls Herd's task CLI does not, and they belong to the agent. Herd's CLI stays unchanged for those who do not opt in |
| Creating a kennel when none exists | M4 runs in agent-kennel; a second user's kennel can come later |

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Parallel sessions cost more than the human expected | `--max-budget-usd` per role; the spawn record holds the real cost |
| A feedback issue leaks a private project's details to a public repository | The body is built from Herd's records; the human sees it at `gate_feedback`; no standing approval by default |
| A Learner rule misquotes the human or invents a rule | `bin/learn-check` refuses a quote the human did not type; the human reviews and merges the pull request |
| A stack of learning pull requests conflicts when merged out of order | Each branch is cut from the newest open one, so merging in creation order is clean |
| The baseline carries rules that suit only the owner | Each has a source tag, so a human can drop it; the Learner records the human's corrections against it |
| The coordinator skips a node, for example a report | Report timing is text; everything that accepts work or acts on GitHub is code or a gate; `accept.py` measures report timing for M4 |
| The computer sleeps or the Remote Control process ends, so the phone has no session | Detached start; the reattach command is in run state. Known limit: Claude runs on this computer, which must stay awake |
| A phone-driven session runs with too wide permissions | The human picks the mode at `gate_setup`; `default` is proposed and `bypassPermissions` never is. Herd's guard and done gate still apply in every Herd task |
| Remote Control in a folder never trusted asks about trust, with no terminal to answer | CUJ 6 runs `claude` once in the checkout first; `setup` names this at its gate |
| A terminal session and the Remote Control session coordinate at once | `setup` ends the terminal session; `bin/spawn` refuses an issue already Running or claimed |
| Magpie's runs depend on the owner's local plugin cache | `bin/spawn` uses the newest installed herd-sdlc and records its version in the spawn record |

## Not proven

* That a pastor from the baseline coordinates as well as Collie on a project it does not know. CUJ 6 is one project.
* Spike S6's five facts.
* That the coordinator's triage finds Herd's problems. Code only builds the body and removes duplicates.
* That event-driven reports reach the human at the right moments. The graph says when; `accept.py` checks it after the fact.
* That D7's log shapes hold on other clients and later Claude Code versions.

## Context and sources

* The owner's M4 decisions: herd-sdlc issue #33, milestone "M4 Graph agents in Herd", 2026-11-24, and three later decisions relayed verbatim by Collie (Decided by the owner).
* The owner's request for the coordinator, quoted in the Overview (2026-11-24), and for the Learner (agent-kennel, `plugins/collie/agents/learner.md`).
* Collie's setup: agent-kennel's `graphs/README.md`, `graphs/validate.py`, `plugins/collie/agents/*.md`, `plugins/collie/graphs/change.yaml`, `plugins/collie/bin/spawn` (roles, models, budgets, command line, continuation rule, `check`).
* Herd's code: `herd done` writes `evidence.md`, sets `resolved_at` and clears `.herd/active`; `herd pr` creates the PR with the goal in its body (`pr_body`, `open_pr` in `scripts/herd.py`).
* Spikes S4 and S5: plugin agents as the main agent, `agent_type`. S5's findings 1 and 3 served v4's in-repository pastor and do not apply to v5.
* v4 of this design, commit c63fb51: the lessons store, corrections and guard rules this version drops.
* `claude remote-control --help` and `claude plugin install --help`, Claude Code on this machine, 2026-11-24.
* GitHub: Mermaid diagrams and alerts in Markdown (docs.github.com, "Creating diagrams" and "Basic writing and formatting syntax"), and the pull-request reviews REST endpoint.
