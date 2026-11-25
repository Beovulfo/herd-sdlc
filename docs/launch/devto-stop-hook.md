---
title: How a Stop hook makes an agent prove its work
published: false
tags: claudecode, ai, python, testing
ai_disclosure_level: "TONI TO CONFIRM: drafted with AI assistance"
# canonical_url: add only if this is published elsewhere first
---

<!-- Draft. Before publishing: set ai_disclosure_level to a value the dev.to editor guide allows (values not verified), edit the text, and delete this comment. -->

# How a Stop hook makes an agent prove its work

*Disclosure: I wrote the plugin described here. This article was drafted with AI assistance.*

A coding agent can say "done" while a test still fails, or before it ran any test. Telling it to check helps, but an instruction can be ignored. A hook is different: it is a program that Claude Code runs, whatever the model decides.

This article walks through the Stop hook in [Herd](https://github.com/Beovulfo/herd-sdlc), an open source Claude Code plugin. The code is Python, standard library only. The quotes are from version 0.14.0.

## The idea

1. Each success criterion has a shell command. Exit 0 means pass.
2. `herd verify` runs the commands and stores the results as evidence.
3. When Claude tries to stop, a hook reads that evidence.
4. If the evidence is missing, failing or out of date, the hook says no and says why.

## Register the hook

This is the `Stop` entry from `plugin/hooks/hooks.json`:

```json
"Stop": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/herd.py\" gate",
        "timeout": 30
      }
    ]
  }
]
```

`${CLAUDE_PLUGIN_ROOT}` is the folder of the installed plugin. The hook runs `herd.py gate` with a 30 second timeout.

## Read the input, print the answer

Claude Code sends the hook a JSON object on stdin. This is the `gate` branch of the command line in `plugin/scripts/herd.py`:

```python
elif cmd == "gate":
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    hook = json.loads(raw) if raw.strip() else {}
    out = gate(find_root(Path(hook.get("cwd") or root)), hook)
    if out:
        print(json.dumps(out))
```

If `gate` returns nothing, nothing is printed and the session may stop. If it returns a dict, the dict is printed as JSON.

## The gate

The start of the function:

```python
def gate(root, hook):
    """Stop hook. None allows the stop; a dict blocks it with a reason for the agent."""
    slug = active_slug(root)
    if not slug or not _dir(root, slug).exists() or cancelled(root, slug):
        return None
    counter = _dir(root, slug) / "gate_blocks"
    try:
        probs = problems(root, slug)
    except STATE_ERRORS as e:  # a corrupt or hand-edited state file: block and say so, never crash the hook
        probs = [f"a state file of task {slug} is unreadable ({e}): a human restores it, or cancels the task"]
```

Three cases pass straight through: no active task, a task folder that is gone, or a cancelled task. The plugin stays out of the way in ordinary sessions.

The `except` matters. A state file with the wrong content blocks with a message. It does not crash the hook.

Note what is not here: the gate does not run your tests. It reads what `herd verify` stored.

## When something is wrong

Further down in the same function:

```python
(_dir(root, slug) / "done_blocks").unlink(missing_ok=True)  # passing again later reminds about `herd done` again
n = _count(counter)
if n >= MAX_BLOCKS:
    _stop(root, slug, "released")
    return None
counter.write_text(str(n + 1))
cmd = f"python3 {SELF} verify"
causes = _escalations(root, slug)
if causes:
    _stop(root, slug, "escalated", "; ".join(causes))
esc = [f"{c}: ask the human one question" for c in causes]
reason = (f"Herd task `{slug}` is not done ({n + 1}/{MAX_BLOCKS} stop attempts blocked). "
          + "; ".join(probs + esc) + f". Run `{cmd}` after fixing. If you are stuck, ask the human one question and stop."
          + f" If the human abandoned the task, run `python3 {SELF} cancel --reason \"...\"`.")
