# temporal-async-debug Specification

## Project overview

A deliberately misbehaving Temporal Python demo application for a tutorial on diagnosing blocking calls in `async def` activities.
The app runs two workflows on one worker: a misbehaving workflow whose async activities can be switched into a blocking or slow mode, and an innocent victim workflow that fails through no fault of its own.
Readers reproduce the classic production failure modes (missed heartbeats, serialized activities, a frozen poller, slot exhaustion, schedule-to-start timeouts) and then diagnose them from outside the process with Python 3.14+ native tooling (`python -m asyncio ps` / `pstree`) with zero instrumentation.
The two failure modes teach the core diagnostic distinction: a frozen event loop (blocking call) versus an undersized busy worker (slot exhaustion), which look identical to the victim workflow but have different signatures in the tooling and different fixes.
The repo is the companion to a tutorial and a deep-dive blog post on masonegger.com; it is a teaching artifact, not a maintained tool, and will never be published to PyPI.

## Starting context

This repo replaces a demo referenced by an unpublished 2026 tutorial draft that was never actually built.
Research (August 2026) established the mechanism this demo must exhibit: the Temporal Python worker runs its poller, heartbeat sender, and every `async def` activity on one asyncio event loop, so a single blocking call starves all of them.
The Python 3.14 introspection commands read the target process memory without executing code in it, so they work while the loop is fully frozen.
The diagnostic signature: a healthy suspended task's coroutine stack ends on an asyncio suspension point (for example `Task.sleep` or `Semaphore.acquire`), while the blocking task's stack ends in user code at the exact file and line of the blocking call.
Worker-tuning research (September 2026) added the second mechanism: when `max_concurrent_activities` slots fill, the worker stops polling for activity tasks entirely, schedule-to-start latency climbs for every other workflow on the queue, and the Temporal UI stops listing the worker as a poller even though the process is healthy.
Known tooling gotchas the README must cover: inspector and target must both be Python 3.14+, Linux defaults to Yama `ptrace_scope=1` (failure presents as "Failed to find the PyRuntime section", fixed with sudo or `ptrace_scope=0`), macOS requires sudo, and 3.14's `asyncio ps` can fail transiently and should just be re-run.

## Available tooling

Tooling available to the validator and executor during autonomous runs.

**MCPs:**

- temporal-docs (`search_temporal_knowledge_sources`) for authoritative Temporal SDK behavior questions

**Skills:**

- python:python (project standards: strict typing, canonical ruff/mypy/pytest config, uv workflows)
- temporal:temporal-developer (Temporal SDK APIs, worker configuration, testing helpers)
- content-design:tutorial-writing (procedural documentation style for the README quickstart and lessons)
- content-design:review-content (Vale run plus copy-editor agent; prose review against the writing hard rules)

**Notes:** All Python code follows the python:python skill without exception (type hints everywhere, Google docstrings on public interfaces, no single-letter names, canonical config blocks verbatim).
Demo code must stay small and readable; it will be excerpted line-by-line in a tutorial.
Comment density should serve a reader learning the failure mode, not the maintainer.
Every deliberately wrong line, setting, or pattern carries an inline comment on or immediately above the offending line using the fixed marker format below; the validator should flag any mistuning or antipattern that lacks one.

## External tool candidates

Marketplace skills and public plugins surfaced by `bpe:cheap-research` (September 2026), cached for later `/bpe:plan` runs.
These are candidates only, not tools declared in the session pool; fold one into a plan Tools block only when it plausibly applies.

- temporal-developer (Temporal Marketplace) :: Comprehensive reference for Temporal Python workflows, activities, workers, testing, and error handling :: /home/mmegger/.claude/plugins/cache/temporal-marketplace/temporal-developer/0.2.0/.claude-plugin/plugin.json
- temporal-python-testing :: Temporal workflow testing: pytest fixtures, time-skipping for long-running workflows, replay testing for determinism :: https://github.com/wshobson/agents/tree/main/plugins/backend-development/skills/temporal-python-testing
- async-python-patterns :: asyncio event loops, async/await, concurrent I/O patterns, and task coordination for async activity debugging :: https://claude-plugins.dev/skills/@wshobson/agents/async-python-patterns
- python-testing (pytest) :: pytest fixtures, parametrization, mocking, async testing with pytest-asyncio, test organization :: https://playbooks.com/skills/laurigates/claude-plugins/python-testing
- uv package manager (astral-sh official) :: uv project dependency management matching the project build toolchain :: https://claudemarketplaces.com/skills/astral-sh/claude-code-plugins/uv
- justfile-expert :: Just command runner recipes and cross-platform task automation as used in this project :: https://agentskills.so/skills/laurigates-claude-plugins-justfile-expert
- ruff linting (astral-sh official) :: Official Ruff linter integration matching the project code-quality toolchain :: https://claude-plugins.dev/skills/@laurigates/dotfiles/ruff-linting
- python-code-quality :: Multi-tool ruff, mypy, and code-quality coverage for the linting and type-checking stack :: https://mcpmarket.com/tools/skills/python-code-quality-linting-2
- Doc-Driven Development :: Documentation-first pattern, then generate implementation to match; relevant to a tutorial/README-first approach :: https://github.com/cbrake/claude-plugins/blob/main/doc-driven-development/README.md
- python-dev (L3DigitalNet) :: General Python development with async patterns, type safety, testing, resilience :: https://agentskill.sh/plugins/l3digitalnet/python-dev

