# Show HN: fact sheet and outline

> **Do not paste this file into Hacker News.** Hacker News forbids generated text, in posts and in comments, and AI-edited text too. An AI drafted this file. Use it as notes, then write your title comment and every reply in your own words, without asking a model to edit them.
>
> Sources: <https://news.ycombinator.com/showhn.html>, <https://news.ycombinator.com/newsguidelines.html>

Post on a weekday, 12 to 17 UTC. Link: <https://github.com/Beovulfo/herd-sdlc>

## Title options

Pick one or write your own. Retype it.

Show HN: Herd, a Claude Code plugin that asks for proof before "done"

Show HN: Herd, a Stop hook that makes a coding agent run its checks

Show HN: Herd, runnable success criteria for Claude Code

## Outline for your first comment

Write a few sentences for each point, from your own experience.

1. Who you are and that you built this.
2. The problem you hit: an agent says "done" and you cannot tell.
3. What Herd does: goal in, checks written first, a Stop hook, an evidence report.
4. How to try it.
5. What it does not do. Pick from the limits below.
6. The question you want answered by readers.

## Key facts

### Product

| Fact | Source |
| --- | --- |
| A Claude Code plugin, Apache 2.0 licence | `README.md`, `LICENSE` |
| Needs Claude Code, Python 3.11 or newer as `python3`, a git repository | `README.md` |
| Standard library only, no dependencies | `README.md` |
| Install: `/plugin marketplace add Beovulfo/herd-sdlc`, then `/plugin install herd@herd-sdlc` | `README.md` |
| Run: `/herd:run <goal>` | `README.md` |
| Each criterion has a shell command; exit 0 means pass | `README.md` |
| The Stop hook reads stored evidence; it blocks at most 3 times, then releases and records that | `plugin/scripts/herd.py`, `gate` |
| `herd pr` is opt-in; Herd never merges | `README.md` |
| Since 0.13.0 no second model reviews the change | `CHANGELOG.md` |
| Since 0.14.0 Sonnet designs and Haiku builds by default | `CHANGELOG.md` |

### Results: Herd 0.3.1, 6 runs per arm

One task (a route planner in a supermarket), hidden verifier. Source: `examples/supermarket-route/BENCHMARK.md`.

| Arm | Valid stores | Bad inputs handled, of 6 | Cost per run |
| --- | --- | --- | --- |
| Claude Sonnet 5.5 with Herd 0.3.1 | 48.0 of 48 | 6.0 | $0.61 |
| Claude Sonnet 5.5, no workflow | 45.2 of 48 | 3.5 | $0.29 |
| Claude Haiku 5.5 with Herd 0.3.1 | 44.3 of 48 | 6.0 | $0.29 |
| Claude Haiku 5.5, no workflow | 41.7 of 48 | 4.3 | $0.04 |

The Herd runs in these arms were emulated sessions: no Stop hook fired.

### Results: Herd 0.12.1, real sessions, 6 runs

Claude Haiku 5.5 with all hooks: 47.3 of 48 valid stores, 5 of 6 runs fully valid, 6 of 6 bad inputs, $0.35 per run. It used a Sonnet 5.5 reviewer, which 0.13.0 removed. The method differs from the 0.3.1 arms, so do not compare them as one series.

### Cost: Herd 0.13.3

On Haiku, 0.13.3 cost $0.28 per supermarket run against $0.10 with no plugin. The same entry reports 3 runs. Source: `CHANGELOG.md`, 0.13.4. Check that run count before quoting it.

### Design step: Herd 0.14.0, 6 runs per arm

Design eval on the same task. A Sonnet design with a "be specific" second look before the attacks got the key design choice right in 6/6 runs. A Haiku design got it right in 2/6. The judge matched hand labels 9 of 10 times. Source: `CHANGELOG.md`, 0.14.0. This measures the design, not the built code.

## Limits to say yourself

- One task measured in the results above, 6 runs per arm at most.
- 0.14.0 has no run of the full benchmark.
- Herd costs more than no workflow.
- Bugs outside the attacks and criteria are not caught.
- Checks run as shell commands with your permissions.
- The Stop hook is not a hard lock, and the guard is not a sandbox.

## Likely questions, with facts for your answer

**Why not just tell the agent to run the tests?**
An instruction can be ignored. The Stop hook is a program that reads stored evidence. It still releases after 3 blocks.

**Can the agent cheat with a weak check?**
Yes. Herd warns about some empty checks, does not count them for attacks, and asks for red first. It cannot tell whether a check is the right one.

**Can the agent edit the evidence?**
A guard hook denies edits to Herd's state files by pattern. It is not a sandbox.

**Does it work without Claude Code?**
No. It is a Claude Code plugin.

**Does it make the code better?**
On this task, route quality was the same in the four 0.3.1 arms. The difference was robustness and valid results.

**What does it cost?**
Use the cost lines above, each with its version.

**How does it compare with other workflow plugins?**
Not measured. Say so. The run skill uses Superpowers skills when they are installed.

**Does it send data anywhere?**
GitHub through `gh` is the only external service Herd itself talks to. Claude Code talks to its model as usual.
