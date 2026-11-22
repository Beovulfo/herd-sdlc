# Example: a supermarket route optimizer

A benchmark of Herd against no workflow on one task, with three models. Start with [`BENCHMARK.md`](BENCHMARK.md).

![Animation of one basket: list-order route against the optimized route](images/simulation.svg)

| What | Where |
| --- | --- |
| Method, results, cost, caveats | [`BENCHMARK.md`](BENCHMARK.md) |
| Round-by-round log | [`comparison.md`](comparison.md) |
| Issues the test found in Herd, and their fixes | [`issues.md`](issues.md) |
| The prompts | [`goal-v2.md`](goal-v2.md), and the appendix of the benchmark |
| Solutions | `herd-run`, `run-1-original-prompt`, `baseline-run`, `haiku-herd-run`, `haiku-baseline-run`, `sonnet-herd-run`, `sonnet-baseline-run` |
| Hidden verifiers and tests | [`verifier/`](verifier) |
| Images, and the script that draws them | [`images/`](images) |
| How the live runs were driven | [`RUNBOOK.md`](RUNBOOK.md) |
