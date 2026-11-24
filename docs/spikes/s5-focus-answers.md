# Spike S5: the reviewer's log and the focus answer format

Goal: confirm, before any code, what [`herd-focused-review.md`](../designs/herd-focused-review.md) relies on in G6, G7, F3 and F4.2: (a) the reviewer's log gives an exit status per Bash call; (b) a Sonnet reviewer follows the `BRIEF` and `FOCUS` line shapes and exit 3 from a brief of 14 items. Run on 2026-11-24 with Claude Code 2.1.330 (as S3).

## S5(a): the log

### Method

Read the 10 `herd:herd-reviewer` transcripts of the six 0.12.1 benchmark runs (a saved benchmark run; `agent_type` is in each `.meta.json`). Matched each `tool_use` (Bash) to its `tool_result` by `tool_use_id`, and listed every field on the result line. Because those 10 logs hold only 15 Bash results and one failure, also scanned all saved transcripts for failed results (`is_error: true`) to see exit 3, other exit codes and denials.

### Result

The reviewer logs: 10 reviewers, 15 Bash results (14 exit 0, 1 exit 1), 66 tool results with the same `permissionDecision`. No exit 3 and no denial exists in the 0.12.1 reviewer logs; the other transcripts supply those shapes.

Fields on a Bash result. There is **no numeric exit-code field**. The result is a `user` line with these top-level keys: `type`, `message`, `uuid`, `parentUuid`, `timestamp`, `agentId`, `isSidechain`, `sandboxed`, `permissionDecision`, `sourceToolAssistantUUID`, and `toolUseResult` only on failure. The content block has `type`, `tool_use_id`, `content` (a string) and `is_error`. A search of all fields found no `exitCode`, `returnCode` or `interrupted`.

Exit 0 (`is_error: false`, content is the raw output, no `toolUseResult`):

```json
{"type":"user","message":{"content":[{"tool_use_id":"toolu_01Ar8y...","type":"tool_result","content":"       3 route_optimizer/__init__.py\n ... 783 total","is_error":false}]},"permissionDecision":{"decision":"accept","source":"config","reasonType":"rule","ruleSource":"cliArg"},"sandboxed":false}
```

Non-zero exit (0.12.1 run 6 reviewer; `toolUseResult` repeats the text with an `Error: ` prefix):

```json
{"type":"user","message":{"content":[{"type":"tool_result","content":"Exit code 1\nTraceback (most recent call last):\n  ...\nModuleNotFoundError: No module named 'route_optimizer'","is_error":true,"tool_use_id":"toolu_01RPd6..."}]},"toolUseResult":"Error: Exit code 1\nTraceback ...","permissionDecision":{"decision":"accept",...}}
```

Across all transcripts, every failed Bash result with an exit code begins `Exit code <N>\n` (seen: 1 x134, 127 x29, 2 x4, 128 x2). No exit 3 occurred in saved logs, but the harness writes the number the same way for any N. S5(b) below shows no exit 3 either, because the reviewer's commands were batched. Treat 3 as the same shape.

Denial. A denied call has `is_error: true`, no `Exit code` text, and a top-level `permissionDecision.decision` of `"reject"`:

```json
{"message":{"content":[{"type":"tool_result","content":"PreToolUse:Bash hook error: PROBE-DENY: not allowed","is_error":true,...}]},"toolUseResult":"Error: ...","permissionDecision":{"decision":"reject","source":"hook","reasonType":"hook","reasonCode":"hook:PreToolUse"}}
```

Other rejects seen: `reasonType: "rule"` (`File is in a directory that is denied by your permission settings.`) and `reasonType: "safetyCheck"`. `permissionDecision` is on the line, not in the content block. Every non-denied call carries `decision: "accept"`.

