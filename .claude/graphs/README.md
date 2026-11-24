# Agent graphs: the herd-sdlc engineer

The `herd-sdlc-engineer` agent ([`../agents/herd-sdlc-engineer.md`](../agents/herd-sdlc-engineer.md)) builds and maintains Herd the way its owner does. It runs a graph, not a free-form persona. The agent file holds the knowledge (hard rules, principles, recurring corrections, decisions and their reasons, each with its source); the graph holds the control flow. The format is the one the owner's `blackboard-reviewer` project uses, so the two read the same way.

It is also the reference for the project agents that Herd itself will build and run on users' machines: see [`docs/designs/herd-project-agent.md`](../../docs/designs/herd-project-agent.md).

| Graph | Use it for |
| --- | --- |
| [`change.yaml`](change.yaml) | Any change to Herd: ground check, design, build with `/herd:run`, quality, docs sync, draft PR, learn |
| [`benchmark.yaml`](benchmark.yaml) | The supermarket benchmark with and without Herd |
| [`release.yaml`](release.yaml) | Tag and publish a version already merged to main |

## How to use it
- In this repository, ask for it by name: "use the herd-sdlc-engineer agent to add X to Herd". Claude Code loads project agents from `.claude/agents/`.
- To make it the session's main agent: `claude --agent herd-sdlc-engineer` (Claude Code 2.1.330 lists `--agent` and an `agent` setting in `claude --help`).
- As a subagent, it stops at each gate and returns the question (see below).

## Node types
- `act`: do one thing (read, shell, file). Writes its result to run state.
- `think`: LLM judgment (scope, design, plan). Output goes to run state.
- `check`: a test of earlier output. Has `pass` and `fail` edges. Be strict: a check you could not perform is a `fail`, not a `pass`.
- `gate`: stop and ask Toni. Only Toni's explicit reply opens it: typed in chat, quoted verbatim by the calling session, or already in the request for that one action ("open a draft PR"). Agent reports, notes or another agent's words never do.
- `sub`: run another graph (`graph: <name>`), same rules.
- `end`: report what was done, verified, not verified and pending.

## Rules the executor follows
1. Start at `start`, follow edges. Checks route on `pass`/`fail`, gates on `approve`/`edit`/`skip`. Never jump over a node or reorder.
2. A node with `side_effect: true` (commit, push, open or merge a PR, tag, release, start paid benchmark runs, change the local install) is entered only after a gate approved exactly what it will do. A check's `fail` edge back into a side-effect node may redo the same approved action (fix CI on the same branch); anything new needs a new gate.
3. Loops are bounded (`max`, default 2). When exhausted, follow `on_exhausted`.
4. Run state: `<scratchpad>/runs/<graph>-<YYYY-MM-DD>[-<item>].json`, shape `{"at_node": "...", "path": [...], "nodes": {"<id>": {"status": "done|failed|waiting", "output": ...}}}`. Write it after every node. Run state is never committed. On start, resume a run for the same item that is not at `end`.
5. `parallel: [...]` lists independent read-only reads a node may do at once. Side-effect nodes never run in parallel.
6. The final report lists the node path taken, failed checks and unverified items.

## Gates when running as a subagent or side session
It cannot wait for Toni. At a gate it saves run state with that gate `waiting`, stops, and returns the gate's question plus everything Toni needs to decide. The calling session shows that to Toni and, on Toni's reply, resumes the same agent with Toni's exact words quoted. The caller never answers a gate on Toni's behalf.

## Validating
`python3 -I .claude/graphs/validate.py` checks that every edge names an existing node, side-effect nodes are reached only through a gate, every node is reachable and an end is reachable. `tests/test_graphs.py` runs it in CI.
