# Spikes

Short experiments that answered a question before Herd was built on the answer.

| Spike | Question | Result |
| --- | --- | --- |
| [S1](s1-egm-unattended.md) | Can EGM's brainstorm, draft, review and resolve steps run with no human turn? | Yes, with a driver that answers each gate from the PRD. Reviewers ran unattended in every run (10 to 11 reviewer runs per review, none failed). Human input was needed only for scope decisions the reviewers escalated: 2, 1 and 0 answers over three runs. Seven gaps are listed in the spike. |
| [S3](s3-hook-inputs.md) | Do the hook inputs the guardrails design relies on exist? | Yes, tested live on Claude Code 2.1.330. Three changes to the design: the reviewer's `agent_type` is `herd:herd-reviewer`, its final text can be in a `SubagentHandback` call, and the start time comes from `started`. |
| [S4](s4-project-agent.md) | Do the session log, `--agent` and the git common dir support the project-agent design? | Yes, on Claude Code 2.1.330. A plugin agent can be the main agent (`--agent herd:<name>` or the project `agent` setting). Read calls are in the log; `CLAUDE.md` is recorded as an `instructions` attachment, so the read check must count it. |
| [S2](s2-baseline.md) | What does EGM cost a human today? | Protocol only, not run yet. It will give the baseline for the PRD's touchpoint and human-minute targets. |

## S1 run logs

One log per EGM run on Herd's own features, with each step, the reviewer counts and what broke:

- [Triage](s1-runs/triage/run-log.md): three review rounds, Blockers went from 8 to 4 after round 2. Spec: [`herd-triage.md`](../designs/herd-triage.md).
- [Arbiter](s1-runs/arbiter/run-log.md): spec [`herd-arbiter.md`](../designs/herd-arbiter.md).
- [Escalation](s1-runs/escalation/run-log.md): spec [`herd-escalation.md`](../designs/herd-escalation.md).
- [v0.2 plan](s1-runs/coco-ideas/run-log.md): plan review of [`herd-coco-ideas.md`](../designs/herd-coco-ideas.md).

The logs name the raw review reports they produced (`round1/`, `concepts_brief.md`, and so on). Those 51 files were removed to keep this folder readable. They are in git history at commit `b1a6d86`, under `docs/spikes/s1-runs/`.
