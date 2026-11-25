# r/ClaudeCode post

> Rules **NOT verified**: read the sidebar rules logged in before posting: self-promotion, flair, disclosure.
>
> Week 2. Post it on a different day from the r/ClaudeAI one. An AI drafted this. Edit it so it says what you mean.

**Title:** Using a Stop hook so Claude Code cannot just say "done" (my plugin, open source)

**Body:**

Disclosure: I wrote this plugin, Herd. It is Apache 2.0. An AI helped me draft this post.

The hooks it uses:

- `Stop`: reads the stored evidence of the active task. If a check fails, or the work changed since the last run, it returns `{"decision": "block", "reason": ...}`.
- `PreToolUse`: a guard that denies edits to secrets and to Herd's state files, and irreversible git and GitHub commands, while a task is active.
- `PostToolUse`: optional lint after each edit.
- `SubagentStop`: records which model did the design.

Things worth knowing if you write your own Stop hook:

- Mine does not run the tests. It reads what the last `herd verify` stored, so the hook stays inside its timeout.
- It blocks at most 3 times, then lets the session stop and records why. A hook that blocks for ever is a loop.
- A corrupt state file blocks with a message instead of crashing the hook.

Cost, since someone will ask: on the supermarket benchmark task, Claude Haiku 5.5 with Herd 0.3.1 cost $0.29 per run against $0.04 with no workflow, 6 runs each. Those Herd runs were emulated sessions, and the current version has no run of the full benchmark.

Limits: a weak check passes weakly. The guard matches patterns and is not a sandbox.

Code: https://github.com/Beovulfo/herd-sdlc (the gate is `gate()` in `plugin/scripts/herd.py`).

How do you stop your agent from finishing early?