## Architecture

Package layout under `src/temporal_async_debug/` (src layout, hatchling, empty `__init__.py`):

- `shared.py`: frozen dataclasses for workflow inputs and outputs, including `block_seconds: float` and `mode: str` ("block" or "slow") on the misbehaving activity input; task queue name constant.
- `activities.py`: the misbehaving workflow's two async activities using httpx (`get_ip` fetching https://icanhazip.com, `get_location` fetching a geo lookup for that IP).
  Each activity heartbeats, then applies its mode when `block_seconds > 0`: mode "block" calls `time.sleep(block_seconds)` (the deliberate bug, freezes the loop), mode "slow" calls `await asyncio.sleep(block_seconds)` (cooperative, but hogs a slot), then performs its httpx call.
  A module constant lists the healthy equivalents (`asyncio.sleep`, httpx) so the tutorial can point at the contrast in one place.
- `victim.py`: the innocent victim, a quick workflow (`VictimWorkflow`) with one small async activity (`quick_task`, no network, returns fast) that is correct code in every respect.
  Its activity options set a short `schedule_to_start_timeout` (10 seconds) so slot exhaustion produces a visible non-retryable timeout quickly; the tutorial notes that setting this timeout is normally an antipattern and exists here to make the failure legible.
- `workflow.py`: the misbehaving workflow (`GreetingWorkflow`) executing `get_ip` then `get_location`, each with a `heartbeat_timeout` short enough (10 seconds) that a 30-second block demonstrably misses heartbeats, and a retry policy with `maximum_attempts=1` so failures surface instead of retrying silently.
- `worker.py`: connects to localhost:7233, registers both workflows and all activities, and prints a startup banner with the process PID and copy-paste `python -m asyncio ps <PID>` / `pstree` commands.
  The worker is deliberately mistuned: `max_concurrent_activities=2`, so two slow-mode activities exhaust the slots.
  No `activity_executor` is configured; the activities are async on purpose.
  The SDK's Prometheus metrics endpoint is enabled (via `Runtime` telemetry config) on localhost:9464 so the tutorial can `curl` `temporal_worker_task_slots_available` and the schedule-to-start latency metrics live.
- `starter.py`: CLI (argparse) that starts workflows and prints results.
  Flags: `--name`, `--block-seconds`, `--mode block|slow`, `--count` (submit several misbehaving workflows concurrently), and `--victims` (submit N victim workflows so the reader watches innocent work fail).

No web UI; the CLI starter plus the Temporal Web UI (localhost:8233, which shows pending activities, timeouts, and the vanishing poller) cover the interaction surface, and the earlier draft's Flask front end is explicitly dropped.

## Behavior requirements

- With `block_seconds=0`, concurrent submissions of both workflow types complete with overlapping activity execution and all heartbeats delivered.
- With `--mode block --block-seconds 30`, the worker's event loop is frozen for the duration: heartbeats for in-flight activities stop, concurrent submissions serialize, victim workflows stall entirely (workflow tasks included), and `asyncio ps` during the freeze shows the blocked task's stack ending at the `time.sleep` call site in `activities.py`.
- With `--mode slow --block-seconds 30 --count 2 --victims 3`, the event loop stays healthy but both activity slots are held: victim activities queue server-side and fail with schedule-to-start timeouts, victim workflow tasks still process, heartbeats still flow, `asyncio ps` shows all tasks parked on asyncio suspension points, and the metrics endpoint shows `temporal_worker_task_slots_available` at 0.
- The two modes must be distinguishable purely from tool output: frozen loop (`asyncio ps` shows a task stack ending in user code at the `time.sleep` call site in `activities.py`) versus busy worker (all stacks parked on asyncio suspension points, `temporal_worker_task_slots_available` at 0, schedule-to-start latency climbing).
  The metrics endpoint stays reachable in both modes, so it is not the frozen-loop signal: the SDK serves Prometheus from the Temporal core (Rust) runtime on its own threads, off the Python event loop, so freezing the loop does not take the endpoint down.
  Verified live on 2026-09-17: during a 30-second block, 10 of 10 scrapes of `http://127.0.0.1:9464/metrics` returned in under a millisecond, at the same latency as the healthy baseline.
