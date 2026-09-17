# temporal-async-debug Todo

Mirrors `plan.md`. Check off each numbered sub-step as `/bpe:execute-plan` completes it.

## Section 1: Scaffolding And Shared Types

### Step 1: Package And Test Scaffolding (task)

- [x] 1. Scope defined (src package, py.typed, tests dir, conftest, pyproject edits)
- [x] 2. Tooling ready (uv, ruff, mypy, pytest)
- [x] 3. Do: create src/temporal_async_debug/__init__.py and py.typed
- [x] 3. Do: create tests/__init__.py and tests/conftest.py
- [x] 3. Do: add hatchling wheel target to pyproject.toml
- [x] 3. Do: add pytest asyncio/pythonpath/testpaths config to pyproject.toml
- [x] 4. Verify: `just check` exits 0 (one import smoke test collected; see deviation note)
- [x] 5. Document: none

### Step 2: Shared Dataclasses And Task Queue Constant

- [x] 1. RED: tests/test_shared.py (block_seconds default 0.0, mode default, frozen, TASK_QUEUE value)
- [x] 2. Document: module and class docstrings in shared.py
- [x] 3. GREEN: shared.py with TASK_QUEUE and four frozen dataclasses
- [x] 4. RED: round-trip test for GreetingInput values
- [x] 5. GREEN: satisfy round-trip test
- [x] 6. REFACTOR: field ordering and docstrings for excerpting
- [x] 7. Docs: none beyond docstrings
- [x] 8. Verify: coverage of the data contract, run `just check`

## Section 2: Activities And The Starvation Probe

### Step 3: Misbehaving Activities With Mode Logic

- [x] 1. RED: tests/test_activities.py (heartbeat ordering, block calls time.sleep, slow awaits asyncio.sleep, healthy no-delay, mocked returns)
- [x] 2. Document: module docstring, HEALTHY_EQUIVALENTS constant, function docstrings
- [x] 3. GREEN: activities.py with get_ip, get_location, _apply_mode, antipattern marker on time.sleep
- [x] 4. RED: end-to-end ActivityEnvironment test (slow mode, both heartbeats, ordered results)
- [x] 5. GREEN: wire integration
- [x] 6. REFACTOR: keep mode branch a plain obvious if
- [x] 7. Docs: confirm HEALTHY_EQUIVALENTS and docstrings
- [x] 8. Verify: coverage of mode branching and heartbeat ordering, run `just check`

### Step 4: Event-Loop Starvation Probe Test

- [x] 1. RED: tests/test_starvation_probe.py (block mode misses ticks, slow mode keeps ticks)
- [x] 2. Document: module docstring explaining the deterministic proof
- [x] 3. GREEN: call _apply_mode directly or extract a pure inner function
- [x] 4. RED: comparative assertion (fewer ticks in block than slow)
- [x] 5. GREEN: tune thresholds to be reliable, not flaky
- [x] 6. REFACTOR: factor shared probe setup
- [x] 7. Docs: none
- [x] 8. Verify: test has teeth (fails if block branch becomes cooperative), run `just check`

## Section 3: Workflows

### Step 5: Misbehaving Greeting Workflow

- [x] 1. RED: tests/test_workflow.py happy path (start_time_skipping, stubbed activities, output shape, ordering)
- [x] 2. Document: GreetingWorkflow class docstring
- [x] 3. GREEN: workflow.py GreetingWorkflow with timeouts and antipattern marker on maximum_attempts=1
- [x] 4. RED: error-path test (get_ip raises, workflow fails, no silent retry)
- [x] 5. GREEN: wire failure to surface
- [x] 6. REFACTOR: clean activity-execution calls for excerpting
- [x] 7. Docs: none
- [x] 8. Verify: coverage of orchestration and no-retry behavior, run `just check`

### Step 6: Innocent Victim Workflow

