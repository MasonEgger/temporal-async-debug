# temporal-async-debug Specification

## Project overview

A deliberately misbehaving Temporal Python demo application for a tutorial on diagnosing blocking and saturation failures in `async def` activities.
The app runs several unrelated workflow types on one worker and can drive activities into a range of misbehavior modes.
It is a comprehensive catalog of the ways a single asyncio event loop, shared by a Temporal worker's poller, heartbeat sender, workflow-task processing, and every async activity, gets wedged, and of how each failure looks from outside the process.

Nothing in the code is named "victim" or "villain", because the whole point is that the fleet looks normal and then goes sideways, and the reader has to find the cause from the tooling rather than from a label.
The headline lesson is the cross-type blast radius: a problem in one workflow type takes down a completely unrelated workflow type, purely because they share a worker.

Readers reproduce each failure and diagnose it from outside the process with Python 3.14+ native tooling (`python -m asyncio ps` / `pstree`) with zero instrumentation, plus the SDK's Prometheus metrics.
The two root diagnostic families are a frozen event loop (a blocking or CPU-bound call) versus an undersized or saturated worker (slot exhaustion, heartbeat loss, queue timeouts).
They can look the same to the workflows that suffer them but have different signatures in the tooling and different fixes.
The repo is the companion to a tutorial and a deep-dive blog post on masonegger.com; it is a teaching artifact, not a maintained tool, and will never be published to PyPI.

## Starting context

This repo replaces a demo referenced by an unpublished 2026 tutorial draft that was never actually built.
Research (August 2026) established the mechanism this demo must exhibit: the Temporal Python worker runs its poller, heartbeat sender, and every `async def` activity on one asyncio event loop, so a single blocking call starves all of them.
The Python 3.14 introspection commands read the target process memory without executing code in it, so they work while the loop is fully frozen.
The diagnostic signature: a healthy suspended task's coroutine stack ends on an asyncio suspension point (for example `Task.sleep` or `Semaphore.acquire`), while the blocking task's stack ends in user code at the exact file and line of the blocking call.
Worker-tuning research (September 2026) added the second mechanism: when `max_concurrent_activities` slots fill, the worker stops polling for activity tasks entirely, schedule-to-start latency climbs for every other workflow on the queue, and the Temporal UI stops listing the worker as a poller even though the process is healthy.
Known tooling gotchas the README must cover: inspector and target must both be Python 3.14+, Linux defaults to Yama `ptrace_scope=1` (failure presents as "Failed to find the PyRuntime section", fixed with sudo or `ptrace_scope=0`), macOS requires sudo, and 3.14's `asyncio ps` can fail transiently and should just be re-run.

Live testing (September 2026) established the exact timeout mechanics the catalog must respect:

- `time.sleep` and a CPU-bound loop are uncancellable, so they freeze the loop and hold their slot for the full duration; `time.sleep` releases the GIL while a CPU-bound loop pins it (a top or py-spy distinguisher, sub-millisecond CPU versus 100 percent).
- An async activity that awaits (for example `asyncio.sleep`) is cancelled by the SDK at `start_to_close`, so it does not hold its slot past that unless the timeout is generous or it heartbeats.
- A frozen loop also freezes workflow-task processing, so work submitted during a freeze never schedules its activity and only stalls; only activities already scheduled or in-flight when the freeze lands trip `start_to_close` (in-flight) or `schedule_to_close` (queued). Instant activities are not caught by a freeze; activities that do a little work are.
- The metrics endpoint is served by the Rust core off the event loop, so it stays reachable during a freeze and is not the frozen-loop signal (verified: 10 of 10 scrapes sub-millisecond during a 30-second block).
- The SDK's default Core runtime has no public shutdown (temporalio/sdk-python#300); a short-lived starter flushes and `os._exit(0)` to avoid an intermittent teardown hang.

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

