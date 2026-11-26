# Quick route

For a trivial change: one file, no new behaviour surface, and an existing command that can fail first.

1. Run `herd init <slug> "<goal>" --quick "<check>" --request "<their message, verbatim>"`. Herd records the `/herd:run` message itself from the session log; `--request` counts only without one. It refuses a `high` risk floor: then use the standard route.
2. Skip triage, criteria, the gate and break it: continue at run step 4 (red).
3. Still required: red first (`herd verify` fails), build, `herd verify` passes, `herd done`, the final report.
