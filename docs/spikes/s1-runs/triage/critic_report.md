# Goldfish Review Report: Critic Review (one round)

**Target:** `docs/designs/herd-triage.md` (lines 1-153). Standard: `feature-spec-standard`.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-design` | completed |
| `egm-structural` | completed |
| `egm-style` | completed |

## Important caveat: apparent text corruption is a view artifact

Design and structural reviewers reported truncated or garbled passages (Non-Goals L26-29, CUJ 3/4, Alternative A L117-121, Trust rules L80, L149). The Read tool returned a lossy, compressed view for some reviewers (and for the synthesizer). The style reviewer retrieved the original and found coherent text. Synthesizer spot-check with Grep confirmed: L33 reads "The PRD needs an edit, or this design needs size and path restored"; L121 contains a full rejection reason; `### Verification Plan` exists at L188. Findings that rest only on "text is missing" are marked **Unverified (view artifact)** and downgraded to Nit pending a raw-file check by the author.

## Prioritized Findings (Blockers -> Major -> Nits)

### Agent-editable state file: floor/effective integrity not enforced - Severity: Blocker
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** L20 (G2), L86
* **Description:** The state file lives on `herd/<feature>`, the branch agents in steps 2-5 push to. "Record writer rejects agent output" covers only the Triage call. Any later agent commit can edit `floor` or `effective`. No integrity control (CI check on state-file diffs, CODEOWNERS entry, signed commits, hash verified at read) is specified.
* **Rationale:** Defeats P6 and G2 despite the trust split.
* **Fix:** Add an enforced mechanism and a test, for example `state_file_tamper_detected`.

### Floor input extraction unspecified and attacker-influenced - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** L15, L75
* **Description:** Nothing says who extracts paths from the issue body. If the LLM does, G2 is broken; if a regex, rules are undefined. An issue naming only `docs/x` is "known, matches no rule", floor `low`, while the real change touches `migrations/`. Floor is as strong as untrusted text.
* **Fix:** State the limit; consider `medium` unless a maintainer label confirms scope; add CUJ 3 variants.

### Ratchet vs human override, write semantics contradictory - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** L63, L69, L73, L77, L81, L86
* **Description:** L86 "written once by orchestrator" vs CUJ 4, CUJ 5, ratchet and `/herd retriage` writes; L73 "only record writer writes" vs orchestrator writes in CUJ 4. Human-lowered value vs step 5 re-raise is undefined, and the H1 re-open loop has no termination rule.
* **Fix:** One writer, explicit write-event list, precedence table plus a CUJ.

### Shadow mode contradicts G1 and PRD; no exit criterion - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-style`
* **Affected Scope:** L19, L141
* **Description:** "Arbiter ignores" results vs G1 (effective never below floor). "Agreement" and threshold undefined; the 5-feature S2 baseline is not the PRD 20-feature M0 bar, and the PRD baseline is a hand-run EGM, not Triage agreement.
* **Fix:** Say whether floor enforcement is off in shadow mode; define agreement metric and exit figure.

### No Risks and Mitigations section - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-structural`, `egm-style`
* **Affected Scope:** whole FeatureRange (L84, L139-143 partial)
* **Description:** Standard requires one. Uncovered: glob mis-specification, path normalisation (`..`, case, renames), `herd.yaml` drift over a feature's life, concurrent runs ("race" L84), `medium` default making the floor weak, label-spam or retriage DoS, scalability limits.
* **Fix:** Add a Risks table with mitigations.

### G1/G2 checks reference unresolved artifacts - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-style`, `egm-structural`
* **Affected Scope:** L19, L20, L45
* **Description:** L19 "see Verification Plan" and `fixtures/` vs `fixtures/triage/`; Verification Plan exists at L188 (beyond FeatureRange) so this is a path and reference mismatch, not a missing section. L45 "fixture ... in `scripts/triage_check.py`" is ambiguous. G2 gives no mechanism for determining agent origin of a field (name the typed enum plus reason contract).

### Unmeasured claims and thresholds - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** L15, L37, L120-121, L141
* **Description:** "often names no paths", "most features land on medium" lack data (use "expected to" or cite). Alt A fallback has no threshold; edit-rate warning threshold open (L37) so G3 cannot be judged.

### Rejection attributed to the author - Severity: Major
* **Reviewer Lens:** `egm-structural`, `egm-style`, `egm-design`
* **Affected Scope:** L121, L127, L133
* **Description:** "Rejected by author:" is the pattern the standard bars without a linked discussion. Technical reasons follow; drop the attribution, rename "Reason Rejection" to "Reason for rejection".

### Heading hierarchy: Future Improvements is H3 beside H2 sections - Severity: Major
* **Reviewer Lens:** `egm-structural`, `egm-style`
* **Affected Scope:** L147
* **Description:** Should be `##`. Also section names drift from the standard ("Problem" vs "Problem Statement", "Technical Plan (Architecture)" vs "Proposed Architecture"), and Open Questions (L31) precede the CUJs.

### Possible missing text (Non-Goals, CUJ 3/4, Alt A, Trust rule L80, L149) - Severity: Nit (Unverified, view artifact)
* **Reviewer Lens:** `egm-design`, `egm-structural`
* **Affected Scope:** L26-29, L57-63, L80-81, L117-121, L149
* **Description:** Reviewers (design, structural) saw fragments. Synthesizer verification shows at least L33 and L121 are intact in the raw file. Author should confirm L80 (herd.yaml-edit rule) and L26-29 in the raw file. Alt A content substance (L120 "rules alone give little signal") exists; the style point is the missing quantified threshold (covered above).

### `triage.status` enum `failed` undefined - Severity: Nit
* **Reviewer Lens:** `egm-design`, `egm-style`
* **Affected Scope:** L22, L84, L92
* **Description:** Define `failed` or remove; G4 only produces `fallback`.

### Rollback loses round counter and budget - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** L142
* **Description:** "Ignore `.herd/state`" drops PRD record fields; scope rollback to risk fields.

### Cost, PRD divergence and L0 owners - Severity: Nit
* **Reviewer Lens:** `egm-design`, `egm-style`
* **Affected Scope:** L33, L35, L140
* **Description:** No token or latency ceiling for the Triage call. PRD divergence and L0 need owner and date; PRD step 1 and section 5 table updated in the same change.

### Wording and notation nits - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** L11, L15, L29, L73, L80, L84, L86, L99, L140, L143, L149, rules at L135/L145/L152
* **Description:** Use "record writer" not "Code"; trim L15 "The difficulty:" fragment; add "(manual `/herd retriage` is in scope)" to L29; "loud warning" to "posts a comment on the issue"; define "race"; write "agents may push only to `herd/*` branches"; state low<medium<high ordering once; rewrite L140, L143, L149; make horizontal rules consistent; reduce dropped articles for a fresh reader.

## Reviewer process notes
* The structural reviewer could not find the PRD at the task-supplied path (path omitted "the"); PRD cross-references (L11, L33) were not checked by it. Design and style reviewers found the correct file.