- No labeled roles. Workflow types have realistic, neutral names. Nothing calls one the culprit and another the victim; the reader diagnoses from `asyncio ps` and the metrics, not from the source.
- The mode is data, not a type. The same activity code runs for healthy and misbehaving instances; a bad run is bad because of its input.
- Realistic timeouts. Activities set `start_to_close` (universal) and, where an SLA fits, `schedule_to_close`. `schedule_to_start` appears only in the one sample that exists to show it, since setting it is rare. Heartbeats appear only in the long-running-activity modes, since a quick activity would not heartbeat.
- Exhaustive but grounded. The catalog covers the realistic failure modes of this one mechanism (a shared asyncio event loop under blocking and saturation), each shown firing its real timeout and diagnosed from the tooling. It is not a catalog of every Temporal failure.
- Deliberately broken lines carry the greppable antipattern marker, a source-hygiene device that does not spoon-feed the runtime diagnosis.

## Foundation already in place

The two-workflow foundation is built and committed; the catalog extends it. In place:

- `shared.py`: frozen dataclasses (`GeoEnrichmentInput` with `block_seconds` and `mode`, `GeoEnrichmentOutput`, `OrderReceiptInput`, `OrderReceiptOutput`) and `TASK_QUEUE`.
- `activities.py`: `get_ip` and `get_location` over async httpx with round-robin plus failover across five IP providers and three geo providers; `_apply_mode` handling `block` (time.sleep) and `slow` (asyncio.sleep); `HEALTHY_EQUIVALENTS`; no heartbeats.
- `receipt.py`: `OrderReceiptWorkflow` and `validate_order` / `compute_total` / `format_receipt`, fast and no network.
- `workflow.py`: `GeoEnrichmentWorkflow` running get_ip then get_location, `start_to_close` plus `schedule_to_close`, `maximum_attempts=1` (marked).
- `worker.py`: both workflow types and all activities on one queue; `max_concurrent_activities=2` (marked); Prometheus metrics on 127.0.0.1:9464; PID banner.
- `starter.py`: fleet CLI (`--mode block|slow`, `--block-seconds`, `--bad`, `--geo`, `--receipts`) that sequences slot exhaustion; `os._exit(0)` teardown workaround.
- Tests for all of the above; `just check` green.

## Architecture (target for the catalog)

The catalog adds misbehavior modes, bystander shapes, a schedule-to-start sample, and one scenario per failure, retuning timeouts against live behavior. Package layout under `src/temporal_async_debug/`:

- `shared.py`: extend the mode set to `block`, `cpu`, `slow`, `slow_heartbeat`, `stuck_no_heartbeat`. Add any inputs the new bystander shapes and the schedule-to-start sample need.
- `activities.py`: `_apply_mode` gains:
  - `cpu`: a CPU-bound loop that spins for `block_seconds`, pinning the GIL and freezing the loop (uncancellable). Marked antipattern.
  - `slow_heartbeat`: awaits `asyncio.sleep` in short steps and heartbeats between them, the correct way to hold a slot for legit long work (not an antipattern).
  - `stuck_no_heartbeat`: awaits a long `asyncio.sleep` while the workflow sets a `heartbeat_timeout` it never satisfies, so it trips the heartbeat timeout. Marked antipattern (claims long-running work without heartbeating).
  - `block` and `slow` carry over.
- Bystander (unrelated) workflows sharing the worker, both correct and neither labeled:
  - `OrderReceiptWorkflow` (exists): instant, no network. Stalls during a freeze, starves during exhaustion.
  - A short-work, no-network bystander (a couple of seconds of cooperative `asyncio.sleep` simulating in-memory work): caught in-flight by a freeze (trips `start_to_close`) and starved during exhaustion (trips `schedule_to_close`). This is what makes a freeze produce cross-type activity-timeout failures rather than only stalls.
