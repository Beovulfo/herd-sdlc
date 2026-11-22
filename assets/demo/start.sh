#!/bin/zsh
# Start a clean Claude Code session for the demo, without the host session's environment.
for v in ${(k)parameters[(I)CLAUDE*]}; do unset $v; done
cd /tmp/herd-demo/textutil
exec claude --plugin-dir /tmp/herd-demo/herd-plugin --model sonnet --permission-mode acceptEdits --allowedTools Bash
