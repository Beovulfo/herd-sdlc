# S3: Herd in a live Codex session with a local open model

**Question.** After `herd setup --user`, does a real Codex session read Herd's rules, and does the Stop gate fire?

**Answer, 2026-11-23.** The `AGENTS.md` block was read. No hook from `hooks.json` ran, not even a trivial one. The cause is not known.

## Setup

- Codex CLI 0.139.0 (`codex --version`), `features.hooks` stable and on (`codex features list`).
- Ollama 0.40.17 with `qwen3` (8B), driven through `codex exec --oss --local-provider ollama`.
- A fresh `CODEX_HOME` and `HOME` in a scratch folder, so the user's own Codex config was not read or changed.
- A scratch git repository with an active, failing quick task: `herd init live "Write ok.txt" --quick "<check that ok.txt exists>"`, then `herd verify` (1 failing).
- `HOME=<scratch>/home CODEX_HOME=<scratch>/codex python3 scripts/herd.py setup --user`.

## Runs

Each run, from the scratch repository, with stdin closed:

```bash
CODEX_HOME=<scratch>/codex codex exec --oss --local-provider ollama -m qwen3 \
  -s read-only --skip-git-repo-check --dangerously-bypass-hook-trust \
  "Reply with the single word hi. Do not run any commands." < /dev/null
```

1. Herd's Stop hook only. The model answered `hi`. Its reasoning cited the Herd instructions ("if the user asks for a Herd run, I should follow the SKILL.md file"), so `$CODEX_HOME/AGENTS.md` was in its context. No `gate_blocks` file appeared in the task folder, so `herd gate` did not run or did not block.
2. A second Stop hook added, `cat > <scratch>/stop-input.json`. No file appeared.
3. `-s workspace-write`, the probe writing into the repository, and a `SessionStart` hook doing the same. Neither file appeared.
4. `--json` and `RUST_LOG=codex_hooks=trace`. The event stream had `thread.started`, a warning that `--dangerously-bypass-hook-trust` is enabled, `turn.started`, the answer and `turn.completed`. There were no hook events and no hook log lines.

The first `codex exec --oss` run pulled the 4.9 GB `qwen3` model through Ollama on its own, although it was already listed by `ollama list`.

## What this means

- The rules in `AGENTS.md` reach a local open model in Codex.
- The Codex Stop gate is configured as Codex's source describes (`codex-rs/protocol/src/hooks.rs`, `codex-rs/hooks/schema/generated/stop.command.*.schema.json`), and `tests/test_herd_setup.py` runs its command with Codex's Stop input. It was not seen firing in `codex exec`. Not tried: the interactive `codex` CLI with the hook trusted in `/hooks`, and a hosted OpenAI model.
- Until a live run shows the gate firing, treat Codex as an agent with only the rule, and check `herd status` yourself.

## Sources for the open-model claims

- Unsloth runs open models in Codex through Unsloth Studio or `llama-server` with the Responses API, and `unsloth start codex` uses its own Codex home: <https://unsloth.ai/docs/basics/codex>, <https://unsloth.ai/docs/integrations/unsloth-start>.
- Unsloth runs them in Claude Code through `unsloth start claude` or `ANTHROPIC_BASE_URL`: <https://unsloth.ai/docs/basics/claude-code>.