SubagentStop input. Per S3 finding 1, `agent_transcript_path` is `.../<session>/subagents/agent-<agent_id>.jsonl`. The 10 files read here sit at exactly that pattern, so the transcript the hook gets is the same file (not the main session's `transcript_path`). This spike did not test whether the file is complete when the hook fires.

Fakeability. The `Exit code N\n` text is written by the harness as the first characters of `content`, and only when `is_error` is true. A command's own output follows it and cannot precede it. A command that prints `Exit code 3` and exits 0 gives `is_error: false` and content that starts with its output, so it does not match `^Exit code (\d+)\n` with `is_error: true`.

### Decision for the design (G7, F4.2)

- G7 can read "exit 3" from the log reliably, from text only: `is_error` is true and `content` matches `^Exit code (\d+)\n` (take group 1). No field carries it. Exit 0 is `is_error: false`. A denial is `permissionDecision.decision == "reject"` on the result line.
- A command's output cannot fake it (anchored at the start, set by the harness, and `is_error` must be true).
- `reviewer_calls()` must read `permissionDecision` from the line, `is_error` and `content` from the block, and tolerate `content` being a list of blocks. A result that fits none of these is unconfirmable.
- The reviewer can still wrap exit 3 wrongly; this is the known limit in the Risks table, not new.

## S5(b): one live call

### Method

Copied the finished 0.12.1 run 6 folder to `/tmp/s5-spike/run6`. Wrote the brief by hand per F2 and F3 (`/tmp/s5-spike/brief.txt`): goal, request, files to read, the diff command, `Focus list: answer every id` with 14 items, `Brief: s5test1`, and the answer rules. Items by F1 from `task.toml` and `notes.jsonl`: A:C1, A:C2; B:budget, B:limit-1, B:note-11, B:note-18, B:note-19 (the three open notes; positions 11, 18, 19 in the full file); C:bad-input, C:collision, C:one-bad-part, C:recount, C:refusal; D:1, D:2. Ran from the folder:

`claude -p "<brief>" --model claude-sonnet-5-5 --setting-sources project --permission-mode dontAsk --allowedTools "Bash,Read,Glob,Grep" --max-budget-usd 0.5 --output-format stream-json --verbose < /dev/null`

Then `/tmp/s5-spike/check.py` parsed the final text, compared each FOCUS command to the logged Bash calls (whitespace-collapsed, exact), and reran each from the folder.

Caveat on the ground truth: the copy is the finished run, where the unbounded cache was already replaced by a 32-entry LRU (`store.py` `MAX_CACHED_SOURCES`). So A:C2 "holds" is now correct, and the known cache defect cannot show. The 14 items include the late open notes 18 and 19, which a first-round brief would not have.

### Result

Cost $0.160, 55.5 s, 6 turns, 5 Bash calls, success.

| Check | Outcome |
| --- | --- |
| Final text starts with `BRIEF s5test1` | No. It began `Checking done; here is the report. I ran each command below myself...`, then a blank line, then `BRIEF s5test1` on line 3. |
| Ids with a well-formed line | 14 of 14. No unknown or duplicate ids. Every line matched `^FOCUS (\S+): (holds\|breaks): (.+)$`. |
| `breaks` | 5 (B:limit-1, B:note-18, B:note-19, D:1, D:2) and 9 `holds`. Two `EXTRA` lines. |
| Each `breaks` command among its logged Bash calls (exact, one line) | 0 of 5. None of the 14 commands matched. |
| Rerun of each `breaks` from the folder | 5 of 5 exit 3, each in under 0.2 s. All 9 `holds` commands exit 0 (longest 6.4 s). |

Why no command matched the log: the reviewer ran 5 Bash calls, each a multi-line script (`cd ...; cat ...`, heredocs, several `python3 -c` blocks and `echo $?`), not one call per item. The FOCUS commands are tidy one-line versions written afterwards. The log's exit status for those calls is that of the last command in the script, so the log cannot show a per-item exit 3.

Raw FOCUS lines (trimmed):

```
FOCUS A:C1: holds: python3 -m unittest tests.test_savings
FOCUS A:C2: holds: python3 -m unittest tests.test_layouts tests.test_scale
FOCUS B:budget: holds: python3 -m unittest tests.test_layouts tests.test_scale
FOCUS B:limit-1: breaks: python3 -c "import sys; from route_optimizer.store import Store; ...; s=Store.from_dict({'width':10,'height':3,'products':[{'id':'1','short_name':'m','x':9,'y':0}]}); a=run_summary(s,list_order_route(s,['1','1']))[...]; b=...; sys.exit(3 if saving_pct(a,b)<30 else 0)"
FOCUS B:note-11: holds: python3 -m unittest tests.test_refusal
FOCUS B:note-18: breaks: (the same command as B:limit-1, character for character)
FOCUS B:note-19: breaks: python3 -c "import sys; sys.exit(3 if not any(k in open('route_optimizer/store.py').read() for k in ('MAX_CELLS','too large','MAX_WIDTH')) else 0)"
FOCUS C:bad-input: holds: python3 -m unittest tests.test_bad_input
FOCUS C:collision: holds: python3 -m unittest tests.test_collision
FOCUS C:one-bad-part: holds: python3 -m unittest tests.test_one_bad_part
FOCUS C:recount: holds: python3 -m unittest tests.test_recount
FOCUS C:refusal: holds: python3 -m unittest tests.test_refusal
FOCUS D:1: breaks: python3 -c "import sys; from route_optimizer.store import Store; exec('try:\n Store.from_dict({\"width\":5,\"height\":1,\"blocked\":[[0,0]],\"products\":[{\"id\":\"1\",\"short_name\":\"m\",\"x\":3,\"y\":0}]})\nexcept ValueError: sys.exit(3)')"
FOCUS D:2: breaks: python3 -c "import sys,io,json,pathlib; from unittest import mock; ... rc=main([\"--store\",\"m\",\"--order\",\"o\"])'); sys.exit(3 if rc==0 else 0)"
EXTRA: route_optimizer/store.py:56 The entrance defaults to (0,0) ... a corner shelf is refused ... :: (same command as D:1)
EXTRA: route_optimizer/__main__.py:18 The order's short_name is read and then dropped ... 1:WRONG is accepted with exit 0. This is the D:2 break above.   (no command)
```

Quality of the answers against the known truth:

- D:1: found a real narrowness in the input form (the map has no entrance field and defaults to cell (0,0), so a blocked corner refuses the whole store). This is not the exact known truth (products given on walkable cells while the request puts them on shelves), so it was not matched, but the item was attacked by building input from the request and the break is real. D:2 is a second real break (the order's `short_name` is ignored), unexpected.
- A:C2: `holds`, correct for this tree (cache already bounded). The pre-fix defect is not testable here.
- B:limit-1 and B:note-18 are weak: the break restates a known limit (a 2-item basket saves under 30%), so exit 3 on rerun confirms a stated limit, not a defect. They share one command, which G6's "differs from every other item" rule would catch.
- B:note-19 is a source grep for names, not an attack on the program. It exits 3 on rerun, so G7 as written would confirm it. A grep-based break passes the rerun gate.
- Each `holds` command was a project test, not an attack written for the item: B:budget reused the A:C2 command, and four C items reused the check from the brief (G6's rule that `holds` commands differ and are not copies is not met for B:budget vs A:C2; the C ones are distinct).

### Decision for the design

The answer format works: 14 of 14 ids in well-formed lines, `breaks` commands are one-line, self-contained, run under 1 s, and all 5 exit 3 on rerun by an external script, which is the check the hook performs. The `BREAK:` fallback is not needed. Three things in the design must change:

1. **Log matching fails as written (G6, G7, F4.2).** The reviewer ran its commands in 5 multi-line scripts, then wrote tidy one-liners. 0 of 14 commands equal a logged call. If G7 requires a logged exit 3, every break would be unconfirmed and every review `none`. Fix the instruction (F3): "run each command you will cite as its own Bash call, exactly as you will write it, one call per item, before the report; a command you did not run that way is rejected". Then re-test (a second S5(b) call, $0.15) to see whether Sonnet obeys. If it does not, drop the logged-exit requirement for `breaks` and keep only the rerun by the hook (exit 3, G10 deadline) and the guard rule check; keep the log requirement for `holds` only if that test passes.
2. **First-line rule.** The report began with a preamble line. Make `parse_focus()` find a line equal to `BRIEF <id>` anywhere in the text (as `VERDICT` is read), and drop "start" from F3 or keep it as advice. Strict first-line would have made this review `none`.
3. **Break quality.** A rerun of exit 3 does not show the defect is real. Add to the agent file: a `breaks` that only restates a known limit (B:limit) is a `holds` with the limit shown, and a break may not only grep source. Keep the report's output tail so a human sees what exit 3 meant (already in F4.6). Do not claim G7 filters these; it does not.

Cost fit: $0.16 for one round of 14 items on a 0.12.1-sized project, above the F8 estimate of $0.09 to $0.12 and above the G14 cap of $0.15 per run. The owner decides whether it is worth it; this spike used 6 turns with no repeated reads, so the estimate in F8 should be raised to about $0.16 per round.
