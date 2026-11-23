# Pull request (opt-in)

Only when the request asks for a pull request, or `herd.toml` has `[pr] open = true`.

1. Commit everything. `herd pr` refuses a dirty working tree.
2. Run `herd pr <slug>`, adding `--yes` when the request asked for the PR. It pushes only `herd/<slug>` and opens a PR whose description is the evidence. A worktree task targets the branch it started from.
3. A criterion that needs the PR to exist: open it before the final `herd verify`.
4. After `herd done`, run `herd pr <slug>` again so the description shows the final evidence. Put the PR link in the final report.
5. Never merge. The human reviews the evidence and merges.
