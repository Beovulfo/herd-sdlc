# r/ClaudeAI post

> Rules **NOT verified**: read the sidebar rules logged in before posting: self-promotion, flair, disclosure.
>
> Week 2. An AI drafted this. Edit it so it says what you mean.

**Title:** I built a Claude Code plugin that asks for proof before the agent says "done"

**Body:**

I am the author of Herd, a free and open source (Apache 2.0) plugin for Claude Code. An AI helped me draft this post.

The problem: an agent says the task is finished, and I have to check that myself.

With Herd you give a goal and, if you like, success criteria. Each criterion gets a shell command. The checks run before any code, and should fail. A Stop hook reads the results when Claude tries to finish, and sends it back while a check is failing or out of date. You get a report with command output, commit SHA and timestamps.

One measurement, on one task (a route planner in a supermarket), with a hidden verifier, Herd 0.3.1, 6 runs per arm:

- Claude Sonnet 5.5 with Herd: 48.0 of 48 stores valid, 6.0 of 6 bad inputs handled, $0.61 per run.
- Claude Sonnet 5.5 without a workflow: 45.2 of 48, 3.5 of 6, $0.29 per run.

Limits: those Herd runs were emulated sessions, so no Stop hook fired. The version is old, and the current one has no run of the full benchmark. One task says little about yours. The hook releases after 3 blocks, so it is not a hard lock.

Try it:

```text
/plugin marketplace add Beovulfo/herd-sdlc
/plugin install herd@herd-sdlc
/herd:run Add a --json flag to the export command. Output must be valid JSON with every row.
```

It needs Python 3.11 or newer and a git repository.

Repository: https://github.com/Beovulfo/herd-sdlc

What do you check by hand today after an agent says "done"?
