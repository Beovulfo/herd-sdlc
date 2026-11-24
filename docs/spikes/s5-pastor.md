# Spike S5: inputs for the pastor design

Goal: confirm, before any code, the three facts [`herd-pastor.md`](../designs/herd-pastor.md) relies on. Run on 2026-11-24 with Claude Code 2.1.330 and `claude -p --model haiku` on macOS.

## Method

An empty git repository in a scratch folder with:

- `.claude/agents/pip.md`, a project agent whose only instruction is to answer a question with a fixed token;
- `.claude/settings.local.json` with `"agent": "pip"` and a `SessionStart` hook that saves its input to a file and prints `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "The spike word is ..."}}`;
- both files left untracked (never committed).

Each run asked for the agent's token and the hook's word. Then `git worktree add ../wt`, a sibling folder (so not found by walking up), and the same question from inside it.

## Findings

| Run | Answer |
| --- | --- |
| Main checkout, `agent` in `.claude/settings.local.json` | the agent's token and the hook's word |
| Main checkout, `--settings '{"agent": ""}'` (control) | `NONE` |
| Linked worktree, no `.claude/` folder in it | the agent's token |
| Linked worktree, `--agent pip` | the agent's token |
| `--agent egm:egm-style`, and `--settings '{"agent": "egm:egm-style"}'` (a plugin agent) | hook input `agent_type: "egm:egm-style"` in both |

1. **A project agent named in `.claude/settings.local.json` is the main agent.** Spike S4 showed this for `.claude/settings.json` and a plugin agent; the local file and a project agent work the same way.
2. **A SessionStart hook can add context and knows the main agent.** Its `additionalContext` reached the model. Its input was `{"session_id", "transcript_path", "cwd", "scratchpad_dir", "agent_type", "hook_event_name", "source"}`, with `agent_type: "pip"` and `source: "startup"`. With `--settings '{"agent": ""}'` the key was absent. A plugin agent, chosen by `--agent` or by the `agent` setting, arrives with its plugin-scoped name (`egm:egm-style`).
3. **A linked worktree uses the main checkout's untracked `.claude/` files.** The worktree had no `.claude/` folder and was not below the main checkout, yet the session found the agent and the `agent` setting. So a pastor kept out of git still works in every worktree of the clone.

## Not tested

- Whether a tracked `.claude/agents/<name>.md` in the worktree takes precedence over the main checkout's copy when both exist.
- Claude Code versions other than 2.1.330, and other harnesses.

## Note for design v5 (2026-11-24)

Design v5 moved the pastor out of the product repository into a kennel plugin. Findings 1 and 3 served v4's in-repository pastor and no longer apply. Finding 2 (`agent_type` carries a plugin agent's scoped name, such as `egm:egm-style`) still supports starting a kennel pastor with `--agent <name>:<name>`. The open questions for v5 are in spike S6, listed in the design.
