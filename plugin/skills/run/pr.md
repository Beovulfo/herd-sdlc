# Pull request (opt-in)

Only when the request asks for a pull request, or `herd.toml` has `[pr] open = true`.

1. Commit everything. `herd pr` refuses a dirty working tree.
2. Run `herd pr <slug>`, adding `--yes` when the request asked for the PR. It pushes only `herd/<slug>` and opens a PR whose description is the evidence. A worktree task targets the branch it started from.
   - A draft PR: add `--draft`. A milestone: add `--milestone NAME` (quote a name with spaces). Both also apply to an open PR; leaving one out changes nothing. Any other flag is refused. Never `git push` for this.
3. A criterion that needs the PR to exist: open it before the final `herd verify`.
4. Once the PR exists, every `herd verify` rewrites its description from the new evidence (body only; not with `--only`). A `not refreshed` warning does not change the exit code: fix its cause and verify again.
   - To link an issue, put `Closes #N` after the footer, it is kept: `herd pr`, `herd verify` and `herd done` replace the footer line ("Opened by Herd ...") and everything above it, never the lines below.
5. `herd done` updates the PR description with the final evidence and prints the link. If it prints a warning instead, fix the cause and run `herd pr <slug>` again. The final report it prints names the PR.
6. Never merge. The human reviews the evidence and merges.
