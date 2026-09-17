# temporal-async-debug Implementation Plan

This plan turns `spec.md` into an executable, test-driven build sequence.
Each step is a literal prompt for a code-generation LLM.
Feature steps follow RED/GREEN/REFACTOR; Task steps follow Scope/Tooling/Do/Verify/Document.
Steps build strictly on their predecessors with no orphaned code.

## Current Status

- [ ] Section 1: Scaffolding And Shared Types
  - [ ] Step 1: Package And Test Scaffolding (task)
  - [ ] Step 2: Shared Dataclasses And Task Queue Constant
- [ ] Section 2: Activities And The Starvation Probe
  - [ ] Step 3: Misbehaving Activities With Mode Logic
  - [ ] Step 4: Event-Loop Starvation Probe Test
- [ ] Section 3: Workflows
  - [ ] Step 5: Misbehaving Greeting Workflow
  - [ ] Step 6: Innocent Victim Workflow
- [ ] Section 4: Worker And Starter CLI
  - [ ] Step 7: Mistuned Worker With Metrics And Banner (task)
  - [ ] Step 8: Starter CLI With Argument Parsing
- [ ] Section 5: Documentation And CI
  - [ ] Step 9: README And License (task)
  - [ ] Step 10: CI Workflow, pip-audit, Dependabot (task)

## Architecture Recap

Package `src/temporal_async_debug/` (src layout, hatchling, empty `__init__.py`).

- `shared.py`: frozen dataclasses for workflow inputs and outputs (misbehaving input carries `block_seconds: float` and `mode: str`), plus the task queue name constant.
- `activities.py`: two async activities (`get_ip`, `get_location`) using httpx; each heartbeats, then applies its mode when `block_seconds > 0` (mode "block" calls `time.sleep`, the deliberate bug; mode "slow" awaits `asyncio.sleep`), then makes its httpx call.
- `victim.py`: `VictimWorkflow` and its correct `quick_task` activity; a short `schedule_to_start_timeout` makes slot exhaustion legible.
- `workflow.py`: `GreetingWorkflow` runs `get_ip` then `get_location`, each with a short `heartbeat_timeout` and a `maximum_attempts=1` retry policy.
- `worker.py`: connects to localhost:7233, registers both workflows and all activities, mistuned with `max_concurrent_activities=2`, no `activity_executor`, Prometheus metrics on localhost:9464, and a startup banner printing the PID and the copy-paste introspection commands.
- `starter.py`: argparse CLI with `--name`, `--block-seconds`, `--mode`, `--count`, `--victims`.

Antipattern marker convention (fixed, greppable), applied at every deliberate bug, mistuning, or antipattern line:

```
# ANTIPATTERN (deliberate, for teaching): <why it is wrong>. Correct: <the right approach>. Do not copy.
```

Marked lines: the `time.sleep` call (Step 3), the `maximum_attempts=1` retry policy (Step 5), the victim's `schedule_to_start_timeout` (Step 6), and the `max_concurrent_activities=2` mistuning (Step 7).

## Section 1: Scaffolding And Shared Types

**Tools:**
- Skills: python:python, temporal:temporal-developer
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: uv run ruff check --output-format=json ., uv run mypy .

### Step 1: Package And Test Scaffolding (task)

**Tools:** none

**NOTE**: `pyproject.toml`, `justfile`, and `.gitignore` already exist. Do not recreate them from scratch; extend `pyproject.toml` only where noted. The `src/` tree and `tests/` tree do not yet exist.

