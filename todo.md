# temporal-async-debug Todo (Event-Loop Exercises)

Mirrors `plan.md`. Check off each numbered sub-step as `/bpe:execute-plan` or `/bpe:goal` completes it.

## Section 0: Prose Tooling Pre-flight

### Step 0: Vale Config, Prose Lint Recipes, And The Pre-flight Gate (task)

- [ ] 1. Scope defined (.vale.ini at the repo root; justfile gains preflight, lint-prose, lint-keyboard; `just check` untouched)
- [ ] 2. Tooling: content-design:style-linting; vale >= 3.20, content-design scripts (normalize-keyboard-chars.py, wordcount), voice:teaching skill files, uv
- [ ] 3. Do: create .vale.ini exactly as plan.md Step 0 gives it (MasonBase default; MasonBase + MasonTechnical under {docs/drafts,exercises}/**/*.md; Std package)
- [ ] 3. Do: add the preflight, lint-prose, and lint-keyboard recipes exactly as plan.md Step 0 gives them (plugin roots resolved by glob, never pinned)
- [ ] 3. Do: run `just preflight` and fix the tooling until it exits 0; never weaken a check
- [ ] 4. Verify: `just preflight` exits 0 with every ok line; `vale ls-config` shows MasonTechnical under the docs/drafts,exercises glob; `just lint-prose` (no args, and with one file named) exits 0 and emits JSON; `just lint-keyboard` exits 0 both ways; bare `just` lists the three recipes; `just check` exits 0
- [ ] 5. Document: recipe comments only (README and CLAUDE.md recipe tables are Step 13)

## Section 1: Root Package Trim

### Step 1: Trim The Root Package To The Frozen-Loop Reference

- [ ] 1. RED: update root tests to the trimmed surface (VALID_MODES {block,cpu}; delete slow/slow_heartbeat/stuck tests; fixed timeouts, no maximum_attempts; registration without the quote; drop saturation/--quotes starter tests; delete quote/geo-options timeout cases); `just check` now fails against untrimmed source
- [ ] 2. Document: module docstrings describe the frozen-loop reference (block and cpu only)
- [ ] 3. GREEN: trim shared.py (VALID_MODES, drop quote dataclasses), activities.py (keep block+cpu, drop the rest and the heartbeat helper), workflow.py (one fixed options set, drop RetryPolicy and marker), delete quote.py, worker.py (drop quote, keep max=2 but remove its marker + add plain comment), starter.py (drop saturation ordering/SATURATION_MODES/concurrent fallback/--quotes, keep freeze ordering + gate + os._exit); grep for removed surface returns nothing
- [ ] 4. RED: guard test (importing quote raises ModuleNotFoundError; VALID_MODES length 2)
- [ ] 5. GREEN: guard passes
- [ ] 6. REFACTOR: remove dead imports/constants/helpers; keep block+cpu markers exact
- [ ] 7. Docs: none (root README/CLAUDE.md are Step 13; README recapture is Step 10)
- [ ] 8. Verify: suite covers block/cpu/healthy/failover/fixed-timeouts/registration/ordering; `grep ANTIPATTERN src` returns exactly block+cpu; run `just check`

## Section 2: Observability Stack

### Step 2: Observability Config And Its Tests

- [ ] 1. RED: tests/test_observability_config.py, invariants only (compose exactly prometheus and grafana, no temporal image; prometheus.yml exactly the two targets 9464 and 9465; panel exprs in the frozen-loop metric allowlist, passes with a panel removed); no test that only asserts a file parses or a config value we chose
- [ ] 2. Document: header comments on docker-compose.yml and prometheus.yml (stack scope, ports, host networking)
- [ ] 3. GREEN: observability/docker-compose.yml, prometheus.yml, grafana/provisioning/{datasources,dashboards}, grafana/dashboards/async-debug.json (activity+workflow-task latency, failures/timeouts, slots used, backlog)
- [ ] 4. RED: cross-file consistency test (provider path matches the compose mount path)
- [ ] 5. GREEN: align mount and provider paths
- [ ] 6. REFACTOR: minimal YAML and JSON, no stray services
- [ ] 7. Docs: none (Observability README section is Step 13)
- [ ] 8. Verify: config tests cover the two-service invariant, two targets, allowlist; run `just check`

### Step 3: Metrics And Server Just Recipes (task)

- [ ] 1. Scope defined (justfile edit: server --metrics-port 9465, metrics, metrics-down)
- [ ] 2. Tooling: none (just, docker-compose v1)
- [ ] 3. Do: server appends --metrics-port 9465; metrics up -d; metrics-down down; default stays first
- [ ] 4. Verify: bare `just` lists recipes, `just --list` shows the three, `just check` exits 0
- [ ] 5. Document: none (README section is Step 13)

