# temporal-async-debug Specification

## Project overview

A deliberately misbehaving Temporal Python demo application for a tutorial on diagnosing blocking and saturation failures in `async def` activities.
The app runs several unrelated workflow types on one worker and can drive activities into a range of misbehavior modes.
It is a catalog of the ways a single asyncio event loop, shared by a Temporal worker's heartbeat recording, the Python side of workflow-task handling, the hand-off of poll results to user code, and every async activity, gets wedged, and of how each failure looks from outside the process.

Nothing in the code is named "victim" or "villain", because the whole point is that the fleet looks normal and then goes sideways, and the reader has to find the cause from the tooling rather than from a label.
The headline lesson is the cross-type blast radius: a problem in one workflow type takes down a completely unrelated workflow type, purely because they share a worker.

Readers reproduce each failure and diagnose it from outside the process with Python 3.14+ native tooling (`python -m asyncio ps` / `pstree`) with zero instrumentation, plus the SDK's Prometheus metrics, and use `py-spy dump` to read the exact blocking line.
The two root diagnostic families are a frozen event loop (a blocking or CPU-bound call) versus an undersized or saturated worker (slot exhaustion, heartbeat loss, queue timeouts).
They can look the same to the workflows that suffer them but have different signatures in the tooling and different fixes.
The repo is the companion to a tutorial and a longer blog post on masonegger.com.
It is a teaching artifact, not a maintained tool, and will never be published to PyPI.

## Starting context

