# temporal-async-debug Todo (Failure-Mode Catalog)

Mirrors `plan.md`. Check off each numbered sub-step as `/bpe:execute-plan` or `/bpe:goal` completes it.

## Section 1: Misbehavior Modes And The Starvation Probe

### Step 1: Extend The Mode Set (cpu, slow_heartbeat, stuck_no_heartbeat)

- [x] 1. RED: tests/test_activities.py cases for cpu (no sleep/await), slow_heartbeat (awaits + heartbeats >= 2), stuck_no_heartbeat (awaits, no heartbeat), VALID_MODES set
- [x] 2. Document: VALID_MODES constant in shared.py, extended _apply_mode docstring
- [x] 3. GREEN: three new _apply_mode branches; markers on cpu loop and stuck_no_heartbeat; block/slow unchanged
- [x] 4. RED: end-to-end slow_heartbeat activity test (result returns and heartbeats fire)
- [x] 5. GREEN: wire the branch; tune step size for the asserted heartbeat count
- [x] 6. REFACTOR: keep the five-way branch flat and readable
- [x] 7. Docs: confirm VALID_MODES and docstrings present
- [x] 8. Verify: coverage of the three new branches, run `just check`

### Step 2: Extend The Starvation Probe To cpu And slow_heartbeat

- [x] 1. RED: tests/test_starvation_probe.py cpu starves, slow_heartbeat does not
- [x] 2. Document: module docstring names the two families (freeze vs cooperative)
- [x] 3. GREEN: call real _apply_mode; no new product code
- [x] 4. RED: comparative assertion (cpu records fewer ticks than slow_heartbeat)
- [x] 5. GREEN: tune thresholds/tick counts to be reliable, not flaky
- [x] 6. REFACTOR: fold four modes through one probe helper
- [x] 7. Docs: none
- [x] 8. Verify: cpu case has teeth (fails if switched to await), run `just check`

## Section 2: Bystander Workflows

### Step 3: Short-Work Bystander (SalesRollupWorkflow)

- [x] 1. RED: tests/test_rollup.py happy path (start_time_skipping, summary includes period, no network) + roll_up_sales unit test
- [x] 2. Document: rollup.py module + class + activity docstrings
- [x] 3. GREEN: SalesRollupInput/Output in shared.py; rollup.py with roll_up_sales (cooperative work, no network) and SalesRollupWorkflow
- [x] 4. RED: concurrent executions all succeed with distinct periods
- [x] 5. GREEN: wire concurrent test
- [x] 6. REFACTOR: keep rollup.py minimal and obviously correct
- [x] 7. Docs: none
- [x] 8. Verify: coverage of rollup computation and orchestration, run `just check`

### Step 4: Schedule-To-Start Sample (PriceQuoteWorkflow)

- [ ] 1. RED: tests/test_quote.py happy path (quote includes sku, no network) + quote_activity_options schedule_to_start assertion
- [ ] 2. Document: quote.py module + class + activity docstrings (staleness rationale)
- [ ] 3. GREEN: PriceQuoteInput/Output in shared.py; quote.py with compute_quote, quote_activity_options (marked schedule_to_start_timeout), PriceQuoteWorkflow
- [ ] 4. RED: concurrent quotes reflect sku and quantity
- [ ] 5. GREEN: wire concurrent test
- [ ] 6. REFACTOR: keep quote.py minimal
- [ ] 7. Docs: none
- [ ] 8. Verify: coverage of quote computation and options helper, run `just check`

## Section 3: Workflow Timeout Selection Per Mode

### Step 5: Per-Mode Activity Options In The Geo Workflow

- [ ] 1. RED: tests/test_geo_options.py geo_activity_options per mode (generous start_to_close, heartbeat_timeout for slow_heartbeat/stuck_no_heartbeat, maximum_attempts==1, schedule_to_close set) + unknown-mode ValueError
- [ ] 2. Document: geo_activity_options docstring mapping each mode to its timeouts
- [ ] 3. GREEN: geo_activity_options in workflow.py (maximum_attempts=1 marker kept); build activity kwargs from it
- [ ] 4. RED: existing workflow tests pass; slow_heartbeat runs to completion under start_time_skipping
- [ ] 5. GREEN: adjust execution wiring; keep get_ip/get_location signatures
- [ ] 6. REFACTOR: per-mode branching lives only in geo_activity_options
- [ ] 7. Docs: none
- [ ] 8. Verify: coverage of every mode's options and the guard, run `just check`

