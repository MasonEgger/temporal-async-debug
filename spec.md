# temporal-async-debug Specification

## Project overview

A deliberately misbehaving Temporal Python demo application for a tutorial on diagnosing blocking calls in `async def` activities.
The app runs two unrelated workflow types on one worker.
One of them can be driven into a blocking or a slow mode through its input; the other is ordinary, fast, unrelated work.
Nothing in the code is named "victim" or "villain", because the whole point is that the fleet looks normal and then goes sideways, and the reader has to find the cause from the tooling rather than from a label.

The headline lesson is the cross-type blast radius: a problem in one workflow type takes down a completely unrelated workflow type, purely because they share a worker.
A Temporal Python worker runs its poller, its heartbeat sender, and every `async def` activity from every workflow type on one asyncio event loop in one thread, so one blocking call freezes all of them, and a full slot pool stalls all of them.
This is the failure mode that surprises people: the workflow that breaks is not the one with the bug.

Readers reproduce two failure modes and diagnose them from outside the process with Python 3.14+ native tooling (`python -m asyncio ps` / `pstree`) with zero instrumentation.
The two modes teach the core distinction: a frozen event loop (a blocking call) versus an undersized busy worker (slot exhaustion).
They look the same to the workflows that suffer them but have different signatures in the tooling and different fixes.
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

## Design principles

- No labeled roles. The workflow types have realistic, neutral names. Nothing calls one the culprit and the other the victim, because that would hand the reader the answer. The reader diagnoses from `asyncio ps` and the metrics, not from the source.
- The mode is data, not a type. The same activity code runs for healthy and misbehaving instances; a bad run is bad because of its input, not because it is a differently-named "misbehaving" activity.
- Realistic timeouts only. Every activity sets `start_to_close_timeout` (required and universally set) and a `schedule_to_close_timeout` (a plausible SLA). There are no heartbeats and no `schedule_to_start_timeout`, because a quick activity would not set either, and leaning on them to surface the failure is unrealistic. Slot exhaustion is read from the `temporal_activity_schedule_to_start_latency` metric, which climbs on its own, not from a timeout the demo had to set.
- The deliberately broken lines still carry the greppable antipattern marker (see below). That marker is a source-hygiene device for the "do not copy" purpose; it does not spoon-feed the runtime diagnosis, which the reader still does from the tooling.

## Architecture

Package layout under `src/temporal_async_debug/` (src layout, hatchling, empty `__init__.py`):

- `shared.py`: frozen dataclasses for both workflow types' inputs and outputs, plus the task queue name constant.
  The geo-enrichment input carries `block_seconds: float` (default 0.0, the healthy value) and `mode: str` ("block" or "slow").
- `activities.py`: the geo-enrichment workflow's two async activities using httpx, `get_ip` and `get_location`.
  Each fetches from a short round-robin list of providers (several plain-text IP echo services for `get_ip`, several no-key geo services for `get_location`, each with a tiny parser), starting at a rotating provider and falling back to the others on failure, so a single provider's rate limit or outage does not break the demo.
  There are no heartbeats.
  Each activity applies its mode when `block_seconds > 0`: mode "block" calls `time.sleep(block_seconds)` (the deliberate bug, which freezes the one event loop), mode "slow" awaits `asyncio.sleep(block_seconds)` (cooperative, and because a running activity holds its slot until it returns, it keeps its slot for the full delay), then performs its httpx call.
  A module constant lists the healthy equivalents (`asyncio.sleep`, httpx) so the tutorial can point at the contrast in one place.
- `receipt.py`: an ordinary, unrelated workflow, `OrderReceiptWorkflow`, with three fast async activities that touch no network (`validate_order`, `compute_total`, `format_receipt`).
  It is correct code in every respect and normally completes in milliseconds.
  It exists to be the workflow that breaks when the geo workflow misbehaves, even though the two share nothing but a worker, which is the surprise the tutorial drives home.
- `workflow.py`: the geo-enrichment workflow, `GeoEnrichmentWorkflow`, executing `get_ip` then `get_location`.
  Each activity call sets a `start_to_close_timeout` (a realistic per-attempt bound) and a `schedule_to_close_timeout` (a plausible SLA that backed-up work breaches when the worker is jammed), with a retry policy of `maximum_attempts=1` so failures surface instead of retrying silently.
  No `heartbeat_timeout` and no `schedule_to_start_timeout`.
