---
name: evidence
description: Decide with a human how to create and check evidence for their project, then write criteria Herd can run. Use when setting up Herd on a project, when criteria are weak or unchecked, or when the user asks how to prove a change works. Interactive; not part of /herd:run.
---

# Plan the evidence

Help the human choose what proves their goal works, for their kind of project. This skill asks questions, so run it on request, not inside `/herd:run` (which asks none).

`herd` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/herd.py"`, run from the project root.

## Steps

1. **Detect.** Run `herd detect`. It lists likely test and lint commands for Python, Node, Rust, Go and `make test`. These are conventions, not facts. Show them and ask the human to confirm or correct each. If the list is empty, ask what command runs the tests. Never assume a command runs real tests: a command that runs zero tests still exits 0.
2. **Ask the gaps, at most 5.** Skip anything you can already answer from the repository or the request:
   - What does "working" look like from the outside, for a user or caller?
   - What can you run yourself to see it?
   - What can you not run (credentials, hardware, production, a human eye)?
   - What must not change (public API, output format, schema)?
   - How slow may a check be? Keep each under a minute, and put slow ones in their own criterion.
3. **Draft criteria.** Follow the `herd:criteria` skill. One observable behaviour per criterion, each with a `check`. Use the strongest evidence the project can run:
   - Library: tests of the public API, plus the type check if there is one.
   - CLI: run it on fixed input and compare stdout and exit code to a stored expected file.
   - Web app: an end-to-end test that asserts on what the user sees.
   - HTTP API: a request against a started server, checked against the schema or expected body.
   - Data pipeline: assertions on output rows, counts and schema, not "the job exited 0".
   - Docs: a build or link check that fails on errors.
   Weak evidence to avoid: a bare `grep`, `test -f`, "the page loads", coverage percentage alone, tests that mock the behaviour being claimed.
4. **Cannot automate it?** Write a proxy check and say so in the criterion text (for example "proxy: screenshot diff"). If nothing runs, leave `check = ""`: the criterion stays `unchecked`, is listed, and is never counted as met.
5. **Check the draft.** Run `herd check`. Fix its warnings or explain them to the human: it flags checks that do not run project code. It is advisory and has gaps, so also read each check yourself and ask whether it could pass while the feature is broken.
6. **Red first.** Run `herd verify` before any work. Checks should fail. The evidence report then prints how many failed before the work, so a check that was green from the start is visible.
7. **Show the evidence.** After the work, run `herd verify` and show the command, exit code and output tail for the human to review. Offer `herd lint --suggest` if the project has a per-file linter: it prints a `[lint]` block for `herd.toml` that gives lint feedback after each edit.

## Notes

- When you find a problem, record it with `herd note --found "..."` (and `--fixed`, `--open`, `--tried`): the report lists them with the time each was found.
- A `test_budget` line in `task.toml` records what is tested at which level and what is deliberately not tested.
- Human-written criteria are never reworded or weakened.