- The worker banner and README both state the PID, the introspection commands, the metrics URL, and the platform gotchas (Yama ptrace_scope on Linux, sudo on macOS, both processes 3.14+).
- The blocking path is a plain `if` on the mode in the activity body, kept obvious; the tutorial's whole point is that this line looks innocent.
- Antipattern marker convention: every deliberate bug, mistuning, or antipattern is labeled at the offending line with a comment of the form `# ANTIPATTERN (deliberate, for teaching): <why it is wrong>. Correct: <the right approach>. Do not copy.`
  This applies to the `time.sleep` call, the `max_concurrent_activities=2` mistuning, the victim's `schedule_to_start_timeout`, the `maximum_attempts=1` retry policy, and any other intentionally bad choice.
  The marker string `ANTIPATTERN (deliberate, for teaching)` is fixed and greppable; the tutorial references it, and it labels the bad pattern for any human or automated system (code-completion tools, model training pipelines, snippet scrapers) that ingests the file without the surrounding README context.
  The README and the GitHub repo description both state that the repo contains deliberately broken code for educational purposes.

## Test requirements

Tests must not require a running Temporal server unless using the SDK's own test facilities.

- Unit tests for `shared.py` dataclasses and starter argument parsing.
- Activity tests via `temporalio.testing.ActivityEnvironment` with httpx calls mocked; verify heartbeat is called, blocking mode calls `time.sleep` (monkeypatched to record, not sleep), and slow mode awaits `asyncio.sleep` instead.
- An event-loop starvation probe test that proves the contrast deterministically without Temporal: run the activity body on an event loop next to a probe task that ticks every 50 ms with a patched short sleep of 0.5 s; assert the probe misses ticks in block mode and does not in slow mode.
- Workflow tests via `temporalio.testing.WorkflowEnvironment.start_time_skipping()` exercising the happy path of both workflows with mocked-network activities.
- Slot exhaustion is demonstrated live in the tutorial rather than asserted in CI; no integration test attempts to reproduce real schedule-to-start timing.
- The full gate is `just check` (ruff check, ruff format --check, mypy strict, pytest); pytest alone is the autonomous-run verification command via pyproject autodetection.

## Documentation requirements

- README: what the repo demonstrates, quickstart (three terminals: `just server`, `just worker`, then `just block` or `just slow`), the two-lesson diagnostic walkthrough (frozen loop vs exhausted slots) with expected healthy vs broken output shapes for both `asyncio ps` and the metrics endpoint, the platform gotchas, and a link placeholder for the tutorial.
- README prose follows the repo owner's writing rules: no em-dashes, one sentence per line in committed Markdown.
- MIT license.

## Future work (v2, not in scope for this arc)

A lab mode turning the demo into a whodunit learning environment; decisions recorded September 2026, build deferred until after the tutorial publishes:

- A fleet generator (a script invoked via `just generate N`) that writes real per-workflow source files (for example `fleet/workflow_c.py` through `fleet/workflow_z.py` by default, with no upper limit on count or naming) so every generated activity has its own file and line and stack traces remain genuine clues at any scale.
- Seeded culprit selection: a `--seed` picks which generated activity misbehaves and how, without announcing it; a `reveal` command checks the learner's answer.
- A FastAPI "game master" app (async, fully typed, matching project standards): starts and stops scenarios, shows a live fleet status board and symptom feed, and accepts the learner's culprit guess for the reveal flow.
  This serves the game loop the Temporal Web UI cannot; it does not duplicate the Temporal UI's workflow views, and the tutorial-facing v1 remains CLI plus Temporal UI plus metrics.
- v1 misbehavior modes (block, slow) carry over; cpu-bound and intermittent variants are candidates for the lab, not v1.

## Non-goals

- No detection library, watchdog, linter, or any maintained tooling; native Python tooling only.
- No Flask or web front end; the Temporal Web UI and the metrics endpoint are the visual layer.
- No CI beyond the canonical application CI workflow (single pinned Python 3.14, `just check`, pip-audit, dependabot); no Docker (the metrics endpoint is served in-process by the SDK).
- No support for Python older than 3.14.
- No lab mode in this arc (see Future work).
