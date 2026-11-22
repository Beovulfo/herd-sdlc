# Spike S1: can EGM run unattended?

Question: can Herd run EGM's brainstorm, draft, review and resolve steps with no human turn?
Method: read `skills/*/SKILL.md` and `docs/claude.md` in the installed EGM plugin (v0.1.1). Nothing was executed; this is a static read.

## Result: not as shipped. Herd needs its own driver for 3 of 4 skills.

| Skill | Human pauses in the skill text | Unattended today? | What Herd must do |
| --- | --- | --- | --- |
| `egm-brainstorm` | Multi-turn open-ended interview is mandatory. It must not spawn reviewers until the user confirms readiness (Step 1.3 gate). A handoff gate ends the skill (Step 4). | No | Herd supplies the interview answers itself (FR "self-answered interview") and the two gate answers (`Review with Goldfishes`, `Conclude... keep brief`), or skips the skill and calls the Goldfish reviewers directly. |
| `egm-draft` | Per-section approval gate after every section; a "where to save" gate; stops and waits if the brief and draft contradict. | No | Herd supplies "approve and proceed" at each gate, and treats a contradiction as an escalation. |
| `egm-resolve` | Yields with zero tools and waits for the human after proposing fixes (accept, contest, "auto accept"). | Partly: it has an "auto accept" reply that applies all `PROPOSE FIX` items and skips `CONTEST`, `ESCALATE`, `DECLINE`. | The Arbiter replaces the human reply. "auto accept" already matches the M0 rule that only safe rulings apply automatically. |
| `egm-review` / `egm-review-loop` | Preset gate and per-stage gates. The consolidated preset (uninterrupted) runs all stages with no checkpoints; the loop has a round cap and, at the cap, asks the user one question. Links outside the working directory need approval. | Yes in consolidated mode; the cap question needs an answer. | Use the consolidated preset. Answer the cap question by escalation. Pre-approve or drop external links. |

## Constraints found

1. **Skills cannot be called from other skills.** All EGM skills set `disable-model-invocation: true`, so the `Skill` tool refuses them. EGM's own guide says to read the target `SKILL.md` and follow it in the same thread. A Herd skill must do that, or re-implement the steps.
2. **Gates are written as "yield the turn".** A gate ends the model's turn. An unattended driver cannot "answer" a yield; it has to run each stage as its own invocation, with the gate answer given as input, or fold the gate answer into the prompt.
3. **The Goldfish reviewers are the reusable part.** The `egm:egm-*` agents are registered subagent types and take a prompt (target file, persona, standard, context files). They run fine without a human. This session's review used them directly.
4. **Review isolation is real.** Reviewer adapters set `omitClaudeMd: true` and read-only tools; the synthesizer can write reports. This supports the fail-closed rule.
5. **Interview skipping is a deliberate departure.** EGM requires the human interview. The self-answered interview (hypothesis 3 in the PRD) is Herd's change, not an EGM mode.

## Decision for the PRD

- Depend on EGM's reviewer agents and rubrics (`resources/document_standards/*`) as they are.
- Do not fork. Write Herd skills that follow EGM's `SKILL.md` flow with the gate answers supplied by Herd (Elephant and Arbiter), and keep a one-line note per skill saying which gate it fills.
- Use EGM's consolidated review mode for step 6 and `egm-resolve` "auto accept" semantics for the Arbiter.
- Open item: whether upstream EGM would accept a "no pauses" flag. Not needed for M0; revisit after the pilot.
- Risk: EGM skill text can change between versions. Pin the plugin version and re-run this spike on upgrade.

## Addendum: executed runs (2026-11-22)

The static read above was followed by three real runs of brainstorm, draft, review (consolidated) and resolve on Herd's own features. Logs: `docs/spikes/s1-runs/{triage,arbiter,escalation}/run-log.md`. Designs: `docs/designs/herd-{triage,arbiter,escalation}.md`.

Result: the four steps complete with no human turn at the gates, with the driver (the Elephant) answering each gate from PRD text. Confirmed by running:
- Reviewer agents and the synthesizer run unattended and write the reports. 10 to 11 reviewer runs per review, none failed.
- `egm-resolve` "auto accept" applies PROPOSE FIX items only. The driver applied them by rewriting the design; the skill's own yield was not exercised.
- Human input was needed only for scope decisions the reviewers escalated (2 answers in run 1, 1 in run 2, 0 in run 3). These are the decisions the Arbiter will face.

Gaps found:
1. `egm-draft` rule 13 (author picks architecture) and step 6.1 (contradiction audit) say stop and wait. The driver decided and recorded; an unattended driver needs a rule for these.
2. `egm-review-loop` and its round cap were not run. Each review was one consolidated round.
3. The synthesizer can hand back "not complete" while its reviewers still run. Wait on the completion notification.
4. The Read tool can show reviewers a lossy view; round 1 of run 1 had false "corrupted text" findings. Reviewers must verify with Grep.
5. Reviewers have no write tool, so the synthesizer writes stage files; summary counts can go stale.
6. Cross-design drift appears fast: three designs found conflicts in `herd.yaml` keys and the `/herd` command set. The Triage unknown-key rule was fixed during run 3.
7. Only the Triage design got a second review round (4 Blockers after round 2, down from 8). The Arbiter and Escalation designs were not re-reviewed after resolve, so their fix quality is unverified.
