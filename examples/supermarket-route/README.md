# Example: a supermarket route optimizer

One benchmark: the same prompt, given 6 times each to four arms (Claude Sonnet 5.5 and Claude Haiku 5.5, each with Herd 0.3.1 and with no workflow). Start with [`BENCHMARK.md`](BENCHMARK.md).

![Animation of one basket: list-order route against the optimized route](images/simulation.svg)

| | |
| --- | --- |
| [`BENCHMARK.md`](BENCHMARK.md) | method, results with mean and standard deviation, cost, failure analysis, limits |
| [`prompt.md`](prompt.md) | the prompt every run received |
| [`runs/`](runs) | the 24 runs: code, Herd task records (`herd-task/`), adapters, raw results, tokens and cost (`usage.json`) |
| [`verifier/`](verifier) | the hidden general verifier, the robustness probe, the adapter spec, the scoring and aggregation scripts |
| [`images/`](images) | the three images, and the script that draws them |
| [`with-herd/`](with-herd), [`without-herd/`](without-herd), [`results/`](results) | the first version of the benchmark: one Sonnet run per arm with Herd 0.2.4 |

## Run isolation

Since 0.12.10 an install ships only `plugin/`, not this folder. But the repository is public and a checkout holds `verifier/` (the hidden verifier) and `runs/` (the published solutions), so a run that can read the disk can read both. `verifier/run_leg.py` starts every run of a leg in a sandbox that denies:

- your home folder (`~/`), so a run cannot read your other projects;
- every other entry in the leg's parent folder, such as earlier benchmark legs;
- every other run of the same leg, including its log and error files;
- the network (`WebFetch`, `WebSearch`, and outbound connections from Bash).

It refuses to start if the root is inside your home folder, if the root exists, or if a copy of the hidden verifier or a probe (`verify_general.py`, `robustness_probe.py`, `probe6.py`) sits under `/tmp`, `/private/tmp` or `$TMPDIR` where a run could read it. Each run gets its own empty git repository, git config and plugin copy. The plugin copy is built with `git archive` of the tag's `plugin/` folder when the tag has one (0.12.10 and later), or, for older tags, of the whole tree without `examples/`, `tests/` and `docs/`.

```
python3 examples/supermarket-route/verifier/run_leg.py --name haiku-herd-v0.12.1 --runs 6 \
  --model claude-haiku-5-5 --prompt examples/supermarket-route/prompt.md --herd-tag v0.12.1
```

Check the sandbox on your machine and Claude Code version before a leg (about one cent):

```
python3 examples/supermarket-route/verifier/run_leg.py --selftest
```

After a run finishes, audit its log:

```
python3 examples/supermarket-route/verifier/leak_audit.py RUN.jsonl --work <root>/run-N/work
```

The audit does two things. It reports what the sandbox blocked: any tool result with a `<sandbox_violations>` block, `Operation not permitted` or `denied by your permission settings` (a blocked attempt is still a finding), and any `WebFetch` or `WebSearch` call, in the main run and in subagents. It also proves the run used the isolation settings: it reads `<root>/run-N/settings.json` (or `--settings FILE`) and reports `not isolated` unless the sandbox is on, unsandboxed commands are off, and the deny rules for `~/`, `Read(~/**)`, `WebFetch` and `WebSearch` are present. It does not try to read paths from commands: shell text cannot be parsed completely. The sandbox is the guard, and `--selftest` shows it blocks reads on your machine.

Do not put the root directly in `/tmp`: every other entry of the root's parent is denied, which would include Claude Code's own scratch folder. The default root is `$TMPDIR/herd-bench/<name>`.

A leg's siblings are denied as they are when it starts, so start a leg only after the earlier legs in the same parent exist. `--dry-run` also creates the root and the run folders, so delete the root before the real start. A checkout outside your home folder is added to the deny list.

### Which runs count

A finding marked `blocked` is an attempt that the sandbox refused, such as `mktemp -d` in the system temp folder or an access to `__pycache__`. It counts as clean. Only a read of the hidden verifier, of another run or of the network voids a run.

So a run's score counts when the audit prints `leak audit: clean`, or when every finding it lists is `blocked`, or is a refused network call as below. The audit still exits 1 for blocked findings, so read its lines. Two kinds of finding print as `not blocked` and need a look. A `not isolated` finding is different: it shows no read, but the sandbox is not proven to be on, so do not score the run. A `network tool call` finding can be a refused call: check its tool result. A refused call counts as blocked.