## Section 3: Exercise Gate Harness

### Step 4: The Per-Directory Solution Gate And Practice Lint Pass (task)

- [ ] 1. Scope defined (justfile + pyproject edit; root gate excludes exercises/, per-dir loops, no-op when empty)
- [ ] 2. Tooling: python:python (pyproject config shape)
- [ ] 3. Do: exclude exercises/ from root ruff/mypy/pytest; `just check` loops solution dirs (ruff, ruff format, mypy, pytest) fail-fast and no-op when empty; `just check-practice` loops practice dirs (ruff, mypy)
- [ ] 4. Verify: `just check` exit 0 with no exercises present; `just check-practice` exit 0; check-practice in `just --list`
- [ ] 5. Document: none (CLAUDE.md gate description is Step 13)

## Section 4: The Five Exercises

### Step 5: Exercise 01 Sync HTTP Client

- [ ] 1. RED: create solution/ flat copy (flat imports, bystander fleet, freeze ordering, slow_upstream.py, tests/conftest); async def geo on sync httpx.Client, bad run points at the local slow endpoint; solution/tests/test_probe.py failing against the unfixed copy
- [ ] 2. Document: module docstrings on solution activities.py and worker.py
- [ ] 3. GREEN: def geo activities on sync httpx.Client; worker activity_executor=ThreadPoolExecutor sized to max_concurrent_activities; no marker; grep clean
- [ ] 4. Create practice/: same copy before the fix (async def + sync client on the loop, marker kept), `# TODO PART C/D:` comments, practice/tests/test_probe.py stub
- [ ] 5. Integrate into the gate: `just check` green incl. solution loop; `just check-practice` green
- [ ] 6. REFACTOR: keep the solution-vs-practice diff to the fix lines and TODO comments
- [ ] 7. Docs: none (README is Step 11)
- [ ] 8. Verify: probe test has teeth (fails if reverted to async-on-loop), revert, run `just check` and `just check-practice`

### Step 6: Exercise 02 Sleep Between Heartbeats

- [ ] 1. RED: create solution/ flat copy; poll loop over a slow job keyed on the workflow run id, waiting in awaited 1-second ticks with activity.heartbeat() per tick, under a fixed heartbeat_timeout (5 s) shorter than the poll interval (8 s); solution/tests/test_heartbeat.py asserting heartbeat count >= 2 within one poll wait AND an unstarved probe, failing against the time.sleep loop
- [ ] 2. Document: module docstring on solution activities.py (awaited short-tick wait with a heartbeat per tick, so heartbeats flush and cancellation lands)
- [ ] 3. GREEN: replace the single time.sleep(poll_interval) with the awaited tick loop; keep activity async; remove marker; grep clean
- [ ] 4. Create practice/: one heartbeat then time.sleep(poll_interval) per poll (marker kept, explaining the frozen heartbeat task and the uncancellable sleep), `# TODO PART C:` at the time.sleep line, test_heartbeat.py stub with `# TODO PART D:`
- [ ] 5. Integrate into the gate: solution green (incl. heartbeat+probe), practice green
- [ ] 6. REFACTOR: keep the diff to the wait (one sleep line becomes the tick loop) and the TODO comment
- [ ] 7. Docs: none
- [ ] 8. Verify: test fails if reverted to the single time.sleep, revert, run `just check` and `just check-practice`

### Step 7: Exercise 03 CPU Bound

- [ ] 1. RED: create solution/ flat copy; async def geo with a CPU-bound transform of the provider response; solution/tests/test_probe.py failing against the on-loop computation
- [ ] 2. Document: module docstrings on solution activities.py and worker.py
- [ ] 3. GREEN: def activities + ThreadPoolExecutor; CPU transform kept but no marker; grep clean
- [ ] 4. Create practice/: async def + GIL-pinning transform (marker kept), TODO C/D comments, test_probe.py stub
- [ ] 5. Integrate into the gate: solution green, practice green
- [ ] 6. REFACTOR: keep the diff to the fix lines and TODO comments
- [ ] 7. Docs: none
- [ ] 8. Verify: probe fails if the transform moves back onto the loop, revert, run `just check` and `just check-practice`

### Step 8: Exercise 04 Zombie Thread

