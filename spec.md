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

The repo has three layers.
The root package under `src/temporal_async_debug/` is the full failure-mode catalog, documented lesson by lesson in `README.md`.
`exercises/` holds five hands-on exercises in the Temporal 101/102 course layout (a `README.md`, a `practice/` copy with the bug, a `solution/` copy with the fix), one per failure family, so the reader observes the failure, finds it with the tooling, fixes the code, and verifies the fix.
`observability/` holds a Prometheus and Grafana stack that graphs the SDK and dev-server metrics over time, so the slot gauges and the Task Queue backlog are visible as they move instead of only as one-off `curl` readings.
The repo is the companion to a six-part tutorial series, "Debugging blocking calls in Temporal async Activities" (part 1 is the setup and healthy baseline, parts 2 to 6 are the five exercises); the publication venue is not yet chosen.
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

The exercises phase (decided October 31, 2026) started from the owner's definition of the deliverable, in his words:
"If there's nothing to be done, then it's not actually a section. We're not here just teaching and talking. Every single tutorial should have something for the user to do. That is what defines a tutorial. Is that there is actually an achievable goal. So the process of observing the bug, finding the bug, and then fixing the bug should be in every single tutorial present. It actually might even be important for us to set up temporal metrics and use Grafana so we can actually see what's going on."
On how the fixes live in the repo: "Look at our old course content, which has `practice` and `solution` directories per exercise. Temporal 101 and Temporal 102 show this. We should continue to follow this methodology."
The local reference for that layout is `~/Code/Temporal/edu-102-python-code/exercises/debug-activity/`: an exercise `README.md` that opens with "During this exercise, you will" bullets, tells the reader to edit `practice` and peek at `solution`, runs Parts A through E of numbered steps, and ends with "### This is the end of the exercise."; `practice/` is a full standalone copy of the app with `# TODO PART X:` comments at the edit points; `solution/` is the same copy completed.
On the server: "be sure you're using the temporal dev server single binary CLI, not standing up an ENTIRE temporal self hosted cluster."
Temporal's own guidance for the fixes, from the Python SDK sync-versus-async page: Activities should be synchronous (`def`) by default and run on the Worker's `activity_executor` (a `ThreadPoolExecutor`), because the OS preempts threads where the event loop coordinator does not; `async def` is for call stacks that are async-safe end to end.
A `ProcessPoolExecutor` is possible but discouraged (pickling, no cancellation), and true CPU parallelism comes from more Worker processes.
`temporal server start-dev` accepts `--metrics-port`, so the dev server's own metrics (including Task Queue backlog) can be scraped next to the SDK's.
The capture machine has `docker` and `docker-compose` v1 (no `docker compose` v2 plugin) and `ptrace_scope` set to 0.

## Invariants

Rules that hold across every phase of this repo.

