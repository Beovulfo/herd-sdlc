# Example: a supermarket route optimizer

One benchmark: the same prompt, given to the same model with and without Herd. Start with [`BENCHMARK.md`](BENCHMARK.md).

![Animation of one basket: list-order route against the optimized route](images/simulation.svg)

| | |
| --- | --- |
| [`BENCHMARK.md`](BENCHMARK.md) | method, results, cost, limits |
| [`prompt.md`](prompt.md) | the prompt both runs received |
| [`with-herd/`](with-herd) | the Herd run: code, task file, evidence report, caveat log |
| [`without-herd/`](without-herd) | the run with no workflow: code |
| [`verifier/`](verifier) | the hidden general verifier, the robustness probe, and their tests |
| [`results/`](results) | raw verifier and probe output |
| [`images/`](images) | the three images, and the script that draws them |