```text
1. Scope:
   - Artifact(s):
     - src/temporal_async_debug/__init__.py (new, empty)
     - src/temporal_async_debug/py.typed (new, empty marker file)
     - tests/__init__.py (new, empty)
     - tests/conftest.py (new)
     - pyproject.toml (edit only: add hatchling wheel target and pytest config)
   - Desired end state: `uv run pytest` collects zero tests and exits 0; `uv run mypy .` passes on the empty package; the package imports as `temporal_async_debug`.

2. Tooling:
   - Skills: python:python
   - MCPs: none
   - External: uv, ruff, mypy, pytest

3. Do the work:
   - Create the directory src/temporal_async_debug/ with an empty __init__.py and an empty py.typed.
   - Create tests/__init__.py (empty) and tests/conftest.py containing only a module docstring for now (a placeholder for shared fixtures added in later steps).
   - Edit pyproject.toml: add the hatchling src-layout wheel target so the package is discoverable:
       [tool.hatch.build.targets.wheel]
       packages = ["src/temporal_async_debug"]
   - Edit pyproject.toml: add pytest configuration enabling asyncio auto mode and the src path:
       [tool.pytest.ini_options]
       asyncio_mode = "auto"
       pythonpath = ["src"]
       testpaths = ["tests"]
   - Do not add or remove dependencies; the required ones (temporalio, httpx, ruff, mypy, pytest, pytest-cov, pytest-asyncio) already exist in pyproject.toml.

4. Verify:
   - Run `just check` and confirm exit 0 (ruff, ruff format --check, mypy strict, pytest with zero collected tests all pass).

5. Document:
   - none (README is authored in Step 9).
```

### Step 2: Shared Dataclasses And Task Queue Constant

**NOTE**: These dataclasses are excerpted line-by-line in the tutorial, so keep them small and readable. `block_seconds` defaulting to 0.0 and `mode` defaulting to a healthy value are load-bearing contract choices: a wrong default turns every run into a misbehaving run.

```text
1. RED: Write dataclass-contract tests first:
   - Create tests/test_shared.py:
     - Test that GreetingInput defaults to block_seconds == 0.0 (the healthy default, meaning "apply no mode delay").
     - Test that GreetingInput defaults to mode == "block" (so an explicit --mode is only needed to switch to slow).
     - Test that GreetingInput, GreetingOutput, VictimInput, and VictimOutput are frozen: attempting to set an attribute raises dataclasses.FrozenInstanceError.
     - Test that TASK_QUEUE is the exact string "async-debug-task-queue".
   - These test our data contract and default choices, not dataclass machinery in general.

2. Document component:
   - Add Google-style module and class docstrings in src/temporal_async_debug/shared.py describing each field, especially that block_seconds is seconds of delay and mode selects "block" (freezes the loop) or "slow" (cooperative await).

3. GREEN: Write MINIMAL code to make tests pass:
   - Create src/temporal_async_debug/shared.py with:
     - from __future__ import annotations, then `from dataclasses import dataclass`.
     - TASK_QUEUE: str = "async-debug-task-queue" as a module constant.
     - @dataclass(frozen=True) GreetingInput with fields: name: str, block_seconds: float = 0.0, mode: str = "block".
     - @dataclass(frozen=True) GreetingOutput with fields: ip: str, location: str, greeting: str.
     - @dataclass(frozen=True) VictimInput with field: label: str.
     - @dataclass(frozen=True) VictimOutput with field: message: str.
   - Full type hints on every field; no single-letter names.

4. RED: Add contract-integration test:
   - In tests/test_shared.py, test that GreetingInput(name="x", block_seconds=30, mode="slow") round-trips its values unchanged (documents that callers pass these three fields positionally or by keyword).

5. GREEN: Confirm the dataclasses already satisfy the round-trip test; add nothing beyond Step 3 unless a test fails.

6. REFACTOR: Ensure field ordering and docstrings read cleanly for tutorial excerpting; no behavior change.

7. Update documentation:
   - none (README is authored in Step 9; module docstrings were added in sub-step 2).

8. Verify meaningful coverage of the data contract and run `just check`.
```

## Section 2: Activities And The Starvation Probe

**Tools:**
- Skills: python:python, temporal:temporal-developer
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: uv run ruff check --output-format=json ., uv run mypy .

### Step 3: Misbehaving Activities With Mode Logic

**NOTE**: This is the heart of the demo. The `time.sleep` line must look innocent and carry the antipattern marker. Both activities heartbeat before applying their mode. The httpx calls hit https://icanhazip.com (get_ip) and a geo lookup for that IP (get_location); tests mock httpx so no network is required.