This repo replaces a demo referenced by an unpublished 2026 tutorial draft that was never actually built.
Research (August 2026) established the mechanism this demo must exhibit, and October 2026 captures measured exactly what it reaches.
Every `async def` activity, the Python side of workflow task handling, heartbeat recording, and the Python tasks that hand poll results to user code share one asyncio event loop, so a single blocking call freezes all of them together.
The Rust core's network polling and the Prometheus endpoint run on their own threads and keep going, which is why the server keeps dispatching tasks that then time out and why the metrics endpoint still answers during a freeze.
The Python 3.14 introspection commands read the target process memory without executing code in it, so they work while the loop is fully frozen.
The diagnostic signature (live-verified October 2026 against temporalio 1.33.0 on Python 3.14.3): `asyncio ps` and `pstree` show the frozen-loop shape, not the blocking line.
Every healthy or merely-stalled task sits at a real await suspension point, so its coroutine stack bottoms out at `asyncio.sleep`, `wait`, or `Queue.get`, while the wedged activity task dead-ends at the SDK frame `_ActivityWorker._handle_start_activity_task` with no await beneath it and no progress.
That truncation is fundamental, not a tooling bug: `asyncio ps` reconstructs a task from its await chain, and a task stuck in a synchronous call (for example `time.sleep` deep in user code) is not suspended at an await, so its synchronous frames live on the OS thread stack instead.
To read the exact file and line of the blocking call, use `py-spy dump` (or `faulthandler`), whose thread stack runs all the way down to `_apply_mode` at the `time.sleep` call site in `activities.py`.
So zero-instrumentation `asyncio ps` tells you the loop is frozen and which task is wedged, and `py-spy` names the line.
Worker-tuning research (September 2026, refined October 2026) added the second mechanism: when every `max_concurrent_activities` slot is held, queued activity tasks wait on the server and starve.
Poller `LastAccessTime` in `temporal task-queue describe` is not a freeze signal at all, because the pollers live in the Rust core and keep long-polling through a freeze.
Idle and healthy, that age cycles from 0 to about 59 seconds with the 60-second long poll, so a single reading is ambiguous.
During a 30-second freeze the ages read 7 seconds at t+8, 19 seconds at t+20, and 7 to 9 seconds at t+40, all inside that idle cycle.
The t+40 ages are low for two different reasons.
The activity poller re-polls in the short thaw between the two freezing activities (60 to 570 ms of live loop across the 8 final runs, depending on `get_ip`'s HTTP call; 138 ms in the run that exposed the bystander race).
The workflow poller re-polls when the next workflow task is dispatched to it, even mid-freeze: in the captured run it re-polled 1.3 seconds into the second freeze, for the receipts' workflow task.
That mid-freeze re-poll is the clearest evidence that the pollers keep long-polling through a freeze.
The activity poller's age grows only while zero activity permits are free, so it is at most a weak saturation hint.
The worker never left the Pollers list in any capture, including one taken 75 seconds into a run.
`temporal_worker_task_slots_available` reads 0 in both families: during a freeze at t+8 and t+20, while the frozen `get_ip` and the in-flight rollup hold both slots, and during saturation.
It reads 1 at t+40 of a freeze, because the rollup's slot is reclaimed at the first thaw and only the frozen `get_location` holds one.
So zero free slots says the slot pool is full, not which family you have; the `asyncio ps` shape and CPU tell them apart.
The saturation tell is the activity backlog age in `task-queue describe` read together with a healthy `asyncio ps` shape: every task parked at an await, none dead-ended.
A freeze also shows a backlog while no permit is free (one task, 8.9 seconds old, the rollup's retry, at t+20 of a `block` run), so a backlog under a dead-ended task is the freeze.
`temporal_activity_schedule_to_start_latency` records only when a queued task finally starts, so it is a lagging confirmation, not a live tell.
Under `just slow` its sum moved from 3464 to 63530 ms (count 27 to 33), because the late healthy geo recorded two waits of about 30 seconds once it finally started.
Under `just slow-heartbeat` it barely moved (63530 to 63543 ms), because nothing queued ever started.
Known tooling gotchas the README must cover: inspector and target must both be Python 3.14+, Linux defaults to Yama `ptrace_scope=1` (failure presents as "Failed to find the PyRuntime section", fixed with sudo or `ptrace_scope=0`), macOS requires sudo, and 3.14's `asyncio ps` can fail transiently and should just be re-run.

Live testing (September 2026) established the exact timeout mechanics the catalog must respect:

- `time.sleep` and a CPU-bound loop are uncancellable, so they freeze the loop and hold their slot for the full duration.
  `time.sleep` releases the GIL while a CPU-bound loop pins it (a top or py-spy distinguisher, near-zero CPU versus 100 percent).
- An async activity that awaits (for example `asyncio.sleep`) is cancelled by the SDK at `start_to_close`, so it does not hold its slot past that unless the timeout is generous or it heartbeats.
- A frozen loop also freezes workflow-task processing, so work submitted during a freeze never schedules its activity and only stalls until the loop thaws.
  An activity already in flight when the freeze lands trips `start_to_close`; under the default retry policy its retry cannot finish inside the remaining budget, so it fails with a top-level `ScheduleToClose` timeout whose cause is `StartToClose`.
  Instant activities are not caught by a freeze; activities that do a little work are.
- When `schedule_to_start` is unset, the server copies `schedule_to_close` into it (the `ActivityTaskScheduled` event shows 10s/10s or 20s/20s), so both timers share one deadline.
  A task that is still queued when that deadline arrives reports the `ScheduleToStart` label with no cause, even though the activity only set `schedule_to_close`.
  It flips to `ScheduleToClose` only if a slot frees in the final milliseconds (observed once in a 12-second `slow` run).
- The metrics endpoint is served by the Rust core off the event loop, so it stays reachable during a freeze and is not the frozen-loop signal (verified: scrapes answered in a few milliseconds throughout both 30-second freezes of a `block` run).
- The SDK's default Core runtime has no public shutdown (temporalio/sdk-python#300); a short-lived starter flushes and `os._exit(0)` to avoid an intermittent teardown hang.

## Invariants

Rules that hold across every phase of this repo.

- paths: src/temporal_async_debug/**, tests/**, justfile, README.md, CLAUDE.md
- Python 3.14+ only; toolchain is uv + ruff + mypy (strict) + pytest, run through `just`; src layout with the hatchling build backend.
- Temporal Python SDK (temporalio) is the only workflow engine; no second orchestration framework.
- Python: per the python:python skill (strict typing, Google docstrings, no single-letter names, canonical ruff/mypy/pytest config verbatim).
- Prose (README, CLAUDE.md, comments, commit messages): per the writing hard rules (no em-dash or en-dash, no banned AI-tell vocabulary, straight quotes, one sentence per line in committed Markdown).
- Every deliberate bug, mistuning, or antipattern carries the fixed greppable marker on or immediately above the offending line: `# ANTIPATTERN (deliberate, for teaching): <why it is wrong>. Correct: <the right approach>. Do not copy.` Do not "fix" a marked antipattern; it is the demo.
- No workflow, activity, or module is named with a role label (victim, villain, culprit). The fleet must read as ordinary so the reader diagnoses from the tooling.
- Tests never require a running Temporal server except through the SDK's own facilities (`temporalio.testing.ActivityEnvironment`, `WorkflowEnvironment.start_time_skipping()`); all network calls are mocked.

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

- temporal-developer (Temporal Marketplace) :: the Temporal marketplace reference for Temporal Python workflows, activities, workers, testing, and error handling :: /home/mmegger/.claude/plugins/cache/temporal-marketplace/temporal-developer/0.2.0/.claude-plugin/plugin.json
- temporal-python-testing :: Temporal workflow testing: pytest fixtures, time-skipping for long-running workflows, replay testing for determinism :: https://github.com/wshobson/agents/tree/main/plugins/backend-development/skills/temporal-python-testing
- async-python-patterns :: asyncio event loops, async/await, concurrent I/O patterns, and task coordination for async activity debugging :: https://claude-plugins.dev/skills/@wshobson/agents/async-python-patterns
- python-testing (pytest) :: pytest fixtures, parametrization, mocking, async testing with pytest-asyncio, test organization :: https://playbooks.com/skills/laurigates/claude-plugins/python-testing
- uv package manager (astral-sh official) :: uv project dependency management matching the project build toolchain :: https://claudemarketplaces.com/skills/astral-sh/claude-code-plugins/uv
- justfile-expert :: Just command runner recipes and cross-platform task automation as used in this project :: https://agentskills.so/skills/laurigates-claude-plugins-justfile-expert
- ruff linting (astral-sh official) :: Official Ruff linter integration matching the project code-quality toolchain :: https://claude-plugins.dev/skills/@laurigates/dotfiles/ruff-linting
- python-code-quality :: Multi-tool ruff, mypy, and code-quality coverage for the linting and type-checking stack :: https://mcpmarket.com/tools/skills/python-code-quality-linting-2
- Doc-Driven Development :: Documentation-first pattern, then generate implementation to match; relevant to a tutorial/README-first approach :: https://github.com/cbrake/claude-plugins/blob/main/doc-driven-development/README.md
- python-dev (L3DigitalNet) :: General Python development with async patterns, type safety, testing, resilience :: https://agentskill.sh/plugins/l3digitalnet/python-dev

## Roadmap / phase log

**Shipped:**

- v1: the two-lesson Greeting/Victim demo (frozen loop plus slot exhaustion), converged then superseded by the two-workflow redesign (.ai-sessions/v1/).
- two-workflow-foundation: the neutrally-named GeoEnrichmentWorkflow and OrderReceiptWorkflow foundation on one worker, with round-robin providers, block/slow modes, and the os._exit teardown workaround (commits 04dec90, 29d68b8; not yet archived under .ai-sessions/).

**Upcoming:**

- The failure-mode catalog: adds the cpu, slow_heartbeat, and stuck_no_heartbeat modes, a short-work bystander shape, a schedule-to-start sample, every activity timeout shown firing, retuned timeouts, and the full README plus CLAUDE.md refresh.
  This is the current arc (see Architecture, Behavior requirements, and Documentation requirements below).

**Deferred:** (a lab mode turning the demo into a whodunit; decisions recorded September 2026, build deferred until after the tutorial publishes)

- Fleet generator (`just generate N`): writes real per-workflow source files so every generated activity has its own file and line and stack traces stay genuine clues at any scale. Trigger: scaling past the hand-written workflow types.
- Seeded culprit selection: a `--seed` picks which generated activity misbehaves and how without announcing it; a `reveal` command checks the learner's answer. Trigger: the lab build.
- FastAPI game-master app (async, fully typed): starts and stops scenarios, shows a live fleet status board and symptom feed, and accepts the learner's guess for the reveal flow. Trigger: the lab build; the tutorial-facing v1 stays CLI plus Temporal UI plus metrics.
- Intermittent and load-dependent variants (a mode that only misbehaves under concurrency, or every Nth call): candidates for the lab, not this arc.

## Design principles

- No labeled roles.
  Workflow types have realistic, neutral names.
  Nothing calls one the culprit and another the victim; the reader diagnoses from `asyncio ps` and the metrics, not from the source.
- The mode is data, not a type.
  The same activity code runs for healthy and misbehaving instances; a bad run is bad because of its input.
- Realistic timeouts.
  Activities set `start_to_close` (universal) and, where an SLA fits, `schedule_to_close`.
  `schedule_to_start` is set explicitly only in the one sample that exists to show it, since setting it is rare.
  Heartbeats appear only in the long-running-activity modes, since a quick activity would not heartbeat.
- Exhaustive but grounded.
  The catalog covers the realistic failure modes of this one mechanism (a shared asyncio event loop under blocking and saturation), each shown firing its real timeout and diagnosed from the tooling.
  It is not a catalog of every Temporal failure.
- Deliberately broken lines carry the greppable antipattern marker, a source-hygiene device that does not spoon-feed the runtime diagnosis.

## Foundation already in place

The two-workflow foundation is built and committed; the catalog extends it.
In place:

- `shared.py`: frozen dataclasses (`GeoEnrichmentInput` with `block_seconds` and `mode`, `GeoEnrichmentOutput`, `OrderReceiptInput`, `OrderReceiptOutput`) and `TASK_QUEUE`.
- `activities.py`: `get_ip` and `get_location` over async httpx with round-robin plus failover across five IP providers and three geo providers; `_apply_mode` handling `block` (time.sleep) and `slow` (asyncio.sleep); no heartbeats.
- `receipt.py`: `OrderReceiptWorkflow` and `validate_order` / `compute_total` / `format_receipt`, fast and no network.
- `workflow.py`: `GeoEnrichmentWorkflow` running get_ip then get_location, `start_to_close` plus `schedule_to_close`, `maximum_attempts=1` (marked).
- `worker.py`: both workflow types and all activities on one queue; `max_concurrent_activities=2` (marked); Prometheus metrics on 127.0.0.1:9464; PID banner.
- `starter.py`: fleet CLI (`--mode block|slow`, `--block-seconds`, `--bad`, `--geo`, `--receipts`) that sequences slot exhaustion; `os._exit(0)` teardown workaround.
- Tests for all of the above; `just check` green.

## Architecture (target for the catalog)

The catalog adds misbehavior modes, bystander shapes, a schedule-to-start sample, and one scenario per failure, retuning timeouts against live behavior.
Package layout under `src/temporal_async_debug/`:

- `shared.py`: extend the mode set to `block`, `cpu`, `slow`, `slow_heartbeat`, `stuck_no_heartbeat`.
  Add any inputs the new bystander shapes and the schedule-to-start sample need.
- `activities.py`: `_apply_mode` gains:
  - `cpu`: a CPU-bound loop that spins for `block_seconds`, pinning the GIL and freezing the loop (uncancellable).
    Marked antipattern.
  - `slow_heartbeat`: awaits `asyncio.sleep` in short steps and heartbeats between them, the correct way to hold a slot for legit long work (not an antipattern).
  - `stuck_no_heartbeat`: awaits a long `asyncio.sleep` while the workflow sets a `heartbeat_timeout` it never satisfies, so it trips the heartbeat timeout.
    Marked antipattern (claims long-running work without heartbeating).
  - `block` and `slow` carry over.
- Bystander (unrelated) workflows sharing the worker, both correct and neither labeled:
  - `OrderReceiptWorkflow` (exists): instant, no network.
    Stalls during a freeze, starves during exhaustion.
  - A short-work, no-network bystander (about five seconds of cooperative `asyncio.sleep` simulating in-memory work): caught in-flight by a freeze (trips `start_to_close`, then fails with `ScheduleToClose` caused by `StartToClose`) and starved during exhaustion.
    A starved run reports the `ScheduleToStart` label, because with `schedule_to_start` unset the server copies `schedule_to_close` into it and the two timers share one deadline.
    This bystander is what makes a freeze produce cross-type activity-timeout failures rather than only stalls.
- A schedule-to-start sample: one workflow or scenario whose activity sets a short `schedule_to_start_timeout` (marked antipattern, the rare routing use case) so that specific timeout fires and the `temporal_activity_schedule_to_start_latency` metric is shown climbing.
- `workflow.py`: the geo workflow drives every mode; where a mode needs a `heartbeat_timeout` (slow_heartbeat, stuck_no_heartbeat), the workflow sets it per that mode.
  Geo activity `start_to_close` is tuned generous enough that the `slow` and `slow_heartbeat` hoggers hold their slots for the full duration (live-verified), while the freeze modes still trip an in-flight short-work bystander's `start_to_close` (the freeze recipes' healthy geo finishes before the bad run is submitted, so the short-work bystander is what carries the cross-type blast radius).
- `worker.py`: register all workflow types and activities; the `max_concurrent_activities=2` mistuning and the metrics endpoint stay.
- `starter.py`: extend `--mode` to the full set; ensure the fleet mix (bad geo plus instant and short-work bystanders) and submission ordering make each scenario's timeouts fire deterministically.
  A `Fleet` value and `select_scenario` route every bystander kind (healthy geo, receipts, rollups, quotes) into the freeze or saturation ordering, so no requested run is dropped.
  The freeze path submits rollups and the healthy geo first and awaits the healthy geo, so the rollups are in flight when the freeze lands and the healthy geo has already finished.
  It then submits the bad run, waits until the server reports the bad run's second activity (`get_location`) STARTED plus a 1-second guard, and only then submits the instant bystanders, so they stall through the final freeze.
  Keep the `os._exit(0)` workaround.
- `justfile`: one recipe per scenario (below).

No web UI; the CLI starter plus the Temporal Web UI (localhost:8233) and the metrics endpoint cover the interaction surface.

## Behavior requirements (scenario catalog)

Each scenario is a `just` recipe, a README lesson, and a distinct tool signature.
Exact durations and timeout values are tuned against live runs; the required behavior is what follows.

- Healthy baseline: a fleet of geo and both bystander shapes all complete, with overlapping activity execution.
- Frozen loop, blocking call (`block`, `time.sleep`): the bad geo run freezes the one event loop twice, once in `get_ip` and once in `get_location`, each for the full duration, with a fraction of a second of live loop between the two freezes (60 to 570 ms across the 8 final runs, depending on `get_ip`'s HTTP call; 138 ms in the run that exposed the bystander race).
  A short-work bystander (the rollup) that was already in flight when the first freeze landed trips `start_to_close` and, under the default retry policy, fails with a top-level `ScheduleToClose` timeout whose cause is `StartToClose` (8 of 8 live runs); that is the cross-type blast radius.
  The healthy geo completes in under a second before the bad run is submitted (8 of 8), because the starter awaits it; it survives by that ordering, not because of its 120-second `start_to_close`.
  The starter then waits until the server reports the bad run's second and last freezing activity (`get_location`) STARTED, adds a 1-second guard, and submits the instant bystanders (receipts, and quotes when requested).
  They stall through the final freeze and complete at the thaw: across 8 live runs all 19 receipts and quotes completed with an `executionDuration` of 28.85 to 29.12 seconds, their first workflow task scheduled 1.03 to 1.26 seconds after `get_location` STARTED, and zero timeouts.
  The gate waits on the second activity, not the first, because a bystander released into the sub-second thaw between the freezes (60 to 570 ms across the 8 final runs; 138 ms in that run) can be dispatched just as the loop re-freezes and then fails `ScheduleToClose` caused by `StartToClose` (observed once in 16 bystanders gated on `get_ip`).
  The starter's wall time is about 61 seconds for a 30-second recipe.
  `asyncio ps` / `pstree` show the wedged geo task dead-ended at `_ActivityWorker._handle_start_activity_task` with no await beneath it, while every other task sits at a normal await suspension (the in-flight rollup at `rollup.py:48`).
  `py-spy dump` names the exact `time.sleep` line: `_apply_mode` at `activities.py:142`, under `get_ip` at `:196` or `get_location` at `:225`, beneath `worker.py:124`, with the thread idle.
  CPU stays near zero because `time.sleep` releases the GIL.
  The metrics endpoint stays reachable, answering in a few milliseconds.
  `temporal_worker_task_slots_available` reads 0 at t+8 and t+20 (the frozen `get_ip` plus the in-flight rollup hold both slots) and 1 at t+40 (the rollup's slot is reclaimed at the first thaw), so it is not a freeze discriminator.
- Frozen loop, CPU-bound (`cpu`): same freeze and same collateral as `block`, but CPU pins at 100 percent because the loop holds the GIL, and `py-spy dump` shows the stack inside the compute loop at `activities.py:148`, with the thread active and holding the GIL.
  `asyncio ps` shows the same frozen shape as `block` (the wedged task dead-ended at the SDK frame).
  The CPU contrast, near-zero for `block` versus 100 percent for `cpu`, is the diagnostic that separates them.
- Slot exhaustion (`slow`): the event loop stays healthy but both activity slots are held for the full duration.
  `temporal_worker_task_slots_available` reads 0 and the activity backlog age in `task-queue describe` climbs; backlog age read together with that healthy `asyncio ps` shape (every task parked at an await, none dead-ended) is the saturation tell, while a backlog under a dead-ended task is a freeze.
  `temporal_activity_schedule_to_start_latency` lags: it records only when a queued task finally starts (under `just slow` its sum jumped from 3464 to 63530 ms once the late healthy geo started; under `just slow-heartbeat`, where nothing queued ever starts, it moved from 63530 to 63543 ms).
  The starved receipts, rollup, and quote fail with the `ScheduleToStart` label and no cause (the quote at 5 seconds, receipts at 10, the rollup at 20).
  The healthy geo submitted after the hold queues behind it and completes late (59.88 seconds in the October 2026 capture, with about 30 seconds of schedule-to-start wait on each of its two activities), because its `schedule_to_close` is 150 seconds.
  The schedule-to-start sample sets that timeout explicitly; the others only set `schedule_to_close`, which the server copies into `schedule_to_start`, so both timers share one deadline and the `ScheduleToStart` label wins while the task is still queued.
  `asyncio ps` shows every task parked at a healthy await suspension with none dead-ended, which is what separates saturation from a freeze.
- Correct long-running activity (`slow_heartbeat`): the activity heartbeats and holds its slot legitimately for the full duration, showing the right way to do long work.
  If the worker is undersized, this still exhausts slots and starves bystanders (with the same `ScheduleToStart` label as `slow`), so the fix is worker sizing, not the activity.
- Heartbeat timeout (`stuck_no_heartbeat`): a long activity with a `heartbeat_timeout` it never satisfies fails with a heartbeat timeout, the failure that a proper heartbeat interval would have surfaced fast.
- Schedule-to-start sample: an activity with a short `schedule_to_start_timeout`, run against a busy worker, fails with a schedule-to-start timeout, and the run shows the `temporal_activity_schedule_to_start_latency` metric climbing once queued tasks start.
- Every activity timeout is shown firing across the catalog: `start_to_close`, `schedule_to_close`, `schedule_to_start`, and `heartbeat`.
  `schedule_to_close` appears as the top-level timeout of the frozen-loop rollup failure, with `start_to_close` as its cause.
  `ScheduleToStart` is the saturation label, even for activities that only set `schedule_to_close`.
- The two diagnostic families must be distinguishable purely from tool output.
  Frozen loop: `asyncio ps` shows one activity task dead-ended at the SDK handler with no await beneath it while the rest sit frozen at awaits; `block` near-zero CPU, `cpu` at 100 percent; `py-spy` names the line; metrics reachable.
  Saturated worker: every task parked at a healthy await suspension, none dead-ended; backlog age climbing.
  Zero free slots and poller `LastAccessTime` do not discriminate: slots read 0 in both families, and the pollers keep long-polling through a freeze, with the activity poller's age growing only while no activity permit is free.
- The blocking and CPU paths are a plain `if` on the mode in the activity body, kept obvious; the tutorial's whole point is that the offending line looks innocent.
- Antipattern marker convention: every deliberate bug, mistuning, or antipattern is labeled at the offending line with `# ANTIPATTERN (deliberate, for teaching): <why it is wrong>. Correct: <the right approach>. Do not copy.`
  This applies to the `time.sleep` call, the CPU-bound loop, the `stuck_no_heartbeat` missing heartbeat, the sample's `schedule_to_start_timeout`, the `max_concurrent_activities=2` mistuning, and the `maximum_attempts=1` retry policy.
  `maximum_attempts=1` is set only on the geo activities; receipt, rollup, and quote keep the default retry policy, and the frozen-loop rollup failure chain depends on that default's second attempt.
  The lesson: one attempt gives at-most-one dispatch, not exactly-once, and effectively-once comes from keeping retries plus an idempotent Activity keyed on `workflow_run_id` and `activity_id`.
  `slow_heartbeat` is correct code and carries no marker.
  The marker string is fixed and greppable; the tutorial references it, and it labels the bad pattern for any human or automated system that ingests the file without the README.
  The README and the GitHub repo description both state that the repo contains deliberately broken code for educational purposes.

## Test requirements

Tests must not require a running Temporal server unless using the SDK's own test facilities.

- Unit tests for `shared.py` dataclasses, starter argument parsing and input construction, and the starter's metrics parser (ActivityWorker gauge, not LocalActivityWorker).
- Activity tests via `temporalio.testing.ActivityEnvironment` with httpx mocked (all providers mocked so rotation is deterministic): each mode does what it claims (`block` calls `time.sleep`; `cpu` spins without awaiting or calling `time.sleep`; `slow` awaits `asyncio.sleep`; `slow_heartbeat` awaits and heartbeats more than once; `stuck_no_heartbeat` awaits and never heartbeats); healthy applies no delay; provider failover moves to the next provider on error and raises when all fail.
- The event-loop starvation probe test proves the contrast deterministically without Temporal: a probe ticks every 50 ms beside the mode under test; `block` and `cpu` starve the probe, `slow` and `slow_heartbeat` do not.
- Tests for the bystander workflows and activities (fast and short-work), verifying output and no network.
- Workflow tests via `WorkflowEnvironment.start_time_skipping()` for the happy path of each workflow type with mocked-network activities, and confirming `maximum_attempts=1` surfaces a failure and an unknown mode raises `ApplicationError(type="InvalidMode")`.
- History-based timeout wiring: workflow tests read the `ActivityTaskScheduled` events from the finished run's history (`tests/history.py`) and assert the timeouts the server actually received, which is the offline-safe way to prove each workflow passes its timeouts to `execute_activity`.
- `build_worker(client)` coverage: a test builds the worker and asserts the `max_concurrent_activities=2` mistuning and the full workflow and activity registration.
- Constant pins: tests pin the timeout constants and their relationships (for example the rollup's 5-second default work fits inside its `start_to_close` with a freeze margin, and `HTTP_TIMEOUT_SECONDS` of 4.0 fits inside the heartbeat timeout).
- Starter tests cover `fleet_from_args` and `select_scenario` routing every bystander kind into its mode family, and the freeze and saturation submission orders.
- The live failure signatures (cross-type blast radius, slot timing, CPU pinning, heartbeat and schedule-to-start timeouts) are demonstrated live in the tutorial and verified during the build, not asserted in CI.
- The full gate is `just check` (ruff check, ruff format --check, mypy strict, pytest); pytest alone is the autonomous-run verification command.

## Documentation requirements

- README: what the repo demonstrates, quickstart (three terminals: `just server`, `just worker`, then a scenario recipe), and one lesson per scenario in the catalog (frozen loop blocking, frozen loop CPU, slot exhaustion, correct long activity, heartbeat timeout, schedule-to-start), each with the expected healthy-versus-broken shapes for `asyncio ps` / `pstree` (the frozen-loop shape: one task dead-ended at the SDK handler, the rest parked at awaits), CPU, `py-spy dump` (the exact blocking line), and the metrics, with the cross-type blast radius called out.
- The two-tool framing stated plainly: `asyncio ps` / `pstree` identify the frozen loop and which task is wedged with zero instrumentation; `py-spy dump` names the exact file and line, because a task stuck in synchronous code is not at an await and so its frames are off the asyncio stack.
- A summary table or section mapping each mode to the timeout it trips and the tool signature that identifies it.
- `maximum_attempts=1` documented correctly: set only on the geo activities, with the at-most-one-dispatch versus idempotency lesson.
- Platform gotchas (including that `py-spy` and `asyncio ps` both need `ptrace_scope=0` or sudo on Linux), the realistic-timeouts framing (`start_to_close` / `schedule_to_close` as the SLA, the `task-queue describe` backlog age, read together with a healthy `asyncio ps` shape, as the saturation tell, with `temporal_activity_schedule_to_start_latency` as a lagging confirmation), and a tutorial link placeholder.
- README prose follows the repo owner's writing rules: no em-dashes, one sentence per line in committed Markdown.
- Update CLAUDE.md's architecture section to the catalog's module and mode layout.
- MIT license (already present).

## Non-goals

- No detection library, watchdog, linter, or any maintained tooling; diagnosis uses read-only introspection the reader runs (native `asyncio ps` / `pstree`, plus `py-spy dump` to reveal the exact line), never tooling this repo builds or ships.
- No Flask or web front end; the Temporal Web UI and the metrics endpoint are the visual layer.
- No CI beyond the canonical application CI workflow (single pinned Python 3.14, `just check`, pip-audit, dependabot); no Docker (the metrics endpoint is served in-process by the SDK).
- No support for Python older than 3.14.
- No lab mode in this arc (see the Deferred list under Roadmap / phase log).
