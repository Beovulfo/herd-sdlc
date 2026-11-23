# Quick route

For a trivial change: one file, no new behaviour surface, and an existing command that can fail first.

1. Run `herd init <slug> "<goal>" --quick "<check>" --request "<the user's message, verbatim>" --worktree` and move into the worktree ([worktree.md](worktree.md)); leave out `--worktree` only when `herd.toml` has `[worktree] required = false`. It refuses a `high` risk floor: then use the standard route.
2. Skip triage, criteria, the gate, break it and review: continue at run step 3 (red).
3. Still required: red first (`herd verify` fails), build, `herd verify` passes, `herd done`, the final report.
