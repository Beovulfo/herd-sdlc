# Focus replay fixtures

`run1` to `run6`: the `task.toml` and `notes.jsonl` of six Haiku benchmark runs on Herd 0.12.1 (supermarket
route, generic benchmark data). `task.toml` is the final file. `notes.jsonl` is cut before the first review note,
so it holds what the builder had written when the first review started. Used by `ReplayTests` in
`tests/test_herd_focus.py` (design G13).