- [ ] 1. RED: create exercises/04-zombie-thread/solution/ flat copy; solution/tests/test_cancel_stops_work.py (ActivityEnvironment cancel: work stops at next heartbeat) + build_worker assertion that executor max_workers >= max_concurrent_activities; failing against the to_thread-no-heartbeat shape and unsized executor
- [ ] 2. Document: module docstrings on solution activities.py and worker.py (def activity + sized executor + heartbeat-from-thread so cancel reaches the work)
- [ ] 3. GREEN: def geo activities that heartbeat from their own thread and catch CancelledError; worker activity_executor sized to max_concurrent_activities; no marker; grep clean
- [ ] 4. Create practice/: the shipped-first state (async def + asyncio.to_thread, heartbeat_timeout, no heartbeat; marker kept, explaining why the cancel never reaches the thread so the work finishes after the failure and the retry runs it twice), `# TODO PART C:` at the to_thread line + worker executor arg, test_cancel_stops_work.py stub with `# TODO PART D:`
- [ ] 5. Integrate into the gate: solution green (incl. cancel + executor-size), practice green
- [ ] 6. REFACTOR: keep the diff to the activity body, the worker executor arg, and the TODO comments
- [ ] 7. Docs: none
- [ ] 8. Verify: cancel test fails if reverted to async to_thread no-heartbeat, revert, run `just check` and `just check-practice`

### Step 9: Exercise 05 Catching Blockers Early

- [ ] 1. RED: create solution/ flat copy; async def get_location with a synchronous JSON round trip of a generated payload (200-500 ms) on the loop, the starter submitting receipts during the serialization so their delay is reproducible; solution/tests/test_probe_all_activities.py parametrized over every registered async def activity, failing against the on-loop serialization
- [ ] 2. Document: module docstring on solution activities.py (serialization off the loop; probe test as the regression guard)
- [ ] 3. GREEN: move the serialization off the loop (to_thread or def+executor, whichever keeps the probe green); no marker; grep clean
- [ ] 4. Create practice/: synchronous serialization on the loop (marker kept), `# TODO PART C:` at the serialization line, test_probe_all_activities.py stub with `# TODO PART D:`
- [ ] 5. Integrate into the gate: solution green (incl. parametrized probe), practice green
- [ ] 6. REFACTOR: keep the diff to the serialization line and the TODO comment
- [ ] 7. Docs: none
- [ ] 8. Verify: parametrized probe fails if the serialization moves back onto the loop, revert; `grep -rn "ANTIPATTERN (deliberate, for teaching)" exercises/*/solution` empty across all five; run `just check` and `just check-practice`

## Section 5: Live Captures

### Step 10: Capture Before And After For Every Exercise Plus The Baseline (task)