return {"decision": "block", "reason": reason}
```

The answer is `{"decision": "block", "reason": ...}`. The reason is written for the agent: what is wrong, which command to run, and what to do when stuck. A bare "no" would leave the agent guessing.

## What counts as wrong

`problems()` returns a list of reasons. An empty list means done. It starts like this:

```python
def problems(root, slug):  # noqa: C901
    """Reasons the task is not done, from stored evidence. Empty list means done."""
    ev = load_evidence(root, slug)
    if ev is None:
        return ["no evidence yet: run `herd verify`"]
    if _stale(root, slug, ev):
        return ["evidence is stale (the workspace or task.toml changed after the last verify): run `herd verify`"]
    out = [f"{r['id']} is failing: {r['text']}" for r in ev["results"] if r["status"] == "failing"]
    if not ev["summary"]["passing"] and not out:
        out.append("no passing criterion: give at least one criterion a runnable check")
```

No evidence, stale evidence, a failing check, or not a single passing criterion. The function goes on to check more, for example that checks ran before the code existed, that criteria you wrote were not changed, and, on the standard route, that the standard attacks have passing commands.

## Stale evidence

A passing run is worth little if the code changed afterwards. This is how the gate notices:

```python
def _stale(root, slug, ev):
    """The task or the work changed since the last verify. A commit alone changes neither: the content id decides;
    the HEAD fingerprint is the fallback outside git and for evidence without a content id."""
    if ev["task_sha"] != _task_sha(root, slug):
        return True
    if ev.get("content"):
        now_id = task_content(root, slug)
        if now_id is not None:
            return ev["content"] != now_id
    return ev["fingerprint"] != fingerprint(root)
```

If `task.toml` changed, or the content of the work changed, the evidence is stale. When a content id is available, a commit alone changes neither. Outside git, a fingerprint is the fallback.

## When everything passes

This block sits between the two quotes of `gate` above:

```python
if not probs:  # everything passes, but only `herd done` checks the commit and prints the final report
    counter.unlink(missing_ok=True)
    done_counter = _dir(root, slug) / "done_blocks"
    n = _count(done_counter)
    if n >= MAX_BLOCKS:  # `herd done` keeps refusing (say, it may not commit): let the agent stop and ask
        _stop(root, slug, "done_refused")
        return None
    done_counter.write_text(str(n + 1))
    commit = (" Commit first: pull requests are on, so `herd done` refuses uncommitted work; if you may not"
              " commit, say so and stop." if _git(root, "status", "--porcelain", "--", *OWN_FILES).strip()
              and (pr_wanted(root) or (_dir(root, slug) / "pr").exists()) else "")
    return {"decision": "block", "reason": f"Herd task `{slug}`: the evidence passes ({n + 1}/{MAX_BLOCKS})."
            f"{commit} Run `python3 {SELF} done` to close the task and print the final report, then paste it."}
```

Passing checks are not the end. `herd done` is a separate step that checks the commit and prints the final report, so the gate asks for it.

## It is not a hard lock

Both branches count their blocks, and `MAX_BLOCKS` is 3. After that the hook returns `None` and the session may stop. Herd writes a record of why it stopped and what was left.

That is a choice. A hook that blocks for ever turns a stuck agent into a loop that burns tokens. The price is that "the session stopped" does not mean "the work passed". The evidence is what says that.

## Limits

- A weak check passes weakly. The hook proves that the commands passed, not that they test the right thing.
- Checks run as shell commands with your permissions. Read a task file as you read code.
- A separate guard hook denies edits to Herd's state files. It matches patterns and is not a sandbox.
- Since 0.13.0 no second model reviews the change.

## Write your own

You can use the pattern without Herd:

1. Have a script that runs the checks and writes the result with a hash of what it checked.
2. In the Stop hook, read the result. Do not trust the agent's summary.
3. Block with a reason that names the next command.
4. Cap the number of blocks, and record when you give up.
5. Never let the hook crash the session.

The full code is in [the repository](https://github.com/Beovulfo/herd-sdlc).