- `worker.py`: connects to localhost:7233, registers both workflow types and all activities on one task queue, and prints a startup banner with the process PID and copy-paste `python -m asyncio ps <PID>` / `pstree` commands.
  The worker is deliberately mistuned: `max_concurrent_activities=2`, so two slow-mode activities exhaust the slots.
  No `activity_executor` is configured; the activities are async on purpose.
  The SDK's Prometheus metrics endpoint is enabled (via `Runtime` telemetry config) on localhost:9464 so the tutorial can `curl` `temporal_worker_task_slots_available` and `temporal_activity_schedule_to_start_latency` live.
- `starter.py`: CLI (argparse) that submits a fleet of mixed workflows and prints results with neutral labels.
  Flags: `--mode block|slow` (the bad mode), `--block-seconds`, `--bad N` (geo-enrichment workflows submitted in the bad mode), `--geo N` (healthy geo-enrichment workflows), and `--receipts N` (order-receipt workflows).
  When a run has bad geo workflows and any bystanders, the starter sequences submission so the failure is deterministic, not a race: it submits the bad geo workflows first, polls the metrics endpoint until `temporal_worker_task_slots_available` for the ActivityWorker shows the slots are taken, then submits the bystanders, which therefore hit the frozen loop or the full slot pool every run.
  After `main()` returns, the starter flushes stdout and stderr and calls `os._exit(0)` to sidestep an intermittent teardown hang in the SDK's default Core runtime (temporalio/sdk-python#300), which otherwise parks the process on exit.

No web UI; the CLI starter plus the Temporal Web UI (localhost:8233, which shows pending activities, timeouts, and the vanishing poller) cover the interaction surface, and the earlier draft's Flask front end is explicitly dropped.

## Behavior requirements

- With everything healthy (no bad geo workflows, `block_seconds=0`), a fleet of geo-enrichment and order-receipt workflows all complete, with overlapping activity execution.
- With `--mode block --block-seconds 30 --bad 1` plus healthy geo and receipt bystanders, the worker's one event loop is frozen for the block: the poller, and every other async activity from both workflow types, stop running.
  Other geo-enrichment workflows stall, and the unrelated order-receipt workflows stall too, even though they share nothing with the geo workflow but the worker.
  The blocking activity exceeds its `start_to_close_timeout` and fails with a StartToClose timeout, and the stalled bystanders breach their timeouts.
  `asyncio ps` during the freeze shows the blocked task's stack ending at the `time.sleep` call site in `activities.py`.
- With `--mode slow --block-seconds 30 --bad 2` plus healthy geo and receipt bystanders, the event loop stays healthy but both activity slots are held for the full duration (a running activity holds its slot until it returns).
  `temporal_worker_task_slots_available` reads 0 for the run, `temporal_activity_schedule_to_start_latency` climbs, and the worker drops off the Task Queue's poller list in the Web UI.
  The bystander activities (geo and receipt alike) queue with no slot and breach their `schedule_to_close_timeout`.
  `asyncio ps` shows all tasks parked on asyncio suspension points; nothing is blocked.
- The two modes must be distinguishable purely from tool output: frozen loop (`asyncio ps` shows a task stack ending in user code at the `time.sleep` call site in `activities.py`) versus busy worker (all stacks parked on asyncio suspension points, `temporal_worker_task_slots_available` at 0, `temporal_activity_schedule_to_start_latency` climbing).
  The metrics endpoint stays reachable in both modes, so it is not the frozen-loop signal: the SDK serves Prometheus from the Temporal core (Rust) runtime on its own threads, off the Python event loop, so freezing the loop does not take the endpoint down.
  Verified live on 2026-09-17: during a 30-second block, 10 of 10 scrapes of `http://127.0.0.1:9464/metrics` returned in under a millisecond, at the same latency as the healthy baseline.
- The blocking mechanism is `time.sleep`, which blocks the single event loop. It is worth stating precisely in the tutorial that this is event-loop blocking, not a GIL effect: `time.sleep` actually releases the GIL, and the damage comes from parking the one loop thread. A CPU-bound block that holds the GIL is a separate case, deferred to v2.
- The worker banner and README both state the PID, the introspection commands, the metrics URL, and the platform gotchas (Yama ptrace_scope on Linux, sudo on macOS, both processes 3.14+).
- The blocking path is a plain `if` on the mode in the activity body, kept obvious; the tutorial's whole point is that this line looks innocent.
- Antipattern marker convention: every deliberate bug, mistuning, or antipattern is labeled at the offending line with a comment of the form `# ANTIPATTERN (deliberate, for teaching): <why it is wrong>. Correct: <the right approach>. Do not copy.`
  This applies to the `time.sleep` call, the `max_concurrent_activities=2` mistuning, and the `maximum_attempts=1` retry policy, and to any other intentionally bad choice.
  The marker string `ANTIPATTERN (deliberate, for teaching)` is fixed and greppable; the tutorial references it, and it labels the bad pattern for any human or automated system (code-completion tools, model training pipelines, snippet scrapers) that ingests the file without the surrounding README context.
  The README and the GitHub repo description both state that the repo contains deliberately broken code for educational purposes.

