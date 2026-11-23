# Changelog

All notable changes to Herd. Versions follow `.claude-plugin/plugin.json`.

## 0.4.0

Herd outside Claude Code: OpenAI Codex, open models, and other agents that read `AGENTS.md`.

- **Added:** `herd setup [--user]`. It renders the three skills as `herd-run`, `herd-criteria` and `herd-evidence`, with `${CLAUDE_PLUGIN_ROOT}` replaced by the absolute path of this Herd copy and `/herd:<skill>` names replaced by `herd-<skill>`. It also writes a Herd block to `AGENTS.md` (the `herd` command, where the skills are, and the rule never to stop before `herd done` succeeds) and the Stop gate to a Codex `hooks.json`. Codex's Stop hook takes the same `{"decision": "block", "reason": ...}` output that `herd gate` already prints. Project mode writes `.agents/skills/`, `AGENTS.md` and `.codex/hooks.json` in the repository and adds the skill folders to `.git/info/exclude`; `--user` writes `~/.agents/skills/`, `$CODEX_HOME/AGENTS.md` and `$CODEX_HOME/hooks.json`. It keeps the user's own content in both files, replaces only Herd's entries on a rerun (also from a moved copy), and refuses a `hooks.json` it cannot merge without writing anything.
- **Changed:** the run skill says that where the agent has no Stop hook, it must never stop before `herd done` succeeds.
- **Docs:** the README has an "Other agents" section: what works with Claude Code, Codex, open models served by Unsloth Studio or `llama-server` and driven by Codex or Claude Code, and other agents that read `AGENTS.md`. Where there is no Stop hook, only the `AGENTS.md` rule holds. The lint hook stays Claude Code only.

## 0.3.2

- **Changed:** each standard attack names a command. `herd note --tried --attack <name>` needs `--check "<command>"`, usually a regression test, or text starting `n/a:` when the attack cannot apply. `herd verify` runs these commands like criterion checks and stores their exit code and output. `herd done` and the Stop gate count an attack only when its command passed at the last verify (one that ran zero tests or was logged after the last verify does not count), or when it is marked `n/a:`. Commands rerun at every verify, so one failing command blocks its attack however many others pass. An attack note with no command counts only as a stated `n/a:`, so notes from 0.3.1 or a hand-edited log do not pass the gate. `herd verify` prints attacks that need attention (all of them with `--verbose`) and exits 1 when one fails. The latest note for an attack decides, so a mistyped or renamed command can be replaced; earlier commands that now fail stay listed in the PR. A command that runs no project code (`true`, `echo`, `test -f`) warns and does not count. `--timeout S` sets an attack command's time limit; each distinct command runs once per verify. Before, a note was only text: a benchmark run logged three attacks as tried before running them, and the gate accepted them.
- **Changed:** the report and the PR description show each attack's state and command (`bad-input passing (`...`)`, `collision n/a`, failing, ran zero tests, or missing); the PR lists attacks without a passing command under what is not proven.

## 0.3.1

Quality first. A benchmark rerun with 0.3.0 was 3% cheaper than 0.2.4 but scored 45 of 48 on the hidden verifier and 0 of 6 on the robustness probe (0.2.4: 48 and 6). Its agent never opened `adversarial.md`, which 0.3.0 had made an optional reference file. A rerun with a first draft of this version, whose agent did read the file, scored 48 of 48 and 6 of 6.