```text
1. RED: Write activity-behavior tests first (via temporalio.testing.ActivityEnvironment, httpx mocked):
   - Create tests/test_activities.py:
     - Test that get_ip calls activity.heartbeat exactly once before performing its httpx GET (capture heartbeats by setting ActivityEnvironment.on_heartbeat).
     - Test that get_location calls activity.heartbeat exactly once before its httpx GET.
     - Test that in mode "block" with block_seconds > 0, the activity calls time.sleep with block_seconds (monkeypatch time.sleep to record the argument and NOT actually sleep; assert it received block_seconds).
     - Test that in mode "slow" with block_seconds > 0, the activity awaits asyncio.sleep with block_seconds and does NOT call time.sleep (monkeypatch both: record asyncio.sleep arg, assert time.sleep never called).
     - Test that with block_seconds == 0.0, neither time.sleep nor asyncio.sleep is invoked with a positive delay (the healthy path applies no mode delay).
     - Test that get_ip returns the mocked IP string and get_location returns the mocked location string (mock httpx.AsyncClient.get to return a controlled response).
   - These test our mode branching, heartbeat ordering, and return handling, not httpx or Temporal internals.

2. Document component:
   - Add a Google-style module docstring to src/temporal_async_debug/activities.py naming the healthy equivalents in one place: a module constant HEALTHY_EQUIVALENTS listing "asyncio.sleep" and "httpx" so the tutorial can point at the contrast.
   - Document each activity function with its parameters and return type.

3. GREEN: Write MINIMAL code to make tests pass:
   - Create src/temporal_async_debug/activities.py:
     - Imports: import asyncio, import time, import httpx; from temporalio import activity; from temporal_async_debug.shared import GreetingInput (activities take the fields they need; pass block_seconds and mode as parameters or accept GreetingInput, choose one shape and keep it consistent with how workflow.py will call them in Step 5).
     - Define an internal helper `_apply_mode(mode: str, block_seconds: float) -> None` used by both activities: if block_seconds > 0 and mode == "block", call time.sleep(block_seconds) with the antipattern marker on that exact line; elif block_seconds > 0 and mode == "slow", await asyncio.sleep(block_seconds). Because it awaits, this helper is async.
     - @activity.defn async def get_ip(...) -> str: call activity.heartbeat("fetching ip"), then await _apply_mode(...), then GET https://icanhazip.com via httpx.AsyncClient and return the stripped body.
     - @activity.defn async def get_location(ip: str, ...) -> str: call activity.heartbeat("fetching location"), then await _apply_mode(...), then GET a geo lookup URL for that IP via httpx and return a location string.
     - Antipattern marker on the time.sleep line, exactly:
       # ANTIPATTERN (deliberate, for teaching): time.sleep blocks the single worker event loop, starving the poller, heartbeat sender, and every other async activity. Correct: await asyncio.sleep for cooperative delay, or run truly blocking work in an executor. Do not copy.

4. RED: Add integration tests:
   - In tests/test_activities.py, add a test that runs get_ip then get_location end to end under ActivityEnvironment in mode "slow" with a small block_seconds (for example 0.01), asserting both heartbeats fired and both mocked network results are returned in order.

5. GREEN: Wire up integration minimally so the end-to-end ActivityEnvironment test passes; adjust helper signatures only as needed.

6. REFACTOR: Keep the mode branch a plain, obvious `if` as the spec requires; ensure the blocking path reads as innocent. No behavior change.

7. Update documentation:
   - none (README in Step 9); confirm HEALTHY_EQUIVALENTS and docstrings are present.

8. Verify meaningful coverage of the mode branching and heartbeat ordering, then run `just check`.
```

### Step 4: Event-Loop Starvation Probe Test

**NOTE**: This test proves the block-vs-slow contrast deterministically without Temporal. It runs the activity's mode application next to a probe task that ticks on a timer; a blocking sleep makes the probe miss ticks, a cooperative sleep does not. Reuse the `_apply_mode` helper from Step 3 so the test exercises real product code.