## Test requirements

Tests must not require a running Temporal server unless using the SDK's own test facilities.

- Unit tests for `shared.py` dataclasses and starter argument parsing and input construction.
- Unit test for the starter's metrics parser (reads the ActivityWorker slot gauge, not the LocalActivityWorker line).
- Activity tests via `temporalio.testing.ActivityEnvironment` with httpx calls mocked (all providers mocked so provider rotation stays deterministic): verify block mode calls `time.sleep` (monkeypatched to record, not sleep), slow mode awaits `asyncio.sleep` instead, the healthy path applies no delay, and provider failover moves to the next provider when one errors.
- Tests for the order-receipt activities and workflow (fast, no network): verify the receipt output and that the activities perform no network call.
- An event-loop starvation probe test that proves the contrast deterministically without Temporal: run the activity delay on an event loop next to a probe task that ticks every 50 ms with a patched short sleep of 0.5 s; assert the probe misses ticks in block mode and does not in slow mode.
- Workflow tests via `temporalio.testing.WorkflowEnvironment.start_time_skipping()` exercising the happy path of both workflow types with mocked-network activities, and confirming `maximum_attempts=1` surfaces a failure rather than retrying.
- Slot exhaustion and the cross-type blast radius are demonstrated live in the tutorial rather than asserted in CI; no integration test attempts to reproduce real schedule-to-start timing.
- The full gate is `just check` (ruff check, ruff format --check, mypy strict, pytest); pytest alone is the autonomous-run verification command via pyproject autodetection.

## Documentation requirements

- README: what the repo demonstrates, quickstart (three terminals: `just server`, `just worker`, then `just block` or `just slow`), and the two-lesson diagnostic walkthrough (frozen loop vs exhausted slots).
  Each lesson shows the cross-type blast radius (an unrelated order-receipt workflow failing because of the geo workflow) and the expected healthy vs broken output shapes for `asyncio ps` and the metrics.
  The README also covers the platform gotchas, the `start_to_close` and `schedule_to_close` timeouts as the realistic signals, the `temporal_activity_schedule_to_start_latency` metric as the slot-exhaustion tell, and a link placeholder for the tutorial.
- README prose follows the repo owner's writing rules: no em-dashes, one sentence per line in committed Markdown.
- MIT license.

## Future work (v2, not in scope for this arc)

A lab mode turning the demo into a whodunit learning environment; decisions recorded September 2026, build deferred until after the tutorial publishes:

- A fleet generator (a script invoked via `just generate N`) that writes real per-workflow source files (for example `fleet/workflow_c.py` through `fleet/workflow_z.py` by default, with no upper limit on count or naming) so every generated activity has its own file and line and stack traces remain genuine clues at any scale.
  v1 already ships two hand-written, neutrally-named workflow types; the generator scales that idea up so the culprit's file and line are a genuine clue among many.
- Seeded culprit selection: a `--seed` picks which generated activity misbehaves and how, without announcing it; a `reveal` command checks the learner's answer.
- A FastAPI "game master" app (async, fully typed, matching project standards): starts and stops scenarios, shows a live fleet status board and symptom feed, and accepts the learner's culprit guess for the reveal flow.
  This serves the game loop the Temporal Web UI cannot; it does not duplicate the Temporal UI's workflow views, and the tutorial-facing v1 remains CLI plus Temporal UI plus metrics.
- v1 misbehavior modes (block, slow) carry over; a cpu-bound block that holds the GIL, and intermittent variants, are candidates for the lab, not v1.

## Non-goals

- No detection library, watchdog, linter, or any maintained tooling; native Python tooling only.
- No Flask or web front end; the Temporal Web UI and the metrics endpoint are the visual layer.
- No CI beyond the canonical application CI workflow (single pinned Python 3.14, `just check`, pip-audit, dependabot); no Docker (the metrics endpoint is served in-process by the SDK).
- No support for Python older than 3.14.
- No lab mode in this arc (see Future work).