- **Added:** on the standard route, `herd done` and the Stop gate refuse until each of four standard attacks has a recorded attempt, `herd note --tried --attack <name> "..."`: `bad-input` (bad input at every entry point ends in one clear message and a non-zero exit, never a traceback), `collision` (two inputs on the same key or position each still count), `one-bad-part` (a broken entry the request does not ask for does not reject the whole input, while a broken or unreachable requested one still fails with a clear message) and `recount` (every reported number recomputed from the output with separate code). The refusal lists the missing attacks, so an agent that skipped the skill file still learns them. An attack that cannot apply is logged with the reason.
- **Changed:** each adversarial rule is written once. Step 6 of the run skill points to `adversarial.md` and the `herd done` gate instead of repeating the attacks; the note-timing rule is in the run skill's Rules, for every step; empty and malformed input belong to `bad-input` only. An existing test counts for an attack only if it meets that attack's rule, logged with its name and what it covers.
- **Changed:** the report and the PR description say which standard attacks are logged (`Adversarial pass: 5 attempts recorded; standard attacks all logged`, or the missing ones).
- **Docs:** `CLAUDE.md`, the PRD status line, the evidence skill and the README describe the enforced attacks and the mandatory reference reads.
- **Changed:** the run skill makes reading a reference file mandatory when its step applies, and step 6 names the four attacks inline. Its word budget goes from 800 to 900.
- **Added:** a plain `herd init` creates branch `herd/<slug>` from the current branch and switches to it, recording the base for `herd pr`. Uncommitted changes come along. It warns instead of failing on a detached HEAD, a repository with no commit, or an existing branch; outside git it does nothing. Before, the branch was only a sentence in the run skill, and a benchmark run built on `main`.
- **Added:** a plain `herd init` refuses while another task in the same checkout is active (finish it, cancel it, or use `--worktree`). Before, it silently replaced the active task.
- **Added:** `herd pr` records the PR, and `herd done` updates its description with the final evidence. Before, the agent had to remember to run `herd pr` again.
- **Fixed:** parallel `herd init --worktree` calls could fail with `failed to read .git/worktrees/.../commondir`, because git reads every worktree's admin files while another add is half done. The `git worktree add` call now takes a file lock in the git directory (Unix; Windows has no `flock`). This made one CI run on main fail.

## 0.3.0

Herd is short by default. Measured on this repository: the three skills went from 2,592 to 1,662 words (run: 1,286 to 777), a passing `herd verify` from one line per criterion to one line, and `herd done` from the full report (about 1,000 words) to two lines.

- **Changed:** `herd verify` prints one summary line plus only the criteria that need attention (failing, unchecked, ran zero tests); `--verbose` lists all. `herd done` prints two lines (result and the path to `evidence.md`); `--verbose` prints the report. `herd triage` prints one line (`risk: high (auth/**)`, or the config error when `herd.toml` is broken); `--json` prints the full record.
- **Changed:** the run skill is 777 words. The quick route, the worktree start, the adversarial pass and the PR step moved to reference files (`skills/run/quick.md`, `worktree.md`, `adversarial.md`, `pr.md`) that the agent reads only when the step applies. The criteria and evidence skills are under 450 words each.
- **Added:** a fixed final report: seven lines (done, proven, not proven, caveats, decisions, limits, review), filled from `evidence.md`, that link the evidence instead of repeating it, and writing rules in the run skill (answer first, no recap, never drop a negation, numbers and commands exact).
- **Changed:** the PR description shows the result, what is proven and what is not; run details, the caveat log and Reproduce are collapsed `<details>` blocks. Long check commands are cut to 60 characters in the table and kept in full under Reproduce.
- **Added:** `herd check` warns when a criterion text is over 40 words or a coverage note over 50 words.
- **Added:** budget tests (`TestBudgets`) keep these sizes from creeping back.

## 0.2.9

- **Added:** `herd init <slug> "<goal>" --worktree` starts a task on a new `herd/<slug>` branch in its own git worktree at `.claude/worktrees/herd-<slug>`, cut from the local branch you are on. The task's files and active pointer live in that worktree, so several agents can run Herd tasks in one repository at once; a duplicate slug fails cleanly, and a failed init removes the worktree and branch it made. The base branch is recorded and `herd pr` targets it. Uncommitted changes left in the starting checkout are reported.
- **Added:** `[worktree] required = true` in `herd.toml` (opt-in) makes a plain `herd init` refuse outside a linked worktree on `herd/<slug>`.
- **Added:** `herd` commands run from the starting checkout for a task that lives in a worktree refuse and name the worktree, so a forgotten move fails loudly.
- **Added:** `--worktree` adds `/.claude/worktrees/` and `.herd/` to the repository's own `.git/info/exclude` (never committed), so the main checkout's `git status` stays clean, a `git add -A` cannot pick up another agent's worktree, and `git worktree remove` works.
- **Fixed:** the Stop gate and the CLI find the task from any subdirectory: the root is the nearest folder with `.herd/` or `herd.toml`, so a project in a subfolder of a repository keeps its own tasks.
- **Changed:** the run skill's intake step covers the worktree start; the README and `herd.toml` describe it.
- **Docs:** the README is brought up to date for 0.2.7 to 0.2.9: why-use-it points, a Quickstart example asking for a worktree and a PR, a "Several tasks at once" section, `herd pr` in both diagrams and an example PR description, a table of the `herd.toml` settings, the push and merge rule, and the status and roadmap.

