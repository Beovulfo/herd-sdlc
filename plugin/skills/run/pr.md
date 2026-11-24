# Pull request (opt-in)

Only when the request asks for a pull request, or `herd.toml` has `[pr] open = true`.

1. Commit everything. `herd pr` refuses a dirty working tree.
2. Run `herd pr <slug>`, adding `--yes` when the request asked for the PR. It pushes only `herd/<slug>` and opens a PR whose description is the evidence. A worktree task targets the branch it started from.
3. A criterion that needs the PR to exist: open it before the final `herd verify`.
4. `herd done` updates the PR description with the final evidence and prints the link. If it prints a warning instead, fix the cause and run `herd pr <slug>` again. The final report it prints names the PR.
5. Never merge. The human reviews the evidence and merges.
