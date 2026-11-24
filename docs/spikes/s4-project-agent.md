# Spike S4: inputs for the project-agent design

Goal: confirm, before any code, the three facts [`herd-project-agent.md`](../designs/herd-project-agent.md) relies on. Run on 2026-11-24 with Claude Code 2.1.330 and git 2.50.1 on macOS.

## Method

1. Read the main session log of a live Claude Code desktop session working in a worktree of this repository (`~/.claude/projects/<project>/<session>.jsonl`) with a short Python script.
2. Ran `claude -p --model haiku` in an empty git repository in a scratch folder, with this branch loaded by `--plugin-dir`, asking a question only the agent's own instructions answer: "what exact final line must your report end with?". The same question without an agent was the control.
3. Ran `git rev-parse --path-format=absolute --git-common-dir` from the main checkout and from a linked worktree.

## Findings

### 1. Read calls and loaded instruction files are in the session log

A Read is an assistant line whose `message.content` holds `{"type": "tool_use", "name": "Read", "input": {"file_path": "<absolute path>"}}`, the same shape `_edited_files` already reads for edits. Subagent Reads are in `<session>/subagents/*.jsonl`, as for edits.

One change to the design: an agent never needs to Read `CLAUDE.md`, because Claude Code loads it into context itself. The log records that as its own line: `{"type": "attachment", "attachment": {"type": "instructions", "files": [{"path": "<absolute path>/CLAUDE.md", "type": "Project", "content": "..."}]}}`. The read check (Part A, A2) must count a file listed in an `instructions` attachment as read, or it would flag every session. Reads done through Bash (`cat`, `sed -n`) are not tool calls and are not seen.

### 2. A plugin agent can be a session's main agent

| Run | Answer |
| --- | --- |
| No agent (control) | `NONE` |
| `--plugin-dir <repo> --agent herd:herd-reviewer` | "`HERD-REVIEW: PASS` if no Blocker or Major finding, otherwise `HERD-REVIEW: FAIL`." |
| `--plugin-dir <repo>`, project `.claude/settings.json` with `{"agent": "herd:herd-reviewer"}` | the same answer |
| `--agent herd:herd-reviewer` without the plugin enabled | `--agent 'herd:herd-reviewer' not found. Available agents: ...` (plugin agents are listed by their plugin-scoped names, such as `egm:egm-style`) |
| `--agent herd-sdlc-engineer` in this repository (a project agent in `.claude/agents/`) | "`change.yaml`, `benchmark.yaml`, `release.yaml`." |

So Part C can work with no subagent fallback: `claude --agent herd:<name>`, or the `agent` setting in a project's `.claude/settings.json`. An unknown name prints the error and the list of available agents, and the command still exits 0.

### 3. One store for all worktrees

`git rev-parse --path-format=absolute --git-common-dir` printed `<repo>/.git` from the main checkout and from the worktree `.claude/worktrees/magical-rhodes-327979`. A store at `<git-common-dir>/herd/lessons.json` (Part B, B1) is shared by every worktree of a clone and is kept when a worktree is removed.

## Not tested

- Whether the `agent` setting in user-level settings also accepts a plugin agent (only the project file was tried).
- Codex and other harnesses.
