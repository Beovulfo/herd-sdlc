# Spike S2: human baseline for EGM

Goal: measure what EGM costs a human today, so the M0 targets (touchpoints, human minutes, overturn rate) have a baseline.

## Protocol
1. Run EGM by hand on 5 small features, in order: `/egm-brainstorm` -> `/egm-draft` -> `/egm-review` (consolidated) -> `/egm-resolve`.
2. Start a timer when you first answer EGM and stop it when the spec is ready to merge. Count only your own time, not agent run time.
3. Log one row per feature below, right after finishing.
4. Overturn data: for each feature, note how many findings you accepted, rejected or deferred in `/egm-resolve`, and how many you would have been fine letting an agent decide (your guess, one number).

## Candidate features (Herd itself, so no private data)
1. `herd.yaml` config schema (risk path rules, budgets, concurrency limit)
2. Criteria and `check` format, including `human` vs `agent-proposed`
3. `decisions.md` ruling format for the Arbiter
4. State record `.herd/state/<feature>.yaml`
5. Intent gate PR template (H1)

## Log

| # | Feature | Human minutes | Touchpoints (prompts you answered) | Findings total | Accepted / rejected / deferred | Would have delegated to an agent | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | | | | | | | |
| 2 | | | | | | | |
| 3 | | | | | | | |
| 4 | | | | | | | |
| 5 | | | | | | | |

## Exit
Fill the table, then record the medians here and copy them into PRD section 3 as the baseline.

Medians: minutes = ___, touchpoints = ___, delegable share = ___
