# temporal-async-debug Todo (Fleet Localization)

Mirrors `plan.md`. Check off each numbered sub-step as `/bpe:execute-plan` or `/bpe:goal` completes it.

## Section 1: Observability For Two Workers

### Step 1: Third Scrape Target And The Per-Worker Panel

- [x] 1. RED: config tests for three targets, the per-Worker expression, Task Queue parity, the six pinned expressions, unique ids
- [x] 2. Document: `prometheus.yml` header comment
- [x] 3. GREEN: add target 9466 and panel 7
- [x] 4. RED: allowlist test covers the new panel's label selector
- [x] 5. GREEN: fix the metric-name helper only if needed
- [x] 6. REFACTOR: dashboard JSON formatting, panels 1 to 6 untouched
- [x] 7. Docs: none (Step 14)
- [x] 8. Verify: test has teeth, `just check`

## Section 2: Exercise 06 Code

### Step 2: Exercise 06 Solution Copy With The Lock And The Lookup

- [x] 1. RED: copy the base modules, swap the field, write the `db_lock`, activity, probe, metrics-port, and executor tests
- [x] 2. Document: module docstrings for `db_lock.py`, `activities.py`, `shared.py`, `worker.py`
- [x] 3. GREEN: `db_lock.py`, the lookup, the bug form (probe fails), then the fix and the Worker settings
- [x] 4. RED: Workflow passes `location_cache_path` through
- [x] 5. GREEN: wire the Workflow and the Worker registration
- [x] 6. REFACTOR: remove exercise 01 leftovers, isolate the lookup helper
- [x] 7. Docs: none (Step 10)
- [x] 8. Verify: probe test has teeth, no marker in solution, `just check`

### Step 3: The Flood Starter

- [x] 1. RED: flood plan, summary, and formatting tests (`test_flood.py`); parser and gate tests (`test_starter.py`)
- [x] 2. Document: `flood.py` and `starter.py` module docstrings
- [x] 3. GREEN: pure functions in `flood.py`; parser and gate in `starter.py`
- [x] 4. RED: main flow test with a fake client (`--bad 0` and `--bad 1`)
- [x] 5. GREEN: producer, bad run with `arm()`, gate, tail, summary
- [x] 6. REFACTOR: `flood.py` free of I/O and Temporal imports, no role names
- [x] 7. Docs: none
- [x] 8. Verify: bucketing test has teeth, `just check`, live healthy smoke check

### Step 4: Exercise 06 Practice Copy And Gate Integration

- [x] 1. RED: copy the solution, trim the tests, write the probe stub
- [x] 2. Document: practice docstrings describe the code as it is
- [x] 3. GREEN: restore the bug with the marker and the TODO comments, remove the executor
- [x] 4. RED: both gate loops visit exercise 06
- [x] 5. GREEN: fix ruff and mypy findings without removing the bug
- [x] 6. REFACTOR: `diff -r` shows only the fix lines, marker, TODO comments, and tests
- [x] 7. Docs: none
- [x] 8. Verify: marker greps, `just check`, `just check-practice`

## Section 3: Receipt-Gap Helper

### Step 5: Identity View For The Receipt-Gap Helper

- [x] 1. RED: capture and mask fixtures from a live two-Worker bad flood
- [x] 1. RED: identity, attribution, summary, and flag tests; default output byte for byte
- [x] 2. Document: module docstring (run instructions, flags, retried-Activity limit)
- [x] 3. GREEN: flags, identity facts, per-identity summary
- [x] 4. RED: end-to-end `main()` test with a fake runner
- [x] 5. GREEN: wire the flags through `main` and `receipt_ids`
- [x] 6. REFACTOR: module order, type hints, docstrings
- [x] 7. Docs: none (Step 14)
- [x] 8. Verify: default-output test has teeth, `just check`, hostname check on fixtures

## Section 4: Housekeeping

### Step 6: Review Findings With No Behavior Change (task)

- [x] 1. Scope defined (six findings, no behavior change)
- [x] 2. Tooling: python:python, just, grep
- [x] 3. Do: exercise 03 port resolved once
- [x] 3. Do: exercise 05 docstring and `PAYLOAD_RECORDS` comment figures
- [x] 3. Do: `_job_is_done` tests, justfile comment, exercise 01 TODO letters
- [x] 4. Verify: `just check && just check-practice`
- [x] 5. Document: none (findings listed in the step report)

## Section 5: Live Captures

### Step 7: Capture Exercise 06 On Two Workers (task)

- [ ] 1. Scope defined (three floods, each on a fresh dev server)
- [ ] 2. Tooling: temporal CLI, compose stack, py-spy, asyncio ps, top, receipt-gaps, shot.py
- [ ] 3. Do: flood A (healthy, practice)
- [ ] 3. Do: flood B (bad, practice) with every fleet tool reading and the panel images
- [ ] 3. Do: flood C (bad, solution) with the stop-and-correct rule
- [ ] 3. Do: mask excerpts, index, record findings
- [ ] 4. Verify: every tool indexed, floods read as expected, no hostname in committed files
- [ ] 5. Document: scratchpad INDEX.md and FINDINGS.md; commit PNG files only