```text
1. RED: Write the starvation probe test first:
   - Create tests/test_starvation_probe.py:
     - Build an async probe coroutine that records a monotonic timestamp, awaits asyncio.sleep(0.05) (50 ms), and appends a tick, looping for a fixed number of ticks or until a stop event.
     - Test block mode: monkeypatch time.sleep to a real short blocking sleep of 0.5 s (so the test stays fast), run _apply_mode(mode="block", block_seconds=0.5) as a task concurrently with the probe, and assert the probe misses ticks during the block (the gap between two consecutive probe timestamps exceeds a threshold clearly larger than 0.05 s, for example > 0.4 s).
     - Test slow mode: run _apply_mode(mode="slow", block_seconds=0.5) concurrently with the probe and assert the probe does NOT miss ticks (every consecutive gap stays near 0.05 s, for example < 0.2 s), proving the loop kept scheduling the probe.
   - These assert our starvation behavior, the exact teaching claim, not asyncio scheduling in the abstract.

2. Document component:
   - Add a module docstring to tests/test_starvation_probe.py explaining that this is the deterministic, Temporal-free proof of the frozen-loop-vs-cooperative distinction.

3. GREEN: Write MINIMAL code to make tests pass:
   - If _apply_mode from Step 3 is directly callable with mode and block_seconds, call it directly. If its signature couples it to activity context, extract a pure inner function in activities.py that _apply_mode delegates to, and call that from the test. Keep any extraction behavior-preserving and re-run Step 3 tests.

4. RED: Add an edge-case assertion:
   - Assert that in block mode the total number of recorded probe ticks is strictly fewer than in slow mode over the same wall-clock window, making the contrast a single comparative assertion.

5. GREEN: Adjust thresholds or tick counts minimally so both mode assertions hold reliably on a normal machine; avoid flaky tight bounds.

6. REFACTOR: Factor shared probe setup into a local helper within the test module; no product behavior change.

7. Update documentation:
   - none (README in Step 9).

8. Verify the test fails if _apply_mode's block branch is switched to asyncio.sleep (sanity-check the assertion has teeth), revert, then run `just check`.
```

## Section 3: Workflows

**Tools:**
- Skills: python:python, temporal:temporal-developer
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: uv run ruff check --output-format=json ., uv run mypy .

### Step 5: Misbehaving Greeting Workflow

**NOTE**: `GreetingWorkflow` executes `get_ip` then `get_location`. Each activity uses a short `heartbeat_timeout` (10 seconds) so a 30-second block demonstrably misses heartbeats, and a retry policy with `maximum_attempts=1` so failures surface instead of retrying silently (this retry choice carries the antipattern marker). The happy-path test runs under WorkflowEnvironment.start_time_skipping with mocked-network activities.

```text
1. RED: Write the workflow happy-path test first (via temporalio.testing.WorkflowEnvironment.start_time_skipping):
   - Create tests/test_workflow.py:
     - Start a time-skipping WorkflowEnvironment, register GreetingWorkflow and stubbed versions of get_ip and get_location (activities that return fixed strings without network), run a Worker on TASK_QUEUE, and execute GreetingWorkflow with GreetingInput(name="friend", block_seconds=0.0, mode="block").
     - Assert the returned GreetingOutput has ip, location, and a greeting string that includes the name "friend".
     - Assert the workflow calls get_ip before get_location (for example, have the stubbed get_location assert it received the ip produced by get_ip).
   - This tests our workflow orchestration and output shaping, not the Temporal runtime.

2. Document component:
   - Add a Google-style class docstring to GreetingWorkflow in src/temporal_async_debug/workflow.py describing the two-activity sequence and why the timeouts are set the way they are for the demo.

3. GREEN: Write MINIMAL code to make tests pass:
   - Create src/temporal_async_debug/workflow.py:
     - Imports inside a `with workflow.unsafe.imports_passed_through():` block for shared, and the datetime timedelta import; from temporalio import workflow; from temporalio.common import RetryPolicy.
     - @workflow.defn class GreetingWorkflow with @workflow.run async def run(self, args: GreetingInput) -> GreetingOutput.
     - Execute get_ip with start_to_close_timeout=timedelta(seconds=60), heartbeat_timeout=timedelta(seconds=10), retry_policy=RetryPolicy(maximum_attempts=1), passing block_seconds and mode through.
     - Execute get_location with the same timeouts and retry policy, passing the ip from get_ip plus block_seconds and mode.
     - Build and return GreetingOutput(ip=..., location=..., greeting=f"Hello {args.name}, you appear to be in {location}").
     - Antipattern marker on the retry policy (both activity calls or on a shared RetryPolicy variable), exactly:
       # ANTIPATTERN (deliberate, for teaching): maximum_attempts=1 disables retries so the demo surfaces the first failure instead of masking it. Correct: allow retries with sensible backoff in production. Do not copy.

4. RED: Add an error-path integration test:
   - In tests/test_workflow.py, register a stubbed get_ip that raises ApplicationError and assert the workflow fails (WorkflowFailureError) rather than silently retrying, confirming maximum_attempts=1 takes effect.

5. GREEN: Wire the workflow so the error-path test passes; adjust nothing beyond making the failure surface.

6. REFACTOR: Ensure the activity-execution calls read clearly for tutorial excerpting; no behavior change.

7. Update documentation:
   - none (README in Step 9).

8. Verify meaningful coverage of the orchestration and the no-retry behavior, then run `just check`.
```

