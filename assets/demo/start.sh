#!/bin/zsh
# Start a clean Claude Code session for the demo, without the host session's environment.
# /tmp/herd-demo/herd-plugin is the plugin at the version being shown:
#   git archive main .claude-plugin hooks scripts skills | tar -x -C /tmp/herd-demo/herd-plugin
for v in ${(k)parameters[(I)CLAUDE*]}; do unset $v; done
cd /tmp/herd-demo/textutil
exec claude --plugin-dir /tmp/herd-demo/herd-plugin --model sonnet --permission-mode acceptEdits --allowedTools Bash