- paths: src/temporal_async_debug/**, tests/**, exercises/**, observability/**, docs/**, justfile, pyproject.toml, README.md, CLAUDE.md, .github/workflows/ci.yml
- Python 3.14+ only; toolchain is uv + ruff + mypy (strict) + pytest, run through `just`; src layout with the hatchling build backend.
- Temporal Python SDK (temporalio) is the only workflow engine; no second orchestration framework.
- The Temporal server is always `temporal server start-dev` (the single-binary CLI); never a self-hosted cluster, never a Temporal server container, never Temporal Cloud. The compose stack under `observability/` holds Prometheus and Grafana and nothing else, and stays `docker-compose` v1 compatible.
- Python: per the python:python skill (strict typing, Google docstrings, no single-letter names, canonical ruff/mypy/pytest config verbatim).
- Prose (README, CLAUDE.md, exercise READMEs, tutorial drafts, comments, commit messages): per the writing hard rules (no em-dash or en-dash, no banned AI-tell vocabulary, straight quotes, one sentence per line in committed Markdown).
- Every deliberate bug, mistuning, or antipattern carries the fixed greppable marker on or immediately above the offending line: `# ANTIPATTERN (deliberate, for teaching): <why it is wrong>. Correct: <the right approach>. Do not copy.` Do not "fix" a marked antipattern in the root package or in a `practice/` copy; it is the demo. A `solution/` copy carries no antipattern and no marker.
- Exercises follow the Temporal 101/102 layout: `exercises/<NN-name>/README.md`, `practice/`, `solution/`; each copy is standalone and runs from its own directory; the edit points in `practice/` carry `# TODO PART X:` comments.
- Every output block in an exercise README or tutorial draft is a capture of that exercise's own copy (or of the root package for part 1); no reconstructed output, and no edits beyond the trims the root README already discloses.
- No new Python runtime dependency in this phase: the fixes use the standard library and the httpx already present, `py-spy` stays `uvx`, and Prometheus and Grafana run in containers.
- No workflow, activity, or module is named with a role label (victim, villain, culprit). The fleet must read as ordinary so the reader diagnoses from the tooling.
- Tests never require a running Temporal server except through the SDK's own facilities (`temporalio.testing.ActivityEnvironment`, `WorkflowEnvironment.start_time_skipping()`); all network calls are mocked.

## Available tooling

Tooling available to the validator and executor during autonomous runs.

**MCPs:**

- temporal-docs (`search_temporal_knowledge_sources`) for authoritative Temporal SDK behavior questions

**Skills:**

- python:python (project standards: strict typing, canonical ruff/mypy/pytest config, uv workflows)
- temporal:temporal-developer (Temporal SDK APIs, worker configuration, testing helpers)
- content-design:tutorial-writing (procedural documentation style for the README, the exercise READMEs, and the tutorial drafts)
- content-design:review-content (Vale run plus copy-editor agent; prose review against the writing hard rules)

**Notes:** All Python code follows the python:python skill without exception (type hints everywhere, Google docstrings on public interfaces, no single-letter names, canonical config blocks verbatim).
Demo code must stay small and readable; it will be excerpted line-by-line in a tutorial.
Comment density should serve a reader learning the failure mode, not the maintainer.
Every deliberately wrong line, setting, or pattern carries an inline comment on or immediately above the offending line using the fixed marker format below; the validator should flag any mistuning or antipattern that lacks one, and should flag any marker or antipattern that appears inside a `solution/` copy.
No session skill covers Prometheus or Grafana; the compose file, scrape config, and dashboard JSON are validated by the executor's own config tests (see Test requirements) and by the validator checking that the compose file defines no Temporal server service.

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
- failure-mode-catalog: the cpu, slow_heartbeat, and stuck_no_heartbeat modes, the rollup and quote bystanders, the deterministic freeze and saturation orderings in the starter, every activity timeout shown firing, the seven-lesson README with captured output, and the seven-pass adversarial review and correction (commits through 1ed2541; open as PR #4 against main; plan.md and todo.md at the root belong to this phase and are archived by the next `/bpe:plan --archive`).

**Upcoming:**

- exercises-and-observability: the five practice/solution exercises, the Prometheus and Grafana stack, fresh before-and-after captures, the root README and CLAUDE.md refresh, and the six-part tutorial series drafts.
  This is the current arc (see Architecture, Exercise requirements, Observability requirements, Test requirements, and Documentation requirements below).

**Deferred:** (a lab mode turning the demo into a whodunit; decisions recorded September 2026, build deferred until after the tutorial publishes)

- Fleet generator (`just generate N`): writes real per-workflow source files so every generated activity has its own file and line and stack traces stay genuine clues at any scale. Trigger: scaling past the hand-written workflow types.
- Seeded culprit selection: a `--seed` picks which generated activity misbehaves and how without announcing it; a `reveal` command checks the learner's answer. Trigger: the lab build.
- FastAPI game-master app (async, fully typed): starts and stops scenarios, shows a live fleet status board and symptom feed, and accepts the learner's guess for the reveal flow. Trigger: the lab build; the tutorial-facing v1 stays CLI plus Temporal UI plus metrics.
- Intermittent and load-dependent variants (a mode that only misbehaves under concurrency, or every Nth call): candidates for the lab, not this arc.

**Deferred:** (adjacent to the exercises phase; sorted October 31, 2026)

- Alert rules or Alertmanager on the dashboard. Trigger: a reader asks for paging, not graphs.
- An isolation exercise: a second Task Queue and a dedicated Worker for the long geo Activities, the structural alternative to resizing. Trigger: a seventh part after the series publishes.
- A `ProcessPoolExecutor` plus `SharedStateManager` exercise for CPU-bound work. Trigger: demand; the cpu exercise names it in prose and Temporal's docs discourage it.
- Codespaces or devcontainer setup like the 102 repo. Trigger: the series is taught live.
- A committed capture script under `scripts/` that reproduces the before-and-after runs and their disclosed trims. Trigger: the captures need re-taking after a dependency bump.
- Temporal Web UI screenshots in the drafts. Trigger: a venue that prefers screenshots to CLI output; the tool story is CLI plus Grafana.
- Publication venue and frontmatter for the drafts. Trigger: the venue decision; drafts carry no frontmatter and `TODO` cross-links until then.

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
- Observe, find, fix, verify.
  Every exercise and every tutorial part after the first ends with the reader changing code in `practice/` and re-running the same recipe to see the failure gone.
  A part with nothing for the reader to change is not a part.
- The fix is the one Temporal recommends.
  Blocking and CPU-bound work moves into plain `def` Activities on the Worker's `activity_executor`; saturation is fixed by Worker sizing; silent hangs are fixed by heartbeats and a `heartbeat_timeout`; at-most-once retry policies are replaced by retries plus idempotency.
  No fix introduces a dependency or a pattern the docs discourage.
- Each exercise copy is small.
  A `practice/` copy carries only the modes its exercise needs and the full bystander fleet, so the reader reads one failure, not the whole catalog.

## Foundation already in place

The failure-mode catalog is built, reviewed, and open as PR #4; the exercises phase builds beside it and leaves it as the reference.
In place under `src/temporal_async_debug/`:

- `shared.py`: frozen dataclasses for every workflow's input and output, `VALID_MODES` (`block`, `cpu`, `slow`, `slow_heartbeat`, `stuck_no_heartbeat`), and `TASK_QUEUE`.
- `activities.py`: `get_ip` and `get_location` over async httpx with round-robin plus failover; `_apply_mode` with the five modes (`time.sleep` at line 142 and the busy loop at line 148 marked; `stuck_no_heartbeat` marked; `slow_heartbeat` correct); `HTTP_TIMEOUT_SECONDS` of 4.0.
- `workflow.py`: `GeoEnrichmentWorkflow` and `geo_activity_options(mode)` (120-second `start_to_close`, 150-second `schedule_to_close`, 10-second `heartbeat_timeout` for the two heartbeating modes, `maximum_attempts=1` marked).
- `receipt.py`, `rollup.py`, `quote.py`: the instant, short-work, and schedule-to-start bystanders (the quote's 5-second `schedule_to_start_timeout` marked).
- `worker.py`: `build_worker(client)` with `max_concurrent_activities=2` (marked), Prometheus on 127.0.0.1:9464, the PID banner.
- `starter.py`: the fleet CLI with the deterministic freeze ordering (gate on `get_location` STARTED plus 1 second) and saturation ordering; `os._exit(0)` teardown.
- 128 tests; `just check` green; CI on actions/checkout v7, setup-uv v7, setup-just v4, with pip-audit clean.
- `README.md`: seven lessons with captured output and a disclosure of every trim; `CLAUDE.md` current.
- `docs/drafts/tutorial-original-draft.md`: the January 2026 draft kept as provenance, with `docs/drafts/README.md` listing its wrong claims.

## Architecture

### Root catalog package (unchanged in this phase)

The package layout under `src/temporal_async_debug/` is the one described under Foundation.
This phase does not change its behavior.
It is what part 1 of the series baselines, what the root README's lessons quote, and the source each `practice/` copy is trimmed from.

### Exercises

```text
exercises/
  01-blocking-call/          README.md  practice/  solution/
  02-cpu-bound/              README.md  practice/  solution/
  03-slot-exhaustion/        README.md  practice/  solution/
  04-missing-heartbeat/      README.md  practice/  solution/
  05-timeouts-and-retries/   README.md  practice/  solution/
```

Each `practice/` and `solution/` directory is a flat, standalone copy in the 102 shape: `shared.py`, `activities.py`, `workflow.py`, `receipt.py`, `rollup.py`, `quote.py`, `worker.py`, `starter.py`, and `tests/`.
It runs from its own directory with `uv run python worker.py` and `uv run python starter.py ...`, using the root project's virtual environment (the root `pyproject.toml` is the only one; copies are scripts, not packages).
A copy carries only the modes its exercise uses (decision: 01 `block`; 02 `cpu`; 03 `slow` and `slow_heartbeat`; 04 `stuck_no_heartbeat`; 05 `stuck_no_heartbeat` plus the quote; confirm at review), the full bystander fleet, and the starter's freeze or saturation ordering for those modes.
`practice/` keeps the antipattern markers for its bug and adds `# TODO PART X:` comments at every line the README asks the reader to change, including a `TODO` test stub in `tests/`.
`solution/` is the completed copy: no antipattern, no marker, the reader's test implemented and green.

The per-exercise fixes, following Temporal's sync-versus-async guidance:

- 01-blocking-call: `get_ip` and `get_location` become plain `def` Activities using httpx's synchronous client; `worker.py` passes `activity_executor=ThreadPoolExecutor(max_workers=...)` sized to `max_concurrent_activities`; the `time.sleep` stand-in stays in place and no longer freezes the loop because it runs on a pool thread.
- 02-cpu-bound: the same `def` plus executor change; the busy loop runs on a pool thread, so the loop stays live while `top` still shows the process near 100 percent (the GIL bounds throughput).
  The exercise's last part starts a second Worker process and re-runs the fleet, showing CPU-bound work scaling by Worker processes (decision: confirm at review once captured).
- 03-slot-exhaustion: `worker.py` raises `max_concurrent_activities` from 2 to 8 (decision: 8 covers the seven concurrent Activities of the `slow` fleet with headroom; confirm at review); the Activity code is untouched, and the exercise's rule-out part runs `slow_heartbeat` first to show that correct code saturates the undersized Worker the same way.
- 04-missing-heartbeat: the stuck branch gains the stepped `asyncio.sleep` plus `activity.heartbeat` loop (the shape the root package's `slow_heartbeat` already has), under the existing 10-second `heartbeat_timeout`.
- 05-timeouts-and-retries: `workflow.py` drops `RetryPolicy(maximum_attempts=1)` so the geo Activities keep the default retry policy; the quote's `schedule_to_start_timeout` stays, explained as the legitimate case.
  Verification is a `stuck`-mode run that shows attempt 2, 3, and onward in the history after each `Heartbeat` timeout, ending in the `ScheduleToClose` failure when the 150-second `schedule_to_close` runs out (about 150 seconds of wall time), together with the quote behaving as in the root catalog.

### Observability

```text
observability/
  docker-compose.yml         Prometheus and Grafana only, docker-compose v1 syntax, host networking on Linux
  prometheus.yml             scrapes 127.0.0.1:9464 (SDK) and 127.0.0.1:9465 (dev server)
  grafana/provisioning/      datasource (Prometheus) and dashboard provider
  grafana/dashboards/        one provisioned dashboard JSON
```

`just server` becomes `temporal server start-dev --metrics-port 9465` (decision: 9465 sits next to the SDK's 9464 and collides with nothing the demo uses; confirm at review).
`just metrics` runs `docker-compose -f observability/docker-compose.yml up -d`; `just metrics-down` tears it down.
Grafana serves on `localhost:3000` with anonymous viewer access and the dashboard provisioned at startup; Prometheus serves on `localhost:9090`.
The dashboard's panels: `temporal_worker_task_slots_available` and `temporal_worker_task_slots_used` by `worker_type`, `temporal_activity_schedule_to_start_latency` (sum and count, and the rate), `temporal_activity_execution_latency`, and the dev server's Task Queue backlog count and age by task queue (metric names confirmed against the live `/metrics` output during the build; the assumption is that `start-dev` exports the matching-service backlog gauges, and if it does not, the backlog panel is dropped and the README says so).
The compose file defines exactly two services, `prometheus` and `grafana`; a test asserts that.

### Documentation

```text
docs/
  drafts/
    README.md                    what each file is, the venue note, the provenance of the original draft
    tutorial-original-draft.md   unchanged, provenance only
    part-1-healthy-worker.md
    part-2-blocking-call.md
    part-3-cpu-bound.md
    part-4-slot-exhaustion.md
    part-5-missing-heartbeat.md
    part-6-timeouts-and-retries.md
    output/                      the tutorial-writing skill's working files (outline, sections), gitignored
  images/                        Grafana screenshots (PNG), named <exercise>-<state>-<panel>.png
```

The root `README.md` keeps its lessons and gains an "Exercises" table in the 102 root-README shape (directory, exercise link) and an "Observability" section (what `just metrics` starts, the dashboard, the dev server port).
`CLAUDE.md` gains the exercises and observability layout and the solution-copy carve-out.

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

## Exercise requirements

Each exercise's `practice/` copy reproduces the catalog behavior for its modes exactly as the Behavior requirements describe it, from its own directory.
Each `solution/` copy produces the after-state below, and both states are captured fresh from the copy (tool output, starter output, `temporal workflow show` histories, and Grafana screenshots), so every quoted block in the exercise README and the tutorial draft traces to a file for that exercise.

- 01-blocking-call, after the fix: the `block` fleet completes with no timeouts and no stalls; the rollup completes; `asyncio ps` shows the Activity poller and housekeeping tasks parked and no task dead-ended; `py-spy dump` shows the main thread idle in `select` and the `time.sleep` frame on an executor thread; the process stays in state `S`; the slots gauge returns to 2 when the run ends.
- 02-cpu-bound, after the fix: the `cpu` fleet completes with no timeouts; the loop stays live (bystanders complete while the busy loop runs); `py-spy dump` shows the busy loop on an executor thread holding the GIL and the main thread idle; `top` still shows the process near 100 percent.
  With a second Worker process started, two `cpu` runs progress at the same time with the combined CPU above 100 percent (decision: confirm at review from the capture).
- 03-slot-exhaustion, after the fix: the `slow` fleet completes with no `ScheduleToStart` failures; the quote, receipts, and rollup finish in their normal times; the backlog age stays near zero; the slots gauge reads 6 free of 8 while the two hogging runs hold their slots.
  The rule-out part (run before the fix, with `slow_heartbeat`) reproduces the catalog's `slow_heartbeat` behavior.
- 04-missing-heartbeat, after the fix: the formerly stuck run completes after its full delay with heartbeats recorded; no `Heartbeat` timeout; the healthy geo alongside completes; the history shows a single attempt.
- 05-timeouts-and-retries, after the fix: a `stuck` run shows the retry policy at work in `temporal workflow show` (attempt counter rising, one `Heartbeat` timeout per attempt, backoff between attempts) and fails at the 150-second `schedule_to_close` with a `ScheduleToClose` failure whose cause is the last attempt's `Heartbeat` timeout; the exercise text names this as the retry policy doing its job on an Activity that can never succeed, and points back to 04 for the fix that makes it succeed.
  The quote's behavior is unchanged from the catalog: it fails first under saturation and completes under a freeze.
- Each exercise README follows the 102 structure: title "Exercise N: <Doing the thing>", "During this exercise, you will" bullets, the `practice`/`solution` note, a prerequisites section pointing at the root README's setup and at `just metrics`, Parts A through E (run it; read the failure in the tooling and the dashboard; find the bug; write the test and fix it; redeploy and verify), and the closing "### This is the end of the exercise." line.
- Each reader-written test in Part D is one of: for 01 and 02, the probe test pattern from the root suite (a 50 ms ticker beside the Activity is not starved); for 03, a `build_worker` assertion on the new slot count; for 04, an `ActivityEnvironment` run asserting more than one heartbeat; for 05, a history-based assertion that `ActivityTaskScheduled` carries no `maximumAttempts` of 1.
  `practice/tests/` holds the stub with a `TODO PART D` comment; `solution/tests/` holds it implemented.

## Observability requirements

- `just metrics` brings up Prometheus and Grafana with one command on a machine that has `docker` and `docker-compose` v1; `just metrics-down` removes them.
  The compose file defines exactly the two services and no Temporal server.
- Prometheus scrapes the SDK endpoint on 127.0.0.1:9464 and the dev server endpoint on 127.0.0.1:9465 every 5 seconds, so a 30-second scenario produces at least six points per series.
- The dashboard is provisioned from the repo at Grafana startup; no manual import.
  Its panels are the ones listed under Architecture, and each exercise README and tutorial part names the panel the reader looks at and what it shows for the before and after states.
- `just server` passes `--metrics-port 9465`; the root README's quickstart says so and says why.
- Screenshots under `docs/images/` are PNG, with descriptive alt text where they are embedded, one per exercise state at minimum (before and after) plus the healthy baseline.

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
- Exercise gate: every `exercises/*/solution/` copy passes ruff, ruff format, mypy strict, and its own `tests/` under `just check`, run per directory so the near-identical module names in different copies never share one mypy or pytest invocation (decision: a `just` loop over the solution directories with `uv run mypy <dir>` and `uv run pytest <dir>/tests`, and the root pytest configuration excludes `exercises/`; confirm at review).
  `practice/` copies are excluded from the gate because they carry the deliberate bug and the reader's unimplemented test; a lighter `just check-practice` runs ruff and mypy on them so they at least parse and type-check.
- Solution-copy tests include the reader's Part D test for that exercise and the probe test for 01 and 02 showing the `def` Activities on the executor do not starve the loop.
- Observability config tests: `prometheus.yml` parses and names exactly the two scrape targets on ports 9464 and 9465; the compose file parses and defines exactly the services `prometheus` and `grafana` with no image whose name contains `temporal`; the dashboard JSON parses and every panel expression references a metric from the allowed list.
- The live failure signatures (cross-type blast radius, slot timing, CPU pinning, heartbeat and schedule-to-start timeouts) and the after-fix states are demonstrated live and captured during the build, not asserted in CI.
- The full gate is `just check` (ruff check, ruff format --check, mypy strict, pytest, the solution-copy loop, the observability config tests); pytest alone is the autonomous-run verification command.

## Documentation requirements

- README: what the repo demonstrates, quickstart (three terminals: `just server`, `just worker`, then a scenario recipe, plus `just metrics` for the dashboard), and one lesson per scenario in the catalog (frozen loop blocking, frozen loop CPU, slot exhaustion, correct long activity, heartbeat timeout, schedule-to-start), each with the expected healthy-versus-broken shapes for `asyncio ps` / `pstree` (the frozen-loop shape: one task dead-ended at the SDK handler, the rest parked at awaits), CPU, `py-spy dump` (the exact blocking line), and the metrics, with the cross-type blast radius called out.
- README additions for this phase: an "Exercises" table in the 102 root-README shape linking each `exercises/<NN-name>/README.md`, an "Observability" section (what `just metrics` starts, where the dashboard is, the dev server metrics port and why `just server` sets it), and the series title with a `TODO` link.
- The two-tool framing stated plainly: `asyncio ps` / `pstree` identify the frozen loop and which task is wedged with zero instrumentation; `py-spy dump` names the exact file and line, because a task stuck in synchronous code is not at an await and so its frames are off the asyncio stack.
- A summary table or section mapping each mode to the timeout it trips and the tool signature that identifies it.
- `maximum_attempts=1` documented correctly: set only on the geo activities, with the at-most-one-dispatch versus idempotency lesson.
- Platform gotchas (including that `py-spy` and `asyncio ps` both need `ptrace_scope=0` or sudo on Linux), the realistic-timeouts framing (`start_to_close` / `schedule_to_close` as the SLA, the `task-queue describe` backlog age, read together with a healthy `asyncio ps` shape, as the saturation tell, with `temporal_activity_schedule_to_start_latency` as a lagging confirmation), and a tutorial link placeholder.
- Exercise READMEs: five, in the 102 structure described under Exercise requirements, quoting only that exercise's captures, with the Grafana panel named in the observe and verify parts.
- Tutorial drafts: six, under `docs/drafts/`, written with the content-design:tutorial-writing skill from the exercise READMEs and the captures (Title H1, Introduction H3, Prerequisites H2, "Step N: Gerund phrase" H2, Conclusion H2; sentence case; second person; code sandwich; Temporal primitives capitalized), each linking the previous and next parts with `TODO` placeholders, each Vale-clean (MasonBase plus MasonTechnical) and passed through `/review-content`.
  Part 1 covers install, `ptrace_scope`, `just server`, `just worker`, `just metrics`, `just healthy`, and the baseline readings including the dashboard; parts 2 to 6 follow exercises 01 to 05 and end with the reader's fix and its verification.
  The series title is "Debugging blocking calls in Temporal async Activities".
  Drafts carry no frontmatter.
- `docs/drafts/README.md` lists the six drafts, keeps the provenance note on the original draft, and keeps the venue as not yet chosen.
- README and draft prose follows the repo owner's writing rules: no em-dashes, one sentence per line in committed Markdown.
- Update CLAUDE.md to the three-layer layout (root catalog, exercises, observability), the solution-copy carve-out, and the new `just` recipes.
- MIT license (already present).

## Non-goals

- No detection library, watchdog, linter, or any maintained tooling; diagnosis uses read-only introspection the reader runs (native `asyncio ps` / `pstree`, plus `py-spy dump` to reveal the exact line) and the Prometheus and Grafana stack, never tooling this repo builds or ships.
- No Flask or web front end; the Temporal Web UI, the metrics endpoint, and the Grafana dashboard are the visual layer.
- No CI beyond the canonical application CI workflow (single pinned Python 3.14, `just check`, pip-audit, dependabot); CI does not start containers, run the dev server, or take captures.
- No Temporal server in a container, no self-hosted cluster, and no Temporal Cloud; `temporal server start-dev` is the only server.
- No log shipping or tracing (Loki, OpenTelemetry); the stack is metrics only.
- No `fixed` modes, flags, or patch files in the root package; the fixed code lives only in `solution/` copies.
- No support for Python older than 3.14.
- No lab mode in this arc (see the Deferred list under Roadmap / phase log).

## Component boundaries

- Exercise copies (`exercises/<NN-name>/{practice,solution}/`): input is the root package at the start of the phase; output is a standalone flat copy trimmed to the exercise's modes, with `TODO PART X` markers in `practice/` and the fix in `solution/`.
  Owns its own `tests/`.
  Depends on nothing outside the root virtual environment.
- Exercise READMEs (`exercises/<NN-name>/README.md`): input is the exercise's captures; output is the 102-structure instructions.
  Depends on the captures existing.
- Observability stack (`observability/`): input is the two metrics endpoints; output is a provisioned dashboard.
  Owns the compose file, scrape config, provisioning, and dashboard JSON, plus their config tests.
  Depends on `just server` exposing port 9465.
- Captures (scratchpad during the build, trimmed into the READMEs, drafts, and `docs/images/`): input is each copy's before and after runs with the stack up; output is the quoted blocks and screenshots, with the trims disclosed in the root README's "About the captured output" section.
  Depends on the exercise copies and the stack.
- Tutorial drafts (`docs/drafts/part-N-*.md`): input is the exercise READMEs and the captures; output is the six drafts and the Vale and copy-editor passes.
  Depends on every capture and README being final.
- Root docs (`README.md`, `CLAUDE.md`, `docs/drafts/README.md`): input is the finished layout; output is the exercises table, observability section, and architecture refresh.
- Gate (`justfile`, `pyproject.toml`): input is the solution copies and config files; output is `just check` covering them and `just check-practice` covering the practice copies lightly.

## Success criteria

- `just check` is green with the solution-copy loop and the observability config tests included, and `just check-practice` is green.
- Each exercise runs from its own directory: the `practice/` copy reproduces its catalog failure, and the `solution/` copy produces its after-state, both captured and quoted.
- `just metrics` brings up the dashboard on a machine with `docker-compose` v1, with both scrape targets up and every panel populated during a scenario.
- Five exercise READMEs and six tutorial drafts exist, quote only captures of their own exercise, pass Vale, and have been through `/review-content`.
- The root README and CLAUDE.md describe the three-layer layout, and `grep -rn "ANTIPATTERN (deliberate, for teaching)" exercises/*/solution` returns nothing.
- The phase ships as commits on a feature branch against `main`, with a session summary per commit.