### Step 6: Innocent Victim Workflow

**NOTE**: `VictimWorkflow` is correct code in every respect; its one small async activity `quick_task` does no network and returns fast. Its activity options set a short `schedule_to_start_timeout` (10 seconds) so slot exhaustion produces a visible non-retryable timeout quickly. That timeout carries the antipattern marker with the note that it is normally an antipattern and exists here only to make the failure legible.

```text
1. RED: Write the victim happy-path test first (via WorkflowEnvironment.start_time_skipping):
   - Create tests/test_victim.py:
     - Start a time-skipping WorkflowEnvironment, register VictimWorkflow and quick_task, run a Worker on TASK_QUEUE, and execute VictimWorkflow with VictimInput(label="check-1").
     - Assert the returned VictimOutput.message includes the label "check-1" and indicates success.
     - Assert quick_task performs no network (it is a pure function returning a fast result); verify by asserting its returned value flows into the output.
   - This tests our victim orchestration and output, not Temporal.

2. Document component:
   - Add Google-style docstrings to VictimWorkflow and quick_task in src/temporal_async_debug/victim.py, noting quick_task is deliberately correct and fast.

3. GREEN: Write MINIMAL code to make tests pass:
   - Create src/temporal_async_debug/victim.py:
     - @activity.defn async def quick_task(label: str) -> str: return a fast computed string such as f"processed {label}" with no sleep and no network.
     - @workflow.defn class VictimWorkflow with @workflow.run async def run(self, args: VictimInput) -> VictimOutput.
     - Execute quick_task with start_to_close_timeout=timedelta(seconds=10) and schedule_to_start_timeout=timedelta(seconds=10).
     - Return VictimOutput(message=f"victim {args.label}: {result}").
     - Antipattern marker on the schedule_to_start_timeout, exactly:
       # ANTIPATTERN (deliberate, for teaching): a short schedule_to_start_timeout is normally an antipattern; it is set here only to make slot exhaustion fail fast and visibly. Correct: usually leave schedule_to_start unset and size the worker to demand. Do not copy.

4. RED: Add an integration assertion:
   - In tests/test_victim.py, run several VictimWorkflow executions concurrently under the same time-skipping environment and assert all complete successfully with distinct labels reflected in their outputs, confirming the victim path is independent and correct.

5. GREEN: Wire the workflow so the concurrent test passes; change nothing else.

6. REFACTOR: Keep victim.py minimal and obviously correct so the tutorial can contrast it with the misbehaving code; no behavior change.

7. Update documentation:
   - none (README in Step 9).

8. Verify meaningful coverage of the victim orchestration, then run `just check`.
```

## Section 4: Worker And Starter CLI

**Tools:**
- Skills: python:python, temporal:temporal-developer
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: uv run ruff check --output-format=json ., uv run mypy .

### Step 7: Mistuned Worker With Metrics And Banner (task)

**NOTE**: This step is wiring and configuration, not new branching logic, so it uses the Task template. The worker is deliberately mistuned (`max_concurrent_activities=2`) and runs its activities async on purpose (no `activity_executor`). It enables the SDK Prometheus metrics endpoint on localhost:9464 and prints a startup banner with the PID and copy-paste introspection commands. It is verified by import and a smoke run, not by a unit test, because it is a long-running process against a real server.