## 0.2.8

- **Added:** `herd pr [slug] [--yes]`, an opt-in pull request step. It runs only with `[pr] open = true` in `herd.toml` or `--yes` (which the run skill passes when the request asks for a PR). It pushes the task's `herd/<slug>` branch, refuses any other branch, and opens a pull request, or updates the one that exists. The description is the evidence, first: the result and freshness, a table of what is proven and the check that proved each item, what is not proven (failing and unchecked criteria, zero-test runs, coverage gaps, known limits, open caveats), run details, and the check commands to reproduce. It refuses a dirty working tree, leaves check output out of the description, and lists at most 60 caveats. It never merges.
- **Changed:** the run skill has an opt-in step 11 that uses `herd pr`; the README, `herd.toml` and `CLAUDE.md` describe it.

## 0.2.7

- **Added:** `herd verify` flags a check that exits 0 while its output says it ran zero tests (unittest, pytest, cargo, go, jest and mocha wording). The evidence records `zero_tests`, `herd verify` marks the line `(ran zero tests)` and the report warns. It reads the full output, not only the stored tail, and a run where any suite executed tests is not flagged (cargo's empty doc-tests, go packages without tests). Advisory only: the Stop gate and `herd done` do not change. The README, the run skill and the evidence skill describe it.

## 0.2.6

- **Fixed:** the hooks no longer crash on Python older than 3.11, such as the 3.9 `python3` that ships with macOS. They exit quietly, and the CLI says which version it needs.
- **Changed:** Python 3.11 is now the minimum, down from 3.13. Path globs use `PurePosixPath.full_match` on 3.13 and a tested equivalent on 3.11 and 3.12. CI runs on all three.
- **Added:** `herd cancel [slug] [--reason "text"]` abandons a task. Its files stay as a record and the Stop gate stops blocking. The run skill uses it only when the human drops the task.
- **Added:** every command prints its usage line when arguments are missing. `herd help` lists all commands; an unknown command says so.
- **Changed:** tests moved to `tests/` (`python3 -m unittest discover -s tests -t .`), and `ruff check .` runs in CI.
- **Docs:** the PRD moved to `docs/PRD.md`, `docs/spikes/` keeps the run logs and an index (the raw review reports are in git history), `CLAUDE.md` is a contributor guide, `herd.toml` is annotated, and the README has an architecture section.

## 0.2.5

- The evidence report flags caveat notes logged in a batch (3 or more within 5 seconds), because their times then show when they were written, not when found.
- The benchmark focuses on the Sonnet pair, with and without Herd.

## 0.2.4

- Logo and plugin icon.
- The supermarket route benchmark: a hidden general verifier, a robustness probe, and the results with and without Herd.

## 0.2.3

- `herd check` warns when a human criterion uses quantifier or size words (`any`, `every`, `very big`) and its `coverage` does not say what varies or what scale was tried.
- `herd note --found|--fixed|--open|--tried` logs caveats with timestamps; the report lists them.
- The run skill has an adversarial "break it" step before review.

## 0.2.2

- Criteria take a `coverage` note and tasks a `known_limits` field; `herd check` warns when they are missing.
- Commands fall back to the only task when none is active.
- The run skill reports a skipped review instead of stopping to ask.

## 0.2.1

- Version bump so installed copies pick up the files added after 0.2.0.
- The evidence records elapsed time since `herd init`, and flags human criteria that are not verbatim quotes of the request.

## 0.2.0

- Quick route for trivial changes (`herd init --quick`), refused at a high risk floor.
- `herd detect` proposes test and lint commands for Python, Node, Rust, Go and `make test`.
- Opt-in per-file lint hook after edits.
- The evidence skill (`/herd:evidence`).
- The first verify records how many checks failed before the work.

## 0.1.0

- The evidence harness (`herd init`, `check`, `verify`, `status`, `done`), the Stop gate with a 3-block circuit breaker, and the run and criteria skills.
- Triage, Arbiter and Escalation modules, built test-first from EGM-reviewed designs.
