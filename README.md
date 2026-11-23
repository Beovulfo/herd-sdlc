<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
    <img src="assets/logo.svg" alt="Herd" width="300">
  </picture>
</p>

<h3 align="center">Hand an agent a goal. Get back code and proof.</h3>

<p align="center">
  <a href="https://github.com/Beovulfo/herd-sdlc/actions/workflows/ci.yml"><img alt="tests" src="https://github.com/Beovulfo/herd-sdlc/actions/workflows/ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="license: Apache 2.0" src="https://img.shields.io/badge/license-Apache%202.0-blue.svg"></a>
  <img alt="python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-blue.svg">
  <img alt="Claude Code plugin" src="https://img.shields.io/badge/Claude%20Code-plugin-2e7d32.svg">
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> &middot;
  <a href="#how-it-works">How it works</a> &middot;
  <a href="#architecture">Architecture</a> &middot;
  <a href="#several-tasks-at-once">Parallel tasks</a> &middot;
  <a href="#see-it-work">See it work</a> &middot;
  <a href="#benchmark-with-and-without-herd">Benchmark</a> &middot;
  <a href="#commands-and-skills">Commands</a> &middot;
  <a href="#the-design-behind-it">Design</a>
</p>

<p align="center">
  <img src="assets/demo.gif" alt="A real /herd:run session in Claude Code, with a panel above it lighting the current step: intake, criteria, red first, build, break it, review, verify, evidence" width="860">
</p>