```text
1. Scope:
   - Artifact(s): src/temporal_async_debug/worker.py (new)
   - Desired end state: `uv run python -c "import temporal_async_debug.worker"` succeeds; `uv run mypy .` passes; running the module prints a banner with the PID, the metrics URL, and the two introspection commands, then connects to localhost:7233 and serves. The metrics endpoint binds localhost:9464.

2. Tooling:
   - Skills: python:python, temporal:temporal-developer
   - MCPs: mcp__temporal-docs__search_temporal_knowledge_sources (confirm the current Runtime/TelemetryConfig/PrometheusConfig API and Worker keyword arguments)
   - External: uv, mypy, ruff

3. Do the work:
   - Create src/temporal_async_debug/worker.py with an async main() and a __main__ guard that runs it via asyncio.run.
   - Build a Runtime with Prometheus telemetry: from temporalio.runtime import Runtime, TelemetryConfig, PrometheusConfig; Runtime(telemetry=TelemetryConfig(metrics=PrometheusConfig(bind_address="127.0.0.1:9464"))). Confirm exact names via the temporal-docs MCP before finalizing.
   - Connect: await Client.connect("localhost:7233", runtime=runtime).
   - Construct the Worker on shared.TASK_QUEUE, registering workflows=[GreetingWorkflow, VictimWorkflow] and activities=[get_ip, get_location, quick_task], with max_concurrent_activities=2 and no activity_executor.
   - Antipattern marker on the max_concurrent_activities line, exactly:
       # ANTIPATTERN (deliberate, for teaching): max_concurrent_activities=2 undersizes the worker so two slow activities exhaust every slot and stall the queue. Correct: size slots to expected concurrency and load. Do not copy.
   - Before await worker.run(), print a banner (plain print statements) that includes: os.getpid(), the line "python -m asyncio ps <PID>" and "python -m asyncio pstree <PID>" with the real PID substituted, and the metrics URL http://127.0.0.1:9464/metrics.

4. Verify:
   - Run `uv run python -c "import temporal_async_debug.worker"` and confirm exit 0, then run `just check` and confirm exit 0. (A full live run against temporal server start-dev is a manual smoke test documented in the README, not part of this step's automated verification.)

5. Document:
   - none here; the banner text and metrics URL are documented in the README in Step 9.
```

### Step 8: Starter CLI With Argument Parsing

**NOTE**: The starter parses CLI flags and starts workflows. Argument parsing and the concurrent-submission fan-out are our logic and are unit-testable without a server by factoring parsing into a pure function. The actual client submission is thin and exercised manually against the dev server.

```text
1. RED: Write argument-parsing tests first:
   - Create tests/test_starter.py:
     - Test that a build_parser()/parse_args helper defaults --name to a non-empty string, --block-seconds to 0.0, --mode to "block", --count to 1, and --victims to 0.
     - Test that --mode accepts only "block" or "slow" (argparse choices) and that an invalid value causes a SystemExit.
     - Test that --block-seconds parses as float and --count and --victims parse as int.
     - Test that parsing ["--name", "ada", "--mode", "slow", "--block-seconds", "30", "--count", "2", "--victims", "3"] yields exactly those typed values.
   - These test our CLI contract, not argparse itself in the abstract.

2. Document component:
   - Add a Google-style module docstring to src/temporal_async_debug/starter.py describing each flag and what submitting count misbehaving workflows plus victims demonstrates.

3. GREEN: Write MINIMAL code to make tests pass:
   - Create src/temporal_async_debug/starter.py:
     - A build_parser() -> argparse.ArgumentParser function defining --name (default "friend"), --block-seconds (type float, default 0.0), --mode (choices ["block", "slow"], default "block"), --count (type int, default 1), --victims (type int, default 0).
     - An async main() that: parses args, connects Client.connect("localhost:7233"), submits --count GreetingWorkflow executions concurrently (asyncio.gather) with GreetingInput built from the flags, submits --victims VictimWorkflow executions concurrently, awaits all, and prints each result.
     - A __main__ guard calling asyncio.run(main()).

4. RED: Add an input-construction test:
   - In tests/test_starter.py, add a helper in starter.py such as greeting_inputs_from_args(args) -> list[GreetingInput] and victim_inputs_from_args(args) -> list[VictimInput], then test that --count 2 produces two GreetingInput values carrying the parsed mode and block_seconds, and --victims 3 produces three VictimInput values with distinct labels.

5. GREEN: Wire main() to call those helpers so submission and tests share the same construction logic.

6. REFACTOR: Keep parsing, input construction, and submission as separate small functions so the tutorial can show the CLI surface cleanly; no behavior change.

7. Update documentation:
   - none (README in Step 9).

8. Verify meaningful coverage of parsing and input construction, then run `just check`.
```

