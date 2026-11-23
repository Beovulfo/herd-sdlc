# Break it

Try to break your own work on exactly what the request promises. Never skip it because the demo passes. On the standard route `herd done` and the Stop gate refuse until each of the four standard attacks below has a recorded attempt.

1. Turn each quantifier or size word in the request (`any`, `every`, `whatever`, `many`, `big`, `very big`) into hostile inputs:
   - generated cases from several different shapes or families;
   - extremes: empty, huge, degenerate, disconnected, malformed;
   - a scale run with a time limit.
2. Always run the four standard attacks, whatever the request says. Log each with its name:
   - `--attack bad-input`: bad input at every entry point (each file, argument and record a user supplies): missing, unreadable, malformed, wrong type, unknown id, empty. Each must end with one clear message and a non-zero exit, never a traceback.
   - `--attack collision`: two inputs that land on the same key, position or slot (duplicates, shared locations, equal names). Each one must still be counted.
   - `--attack one-bad-part`: a broken or unreachable entry that the request does not use must not reject the whole input.
   - `--attack recount`: recompute every reported number (totals, times, counts) from the output itself, such as the trace or the rows, with separate code. Never check a number with the code that produced it.
   An attack that cannot apply still gets a note that says why, for example `herd note --tried --attack collision "n/a: the tool takes one value"`.
3. Run them. If you can spawn a fresh-context subagent, give it only the request, the criteria and how to run the tool, and ask it to break it. Otherwise do it yourself and say it was not fresh.
4. Log each attempt with `herd note --tried` (plus `--attack <name>` for a standard attack), each failure with `--found`, each fix with `--fixed`, each limit you leave with `--open`: one call each, the moment it happens. Notes logged together are flagged, because their times then mean nothing.
5. Turn each failure into a regression test, then fix it.
