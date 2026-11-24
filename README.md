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
  <img src="assets/demo.gif" alt="A real /herd:run session in Claude Code, with a panel above it lighting the current step: intake, criteria, red first, build, break it, review, verify, evidence" width="860">
  <br><sub>A real session with Herd 0.3.2 and Claude Sonnet 5.5, sped up: one message, then intake, criteria, red first, build, break it, review, verify and evidence. The Stop gate blocks one early finish.</sub>
</p>

Herd is a lightweight [Claude Code](https://claude.com/claude-code) plugin that runs a task end to end with as little human input as possible. You give it a goal and, if you like, success criteria. The agent plans, builds, tries to break its own work, verifies and gets a review. It only stops when **runnable checks prove the criteria pass**, and it only asks you something when an action is irreversible or a real trade-off needs a human.

## The problem

Most agent workflows ask people to write long requirement lists, then trust the agent when it says "done". Herd flips that: you give a goal and, if you like, success criteria; the agent returns the code and **evidence** (command output, commit SHA, timestamps). You review evidence, not process.

- **Done means proven.** A Stop hook blocks the agent from finishing until every check passes, with evidence newer than the last edit.
- **Your words stay yours.** Criteria you write are quoted verbatim and never weakened.
- **Caveats surface early.** The agent must try to break its own work and log what it finds.
- **Light.** A small Python CLI on the standard library, no dependencies, plain-text task files.

## Quickstart

You need Claude Code, Python 3.11 or newer as `python3`, and a git repository. CI tests Python 3.13 only.

```text
/plugin marketplace add Beovulfo/herd-sdlc
/plugin install herd@herd-sdlc
```

Then, inside your project, in a new session:

```text
/herd:run Add a --json flag to the export command. Output must be valid JSON with every row.
```

For a trivial change, say "quick fix". To plan how to prove a change for your project type, run `/herd:evidence`. More in the [Quickstart](https://github.com/Beovulfo/herd-sdlc/wiki/Quickstart) page.

## How it works

```mermaid
flowchart LR
    A[Goal] --> B[Intake and risk floor<br/>branch herd/slug<br/>opt-in: own worktree]
    B -->|standard| C[Criteria with checks]
    B -->|trivial: quick route| Q[One criterion, one check]
    C --> R[Red first<br/>checks fail before the work]
    Q --> R
    R --> D[Build: plan, tests first, code]
    D -->|standard| X[Break it<br/>generated cases, scale<br/>6 attacks, each with a command]
    D -->|quick route| F
    X --> F[herd verify<br/>criteria and attack commands]
    F -->|failing| D
    F -->|passing, standard route, medium or high risk| E[Fresh-eyes review<br/>at most 2 without a PASS]
    E -->|Blocker or Major: fix, verify again| D
    E -->|PASS that counts| G[herd done<br/>evidence report]
    F -->|passing, low risk or quick route| G
    S[Stop hook] -.->|blocks finishing until the conditions hold| G
    G -->|opt-in| P[herd pr<br/>PR with the evidence]
```

Every criterion has a `check`, a shell command where exit 0 means pass. The checks run once before any work and should fail. The agent then builds, tries to break the result with six standard attacks, verifies, and at medium and high risk gets a fresh-context review. `herd done` writes the evidence report. With `herd pr` (opt-in) that report is the pull request description; Herd never merges.

## Settings

All optional, in `herd.toml` at the project root. Without it, Herd uses these defaults.

| Table | Default | What it does |
| --- | --- | --- |
| `[floor]` | `high`: `migrations/**`, `auth/**`, `billing/**`, `herd.toml`; `medium`: `api/**`; any other path is medium | Risk floor by path; a high floor means one approval question and no quick route |
| `[review]` | `tiers = ["haiku", "sonnet", "opus"]`, `step = 1` | The reviewer is `step` tiers above the builder, capped at `sonnet`, never below the builder |
| `[worktree] required = true` | off | Every task starts in its own git worktree |
| `[pr] open = true` | off | Herd may push the task branch and open its pull request |

All settings: [Settings](https://github.com/Beovulfo/herd-sdlc/wiki/Settings).

## Learn more

- [How Herd works](https://github.com/Beovulfo/herd-sdlc/wiki/How-Herd-works): the steps, parallel tasks, architecture, autonomy rules
- [Example](https://github.com/Beovulfo/herd-sdlc/wiki/Example): a task, its evidence and its pull request
- [Attacks](https://github.com/Beovulfo/herd-sdlc/wiki/Attacks), [Review](https://github.com/Beovulfo/herd-sdlc/wiki/Review), [Hooks and guard](https://github.com/Beovulfo/herd-sdlc/wiki/Hooks-and-guard)
- [Commands](https://github.com/Beovulfo/herd-sdlc/wiki/Commands) and [Settings](https://github.com/Beovulfo/herd-sdlc/wiki/Settings)
- [Benchmark](https://github.com/Beovulfo/herd-sdlc/wiki/Benchmark): one task, with and without Herd, with its limits
- [Design and roadmap](https://github.com/Beovulfo/herd-sdlc/wiki/Design-and-roadmap), [requirements](docs/PRD.md), [changelog](CHANGELOG.md)

## Status

Version 0.12.12 (see the [changelog](CHANGELOG.md)). The local autopilot works and has unit tests that CI runs on Python 3.13. Not yet done: many live runs across project types, and issue-to-pull-request automation on GitHub. Checks run as shell commands with your permissions: read a task file as you read code.

## License

[Apache License 2.0](LICENSE)