## Section 5: Documentation And CI

**Tools:** none

### Step 9: README And License (task)

**Tools:**
- Skills: python:python, temporal:temporal-developer, content-design:tutorial-writing, content-design:review-content
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: none

**NOTE**: README prose follows the repo owner's writing rules: no em-dashes or en-dashes, one sentence per line in committed Markdown, straight quotes only, Title Case headings. The README and the GitHub repo description both must state that the repo contains deliberately broken code for educational purposes.

```text
1. Scope:
   - Artifact(s):
     - README.md (new)
     - LICENSE (new, MIT, copyright Mason Egger, 2026)
   - Desired end state: README covers what the repo demonstrates, the three-terminal quickstart, the two-lesson diagnostic walkthrough with expected healthy-vs-broken output shapes, the platform gotchas, and a tutorial link placeholder; LICENSE is a standard MIT text.

2. Tooling:
   - Skills: content-design:tutorial-writing (invoke before drafting; the quickstart and lessons are procedural docs), content-design:review-content (invoke after drafting; Vale plus copy-editor pass), python:python, temporal:temporal-developer
   - MCPs: mcp__temporal-docs__search_temporal_knowledge_sources (verify the exact metric name temporal_worker_task_slots_available and the poller-vanishing and schedule-to-start behavior claims before writing them into prose)
   - External: Vale, if configured, via the review-content skill

3. Do the work:
   - Write LICENSE as the standard MIT License text with holder "Mason Egger" and year 2026.
   - Write README.md with these sections (sentence-per-line prose, no em-dashes):
     - A one-paragraph statement of what the repo demonstrates and a bold warning that it contains deliberately broken code for educational purposes only.
     - Quickstart: three terminals, `just server`, `just worker`, then `just block` or `just slow`.
     - Lesson 1 (frozen loop): what `just block` does, and the expected shapes of healthy vs broken `python -m asyncio ps <PID>` output (broken: the blocked task stack ends in user code at the time.sleep call site in activities.py) and the metrics endpoint (unreachable or stalled during the freeze).
     - Lesson 2 (exhausted slots): what `just slow` does, and the expected shapes of healthy stacks (all tasks parked on asyncio suspension points), temporal_worker_task_slots_available at 0 via curl of http://127.0.0.1:9464/metrics, climbing schedule-to-start latency, and the worker vanishing from the Temporal UI poller list.
     - The distinguishing summary: frozen loop (stack in user code, metrics endpoint unreachable or stalled) versus busy worker (healthy stacks, slots at 0, schedule-to-start latency climbing).
     - Platform gotchas: inspector and target both Python 3.14+, Linux Yama ptrace_scope=1 presents as "Failed to find the PyRuntime section" and is fixed with sudo or ptrace_scope=0, macOS requires sudo, and 3.14 asyncio ps can fail transiently so just re-run it.
     - The antipattern marker convention and how to grep for "ANTIPATTERN (deliberate, for teaching)".
     - A tutorial link placeholder pointing at masonegger.com (mark it TODO).

4. Verify:
   - Invoke content-design:review-content on README.md and address every finding (Vale mechanical checks plus the copy-editor prose pass).
   - Then human-check: read README.md top to bottom and confirm no em-dashes or en-dashes, one sentence per line in prose, both the PID/introspection commands and the metrics URL match worker.py, and the deliberately-broken-code warning is present. Confirm LICENSE is valid MIT text.

5. Document:
   - This step is the documentation.
```

### Step 10: CI Workflow, pip-audit, Dependabot (task)

