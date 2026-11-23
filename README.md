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
  <a href="#other-agents"><img alt="Codex: herd setup" src="https://img.shields.io/badge/Codex-herd%20setup-2e7d32.svg"></a>
  <a href="#other-agents"><img alt="open models: via Codex or Claude Code" src="https://img.shields.io/badge/open%20models-Codex%20or%20Claude%20Code-2e7d32.svg"></a>
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> &middot;
  <a href="#how-it-works">How it works</a> &middot;
  <a href="#architecture">Architecture</a> &middot;
  <a href="#other-agents">Codex and open models</a> &middot;
  <a href="#several-tasks-at-once">Parallel tasks</a> &middot;
  <a href="#see-it-work">See it work</a> &middot;
  <a href="#benchmark-with-and-without-herd">Benchmark</a> &middot;
  <a href="#commands-and-skills">Commands</a> &middot;
  <a href="#the-design-behind-it">Design</a>
</p>

<p align="center">
  <img src="assets/demo.gif" alt="A real /herd:run session in Claude Code, with a panel above it lighting the current step: intake, criteria, red first, build, break it, review, verify, evidence" width="860">
  <br><sub>A real session with Herd 0.3.2 and Claude Sonnet 5.5, sped up: one message, then intake, criteria, red first, build, break it, review, verify and evidence. The Stop gate blocks one early finish.</sub>
</p>