Herd is a lightweight [Claude Code](https://claude.com/claude-code) plugin that runs a task end to end with as little human input as possible. You give it a goal and, if you like, success criteria. The agent plans, builds, tries to break its own work, reviews and verifies. It only stops when **runnable checks prove the criteria pass**, and it only asks you something when an action is irreversible or a real trade-off needs a human.

Most agent workflows ask people to write long requirement lists, then trust the agent when it says "done". Herd flips that:

| You provide | The agent provides |
| --- | --- |
| A goal, and optionally criteria with a check for each | Plan, code, tests, adversarial pass, review, and **evidence** |

You review evidence (command output, commit SHA, timestamps), not process.

**Why use it**
- **Done means proven.** A Stop hook blocks the agent from finishing until every check passes, with evidence newer than the last edit.
- **Your words stay yours.** Criteria you write are quoted verbatim and never weakened. Gaps are filled by the agent and marked `agent-proposed`.
- **Caveats surface early.** The agent must say what each check does not prove, try to break its own work, and log what it finds, so problems appear during the run, not after it.
- **Checks that test nothing are caught.** A check that exits 0 but ran zero tests is flagged instead of counted as proof.
- **The pull request is the evidence (opt-in).** `herd pr` opens a PR whose description shows what is proven and by which check, what is not, and how to reproduce it. It never merges.
- **Short by default.** Commands print a line or two, the agent ends with a seven-line report, and the pull request collapses its details. The full detail is one flag or one file away.
- **Several tasks at once (opt-in).** `herd init --worktree` gives each task its own branch and git worktree, so several agents can work in one repository without touching each other.
- **Light.** A small Python CLI on the standard library, no dependencies, plain-text task files. It reuses [Superpowers](https://github.com/obra/superpowers) and [EGM](https://github.com/google/elephant-goldfish-model) when they are installed.

## Quickstart

You need Claude Code, Python 3.11 or newer as `python3`, and a git repository. With an older `python3` the hooks stay silent and do nothing, and the CLI says which version it needs.

```text
/plugin marketplace add Beovulfo/herd-sdlc
/plugin install herd@herd-sdlc
```

The same from a terminal:

```bash
claude plugin marketplace add Beovulfo/herd-sdlc
claude plugin install herd@herd-sdlc
```

Optional, and recommended, the plugins Herd builds on. Herd works without them and uses them when present:

```bash
claude plugin install superpowers@claude-plugins-official
claude plugin marketplace add google/elephant-goldfish-model
claude plugin install egm@egm
```

Then, inside your project, in a new session:

```text
/herd:run Add a --json flag to the export command. Output must be valid JSON with every row.
```

Herd creates the task, writes criteria with checks and shows them to you, runs them once to see them fail, builds on a `herd/<slug>` branch, tries to break the result, gets a fresh-context review, verifies, and ends with a seven-line report that links the full evidence in `evidence.md`. High-risk changes get one approval question before building. For a trivial change, say "quick fix": one check, no ceremony. To plan with Herd how to prove a change for your project type, run `/herd:evidence`.

Two options are off by default; ask for them in the request, or switch them on in `herd.toml` ([settings](#project-settings-herdtoml)):

```text
/herd:run In its own worktree, add a --json flag to the export command. Open a PR when done.
```

The task then runs on a new branch in its own worktree, cut from the branch you are on, and ends with a pull request whose description is the evidence.

## How it works

```mermaid
flowchart LR
    A[Goal] --> B[Intake and risk floor<br/>opt-in: own worktree]
    B -->|standard| C[Criteria with checks]
    B -->|trivial: quick route| Q[One criterion, one check]
    C --> D[Build: plan, tests first, code]
    Q --> D
    D --> X[Break it<br/>generated cases, scale]
    X --> E[Fresh-eyes review<br/>medium and high risk]
    E --> F[herd verify<br/>run every check]
    F -->|failing| D
    F -->|passing| G[herd done<br/>evidence report]
    G -.->|Stop hook| F
    G -->|opt-in| P[herd pr<br/>PR with the evidence]
```

1. **Intake.** The task gets a folder, `.herd/tasks/<slug>/task.toml`, and a risk floor computed from path rules in `herd.toml` (migrations, auth, billing, and so on). The agent can raise the risk, never lower it. A trivial change takes the **quick route**: one criterion and one check, no criteria interview, no approval question, no review. It is refused at a `high` risk floor and still ends in fresh passing evidence. With `--worktree` (opt-in) the task starts on its own branch in its own git worktree: see [Several tasks at once](#several-tasks-at-once).
2. **Criteria.** Every criterion has a `check`: a shell command where exit 0 means pass. Criteria you write are authoritative: the agent quotes your words, adds a `coverage` note saying what the check proves and what it does not, and the report flags any `human` criterion that is not a verbatim quote. A criterion with no check is `unchecked` and is never counted as met. `herd detect` proposes the project's real test command.
3. **Build.** Tests first, small steps, on a branch. Superpowers is used for planning, TDD and subagents when installed.
4. **Break it, then review.** The agent tries to break its own work on exactly what the request promises: the words `any`, `every`, `very big` become generated cases of different shapes and a scale run. It always also tries bad input at every entry point, collisions, one broken entry it does not need, and recounts every reported number from the output. Each attempt, failure and fix is logged with `herd note`. For medium and high risk, a fresh-context reviewer then looks at the diff.
5. **Verify.** `herd verify` runs every check and stores evidence: status, exit code, output tail, commit SHA, a fingerprint of the workspace, a timestamp, how many checks failed on the first run (a check that was green before any work is visible), and the wall-clock time since `herd init`. A check that exits 0 but whose output says it ran zero tests (`Ran 0 tests`, `no tests ran`, `[no test files]` and the like) is marked in the evidence and the report warns about it. The warning is advisory: the Stop gate does not change. The command prints one summary line plus only the criteria that need attention.
6. **Stop gate.** While a task is active, a Stop hook refuses to let the agent finish unless the evidence is fresh and passing. Edit a file after verifying and the evidence is stale. After 3 blocked attempts the gate lets the agent stop so it can ask you one question instead of looping. To drop a task, `herd cancel` closes it and keeps its files as a record.
7. **Pull request (opt-in).** When the request asks for a PR, or `herd.toml` has `[pr] open = true`, `herd pr` pushes the task's `herd/<slug>` branch and opens a pull request whose description is the evidence: the result, what is proven and by which check, what is not proven (failing or unchecked criteria, coverage gaps, known limits, open caveats), then, collapsed, the run details, the caveat log and the commands to reproduce. Run `herd pr` again after the final `herd verify` and `herd done`: it replaces the description with the latest evidence (it shows stale evidence as stale). It needs a clean working tree, so the PR holds exactly the verified code. It leaves check output out of the description (it can hold secrets) but publishes the check commands, the criteria and the notes as written, so never put a secret in them. It pushes no other branch and never merges: you review the evidence and merge.

### Several tasks at once

Herd keeps a task's state in the checkout it runs in, so two agents in one checkout would share it. To run several tasks in one repository, start each in its own worktree:

```text
$ herd init export-json "Add a --json flag to the export command" --worktree
created worktree <repo>/.claude/worktrees/herd-export-json on branch herd/export-json, cut from feature/reports. Work from there: in Claude Code, EnterWorktree with that path; otherwise cd into it. Run every herd command from it.
```

- **Its own branch, cut from where you are.** `herd/<slug>` starts at the current local branch, which is recorded as the task's base; `herd pr` opens the pull request against it.
- **Its own state.** The task's files and Stop gate live in the worktree. Other agents can start other tasks from the same branch at the same time; each gate sees only its own task, and a duplicate task name fails without touching the first.
- **A forgotten move fails loudly.** `herd` commands run from the starting checkout for a task that lives in a worktree refuse and name the worktree.
- **Clean main checkout.** Herd adds `/.claude/worktrees/` and `.herd/` to the repository's own `.git/info/exclude` (never committed), so other tasks never show up in `git status` or a `git add -A`.
- **Make it the rule.** With `[worktree] required = true` in `herd.toml`, a plain `herd init` refuses outside a matching worktree.
- **Clean up after the merge** with `git worktree remove .claude/worktrees/herd-<slug>`. Uncommitted changes in the starting checkout are not carried over; Herd warns when there are some.

## Architecture

```mermaid
flowchart LR
    subgraph Plugin
        S["Skills<br/>run, criteria, evidence"]
        H["Hooks<br/>Stop gate, lint"]
    end
    CLI["herd CLI<br/>scripts/herd.py"]
    T["herd_triage<br/>risk floor"]
    D["herd_detect<br/>test command"]
    G["git and gh<br/>worktrees, herd pr"]
    subgraph State[".herd/tasks/&lt;slug&gt;/"]
        TT["task.toml<br/>goal, criteria, checks"]
        EV["evidence.json<br/>results, SHA, fingerprint"]
        NO["notes.jsonl<br/>caveats"]
    end
    S -->|instruct the agent to run| CLI
    H -->|gate, lint| CLI
    CLI --> T
    CLI --> D
    CLI -->|opt-in| G
    CLI -->|reads| TT
    CLI -->|runs checks, writes| EV
    CLI -->|appends| NO
```

- **Short skills, details on demand.** The run skill holds the steps; the quick route, the worktree start, the adversarial pass and the PR step are separate files the agent reads only when that step applies. Budget tests keep the skills and the command output from growing back.
- **The skills are the method; the CLI is the referee.** The skills tell the agent what to do in each step. The CLI only records and checks: it runs the commands in `task.toml` and decides from their exit codes, never from what the agent says.
- **The Stop hook enforces it.** It asks the CLI whether the stored evidence is passing and still matches the workspace: a SHA-1 over `HEAD`, the diff and untracked files, plus a hash of `task.toml`. Any edit after `herd verify` makes the evidence stale. The hook finds the task from any subdirectory: the root is the nearest folder with `.herd/` or `herd.toml`, so a project in a subfolder of a repository keeps its own tasks.
- **State is plain files** in the project, one folder per task (in the task's own worktree when it has one), so a human can read, diff or delete it.
- **GitHub only when you opt in.** `herd pr` uses the `gh` CLI to push the task's branch and open its pull request. Nothing else talks to a service.
- **Two modules are not wired in yet.** `herd_arbiter.py` (rules on review findings) and `herd_escalation.py` (one GitHub issue to pause and ask a human) are tested building blocks for the GitHub automation on the roadmap.

## See it work

A task is a goal plus criteria, each with a runnable check:

```toml
goal = "Add a slugify(text) function"
known_limits = "ASCII text only; non-Latin scripts are not handled"

[[criteria]]
id = "C1"
text = "Given 'Hello, World!', when slugify runs, then it returns 'hello-world'"
source = "human"
coverage = "proves the basic case and punctuation; does not prove accents or very long input"
check = "python3 -m unittest test_textutil.TestSlugify.test_basic"

[[criteria]]
id = "C2"
text = "Given only punctuation, when slugify runs, then it returns an empty string"
source = "agent-proposed"
check = "python3 -m unittest test_textutil.TestSlugify.test_empty"
```

Before any work, both checks fail, which proves they test something. After the work (output abridged):

```text
$ herd verify
2 passing, 0 failing, 0 unchecked

$ herd done
done: evidence is fresh and passing (2 of 2 criteria proven)
report: .herd/tasks/slugify/evidence.md
```

`herd verify` lists a criterion only when it needs attention (failing, unchecked, or ran zero tests); `--verbose` lists all. The report in `evidence.md` (also `herd done --verbose`):

```text
# Evidence: slugify
Result: 2 passing, 0 failing, 0 unchecked
First verify: 2 of 2 checks failed before the work
Elapsed: 2m 05s from herd init to this verify; first verify at 0m 40s (wall clock, includes any waiting on the human)
Known limits: ASCII text only; non-Latin scripts are not handled
Adversarial pass: 2 attempts recorded
| id | status | source | check |
| C1 | passing | human | `python3 -m unittest test_textutil.TestSlugify.test_basic` |
| C2 | passing | agent-proposed | `python3 -m unittest test_textutil.TestSlugify.test_empty` |
```

The agent's final message to you is seven lines, filled from the report and linking it instead of repeating it:

```text
Done: added slugify(text) in textutil.py.
Proven: 2 of 2 criteria; evidence in .herd/tasks/slugify/evidence.md.
Not proven: accents and very long input (C1 coverage).
Caveats: found that an empty string crashed (0m 50s), fixed (1m 10s).
Decisions: none.
Limits: ASCII text only; non-Latin scripts are not handled.
Review: fresh-context subagent, no Blocker or Major findings.
```

With `herd pr`, the same evidence becomes the pull request description (abridged):

```markdown
# Evidence: slugify

**Result:** 2 of 2 criteria proven by a passing check (0 failing, 0 unchecked).

The evidence is fresh: the checks ran at 2026-11-23T10:02:11Z on commit `4cd7bd83130f`.

## What is proven
| id | source | criterion | proof: the check that passed |
| C1 | human | Given 'Hello, World!', when slugify runs, then it returns 'hello-world' | `python3 -m unittest test_textutil.TestSlugify.test_basic` exit 0 |

## What is not proven
- C1, what its check proves and does not: proves the basic case and punctuation; does not prove accents or very long input
- Known limits: ASCII text only; non-Latin scripts are not handled

<details><summary>Run details and caveat log (2 tried, 0 found, 0 fixed)</summary> ... </details>
<details><summary>Reproduce: run from the repository root</summary> ... </details>
```

Long check commands are cut in the table and shown in full under Reproduce.

If the agent tries to finish while a check is failing, the Stop hook answers instead:

```text
{"decision": "block", "reason": "Herd task `slugify` is not done (1/3 stop attempts blocked).
 C1 is failing: Given 'Hello, World!', ... Run `herd.py verify` after fixing. ..."}
```

## Benchmark: with and without Herd

<p align="center">
  <img src="examples/supermarket-route/images/simulation.svg" alt="Animation: one basket walked in shopping-list order and on the optimized route, with time and distance bars running" width="860">
</p>

One short prompt, a route optimizer for picking a shopping list in a supermarket that "works for any layout, even very big ones", was given to the same model (Sonnet) twice: once with Herd and once with no workflow. Then each solution was checked by a hidden verifier it had never seen: 48 generated stores from eight layout families, up to 600 by 400 cells with 200 items, with every walk validated step by step.

<p align="center">
  <img src="examples/supermarket-route/images/layouts.svg" alt="The optimized route on eight generated store layouts: parallel aisles, vertical aisles, islands, random obstacles, comb, L-shape, maze and departments" width="860">
</p>

| | With Herd | Without Herd |
| --- | --- | --- |
| Stores solved with a valid route | **48 of 48** | 38 of 48 |
| Failure | none | crash when a shelf borders a disconnected pocket of floor |
| Bad-input scenarios handled (unknown product, duplicate, empty list, unreachable product, malformed map) | **6 of 6** | 4 of 6 |
| Test lines written | 119 | 20 |
| Median time to plan a 600 by 400 store | 36.1 s | 72.7 s |
| Time to a finished result | 3m 19s | 1m 03s |
| Tokens | 87k | 73k |

<p align="center">
  <img src="examples/supermarket-route/images/benchmark.svg" alt="Bars comparing with and without Herd on stores solved, bad inputs handled, test lines, time and tokens" width="760">
</p>

- **More robust and better tested.** Without Herd, the code crashed on stores with disconnected floor pockets, on an unreachable product and on a malformed map. With Herd it handled all of them, and wrote six times as many test lines.
- **The route itself is not better.** The optimizers found routes of similar length; the no-workflow routes were slightly shorter on mid-size and large stores.
- **Herd said where the claim fails.** Its `known_limits` stated that the 30% saving does not hold for baskets of about 15 items or fewer. The hidden verifier confirmed it. The no-workflow run reported its best demo number.
- **It costs more.** 3.2 times the time and 19 percent more tokens.
- **No extra input from you.** Herd needs only the one message; it asked no questions.

One run per arm, one model: read it as strong evidence about robustness, not a precise cost figure. The Herd run was an emulation (a subagent following the skills, with no Stop hook and no reviewer), and its "all checks failed first" step was gamed: it moved its code aside for the first verify. The full method, every number and these limits are in [`examples/supermarket-route/BENCHMARK.md`](examples/supermarket-route/BENCHMARK.md). To reproduce the main check:

```bash
python3 examples/supermarket-route/verifier/verify_general.py with_herd examples/supermarket-route/with-herd
```

## Commands and skills

| What | Does |
| --- | --- |
| `/herd:run <task>` | The autopilot: intake, criteria, build, break it, review, verify, evidence |
| `/herd:criteria` | Write success criteria with runnable checks |
| `/herd:evidence` | Interactive: decide with you how to prove the change works for your project type |
| `herd init <slug> "<goal>" --request "<message>"` | Create a task and make it active. `--request` stores the human's message verbatim so `herd check` can flag human criteria that are not quotes |
| `herd init <slug> "<goal>" --quick "<check>"` | Quick route for a trivial change: one criterion, one check. Refused at a `high` risk floor |
| `herd init <slug> "<goal>" --worktree` | Opt-in: start the task on a new `herd/<slug>` branch in its own worktree at `.claude/worktrees/herd-<slug>`, cut from the current local branch, so several agents can run tasks in one repository. `[worktree] required = true` in `herd.toml` makes it mandatory |
| `herd check` | Validate `task.toml`; warns about criterion texts over 40 words, coverage notes over 50 words, checks that do not run project code, human criteria that are not quotes, missing `coverage` or `known_limits`, and quantifier or size words (`any`, `every`, `very big`) whose `coverage` does not say what varies or what scale was tried |
| `herd detect` | Propose test and lint commands for Python, Node, Rust, Go and `make test` |
| `herd note --found\|--fixed\|--open\|--tried "text"` | Log a caveat or an adversarial attempt with a timestamp; the report lists them |
| `herd triage "<text>" [--json]` | Print the risk floor for a task description in one line (`risk: high (auth/**)`); `--json` prints the full record |
| `herd verify [--verbose]` | Run all checks, store `evidence.json`; exit 1 if any fail. Prints one summary line plus only the criteria that need attention (failing, unchecked, ran zero tests); `--verbose` lists all |
| `herd status` | Show evidence and whether the task is done |
| `herd done [--verbose]` | Write `evidence.md`, close the task; refuses unless fresh and passing. Prints two lines; `--verbose` prints the report too |
| `herd cancel --reason "text"` | Abandon the task: keep its files, stop the Stop gate from blocking |
| `herd pr [slug] [--yes]` | Opt-in: push the `herd/*` branch, open or update its PR with the evidence as the description; never merges |
| `herd help` | List every command with its usage |
| `herd gate` | The Stop hook (reads hook JSON on stdin) |
| `herd lint` | The optional PostToolUse lint hook; `herd lint --suggest` prints a `[lint]` block for `herd.toml` |

`herd` is `python3 scripts/herd.py`. Inside the plugin it is `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/herd.py"`.

### Project settings (`herd.toml`)

All optional. Without a `herd.toml`, Herd uses the defaults below. This repository's [`herd.toml`](herd.toml) is an annotated example.

| Table | Default | What it does |
| --- | --- | --- |
| `[floor]` | `migrations/**`, `auth/**`, `billing/**` and `herd.toml` are high | Path rules for the risk floor; a high floor means one approval question and no quick route |
| `[worktree] required = true` | off | Every task must start in its own worktree (`herd init --worktree`) |
| `[pr] open = true` | off | `herd pr` may push the task branch and open its pull request without `--yes` |
| `[lint]` | off | Per-file lint after each edit, see below |

**Lint feedback after each edit (opt-in).** Add a `[lint]` table to your project's `herd.toml`:

```toml
[lint]
command = "ruff check {file}"
globs = ["**/*.py"]
timeout_s = 20
```

While a Herd task is active, each `Edit` or `Write` runs the command on that file, and a failure is handed back to the agent as context (it does not block). Other editing tools such as `MultiEdit` and `NotebookEdit` are not covered. The command comes from the repository and runs with your permissions, the same trust as a `check` in `task.toml`.

## Autonomy rules

- **Gaps never block.** Missing criteria or checks are filled in by the agent, marked `agent-proposed`, and listed for you.
- **Evidence over claims.** `passing` and `failing` come from commands. `unchecked` is listed and never counted as met.
- **Ask rarely, ask once.** The agent stops for an irreversible action, a real trade-off, or when stuck after 3 review rounds or 3 failed attempts on a criterion. It asks one question with numbered options.
- **Decisions are reported** in at most three lines: decision, reason, how to override.
- **Checks run as shell commands** from `task.toml`, in your repository, with your permissions. Treat a task file like code: read it, especially in a repository you do not trust.
- **Push only its own branch, never merge.** `herd pr` pushes only the task's `herd/<slug>` branch from a clean working tree and opens or updates its pull request. The merge is yours.

## Status

Version 0.3.0 (see the [changelog](CHANGELOG.md)). Working and covered by 241 unit tests on Python 3.11 to 3.13: the evidence harness (`scripts/herd.py`), the Stop gate, the quick route, project-type detection, the lint hook, the caveat log, zero-test flagging, the opt-in `herd pr` step, the opt-in worktree start for parallel tasks, short output by default, and the risk-floor module. Releases 0.2.7 to 0.3.0 were each built with Herd itself; 0.2.8 to 0.3.0 were opened as pull requests by `herd pr`. Benchmarked on one task with Sonnet (above). Not yet done: many live runs through the installed plugin across different project types, and issue-to-pull-request automation on GitHub (labelled issue to reviewed spec), which is still design work. `herd pr` covers only the last step: a finished local task opens a pull request with its evidence.

## The design behind it

Herd is built with its own method, using the [Elephant-Goldfish Model](https://github.com/google/elephant-goldfish-model): an Elephant agent with full context drafts, and Goldfish reviewers with no context check. The requirements and decisions are in the open:

- [`docs/PRD.md`](docs/PRD.md): the product requirements, principles and roadmap.
- [`docs/designs/`](docs/designs): specs for Triage, the Arbiter (an agent that rules on review findings) and Escalation (one issue to pause and ask a human), each with a tested module in `scripts/` that will power the GitHub automation phase, plus the [v0.2 plan](docs/designs/herd-coco-ideas.md).
- [`docs/spikes/`](docs/spikes): spike S1 ran EGM unattended on these features; the run logs say what each review found and what broke.
- [`docs/backlog.md`](docs/backlog.md): ideas not yet planned, such as an optional Trail Code integration.

## Roadmap

- **Now (v0.3):** local autopilot with evidence, short output by default, the Stop gate, a quick route, project-type detection, an opt-in lint hook, an adversarial pass, the evidence-planning skill, zero-test flagging, an opt-in, evidence-first pull request step (`herd pr`) and an opt-in worktree start so several agents can run tasks in one repository.
- **Next:** GitHub automation: a labelled issue becomes a reviewed spec, then a pull request, with the Arbiter and Escalation modules.
- **Later:** a release gate for high-risk changes, and other agent harnesses.

## Development

```bash
python3 -m unittest discover -s tests -t .
ruff check .
claude plugin validate ./
```

Python standard library only, no dependencies. Try the plugin from a clone with `claude --plugin-dir /path/to/herd-sdlc`. When plugin files change, bump `version` in `.claude-plugin/plugin.json` and add a [changelog](CHANGELOG.md) entry, because `claude plugin update` compares version numbers only.

## License

[Apache License 2.0](LICENSE)
