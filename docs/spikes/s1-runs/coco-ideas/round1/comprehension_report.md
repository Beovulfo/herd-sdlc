# Stage 6 Report: comprehension

**Target:** `docs/designs/herd-coco-ideas.md` (whole file, no GoldfishContext)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-comprehension` | completed |

## What this proposes

Four additions to a plugin called Herd (the "MVP"). The core rule stays: a task is done only when fresh runnable checks pass. The four are: (1) a "quick" route for trivial changes with one criterion; (2) an optional test budget and per-criterion test level; (3) an opt-in lint/typecheck hook that runs after each file edit; (4) an adaptive `/herd:verify` skill that detects project type and guides a human to write criteria (kind auto/proxy/attested). A shared detector script (`herd_detect.py`) is built first and feeds items 3 and 4. Work goes in five test-first steps, then docs.

## How the existing system works, per this document

Barely described. From hints: a `herd` CLI has `init`, `check`, `report`, `verify`, `gate`. Tasks live in `task.toml` with criteria that each carry a runnable `check`. Config is `herd.toml`. A Stop hook blocks completion without fresh passing evidence, and a triage step assigns a risk "floor". Skills `herd:run` and `herd:criteria` exist. `herd:run` already runs `verify` before building, so checks fail first. Evidence records a command, exit code, output tail and SHA. The reviewer could not build a clear picture of how these pieces connect.

## Findings

### Blocker (2)

- **S6-B1 No description of the existing Herd system (Overview, Order).** Task, criterion, `check`, evidence, gate, Stop hook, "fresh", "active task" are never defined or linked; a cold reader cannot judge fit. (Orchestrator note: this reviewer ran without GoldfishContext by design; the document may reasonably assume repo knowledge, so the Blocker rating is the reviewer's and is likely severe for a plan living beside the PRD. A one-line link to the PRD and README would resolve it.)
- **S6-B2 "Full report in the session" is not durable (L18).** Research report not linked; [V]/[I] claims untraceable beyond three URLs.

### Major (9)

- **S6-M1 Triage, floor, risk levels undefined (L5, L34, L80).** Who assigns them and which values exist.
- **S6-M2 Red-first half defined (L24, L68, L80).** Whether `verify` before building is enforced; where "record it" is stored; "recorded waiver" has no format.
- **S6-M3 "Vacuous" defined only by examples (L34, L54, L67).** "Step 4 lint of checks" vs "check-hygiene warnings" naming; zero-test detection unspecified; `grep` flagged though often legitimate.
- **S6-M4 Enforcement inconsistent (L34 vs L54).** `init --quick` refuses vacuous checks, `herd check` only warns.
- **S6-M5 Detection spec vague (L25, L29).** `scope = "affected"` undefined; `unsure` not in dict schema; which entries are `?` not listed.
- **S6-M6 Project-type table referenced, not included (L25, Step 1).**
- **S6-M7 `attested` freshness undefined; threshold for rubber-stamping undefined (L66, L71, L74).**
- **S6-M8 `herd lint` underspecified (L51-52).** "Active Herd task", `{file}` placeholder, `globs` default, typecheck timing, hook vs `--suggest` dual use.
- **S6-M9 Naming collision and missing link (L14, L71).** `herd verify` CLI vs `/herd:verify` skill; `herd detect` subcommand absent from Overview/Step 1.

### Nit (6)

- **S6-N1 "Coco" never described or linked (L9, title).**
- **S6-N2 [V] claims lack verification note (L20-22)** while L52 correctly flags `MultiEdit` as unverified.
- **S6-N3 `scripts.test_herd_cli` assumed to exist (L38, L46, L55, L72).**
- **S6-N4 Skill type menu does not map to detector types (L61).** No marker for notebook or web app.
- **S6-N5 "CI", "agent trial", "scratch-repo run" undefined (L78).**
- **S6-N6 Status "Draft (plan, not reviewed)" has no approval path or open questions (L4).**

## Counts

Blocker 2, Major 9, Nit 6.