## Section 4: Worker, Starter, And Recipes

### Step 6: Register The Full Fleet On The Worker (task)

- [ ] 1. Scope defined (worker.py edit, import-and-smoke verification)
- [ ] 2. Tooling: python + temporal skill, temporal-docs MCP if needed
- [ ] 3. Do: import rollup and quote workflows/activities; add to workflows= and activities= lists; keep max_concurrent_activities=2 marker and metrics
- [ ] 4. Verify: import succeeds, `just check` exits 0
- [ ] 5. Document: none (fleet documented in README)

### Step 7: Extend The Starter To The Full Scenario Set

- [ ] 1. RED: tests/test_starter.py --mode over five VALID_MODES, --rollups/--quotes flags, input-construction helpers, full-flag parse
- [ ] 2. Document: starter.py module docstring for the full mode set, new flags, per-scenario mix
- [ ] 3. GREEN: mode choices from VALID_MODES; --rollups/--quotes; rollup_inputs_from_args/quote_inputs_from_args; per-scenario submission ordering; keep os._exit(0)
- [ ] 4. RED: input-construction edge test (distinct periods/skus for fan-out)
- [ ] 5. GREEN: wire main() to shared construction helpers
- [ ] 6. REFACTOR: separate parsing, construction, submission ordering
- [ ] 7. Docs: none
- [ ] 8. Verify: coverage of parsing and input construction, run `just check`

### Step 8: One Just Recipe Per Scenario (task)

- [ ] 1. Scope defined (justfile edit)
- [ ] 2. Tooling: none (just)
- [ ] 3. Do: keep `default` (`@just --list`) as the FIRST recipe so bare `just` prints the help
- [ ] 3. Do: healthy, block, cpu, slow, slow-heartbeat, stuck recipes as thin starter wrappers with the right fleet mix
- [ ] 4. Verify: bare `just` prints the recipe list, `just --list` shows every recipe and parses, `just check` exits 0
- [ ] 5. Document: none (recipes documented in README)

## Section 5: Documentation

### Step 9: Comprehensive README Catalog (task)

- [ ] 1. Scope defined (README.md rewrite as the in-repo tutorial home)
- [ ] 2. Tooling: tutorial-writing before drafting, review-content after, temporal skill + MCP for metric-name verification
- [ ] 3. Do: capture real tool output live (asyncio ps/pstree, CPU, metrics) for each scenario
- [ ] 3. Do: what-it-demonstrates + deliberately-broken warning + cross-type blast radius headline
- [ ] 3. Do: three-terminal quickstart
- [ ] 3. Do: one lesson per scenario (healthy, block, cpu, slow, slow_heartbeat, stuck_no_heartbeat, schedule-to-start) with healthy-vs-broken shapes
- [ ] 3. Do: mode-to-timeout-to-signature summary table with the frozen-loop vs saturation split
- [ ] 3. Do: platform gotchas (3.14+, Yama ptrace_scope, macOS sudo, transient asyncio ps)
- [ ] 3. Do: realistic-timeouts framing (start_to_close/schedule_to_close SLA, schedule_to_start rare, latency metric the tell, why no workflow timeouts)
- [ ] 3. Do: antipattern marker grep note + tutorial link placeholder (masonegger.com TODO)
- [ ] 4. Verify: review-content pass addressed; human-check writing rules, commands/metric names match code, output is real, warning present
- [ ] 5. Document: this step is the documentation

### Step 10: Refresh CLAUDE.md Architecture (task)

- [ ] 1. Scope defined (CLAUDE.md Architecture + Commands sections)
- [ ] 2. Tooling: none
- [ ] 3. Do: rewrite Architecture to the real modules (shared, activities five modes, workflow + geo_activity_options, receipt, rollup, quote, worker, starter), cross-type blast radius, diagnostic split
- [ ] 3. Do: update Commands demo recipes to match the justfile (healthy, block, cpu, slow, slow-heartbeat, stuck)
- [ ] 3. Do: keep antipattern marker convention; confirm grep string matches code
- [ ] 4. Verify: grep confirms no victim/Greeting references, module list matches src/, `just check` exits 0
- [ ] 5. Document: this step is the documentation