**NOTE**: Non-goals cap CI at the canonical application workflow: a single pinned Python 3.14, `just check`, pip-audit, and dependabot. No Docker. Keep it minimal.

```text
1. Scope:
   - Artifact(s):
     - .github/workflows/ci.yml (new)
     - .github/dependabot.yml (new)
   - Desired end state: CI runs on push and pull_request against a single pinned Python 3.14, installs via uv, runs `just check`, and runs pip-audit; dependabot is configured for the pip ecosystem and GitHub Actions.

2. Tooling:
   - Skills: none
   - MCPs: none
   - External: none

3. Do the work:
   - Create .github/workflows/ci.yml:
     - Trigger on push and pull_request.
     - One job on ubuntu-latest with a single Python 3.14 (pinned, for example "3.14").
     - Steps: checkout, install uv (astral-sh/setup-uv), `uv sync`, install just (or run the check commands directly if just is not available on the runner), run `just check`, then run `uv run pip-audit` (add pip-audit to the dev dependency group in pyproject.toml if not already present).
   - Create .github/dependabot.yml:
     - version: 2 with two update entries: package-ecosystem "pip" (or "uv" if supported) at the repo root, and package-ecosystem "github-actions" at "/", each on a weekly schedule.
   - If pip-audit is added to pyproject.toml dev group, run `uv lock` if a lockfile is in use.

4. Verify:
   - Run `just check` locally and confirm exit 0. Validate the YAML parses (for example `uv run python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); yaml.safe_load(open('.github/dependabot.yml'))"`) and confirm exit 0. Full CI execution is confirmed on the first push, not in this step.

5. Document:
   - Optionally add a one-line CI note to README.md; otherwise "none".
```

## Implementation Guidelines

- All Python code follows the python:python skill without exception: full type hints, Google-style docstrings on public interfaces, no single-letter names, canonical ruff/mypy/pytest config blocks.
- Demo code stays small and readable; it is excerpted line-by-line in the tutorial. Comment density serves a reader learning the failure mode.
- Every deliberate bug, mistuning, or antipattern carries the fixed marker `# ANTIPATTERN (deliberate, for teaching): <why>. Correct: <right approach>. Do not copy.` on or immediately above the offending line. The validator should flag any mistuning that lacks one.
- Tests must not require a running Temporal server except through the SDK's own test facilities (ActivityEnvironment, WorkflowEnvironment.start_time_skipping).
- Network is always mocked in tests; no test hits icanhazip.com or a geo service.
- The full local gate is `just check` (ruff check, ruff format --check, mypy strict, pytest). Autonomous-run verification is `pytest` alone via pyproject autodetection.
- Slot exhaustion and real schedule-to-start timing are demonstrated live in the tutorial, not asserted in CI.
- Writing rules apply to all prose (README, docstrings, commit messages): no em-dashes or en-dashes, straight quotes, one sentence per line in committed Markdown prose.
- Never commit to main; work on a feature branch. Only Mason merges to main.

## Success Metrics

- `just check` passes: ruff clean, ruff format check clean, mypy strict clean, all tests green.
- Activity tests prove heartbeat ordering, that block mode calls time.sleep and slow mode awaits asyncio.sleep, and that the healthy path applies no delay.
- The starvation probe test deterministically shows the probe misses ticks in block mode and keeps them in slow mode, and fails if the block branch is switched to a cooperative await.
- Workflow tests exercise both GreetingWorkflow and VictimWorkflow happy paths under start_time_skipping with mocked-network activities, and confirm maximum_attempts=1 surfaces failures.
- Starter tests cover flag defaults, choices validation, and input construction for --count and --victims.
- worker.py imports cleanly, binds metrics on 127.0.0.1:9464, and prints a banner with the real PID and copy-paste introspection commands.
- Every deliberately wrong line (time.sleep, maximum_attempts=1, victim schedule_to_start_timeout, max_concurrent_activities=2) carries the exact antipattern marker and is greppable by the fixed marker string.
- README documents both lessons with healthy-vs-broken output shapes, the platform gotchas, the metrics URL, and the deliberately-broken-code warning; LICENSE is MIT.
- CI runs a single pinned Python 3.14 with `just check` and pip-audit; dependabot is configured.
