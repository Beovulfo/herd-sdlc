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
  <a href="#see-it-work">See it work</a> &middot;
  <a href="#benchmark-with-and-without-herd">Benchmark</a> &middot;
  <a href="#commands-and-skills">Commands</a> &middot;
  <a href="#the-design-behind-it">Design</a>
</p>

<p align="center">
  <img src="examples/supermarket-route/images/simulation.svg" alt="Animation: one basket walked in shopping-list order and on the optimized route, with time and distance bars running" width="860">
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

Herd creates the task, writes criteria with checks and shows them to you, runs them once to see them fail, builds on a `herd/<slug>` branch, tries to break the result, gets a fresh-context review, verifies, and ends with an evidence report. High-risk changes get one approval question before building. For a trivial change, say "quick fix": one check, no ceremony. To plan with Herd how to prove a change for your project type, run `/herd:evidence`.

## How it works

```mermaid
flowchart LR
    A[Goal] --> B[Intake and risk floor]
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
```

1. **Intake.** The task gets a folder, `.herd/tasks/<slug>/task.toml`, and a risk floor computed from path rules in `herd.toml` (migrations, auth, billing, and so on). The agent can raise the risk, never lower it. A trivial change takes the **quick route**: one criterion and one check, no criteria interview, no approval question, no review. It is refused at a `high` risk floor and still ends in fresh passing evidence.
2. **Criteria.** Every criterion has a `check`: a shell command where exit 0 means pass. Criteria you write are authoritative: the agent quotes your words, adds a `coverage` note saying what the check proves and what it does not, and the report flags any `human` criterion that is not a verbatim quote. A criterion with no check is `unchecked` and is never counted as met. `herd detect` proposes the project's real test command.
3. **Build.** Tests first, small steps, on a branch. Superpowers is used for planning, TDD and subagents when installed.
4. **Break it, then review.** The agent tries to break its own work on exactly what the request promises: the words `any`, `every`, `very big` become generated cases of different shapes and a scale run. Each attempt, failure and fix is logged with `herd note`. For medium and high risk, a fresh-context reviewer then looks at the diff.
5. **Verify.** `herd verify` runs every check and stores evidence: status, exit code, output tail, commit SHA, a fingerprint of the workspace, a timestamp, how many checks failed on the first run (a check that was green before any work is visible), and the wall-clock time since `herd init`.
6. **Stop gate.** While a task is active, a Stop hook refuses to let the agent finish unless the evidence is fresh and passing. Edit a file after verifying and the evidence is stale. After 3 blocked attempts the gate lets the agent stop so it can ask you one question instead of looping. To drop a task, `herd cancel` closes it and keeps its files as a record.

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
    subgraph State[".herd/tasks/&lt;slug&gt;/"]
        TT["task.toml<br/>goal, criteria, checks"]
        EV["evidence.json<br/>results, SHA, fingerprint"]
        NO["notes.jsonl<br/>caveats"]
    end
    S -->|instruct the agent to run| CLI
    H -->|gate, lint| CLI
    CLI --> T
    CLI --> D
    CLI -->|reads| TT
    CLI -->|runs checks, writes| EV
    CLI -->|appends| NO
```

- **The skills are the method; the CLI is the referee.** The skills tell the agent what to do in each step. The CLI only records and checks: it runs the commands in `task.toml` and decides from their exit codes, never from what the agent says.
- **The Stop hook enforces it.** It asks the CLI whether the stored evidence is passing and still matches the workspace: a SHA-1 over `HEAD`, the diff and untracked files, plus a hash of `task.toml`. Any edit after `herd verify` makes the evidence stale.
- **State is plain files** in the project, one folder per task, so a human can read, diff or delete it.
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
  C1 passing: Given 'Hello, World!', when slugify runs, then it returns 'hello-world'
  C2 passing: Given only punctuation, when slugify runs, then it returns an empty string

$ herd done
# Evidence: slugify
Result: 2 passing, 0 failing, 0 unchecked
First verify: 2 of 2 checks failed before the work
Elapsed: 2m 05s from herd init to this verify; first verify at 0m 40s (wall clock, includes any waiting on the human)
Known limits: ASCII text only; non-Latin scripts are not handled
Adversarial pass: 2 attempts recorded
| id | status | source | check |
| C1 | passing | human | `python3 -m unittest test_textutil.TestSlugify.test_basic` |
| C2 | passing | agent-proposed | `python3 -m unittest test_textutil.TestSlugify.test_empty` |
done: evidence is fresh and passing
```

If the agent tries to finish while a check is failing, the Stop hook answers instead:

```text
{"decision": "block", "reason": "Herd task `slugify` is not done (1/3 stop attempts blocked).
 C1 is failing: Given 'Hello, World!', ... Run `herd.py verify` after fixing. ..."}
```

## Benchmark: with and without Herd

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
| `herd check` | Validate `task.toml`; warns about checks that do not run project code, human criteria that are not quotes, missing `coverage` or `known_limits`, and quantifier or size words (`any`, `every`, `very big`) whose `coverage` does not say what varies or what scale was tried |
| `herd detect` | Propose test and lint commands for Python, Node, Rust, Go and `make test` |
| `herd note --found\|--fixed\|--open\|--tried "text"` | Log a caveat or an adversarial attempt with a timestamp; the report lists them |
| `herd triage "<text>"` | Print the risk floor for a task description |
| `herd verify` | Run all checks, store `evidence.json`; exit 1 if any fail |
| `herd status` | Show evidence and whether the task is done |
| `herd done` | Write `evidence.md`, close the task; refuses unless fresh and passing |
| `herd cancel --reason "text"` | Abandon the task: keep its files, stop the Stop gate from blocking |
| `herd help` | List every command with its usage |
| `herd gate` | The Stop hook (reads hook JSON on stdin) |
| `herd lint` | The optional PostToolUse lint hook; `herd lint --suggest` prints a `[lint]` block for `herd.toml` |

`herd` is `python3 scripts/herd.py`. Inside the plugin it is `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/herd.py"`.

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

## Status

Version 0.2.6 (see the [changelog](CHANGELOG.md)). Working and covered by 188 unit tests on Python 3.11 to 3.13: the evidence harness (`scripts/herd.py`), the Stop gate, the quick route, project-type detection, the lint hook, the caveat log, and the risk-floor module. Benchmarked on one task with Sonnet (above). Not yet done: many live runs through the installed plugin across different project types, and issue-to-pull-request automation on GitHub, which is still design work.

## The design behind it

Herd is built with its own method, using the [Elephant-Goldfish Model](https://github.com/google/elephant-goldfish-model): an Elephant agent with full context drafts, and Goldfish reviewers with no context check. The requirements and decisions are in the open:

- [`docs/PRD.md`](docs/PRD.md): the product requirements, principles and roadmap.
- [`docs/designs/`](docs/designs): specs for Triage, the Arbiter (an agent that rules on review findings) and Escalation (one issue to pause and ask a human), each with a tested module in `scripts/` that will power the GitHub automation phase, plus the [v0.2 plan](docs/designs/herd-coco-ideas.md).
- [`docs/spikes/`](docs/spikes): spike S1 ran EGM unattended on these features; the run logs say what each review found and what broke.
- [`docs/backlog.md`](docs/backlog.md): ideas not yet planned, such as an optional Trail Code integration.

## Roadmap

- **Now (v0.2):** local autopilot with evidence, the Stop gate, a quick route, project-type detection, an opt-in lint hook, an adversarial pass and the evidence-planning skill.
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