### Step 8: Capture Exercise 03 And The Root Reference Readings (task)

- [ ] 1. Scope defined (exercise 03, root logs, exercise 02 panels, ptrace reading)
- [ ] 2. Tooling: temporal CLI, just, py-spy, top, sysctl (read only), shot.py
- [ ] 3. Do: exercise 03 `--bad 2` on one Worker and `--bad 4` on two, with placement
- [ ] 3. Do: root healthy-only Worker log and root `just block` log and panel reading
- [ ] 3. Do: exercise 02 solution panels and the `sysctl` reading
- [ ] 4. Verify: every reading indexed, placement counts add up
- [ ] 5. Document: scratchpad INDEX.md and FINDINGS.md; commit replaced PNG files only

## Section 6: Shared Recognition Block

### Step 9: Recognition Block And Teaching-Code Note (task)

- [ ] 1. Scope defined (README.md, the primer)
- [ ] 2. Tooling: tutorial-writing, voice:teaching, review-content, preflight
- [ ] 3. Do: teaching-code note and recognition block in README.md
- [ ] 3. Do: symptom list, link, and `activity_executor` sentence in the primer
- [ ] 3. Do: review-content pass
- [ ] 4. Verify: lint-keyboard and lint-prose on both files
- [ ] 5. Document: none

## Section 7: Exercise READMEs

### Step 10: Exercise 06 README (task)

- [ ] 1. Scope defined (the exercise 06 README)
- [ ] 2. Tooling: tutorial-writing, voice:teaching, review-content, preflight
- [ ] 3. Do: opening and Part A
- [ ] 3. Do: Part B with the tools in a fleet and the production note
- [ ] 3. Do: Parts C, D, and E
- [ ] 3. Do: smell-report section and review-content pass
- [ ] 4. Verify: lint, capture provenance, no hostname
- [ ] 5. Document: `docs/drafts/smell-reports.md` section

### Step 11: Fold-Ins For Exercises 01 To 05 (task)

- [ ] 1. Scope defined (five exercise READMEs)
- [ ] 2. Tooling: tutorial-writing, voice:teaching, review-content, preflight
- [ ] 3. Do: single-Worker sentence and Part B link in all five
- [ ] 3. Do: exercise 01 table and `activity_executor` statement; exercise 02 heartbeat sentence
- [ ] 3. Do: exercise 03 second Worker required with `--bad 2` and `--bad 4`; exercise 05 panel sentence
- [ ] 3. Do: review-content pass
- [ ] 4. Verify: lint, no `--bad 3`, links present
- [ ] 5. Document: none

## Section 8: Series Drafts

### Step 12: Draft Part 7 (task)

- [ ] 1. Scope defined (`docs/drafts/part-7-finding-the-frozen-worker.md`)
- [ ] 2. Tooling: tutorial-writing, voice:teaching, review-content, preflight
- [ ] 3. Do: write the draft from the exercise README and the captures
- [ ] 3. Do: smell-report section and review-content pass
- [ ] 4. Verify: lint clean, capture provenance, no hostname
- [ ] 5. Document: `docs/drafts/smell-reports.md` section

### Step 13: Updates To Parts 1 To 6 (task)

- [ ] 1. Scope defined (six parts and the smell reports)
- [ ] 2. Tooling: tutorial-writing, voice:teaching, review-content, preflight
- [ ] 3. Do: single-Worker sentence in all six; fold-ins in parts 2, 3, and 4
- [ ] 3. Do: part 1 clone command, ptrace output, and the tag pair
- [ ] 3. Do: replace the eleven tag pairs in the smell reports with build decisions
- [ ] 3. Do: review-content pass
- [ ] 4. Verify: no old CLAUDE_HELP tags, lint
- [ ] 5. Document: none

## Section 9: Root Documentation Refresh

### Step 14: README, CLAUDE.md, And The Drafts Index (task)

- [ ] 1. Scope defined (README.md, CLAUDE.md, `docs/drafts/README.md`)
- [ ] 2. Tooling: review-content, style-linting, preflight
- [ ] 3. Do: README.md (four layers, table, flags, Observability, permitted edits, ptrace, latency figure)
- [ ] 3. Do: CLAUDE.md and `docs/drafts/README.md`
- [ ] 3. Do: final review-content pass over six READMEs and seven drafts
- [ ] 4. Verify: full gate, lint, greps
- [ ] 5. Document: none

## Section 10: Review Handoff

### Step 15: Decisions Record And The Pull Request Comment (task)

- [ ] 1. Scope defined (the decisions record and one comment on pull request 4)
- [ ] 2. Tooling: gh, lint
- [ ] 3. Do: write the record (reading order, eleven decisions, confirm-at-review list, open tags)
- [ ] 3. Do: lint and privacy check
- [ ] 3. Do: post the comment
- [ ] 4. Verify: comment visible, gate green, tree clean
- [ ] 5. Document: none
