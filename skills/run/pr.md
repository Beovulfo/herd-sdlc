# Pull request

Every task ends in a draft pull request, unless `herd.toml` has `[pr] open = false`; then only when the request asks for one.

1. Commit everything. `herd pr` refuses a dirty working tree.
2. Run `herd pr <slug>`, adding `--yes` only when `open = false` and the request asked for the PR. It pushes only `herd/<slug>` and opens a draft PR whose description is the evidence. A worktree task targets the branch it started from.
3. If `herd pr` fails (no `origin` remote, no `gh`, not signed in), never block on it: run `herd verify` and `herd done`, and put its message in the final report.
4. A criterion that needs the PR to exist: open it before the final `herd verify`.
5. `herd done` updates the PR description with the final evidence and prints the link. If it prints a warning instead, fix the cause and run `herd pr <slug>` again. Put the PR link in the final report.
6. Never mark it ready and never merge. The human reviews the evidence, marks it ready and merges.
