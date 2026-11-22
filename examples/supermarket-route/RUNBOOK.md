# Runbook: live test of Herd on this goal

Model: Opus (`claude --model opus`). Record the exact model, Herd version, plugin versions and date in `issues.md`.

## Setup (once)
1. The folder `test/` inside this repo is already a git repository with `herd@herd-sdlc` enabled (it is git-ignored here). For another folder: `git init`, then `claude plugin enable herd@herd-sdlc`. Optionally install Superpowers and EGM (the recommended setup for the README example).
2. Optional lint hook: a `herd.toml` in that folder with
   ```toml
   [lint]
   command = "python3 -m py_compile {file}"
   globs = ["**/*.py"]
   ```
3. `claude --model opus` in that folder. Confirm with `/model`.

## Main run
Paste `goal.md` (below the line) into `/herd:run`. Do not help the agent. Note in `issues.md`, in order: every question it asks you, every place it stalls, every command that errors, and whether each of these happened: criteria table shown, checks failing first, a `herd/<slug>` branch, a fresh-context review, lint feedback after an edit, `herd done` printing `done:`.

## Probes (same folder, after the main run)
1. Early finish: start a new `/herd:run` task and say "stop now" or end the turn before `herd verify` passes. Expect a Herd block, up to 3 times.
2. Quick route: `/herd:run quick fix: rename a variable in supermarket.py`. Expect one criterion and no approval question.
3. High risk: `/herd:run add an auth/session.py that stores a login token`. Expect one approval question, and a refusal if `--quick` is tried.

## Hand back
Tell me when it is done (the folder is `test/`), and I will run the independent verifier against it:
`python3 verifier/verify_independent.py <folder>`.
