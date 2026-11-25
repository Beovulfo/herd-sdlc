# Quick route

For a trivial change: one file, no new behaviour surface, and an existing command that can fail first.

1. Run `herd init <slug> "<goal>" --quick "<check>" --request "<the user's message, verbatim>"`. It refuses a `high` risk floor: then use the standard route.
2. Skip triage, criteria, the gate and break it: continue at run step 5 (red).
3. Still required: red first (`herd verify` fails), build, `herd verify` passes, `herd done`, the final report.