- [x] 1. RED: tests/test_victim.py happy path (start_time_skipping, output includes label, no network)
- [x] 2. Document: VictimWorkflow and quick_task docstrings
- [x] 3. GREEN: victim.py with quick_task and VictimWorkflow, antipattern marker on schedule_to_start_timeout
- [x] 4. RED: concurrent victim executions all succeed with distinct labels
- [x] 5. GREEN: wire concurrent test
- [x] 6. REFACTOR: keep victim.py minimal and obviously correct
- [x] 7. Docs: none
- [x] 8. Verify: coverage of victim orchestration, run `just check`

## Section 4: Worker And Starter CLI

### Step 7: Mistuned Worker With Metrics And Banner (task)

- [x] 1. Scope defined (worker.py, import-and-smoke verification)
- [x] 2. Tooling: python + temporal skill, temporal-docs MCP for API confirmation
- [x] 3. Do: async main and __main__ guard
- [x] 3. Do: Runtime with Prometheus telemetry on 127.0.0.1:9464 (API confirmed via MCP)
- [x] 3. Do: Client.connect localhost:7233 with runtime
- [x] 3. Do: Worker on TASK_QUEUE, both workflows, all activities, max_concurrent_activities=2, no activity_executor
- [x] 3. Do: antipattern marker on max_concurrent_activities line
- [x] 3. Do: startup banner with PID, introspection commands, metrics URL
- [x] 4. Verify: import succeeds, `just check` exits 0
- [x] 5. Document: none (banner/URL documented in README)

### Step 8: Starter CLI With Argument Parsing

- [x] 1. RED: tests/test_starter.py (defaults, mode choices, type parsing, full-flag parse)
- [x] 2. Document: starter.py module docstring describing flags
- [x] 3. GREEN: build_parser and async main with concurrent submissions
- [x] 4. RED: input-construction test (count -> N GreetingInput, victims -> N VictimInput distinct labels)
- [x] 5. GREEN: wire main to shared construction helpers
- [x] 6. REFACTOR: separate parsing, construction, submission
- [x] 7. Docs: none
- [x] 8. Verify: coverage of parsing and input construction, run `just check`

## Section 5: Documentation And CI

### Step 9: README And License (task)

- [ ] 1. Scope defined (README.md, LICENSE)
- [ ] 2. Tooling: tutorial-writing before drafting, review-content after, temporal skill + MCP to verify metric names and behavior claims
- [ ] 3. Do: LICENSE (MIT, Mason Egger, 2026)
- [ ] 3. Do: README what-it-demonstrates + deliberately-broken warning
- [ ] 3. Do: README three-terminal quickstart
- [ ] 3. Do: README Lesson 1 frozen loop (healthy vs broken asyncio ps and metrics shapes)
- [ ] 3. Do: README Lesson 2 exhausted slots (slots-available 0, latency, poller vanishing)
- [ ] 3. Do: README distinguishing summary
- [ ] 3. Do: README platform gotchas (3.14+, Yama ptrace_scope, macOS sudo, transient asyncio ps)
- [ ] 3. Do: README antipattern marker grep note
- [ ] 3. Do: README tutorial link placeholder (masonegger.com TODO)
- [ ] 4. Verify: review-content pass on README.md, then human-check writing rules, commands/URL match worker.py, warning present, MIT valid
- [ ] 5. Document: this step is the documentation

### Step 10: CI Workflow, pip-audit, Dependabot (task)

- [ ] 1. Scope defined (.github/workflows/ci.yml, .github/dependabot.yml)
- [ ] 2. Tooling: none
- [ ] 3. Do: ci.yml on push and pull_request, single pinned Python 3.14, uv sync, just check, pip-audit
- [ ] 3. Do: add pip-audit to dev group if missing
- [ ] 3. Do: dependabot.yml for pip and github-actions, weekly
- [ ] 4. Verify: `just check` exits 0, YAML parses
- [ ] 5. Document: optional one-line CI note in README, else none