- [ ] 1. Scope defined (scratchpad captures + docs/images/ PNGs; no code changes except a possible panel/metric-name fix)
- [ ] 2. Tooling: temporal skill, temporal-docs MCP; temporal CLI, docker-compose v1, uvx py-spy, PYTHONASYNCIODEBUG for 05, Grafana capture
- [ ] 3. Do: start stack (server 9465, metrics, worker); baseline `just healthy` captures (healthy asyncio ps, latency panels)
- [ ] 3. Do: 01 before+after (frozen shape, py-spy on httpx.Client line, CPU near zero, rollup timeout, workflow-task latency spike; after loop live, HTTP read on executor thread)
- [ ] 3. Do: 02 before+after (retry storm in workflow show through to the succeeding attempt, zombie poll lines in the Worker log, bystanders failing, py-spy on time.sleep; after last-heartbeat advancing every second, first-attempt completion)
- [ ] 3. Do: 03 before+after (frozen shape, top ~100% on one core captured next to 01's near-zero, py-spy in compute loop, rollup failure; after loop live, computation on executor thread, second Worker combined CPU > 100%)
- [ ] 3. Do: 04 before+after (first attempt times out, detached-thread work finishing after the failure and the retry overlapping it, py-spy showing the orphaned thread, the two startup traps; after CancelledError in thread, no overlap)
- [ ] 3. Do: 05 before+after (healthy vs practice receipt started-to-completed gap in workflow show, asyncio debug slow-step warning, py-spy serialization line; after receipt gap back to ms, no warning, parametrized probe passes)
- [ ] 3. Do: save Grafana PNGs under docs/images/ as <exercise>-<state>-<panel>.png
- [ ] 3. Do: if the dev server lacks the backlog gauge or a metric name is wrong, fix the dashboard JSON, update the allowlist test, note for the README, re-run `just check`
- [ ] 4. Verify: every capture Steps 11 and 12 need exists and is from the right copy/state; docs/images/ holds baseline + before/after per exercise; re-run `just check` if the dashboard changed
- [ ] 5. Document: scratchpad index mapping each capture to exercise, state, and tool

## Section 6: Exercise READMEs

### Step 11: Write The Five Exercise READMEs From The Captures (task)

- [ ] 1. Scope defined (five exercises/<NN-name>/README.md in the 102 structure; docs/drafts/smell-reports.md with one section per README)
- [ ] 2. Tooling: `just preflight` must pass; tutorial-writing first, voice:teaching second (draft mode), review-content after; temporal skill + MCP; `just lint-prose` and `just lint-keyboard`
- [ ] 3. Do: run `just preflight` (non-zero is a Failure); invoke tutorial-writing, then voice:teaching (read the profile in full); write each README (title, "During this exercise, you will", practice/solution note, prerequisites -> root README + `just metrics`, Parts A-E with Part A the misbehavior as met in production and Part B the Python-tooling diagnosis with Grafana last as corroboration, closing line); quote only that exercise's Step 10 captures; name the Grafana panel; keep each on the one mechanism
- [ ] 3. Do: write each README's smell report (verbatim quote + rule per bullet) and open questions (CLAUDE_HELP) to docs/drafts/smell-reports.md; the scaffold commit is the handoff, nothing publishes
- [ ] 4. Verify: review-content on each README; `just lint-prose` no error-level alerts, `just lint-keyboard` clean; human-check 102 structure, closing line, capture traceability, panel named, writing rules, smell-reports section per README
- [ ] 5. Document: this step is the documentation (root README table is Step 13)

## Section 7: Tutorial Series Drafts

### Step 12: Write The Six-Part Series Drafts (task)

- [ ] 1. Scope defined (docs/drafts/part-1 .. part-6, tutorial-writing structure, no frontmatter, TODO cross-links; smell-reports.md section per part)
- [ ] 2. Tooling: `just preflight` must pass; tutorial-writing first (generate outline from the new captures), voice:teaching second (draft mode), review-content after; temporal + python skills, MCP; `just lint-prose`, `just lint-keyboard`, wordcount
- [ ] 3. Do: run `just preflight` (non-zero is a Failure); invoke tutorial-writing, then voice:teaching; part 1 from baseline captures + root setup (install, ptrace_scope, server, worker, metrics, healthy, dashboard); parts 2-6 follow exercises 01-05, each ending with the reader's fix and verification; quote only Step 10 captures; keep the series on the one mechanism; TODO links; no frontmatter
- [ ] 3. Do: append each part's smell report and open questions to docs/drafts/smell-reports.md
- [ ] 4. Verify: Vale clean per draft; `just lint-prose` no error-level alerts, `just lint-keyboard` clean; copy-editor pass; wordcount tracked; human-check six drafts, no frontmatter, series title, capture traceability, writing rules, primitives capitalized, smell-reports section per part
- [ ] 5. Document: docs/drafts/README.md updated in Step 13

## Section 8: Root Documentation Refresh

### Step 13: Root README, CLAUDE.md, And docs/drafts/README Refresh (task)

- [ ] 1. Scope defined (README.md, CLAUDE.md, docs/drafts/README.md edits; smell-reports.md section for README.md)
- [ ] 2. Tooling: `just preflight` must pass; tutorial-writing first, voice:teaching second (edit mode), review-content on README after editing; `just lint-prose`, `just lint-keyboard`
- [ ] 3. Do: run `just preflight` (non-zero is a Failure); invoke tutorial-writing, then voice:teaching; README to three lessons (recaptured), remove the saturation/heartbeat/schedule-to-start/timeout sections, add Exercises table + Observability section (what `just metrics` starts, dashboard at 3000, port 9465 and why, backlog note if dropped) + series title with TODO link; recipe table lists preflight, lint-prose, lint-keyboard
- [ ] 3. Do: CLAUDE.md to the trimmed package, three-layer layout, solution-copy carve-out, new recipes (server --metrics-port 9465, metrics, metrics-down, check loop, check-practice, preflight, lint-prose, lint-keyboard), per-dir gate; keep marker convention + grep; remove references to removed modes/quote/saturation
- [ ] 3. Do: docs/drafts/README.md lists part-1..part-6 and smell-reports.md, keeps original-draft provenance, keeps venue open
- [ ] 3. Do: append the README.md smell report and open questions to docs/drafts/smell-reports.md
- [ ] 4. Verify: review-content on README; `just lint-prose` no error-level alerts on README.md, CLAUDE.md, docs/drafts/README.md, `just lint-keyboard` clean; grep for stale refs (removed modes, quote, saturation, maximum_attempts); layer list matches tree; `grep -rn "ANTIPATTERN (deliberate, for teaching)" exercises/*/solution` empty; `just check` and `just check-practice` exit 0
- [ ] 5. Document: this step is the documentation
