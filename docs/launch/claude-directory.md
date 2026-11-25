# Claude plugin directory submission

Sources: <https://code.claude.com/docs/en/plugins/publish.md>, <https://claude.com/docs/plugins/submit>, read on 2026-11-25.

Week 4. Toni submits by hand.

## Requirements

- A paid claude.ai plan.
- GitHub connected to that account.
- Anthropic checks each version.

## Steps

1. From the repository root, run `claude plugin validate --strict ./plugin` and `claude plugin validate --strict .`. Fix what they report.
2. Open <https://claude.ai/directory/manage>.
3. Submit the repository: `https://github.com/Beovulfo/herd-sdlc`. The plugin is in `plugin/`, listed by `.claude-plugin/marketplace.json`.
4. Note the date and the submitted version below.

## Values to have ready

The portal form fields are **NOT verified** (Cloudflare challenge). These are likely values, not the form.

| Value | Text |
| --- | --- |
| Name | Herd (`herd`) |
| Short description | Autopilot SDLC harness: hand an agent a goal with success criteria, and it works until runnable checks prove the criteria pass. |
| Longer description | Each success criterion has a shell command. Checks run before the code. A Stop hook blocks finishing while evidence is missing, failing or stale, and releases after 3 blocks. A guard hook denies edits to secrets and irreversible git commands while a task is active. |
| Repository | https://github.com/Beovulfo/herd-sdlc |
| Author | Beovulfo |
| Licence | Apache-2.0 |
| Requirements | Python 3.11 or newer as `python3`, a git repository |
| What it runs | Hooks that run Python on Stop, before and after tool use, and when a subagent stops; checks run as shell commands with your permissions |

## Record

- Submitted on: `____`
- Version: `____`
- Result: `____`