- A schedule-to-start sample: one workflow or scenario whose activity sets a short `schedule_to_start_timeout` (marked antipattern, the rare routing use case) so that specific timeout fires and the `temporal_activity_schedule_to_start_latency` metric is shown climbing.
- `workflow.py`: the geo workflow drives every mode; where a mode needs a `heartbeat_timeout` (slow_heartbeat, stuck_no_heartbeat), the workflow sets it per that mode. Geo activity `start_to_close` is tuned generous enough that the `slow` and `slow_heartbeat` hoggers hold their slots for the full duration (live-verified), while the freeze modes still trip the bystanders' timeouts.
- `worker.py`: register all workflow types and activities; the `max_concurrent_activities=2` mistuning and the metrics endpoint stay.
- `starter.py`: extend `--mode` to the full set; ensure the fleet mix (bad geo plus instant and short-work bystanders) and submission ordering make each scenario's timeouts fire deterministically. Keep the `os._exit(0)` workaround.
- `justfile`: one recipe per scenario (below).

No web UI; the CLI starter plus the Temporal Web UI (localhost:8233) and the metrics endpoint cover the interaction surface.

## Behavior requirements (scenario catalog)

Each scenario is a `just` recipe, a README lesson, and a distinct tool signature. Exact durations and timeout values are tuned against live runs; the required behavior is what follows.

- Healthy baseline: a fleet of geo and both bystander shapes all complete, with overlapping activity execution.
- Frozen loop, blocking call (`block`, `time.sleep`): the one event loop freezes for the duration. In-flight short-work bystanders (geo and the short-work type) trip `start_to_close`; bystanders whose activities were queued trip `schedule_to_close`; instant bystanders stall and complete late. Cross-type damage is visible. `asyncio ps` shows a task stack ending at the `time.sleep` call site in `activities.py`; CPU stays near zero; the metrics endpoint stays reachable.
- Frozen loop, CPU-bound (`cpu`): same freeze and same collateral as `block`, but CPU pins at 100 percent and `asyncio ps` shows the stack in the compute loop. This is the literal shared-GIL case; the contrast with `block` (near-zero CPU) is a diagnostic.
- Slot exhaustion (`slow`): the event loop stays healthy but both activity slots are held for the full duration. `temporal_worker_task_slots_available` reads 0, `temporal_activity_schedule_to_start_latency` climbs, the worker drops off the poller list, and starved bystanders (geo and both shapes) trip `schedule_to_close`. `asyncio ps` shows healthy suspension-point stacks.
- Correct long-running activity (`slow_heartbeat`): the activity heartbeats and holds its slot legitimately for the full duration, showing the right way to do long work. If the worker is undersized, this still exhausts slots and starves bystanders, so the fix is worker sizing, not the activity.
- Heartbeat timeout (`stuck_no_heartbeat`): a long activity with a `heartbeat_timeout` it never satisfies fails with a heartbeat timeout, the failure that a proper heartbeat interval would have surfaced fast.
- Schedule-to-start sample: an activity with a short `schedule_to_start_timeout`, run against a busy worker, fails with a schedule-to-start timeout, and the run shows the `temporal_activity_schedule_to_start_latency` metric climbing.
- Every activity timeout is shown firing across the catalog: `start_to_close`, `schedule_to_close`, `schedule_to_start`, and `heartbeat`.
- The two diagnostic families must be distinguishable purely from tool output: frozen loop (`asyncio ps` stack in user code; `block` near-zero CPU, `cpu` at 100 percent; metrics reachable) versus saturated worker (healthy suspension-point stacks, slots at 0, schedule-to-start latency climbing, poller gone).
- The blocking and CPU paths are a plain `if` on the mode in the activity body, kept obvious; the tutorial's whole point is that the offending line looks innocent.
- Antipattern marker convention: every deliberate bug, mistuning, or antipattern is labeled at the offending line with `# ANTIPATTERN (deliberate, for teaching): <why it is wrong>. Correct: <the right approach>. Do not copy.`
  This applies to the `time.sleep` call, the CPU-bound loop, the `stuck_no_heartbeat` missing heartbeat, the sample's `schedule_to_start_timeout`, the `max_concurrent_activities=2` mistuning, and the `maximum_attempts=1` retry policy. `slow_heartbeat` is correct code and carries no marker.
  The marker string is fixed and greppable; the tutorial references it, and it labels the bad pattern for any human or automated system that ingests the file without the README.
  The README and the GitHub repo description both state that the repo contains deliberately broken code for educational purposes.

