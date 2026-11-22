# Plan review: herd-coco-ideas (v0.2)

Review round 1: `round1/` (stages 5, 6, 7, 8; stage 9 skipped, the plan has no Detailed Implementation Plan). 7 reviewer runs, none failed. After dedup: 3 Blockers, 11 Majors, 15 Nits (raw 5/37/36). The synthesizer downgraded two stage-6 Blockers to one Major: that reviewer had no context by design.

Resolve (Elephant, no human gate; scope calls are reversible and listed):
- C-B1 red-first claimed as a guard but only prose: made visibility only. `verify` records `red.json` on first verify, report shows the count; no gate rule, no waiver, removed from mitigations as a guarantee.
- C-B2 quick route data flow: init runs triage on goal text, refuses `high` or empty check; skips criteria interview, approval, fresh review; keeps verify and Stop gate; triage evasion stated.
- C-B3 missing sections: added Problem, Goals, Non-Goals, Alternatives.
- C-M1 order: hygiene before routing. C-M2 budget warning needed stored risk: dropped the warning, `test_budget` is a note. C-M3 `kind` weakens evidence: deferred, with `level`. C-M4 lint hook: non-blocking `additionalContext`, timeout above `timeout_s`, `cwd` from payload, reuse `run_check`, exact-shape test. C-M5 `typecheck`: cut. C-M6 vacuity: advisory denylist, one place, limits stated, zero-test detection deferred. C-M7 scope: cut `level`, `kind`, per-type files, extra ecosystems, `lint --suggest` kept small. C-M8 detection table written in the document, no `unsure` rows. C-M9 sections split. C-M10 context linked. C-M11 skill renamed `/herd:evidence`; `herd detect` in Step A.
- Nits: most fixed in the rewrite (terms, links, trust note for `herd.toml`, blank lines). Left: wording of informal terms in the research summary.
Not run: round 2 review of the rewritten plan.