Herd is a lightweight [Claude Code](https://claude.com/claude-code) plugin, also usable from Codex and open models ([other agents](#other-agents)), that runs a task end to end with as little human input as possible. You give it a goal and, if you like, success criteria. The agent plans, builds, tries to break its own work, reviews and verifies. It only stops when **runnable checks prove the criteria pass**, and it only asks you something when an action is irreversible or a real trade-off needs a human.

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
- **The pull request is the evidence.** Each task ends in a draft PR (`herd pr`) whose description shows what is proven and by which check, what is not, and how to reproduce it. It never marks it ready and never merges. `[pr] open = false` turns it off.
- **Short by default.** Commands print a line or two, the agent ends with a seven-line report, and the pull request collapses its details. The full detail is one flag or one file away.
- **Several tasks at once.** Each task gets its own branch and git worktree (`herd init --worktree`), so several agents can work in one repository without touching each other. `[worktree] required = false` turns it off.
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

By default the task runs on a new branch in its own worktree, cut from the branch you are on, and ends with a draft pull request whose description is the evidence. You review it, mark it ready and merge. To turn either off, set `[worktree] required = false` or `[pr] open = false` in `herd.toml` ([settings](#project-settings-herdtoml)). Outside git, or before the first commit, the task starts in the current folder instead; with no `origin` remote or no `gh`, `herd pr` says why and the task still finishes.

## Other agents

The CLI is plain Python and does not depend on Claude Code, so other coding agents can run Herd too. Clone this repository, then run `herd setup` once:

```bash
git clone https://github.com/Beovulfo/herd-sdlc ~/herd-sdlc
python3 ~/herd-sdlc/scripts/herd.py setup --user
```

`herd setup --user` writes the skills as `herd-run`, `herd-criteria` and `herd-evidence` to `~/.agents/skills/`, a Herd block to `$CODEX_HOME/AGENTS.md`, and the Stop gate to `$CODEX_HOME/hooks.json` (`CODEX_HOME` defaults to `~/.codex`). Without `--user` it writes the same into the project: `.agents/skills/`, `AGENTS.md` and `.codex/hooks.json`, in the folder Herd's tasks use (the nearest one with `.herd/` or `herd.toml`, else the repository root). Your own content in both files stays; a rerun replaces only Herd's entries and files, and a `hooks.json` it cannot read is refused unchanged. The files name your Herd copy by absolute path, so run `herd setup` again after moving it. Project mode adds all three to `.git/info/exclude`, so they never reach a commit, and it refuses when `AGENTS.md` or `.codex/hooks.json` is already tracked: use `--user` there. An `AGENTS.md` or `.codex/hooks.json` you had not committed yet is hidden from `git status` too; to commit it later, remove its line from `.git/info/exclude` and switch to `--user`.

Then ask for a run. In Codex: `$herd-run Add a --json flag to the export command.` Elsewhere: "Use Herd to add a --json flag to the export command."

| Agent | How Herd gets in | Stop gate | Lint hook |
| --- | --- | --- | --- |
| Claude Code | the plugin, `/herd:run` | yes | yes, opt-in |
| Codex CLI | `herd setup --user`, then `$herd-run` | configured, unverified live (below) | no |
| Open models in Codex, such as Unsloth Studio or `llama-server` (`unsloth start codex`, `codex --oss`) | `herd setup` in the repository | configured, unverified live (below) | no |
| Open models in Claude Code (`unsloth start claude`, `ANTHROPIC_BASE_URL`) | the plugin, unchanged | yes | yes, opt-in |
| Other agents that read `AGENTS.md` | `herd setup` in the repository; the block names the skill files by path | no | no |

- **Unsloth is not an agent.** It trains and serves open models. [Its docs](https://unsloth.ai/docs/basics/codex) run them as coding agents through Codex (Unsloth Studio or `llama-server`, Responses API) or [through Claude Code](https://unsloth.ai/docs/basics/claude-code). [`unsloth start codex`](https://unsloth.ai/docs/integrations/unsloth-start) gives Codex its own home, so it does not read `~/.codex`: use project mode there.
- **No Stop gate, only a rule.** Where there is no Stop hook, or before you trust it, the `AGENTS.md` block tells the agent never to stop before `herd done` succeeds. A model can ignore a rule; it cannot get past the gate. Check `herd status` yourself. Smaller open models also follow long skills less reliably.
- **The Codex Stop gate is unverified live.** Codex's Stop hook takes the same output as `herd gate`, and Codex runs a new or changed hook only after you trust it in `/hooks`. In one live test (Codex 0.139.0, `codex exec --oss` with a local Ollama model, [spike S3](docs/spikes/s3-codex-live.md)) the model read the `AGENTS.md` block, but Codex ran no hook from `hooks.json`, not even a trivial one. The interactive CLI was not tried. Until it is, treat Codex like an agent with only the rule.
- **Worktree tasks have only the rule in Codex, unless Codex starts there.** Every task runs in its own worktree by default. Codex gives the Stop hook the folder the session started in, and `cd` inside a command does not change it, so a gate started from the main checkout does not see the task. To put the gate there, install with `herd setup --user` and start Codex in the worktree (`codex -C <path>`). Project mode files are never committed, so a new worktree does not have them: run `herd setup` in the worktree too. The same goes for a project in a subfolder: start Codex in that folder or below it, since Codex looks for `.codex/` and `.agents/skills/` only from its start folder up to the repository root.
- **How it is tested.** `tests/test_herd_setup.py` runs `herd setup`, then a whole task through the rendered command and the Stop hook command with Codex's hook input, without Claude Code. CI runs no live Codex or open-model session.

## How it works

```mermaid
flowchart LR
    A[Goal] --> B[Intake and risk floor<br/>own worktree on herd/slug]
    B -->|standard| C[Criteria with checks]
    B -->|trivial: quick route| Q[One criterion, one check]
    C --> R[Red first<br/>checks fail before the work]
    Q --> R
    R --> D[Build: plan, tests first, code]
    D -->|standard| X[Break it<br/>generated cases, scale<br/>4 attacks, each with a command]
    D -->|quick route| F
    X --> E[Fresh-eyes review<br/>medium and high risk]
    E --> F[herd verify<br/>criteria and attack commands]
    F -->|failing| D
    F -->|passing| G[herd done<br/>evidence report]
    G -.->|Stop hook| F
    G -->|default| P[herd pr<br/>draft PR with the evidence]
```

1. **Intake.** The task gets a folder, `.herd/tasks/<slug>/task.toml`, and a risk floor computed from path rules in `herd.toml` (migrations, auth, billing, and so on). The agent can raise the risk, never lower it. A trivial change takes the **quick route**: one criterion and one check, no criteria interview, no approval question, no review. It is refused at a `high` risk floor and still ends in fresh passing evidence. By default (`--worktree`) the task starts on its own branch in its own git worktree: see [Several tasks at once](#several-tasks-at-once).
2. **Criteria.** Every criterion has a `check`: a shell command where exit 0 means pass. Criteria you write are authoritative: the agent quotes your words, adds a `coverage` note saying what the check proves and what it does not, and the report flags any `human` criterion that is not a verbatim quote. A criterion with no check is `unchecked` and is never counted as met. `herd detect` proposes the project's real test command. Before any work, `herd verify` runs the checks once: they should fail (red first), and the report shows how many did.
3. **Build.** Tests first, small steps, on a branch. Superpowers is used for planning, TDD and subagents when installed.
4. **Break it, then review.** The agent tries to break its own work on exactly what the request promises: the words `any`, `every`, `very big` become generated cases of different shapes and a scale run. It always also runs four standard attacks: bad input at every entry point, collisions, one broken entry it does not need, and a recount of every reported number from the output. Each attack is logged with a command that shows it (`herd note --tried --attack <name> --check "<command>"`); `herd verify` runs these commands like criterion checks, and `herd done` and the Stop gate refuse until each attack has one that passes (or an `n/a:` reason). Each attempt, failure and fix is logged with `herd note`. For medium and high risk, a fresh-context reviewer then looks at the diff.
5. **Verify.** `herd verify` runs every check and stores evidence: status, exit code, output tail, commit SHA, a fingerprint of the workspace, a timestamp, how many checks failed on the first run (a check that was green before any work is visible), and the wall-clock time since `herd init`. A check that exits 0 but whose output says it ran zero tests (`Ran 0 tests`, `no tests ran`, `[no test files]` and the like) is marked in the evidence and the report warns about it. The warning is advisory: the Stop gate does not change. The command prints one summary line plus only the criteria that need attention.
6. **Stop gate.** While a task is active, a Stop hook refuses to let the agent finish unless the evidence is fresh and passing. Edit a file after verifying and the evidence is stale. After 3 blocked attempts the gate lets the agent stop so it can ask you one question instead of looping. To drop a task, `herd cancel` closes it and keeps its files as a record.
7. **Pull request.** Unless `herd.toml` has `[pr] open = false`, `herd pr` pushes the task's `herd/<slug>` branch and opens a draft pull request whose description is the evidence: the result, what is proven and by which check, what is not proven (failing or unchecked criteria, coverage gaps, known limits, open caveats), then, collapsed, the run details, the caveat log and the commands to reproduce. `herd done` then replaces the description with the final evidence (run `herd pr` again any time to refresh it; it shows stale evidence as stale). It needs a clean working tree, so the PR holds exactly the verified code. It leaves check output out of the description (it can hold secrets) but publishes the check commands, the criteria and the notes as written, so never put a secret in them. It pushes no other branch, never marks the PR ready and never merges: you review the evidence, mark it ready and merge. With no `origin` remote or no `gh` it fails with one message, and the task still finishes.

### Several tasks at once

Herd keeps a task's state in the checkout it runs in, so a plain `herd init` refuses while another task there is still active. To run several tasks in one repository, start each in its own worktree:

```text
$ herd init export-json "Add a --json flag to the export command" --worktree
created worktree <repo>/.claude/worktrees/herd-export-json on branch herd/export-json, cut from feature/reports. Work from there: in Claude Code, EnterWorktree with that path; otherwise cd into it. Run every herd command from it.
```

- **Its own branch, cut from where you are.** `herd/<slug>` starts at the current local branch, which is recorded as the task's base; `herd pr` opens the pull request against it. A plain `herd init` does the same in the current checkout, without a new folder.
- **Its own state.** The task's files and Stop gate live in the worktree. Other agents can start other tasks from the same branch at the same time; each gate sees only its own task, and a duplicate task name fails without touching the first.
- **A forgotten move fails loudly.** `herd` commands run from the starting checkout for a task that lives in a worktree refuse and name the worktree.
- **Clean main checkout.** Herd adds `/.claude/worktrees/` and `.herd/` to the repository's own `.git/info/exclude` (never committed), so other tasks never show up in `git status` or a `git add -A`.
- **The rule by default.** A plain `herd init` refuses outside a matching worktree and names the fix. `[worktree] required = false` in `herd.toml` turns this off. Outside git, or before the first commit, a plain init works and says why.
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
    G["git and gh<br/>task branch, worktrees, herd pr"]
    subgraph State[".herd/tasks/&lt;slug&gt;/"]
        TT["task.toml<br/>goal, criteria, checks"]
        NO["notes.jsonl<br/>caveats, attacks with commands"]
        EV["evidence.json<br/>criteria and attack results,<br/>SHA, fingerprint"]
        RP["evidence.md<br/>the report"]
    end
    S -->|instruct the agent to run| CLI
    H -->|gate, lint| CLI
    CLI --> T
    CLI --> D
    CLI --> G
    CLI -->|reads| TT
    CLI -->|appends| NO
    CLI -->|runs checks and attack commands, writes| EV
    CLI -->|herd done writes| RP
```

- **Short skills, details on demand, quality first.** The run skill holds the steps; the quick route, the worktree start, the adversarial pass and the PR step are separate files the agent must read in full when that step applies. Where skipping a file would cost quality, the CLI enforces the step itself (the adversarial attacks at `herd done`). Budget tests keep the skills and the command output from growing back.
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
Adversarial pass: 5 attempts recorded; bad-input passing (`python3 -m unittest test_textutil.TestBadInput`); collision n/a; one-bad-part n/a; recount passing (`python3 -m unittest test_textutil.TestRecount`)
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

One short prompt, a route optimizer for picking a shopping list in a supermarket that "works for any layout, even very big ones", was given **6 times each** to four arms: Claude Sonnet 5.5 and Claude Haiku 5.5, each with **Herd 0.3.1** and with no workflow. Every solution was then checked by a hidden verifier it had never seen: 48 generated stores from eight layout families, up to 600 by 400 cells with 200 items, with every walk validated step by step, plus six bad-input scenarios.

<p align="center">
  <img src="examples/supermarket-route/images/layouts.svg" alt="The optimized route on eight generated store layouts: parallel aisles, vertical aisles, islands, random obstacles, comb, L-shape, maze and departments" width="860">
</p>

Mean ± standard deviation over 6 runs per arm:

| | Sonnet + Herd | Sonnet, no workflow | Haiku + Herd | Haiku, no workflow |
| --- | --- | --- | --- | --- |
| Stores solved with a valid route, of 48 | **48.0 ± 0.0** | 45.2 ± 4.8 | 44.3 ± 2.0 | 41.7 ± 2.7 |
| Runs with every store valid | **6 of 6** | 3 of 6 | 1 of 6 | 0 of 6 |
| Bad-input scenarios handled, of 6 | **6.0 ± 0.0** | 3.5 ± 0.5 | **6.0 ± 0.0** | 4.3 ± 2.0 |
| Time saved against list order, mid stores | 66.8 ± 1.3% | 66.7 ± 1.1% | 68.2 ± 1.8% | 66.8 ± 1.4% |
| Time to a finished result | 4.2 ± 1.2 min | 1.1 ± 0.2 min | 10.3 ± 5.5 min | 2.7 ± 0.9 min |
| Estimated cost per run, API list prices | $0.61 ± 0.09 | $0.29 ± 0.03 | $0.29 ± 0.09 | $0.04 ± 0.02 |

<p align="center">
  <img src="examples/supermarket-route/images/benchmark.svg" alt="Bars for the four arms: stores solved, bad inputs handled, cost per run and time to finish, each with its standard deviation" width="760">
</p>

- **Sonnet with Herd never failed.** All 6 runs solved all 48 stores and handled all six bad inputs. Without Herd, 3 of 6 Sonnet runs lost stores (up to 12), and all six crashed on a malformed map.
- **Bad input is safe with Herd on both models.** All 12 Herd runs handled 6 of 6 bad inputs; without Herd the average was 3.5 (Sonnet) and 4.3 (Haiku).
- **The route itself is not better.** Once a store is solved, every arm saves about the same time against list order. Herd buys robustness and evidence, not a better optimizer.
- **Haiku is cheaper but not as good.** Haiku with Herd costs half of Sonnet with Herd and matches it on bad input, but loses 3.7 stores per run, almost all to one bug (a product picked from a sealed side of its shelf). For the same $0.29 as Sonnet without a workflow, it is safer on bad input and solves about as many stores.
- **It costs more.** Herd runs make about 4 times as many model requests: about 2 times the cost on Sonnet and 8 times on Haiku, and 4 times the time.

One task, emulated Herd sessions (no Stop hook, no reviewer), costs estimated from each run's own token log at API list prices. The method, every number, the failure analysis and these limits are in [`examples/supermarket-route/BENCHMARK.md`](examples/supermarket-route/BENCHMARK.md). To score one run:

```bash
sh examples/supermarket-route/verifier/score_run.sh sonnet-herd-1
```

## Commands and skills

| What | Does |
| --- | --- |
| `/herd:run <task>` | The autopilot: intake, criteria, build, break it, review, verify, evidence |
| `/herd:criteria` | Write success criteria with runnable checks |
| `/herd:evidence` | Interactive: decide with you how to prove the change works for your project type |
| `herd init <slug> "<goal>" --request "<message>"` | Create a task, make it active, and switch to a new `herd/<slug>` branch cut from the current one (uncommitted changes come along; it warns instead on a detached HEAD or a repository with no commit). `--request` stores the human's message verbatim so `herd check` can flag human criteria that are not quotes |
| `herd init <slug> "<goal>" --quick "<check>"` | Quick route for a trivial change: one criterion, one check. Refused at a `high` risk floor |
| `herd init <slug> "<goal>" --worktree` | The default start: the task on a new `herd/<slug>` branch in its own worktree at `.claude/worktrees/herd-<slug>`, cut from the current local branch, so several agents can run tasks in one repository. `[worktree] required = false` in `herd.toml` allows a plain init |
| `herd check` | Validate `task.toml`; warns about criterion texts over 40 words, coverage notes over 50 words, checks that do not run project code, human criteria that are not quotes, missing `coverage` or `known_limits`, and quantifier or size words (`any`, `every`, `very big`) whose `coverage` does not say what varies or what scale was tried |
| `herd detect` | Propose test and lint commands for Python, Node, Rust, Go and `make test` |
| `herd note --found\|--fixed\|--open\|--tried [--attack <name> --check "<command>"] "text"` | Log a caveat or an adversarial attempt with a timestamp; the report lists them. `--attack` names a standard attack (`bad-input`, `collision`, `one-bad-part`, `recount`) and needs `--check`, a command `herd verify` runs, or text starting `n/a:` |
| `herd triage "<text>" [--json]` | Print the risk floor for a task description in one line (`risk: high (auth/**)`); `--json` prints the full record |
| `herd verify [--verbose]` | Run all checks, including each standard attack's command, store `evidence.json`; exit 1 if any fail. Prints one summary line plus only the criteria that need attention (failing, unchecked, ran zero tests); `--verbose` lists all |
| `herd status` | Show evidence and whether the task is done |
| `herd done [--verbose]` | Write `evidence.md`, close the task; refuses unless fresh and passing and, on the standard route, until each standard attack has a passing command (or an `n/a:` reason). Updates the task's PR description if `herd pr` opened one. Prints two lines; `--verbose` prints the report too |
| `herd cancel --reason "text"` | Abandon the task: keep its files, stop the Stop gate from blocking |
| `herd pr [slug] [--yes]` | Push the `herd/*` branch, open its PR as a draft or update it, with the evidence as the description; never marks it ready, never merges. Needs `--yes` only with `[pr] open = false` |
| `herd setup [--user]` | Install Herd for Codex and other agents: the skills, an `AGENTS.md` block and a Codex Stop gate, in this repository or, with `--user`, in your home ([other agents](#other-agents)) |
| `herd help` | List every command with its usage |
| `herd gate` | The Stop hook (reads hook JSON on stdin) |
| `herd lint` | The optional PostToolUse lint hook; `herd lint --suggest` prints a `[lint]` block for `herd.toml` |

`herd` is `python3 scripts/herd.py`. Inside the plugin it is `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/herd.py"`.

### Project settings (`herd.toml`)

All optional. Without a `herd.toml`, Herd uses the defaults below. This repository's [`herd.toml`](herd.toml) is an annotated example.

| Table | Default | What it does |
| --- | --- | --- |
| `[floor]` | `migrations/**`, `auth/**`, `billing/**` and `herd.toml` are high; `api/**` is medium | Path rules for the risk floor; a high floor means one approval question and no quick route |
| `[worktree] required = false` | on | Each task starts in its own worktree (`herd init --worktree`); `false` allows a plain `herd init` in the current checkout |
| `[pr] open = false` | on | Each task ends in a draft pull request (`herd pr`); with `false`, `herd pr` needs `--yes`, for a request that asks for one |
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
- **Push only its own branch, never merge.** `herd pr` pushes only the task's `herd/<slug>` branch from a clean working tree and opens its pull request as a draft, or updates it. Marking it ready and the merge are yours.

## Status

Version 0.4.0 (see the [changelog](CHANGELOG.md)). Working and covered by 314 unit tests on Python 3.11 to 3.13: the evidence harness (`scripts/herd.py`), the Stop gate, the quick route, project-type detection, the lint hook, the caveat log, zero-test flagging, the `herd pr` step that opens a draft pull request and a worktree per task (both on by default), short output by default, `herd setup` for Codex and other agents, and the risk-floor module. Releases 0.2.7 to 0.3.0 were each built with Herd itself; 0.2.8 to 0.3.0 were opened as pull requests by `herd pr`. Benchmarked on one task with Sonnet (above). Not yet done: many live runs through the installed plugin across different project types, and issue-to-pull-request automation on GitHub (labelled issue to reviewed spec), which is still design work. `herd pr` covers only the last step: a finished local task opens a pull request with its evidence.

## The design behind it

Herd is built with its own method, using the [Elephant-Goldfish Model](https://github.com/google/elephant-goldfish-model): an Elephant agent with full context drafts, and Goldfish reviewers with no context check. The requirements and decisions are in the open:

- [`docs/PRD.md`](docs/PRD.md): the product requirements, principles and roadmap.
- [`docs/designs/`](docs/designs): specs for Triage, the Arbiter (an agent that rules on review findings) and Escalation (one issue to pause and ask a human), each with a tested module in `scripts/` that will power the GitHub automation phase, plus the [v0.2 plan](docs/designs/herd-coco-ideas.md).
- [`docs/spikes/`](docs/spikes): spike S1 ran EGM unattended on these features; the run logs say what each review found and what broke.
- [`docs/backlog.md`](docs/backlog.md): ideas not yet planned, such as an optional Trail Code integration.

## Roadmap

- **Now (v0.4):** local autopilot with evidence, short output by default, the Stop gate, a quick route, project-type detection, an opt-in lint hook, an adversarial pass whose standard attacks `herd done` enforces, the evidence-planning skill, zero-test flagging, an evidence-first draft pull request (`herd pr`) and a worktree per task so several agents can run tasks in one repository (both on by default), and `herd setup` for Codex, open models and other agents that read `AGENTS.md`.
- **Next:** GitHub automation: a labelled issue becomes a reviewed spec, then a pull request, with the Arbiter and Escalation modules.
- **Later:** a release gate for high-risk changes, and live runs in Codex and with open models.

## Development

```bash
python3 -m unittest discover -s tests -t .
ruff check .
claude plugin validate ./
```

Python standard library only, no dependencies. Try the plugin from a clone with `claude --plugin-dir /path/to/herd-sdlc`. When plugin files change, bump `version` in `.claude-plugin/plugin.json` and add a [changelog](CHANGELOG.md) entry, because `claude plugin update` compares version numbers only.

## License

[Apache License 2.0](LICENSE)
