#!/bin/zsh
# Start a clean Claude Code session for the demo, without the host session's environment.
# Set up and run from a private folder that the caller makes:
#   HERD_DEMO_DIR=$(mktemp -d)
#   cp start.sh demo.tape "$HERD_DEMO_DIR/"
#   mkdir "$HERD_DEMO_DIR/herd-plugin"
#   git archive HEAD:plugin | tar -x -C "$HERD_DEMO_DIR/herd-plugin"
#   mkdir "$HERD_DEMO_DIR/textutil" && cp textutil.py "$HERD_DEMO_DIR/textutil/" && git -C "$HERD_DEMO_DIR/textutil" init && git -C "$HERD_DEMO_DIR/textutil" add -A && git -C "$HERD_DEMO_DIR/textutil" commit -m init
#   cd "$HERD_DEMO_DIR" && vhs <path to>/demo.tape
: ${HERD_DEMO_DIR:?HERD_DEMO_DIR is not set: make a private folder with mktemp -d and export it as HERD_DEMO_DIR}
# No user settings (plugins, hooks) and no MCP servers: only the Herd copy above is loaded.
for v in ${(k)parameters[(I)CLAUDE*]}; do unset $v; done
cd "$HERD_DEMO_DIR/textutil"
exec claude --strict-mcp-config --setting-sources project,local \
  --plugin-dir "$HERD_DEMO_DIR/herd-plugin" --model sonnet --permission-mode acceptEdits --allowedTools Bash Skill Read
