# Contributing to Herd

Questions go to [GitHub Discussions](https://github.com/Beovulfo/herd-sdlc/discussions). New contributors can start with the [good first issue](https://github.com/Beovulfo/herd-sdlc/labels/good%20first%20issue) label.

## Setup

You need:

- `python3` 3.11 or newer
- `gh`, the GitHub CLI
- git
- Claude Code, to validate and try the plugin

There is nothing else to install to run the tests: Herd uses the standard library only. `ruff` is needed for lint.

## Checks

Run the tests for the module you changed, for example:

```bash
python3 -m unittest tests.test_docs_sync
```

CI runs the full suite on your pull request. Also run:

```bash
ruff check .
claude plugin validate ./plugin
claude plugin validate .
```

## Rules

- Python standard library only. Do not add a dependency without a reason.
- GitHub (`gh`) is the only external service Herd talks to.
- No credentials or private data in any file, commit or example. Use generic fixtures.
- Keep the README, the skills and the docs in sync when behaviour changes.
- Whenever plugin files change, bump `version` in `plugin/.claude-plugin/plugin.json` and add a `CHANGELOG.md` entry. Also update the Status line in README.md and the status line in docs/PRD.md.

## Herd tasks

Herd is developed with Herd: tasks on this repository run through `/herd:run`. Criteria need runnable checks, and "done" means evidence exists.
