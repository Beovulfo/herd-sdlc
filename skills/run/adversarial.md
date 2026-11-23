# Break it

Try to break your own work on exactly what the request promises. Never skip it because the demo passes. On the standard route `herd done` and the Stop gate refuse until each of the four standard attacks below has a command that `herd verify` ran and saw pass.

1. Turn each quantifier or size word in the request (`any`, `every`, `whatever`, `many`, `big`, `very big`) into hostile inputs:
   - generated cases from several different shapes or families, and purely random ones you did not design;
   - size and shape extremes: huge, degenerate, disconnected;
   - a scale run with a time limit.
2. Always run the four standard attacks, whatever the request says. Write each as a command that fails if the attack breaks the work (usually a regression test), and log it: `herd note --tried --attack <name> --check "python3 -m unittest tests.test_errors" "what it covers"`. `herd verify` runs it like a criterion check; a failing command, one that runs zero tests, or one that runs no project code (`true`, `echo`, `test -f`) does not count.
   - `--attack bad-input`: bad input at every entry point (each file, argument and record a user supplies): missing, unreadable, malformed, wrong type, unknown id, empty. Each must end with one clear message and a non-zero exit, never a traceback.
   - `--attack collision`: two inputs that land on the same key, position or slot (duplicates, shared locations, equal names). Each one must still be counted.
   - `--attack one-bad-part`: a broken or unreachable entry that the request does not ask for must not reject the whole input; a requested entry that is broken or unreachable must still fail with a clear message.
   - `--attack recount`: recompute every reported number (totals, times, counts) from the output itself, such as the trace or the rows, with separate code, on the generated and collision inputs too. Never check a number with the code that produced it.
   An existing test, such as a criterion's check, counts for an attack only if it meets that attack's rule above: every entry point for bad-input, separate code for recount. Give that test as the `--check` and say what it covers. An attack that cannot apply has no command and text starting `n/a:` with the reason: `herd note --tried --attack collision "n/a: the tool takes one value"`. The report shows it as n/a.
3. Run them. If you can spawn a fresh-context subagent, give it only the request, the criteria and how to run the tool, and ask it to break it. Otherwise do it yourself and say it was not fresh.
4. Log each attempt with `herd note --tried` (plus `--attack <name> --check "<command>"` for a standard attack; a later note for the same attack replaces a wrong command), each failure with `--found`, each fix with `--fixed`, each limit you leave with `--open`, as the run skill's Rules say.
5. Turn each failure into a regression test, then fix it.
6. A limit you leave that narrows a human any/every claim (only, first, rejected, assumed) is shown to the human as not proven. Prefer testing the claim under it, or lifting it.
