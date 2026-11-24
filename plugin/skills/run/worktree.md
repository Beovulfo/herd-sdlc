# Own worktree

`herd init <slug> "<goal>" --worktree` creates branch `herd/<slug>` in a worktree at `.claude/worktrees/herd-<slug>`, cut from the current branch, and prints the path.

1. Move in before anything else. Claude Code: call EnterWorktree with that path. Otherwise: `cd` into it.
2. Run every later edit and command from there.
3. A `herd` command that says "lives in its worktree" means you are in the wrong place: move there.
4. Never start a second task in a checkout that already has an active one. A plain `herd init` refuses while another task there is active.
5. Uncommitted changes in the starting checkout are not carried over; init warns when there are some.
