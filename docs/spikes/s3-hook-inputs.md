# Spike S3: hook inputs for the guard and the review hook

Goal: confirm, before any code, the hook inputs and outputs that [`herd-guardrails.md`](../designs/herd-guardrails.md) relies on. Run on 2026-11-23 with Claude Code 2.1.330.

## Method

1. Read the current docs: [hooks](https://code.claude.com/docs/en/hooks), [subagents](https://code.claude.com/docs/en/sub-agents), [plugins reference](https://code.claude.com/docs/en/plugins-reference).
2. Ran two live `claude -p --model haiku` sessions with a throwaway plugin loaded by `--plugin-dir`. The plugin had one agent, `agents/probe-reviewer.md` (`model: inherit`), and hooks that saved their stdin to files. The prompt asked for one Bash command, one Write, and a `probe-reviewer` subagent spawned with `model: sonnet`. The second run added a PreToolUse hook that denies `rm -rf`, and two SubagentStop entries with matchers `^probe:probe-reviewer$` and `^nomatch$`.
3. Read the transcripts the sessions left under `~/.claude/projects`, and older transcripts of this project.

## Findings

### 1. SubagentStop input

Live input, with paths shortened:

```json
{
  "session_id": "2999bf35-...",
  "transcript_path": "~/.claude/projects/<project>/2999bf35-....jsonl",
  "cwd": "<project>",
  "permission_mode": "auto",
  "agent_id": "a1301c29d31dfda2a",
  "agent_type": "probe:probe-reviewer",
  "hook_event_name": "SubagentStop",
  "stop_hook_active": false,
  "agent_transcript_path": "~/.claude/projects/<project>/2999bf35-.../subagents/agent-a1301c29d31dfda2a.jsonl",
  "background_tasks": [{"id": "a1301c29d31dfda2a", "type": "subagent", "status": "running", "agent_type": "probe:probe-reviewer"}],
  "session_crons": []
}
```

- `session_id`, `transcript_path` (the main session), `agent_id`, `agent_type`, `agent_transcript_path` and `stop_hook_active` all exist, as expected.
- **`agent_type` of a plugin agent is plugin-scoped:** `probe:probe-reviewer`, not `probe-reviewer`. Herd's reviewer will be `herd:herd-reviewer`.
- The docs list `last_assistant_message` for SubagentStop. **It was absent** in this session. Here the subagent ended with a `SubagentHandback` tool call whose `input.message` held its report; it wrote no final text block. The verdict line was in that tool input.
- A SubagentStop matcher matches the agent type as a regex: `^probe:probe-reviewer$` ran, `^nomatch$` did not.

### 2. Models and timestamps in transcripts

- Every `assistant` line carries `message.model` and a top-level `timestamp`. Main session: `claude-haiku-5-5` on each line, for example `2026-11-23T22:59:25.413Z`. Subagent: `claude-sonnet-5-5`, `isSidechain: true`.
- Timestamps have milliseconds; Herd's own times (`started`) do not. Compare parsed times, not strings.
- In this project's older transcripts, 2,554 assistant lines all had a real model id. The design still treats any id that matches no tier (such as `<synthetic>`, used for messages the client makes up) as unknown.
- `start.json` has no time. The task's start time is the `started` file, written by `herd init`.

### 3. Plugin agents and the model override

- A plugin can ship `agents/<name>.md`; it loaded with no other setup. The docs: "an agent `reviewer` in plugin `deploy-tools` appears as `deploy-tools:reviewer`."
- The Agent tool's `model` overrides the frontmatter. With `model: inherit` in the file and a Haiku main session, the Agent call with `model: sonnet` ran the subagent on `claude-sonnet-5-5`. The docs give the order: the per-invocation `model` parameter first, then the agent's `model` field, then `CLAUDE_CODE_SUBAGENT_MODEL`, then the main model. The Agent parameter takes an alias only.
- When `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` is set, Claude cannot pass a model. The review hook still reads the model from the transcript, so a forced model is judged like any other.
- Plugin agents ignore the `hooks`, `mcpServers` and `permissionMode` frontmatter.

### 4. PreToolUse input and the deny output

- Input fields seen live: `tool_name`, `tool_input.command` (Bash), `tool_input.file_path` (Write), `cwd`, `transcript_path`, `tool_use_id`. The docs give `notebook_path` for NotebookEdit; Herd already reads it in `herd preinit`.
- The deny output works as the design expects. The hook printed `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "PROBE-DENY: not allowed"}}`, the command did not run (the folder was still there), and the agent saw `PreToolUse:Bash hook error: PROBE-DENY: not allowed`.
- The docs: "When multiple PreToolUse hooks return different decisions, precedence is `deny` > `defer` > `ask` > `allow`." So the guard's deny wins over another hook's allow.

### Side observation

In both runs the main agent, in auto mode, said the subagent's report was flagged "Undermining Oversight" and that it would not rely on it. The probe agent's prompt only said to end with `HERD-REVIEW: PASS`, with no review. The hook still received the event and the transcript, so recording does not depend on the main agent trusting the report. A real reviewer that reads the diff may not be flagged; this was not tested.

## Changes to the design

1. B3 step 1 matches `agent_type == "herd:herd-reviewer"`, and the SubagentStop entry in `hooks/hooks.json` uses the matcher `^herd:herd-reviewer$`, so Python starts only for the reviewer. A project's own `.claude/agents/herd-reviewer.md` (type `herd-reviewer`) does not count: its prompt is not Herd's.
2. B3 step 2: the reviewer's final text is the last of its assistant text blocks and `SubagentHandback` `input.message` values in its transcript. If the transcript has neither, the hook input's `last_assistant_message` is used.
3. B3 steps 2 and 3: the reviewer's model is its last assistant `message.model` other than `<synthetic>`; the builder's lines are the main transcript's assistant lines at or after the `started` time.
