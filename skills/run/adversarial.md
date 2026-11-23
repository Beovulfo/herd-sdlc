# Break it

Try to break your own work on exactly what the request promises. Never skip it because the demo passes: the report shows when no attempt was recorded.

1. Turn each quantifier or size word in the request (`any`, `every`, `whatever`, `many`, `big`, `very big`) into hostile inputs:
   - generated cases from several different shapes or families;
   - extremes: empty, huge, degenerate, disconnected, malformed;
   - a scale run with a time limit.
2. Run them. If you can spawn a fresh-context subagent, give it only the request, the criteria and how to run the tool, and ask it to break it. Otherwise do it yourself and say it was not fresh.
3. Log each attempt with `herd note --tried`, each failure with `--found`, each fix with `--fixed`, each limit you leave with `--open`: one call each, the moment it happens. Notes logged together are flagged, because their times then mean nothing.
4. Turn each failure into a regression test, then fix it.