## Test requirements

Tests must not require a running Temporal server unless using the SDK's own test facilities.

- Unit tests for `shared.py` dataclasses, starter argument parsing and input construction, and the starter's metrics parser (ActivityWorker gauge, not LocalActivityWorker).
- Activity tests via `temporalio.testing.ActivityEnvironment` with httpx mocked (all providers mocked so rotation is deterministic): each mode does what it claims (`block` calls `time.sleep`; `cpu` spins without awaiting or calling `time.sleep`; `slow` awaits `asyncio.sleep`; `slow_heartbeat` awaits and heartbeats more than once; `stuck_no_heartbeat` awaits and never heartbeats); healthy applies no delay; provider failover moves to the next provider on error and raises when all fail.
- The event-loop starvation probe test proves the contrast deterministically without Temporal: a probe ticks every 50 ms beside the mode under test; `block` and `cpu` starve the probe, `slow` and `slow_heartbeat` do not.
- Tests for the bystander workflows and activities (fast and short-work), verifying output and no network.
- Workflow tests via `WorkflowEnvironment.start_time_skipping()` for the happy path of each workflow type with mocked-network activities, and confirming `maximum_attempts=1` surfaces a failure.
- The live failure signatures (cross-type blast radius, slot timing, CPU pinning, heartbeat and schedule-to-start timeouts) are demonstrated live in the tutorial and verified during the build, not asserted in CI.
- The full gate is `just check` (ruff check, ruff format --check, mypy strict, pytest); pytest alone is the autonomous-run verification command.

## Documentation requirements

- README: what the repo demonstrates, quickstart (three terminals: `just server`, `just worker`, then a scenario recipe), and one lesson per scenario in the catalog (frozen loop blocking, frozen loop CPU, slot exhaustion, correct long activity, heartbeat timeout, schedule-to-start), each with the expected healthy-versus-broken shapes for `asyncio ps`, CPU, and the metrics, and the cross-type blast radius called out.
- A summary table or section mapping each mode to the timeout it trips and the tool signature that identifies it.
- Platform gotchas, the realistic-timeouts framing (`start_to_close` / `schedule_to_close` as the SLA, `temporal_activity_schedule_to_start_latency` as the saturation tell), and a tutorial link placeholder.
- README prose follows the repo owner's writing rules: no em-dashes, one sentence per line in committed Markdown.
- Update CLAUDE.md's architecture section to the catalog's module and mode layout.
- MIT license (already present).

## Future work (v2, not in scope for this arc)

A lab mode turning the demo into a whodunit learning environment; decisions recorded September 2026, build deferred until after the tutorial publishes:

- A fleet generator (`just generate N`) that writes real per-workflow source files so every generated activity has its own file and line and stack traces stay genuine clues at any scale. v1 ships hand-written, neutrally-named workflow types; the generator scales that up.
- Seeded culprit selection: a `--seed` picks which generated activity misbehaves and how, without announcing it; a `reveal` command checks the learner's answer.
- A FastAPI game-master app (async, fully typed): starts and stops scenarios, shows a live fleet status board and symptom feed, and accepts the learner's guess for the reveal flow. The tutorial-facing v1 remains CLI plus Temporal UI plus metrics.
- Intermittent and load-dependent variants (a mode that only misbehaves under concurrency, or every Nth call) are candidates for the lab, not this arc.

## Non-goals

- No detection library, watchdog, linter, or any maintained tooling; native Python tooling only.
- No Flask or web front end; the Temporal Web UI and the metrics endpoint are the visual layer.
- No CI beyond the canonical application CI workflow (single pinned Python 3.14, `just check`, pip-audit, dependabot); no Docker (the metrics endpoint is served in-process by the SDK).
- No support for Python older than 3.14.
- No lab mode in this arc (see Future work).
