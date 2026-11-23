---
name: evidence
description: Decide with a human how to create and check evidence for their project, then write criteria Herd can run. Use when setting up Herd on a project, when criteria are weak or unchecked, or when the user asks how to prove a change works. Interactive; not part of /herd:run.
---

# Plan the evidence

Choose with the human what proves their goal works. This skill asks questions: run it on request, never inside `/herd:run`. `herd` is `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/herd.py"`, run from the project root.

## Steps

1. **Detect.** Run `herd detect` and show the proposed test and lint commands. They are conventions, not facts: ask the human to confirm or correct each. Empty list? Ask what runs the tests. A command that runs zero tests still exits 0; `herd verify` flags common runners only, so read the command yourself.
2. **Ask the gaps, 5 questions at most.** Skip what the repository or request already answers:
   - What does "working" look like to a user or caller?
   - What can you run to see it?
   - What can you not run (credentials, hardware, production, a human eye)?
   - What must not change (API, output format, schema)?
   - How slow may a check be? Under a minute each; slow ones get their own criterion.
3. **Draft criteria** with the `herd:criteria` skill. Use the strongest evidence the project can run:
   - Library: tests of the public API, plus the type check.
   - CLI: fixed input, compare stdout and exit code to a stored expected file.
   - Web app: an end-to-end test that asserts on what the user sees.
   - HTTP API: a request against a started server, checked against the schema or body.
   - Data pipeline: assertions on output rows, counts and schema.
   - Docs: a build or link check that fails on errors.
   Avoid weak evidence: a bare `grep` or `test -f`, "the page loads", coverage percentage alone, tests that mock the claimed behaviour.
4. **Cannot automate it?** Write a proxy check and say so in the text ("proxy: screenshot diff"). If nothing runs, leave `check = ""`: it stays `unchecked`, never counted as met.
5. **Check the draft.** Run `herd check`. Fix or explain each warning. It has gaps: also ask of each check whether it could pass while the feature is broken.
6. **Red first.** Run `herd verify` before any work. Checks should fail.
7. **Show the evidence** after the work: the command, exit code and output of `herd verify --verbose`. Offer `herd lint --suggest` if the project has a per-file linter.

Record problems with `herd note --found|--fixed|--open|--tried "..."` (`--tried --attack <name> --check "<command>"` for a run-skill attack). Never reword or weaken human criteria.
