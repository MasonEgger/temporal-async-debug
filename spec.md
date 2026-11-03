# temporal-async-debug Specification

## Project overview

A deliberately misbehaving Temporal Python demo application for a tutorial series on one problem: blocking the asyncio event loop from an `async def` Activity.
The app runs several unrelated workflow types on one worker.
Every `async def` activity, the Python side of workflow-task handling, heartbeat recording, and the hand-off of poll results to user code share one asyncio event loop, so one blocking call freezes all of them together.

Nothing in the code is named "victim" or "villain", because the whole point is that the fleet looks normal and then goes sideways, and the reader has to find the cause from the tooling rather than from a label.
The headline lesson is the cross-type blast radius: a blocking call in one workflow type's Activity takes down a completely unrelated workflow type, purely because they share a worker and its event loop.

Readers reproduce each failure and diagnose it from outside the process with Python 3.14+ native tooling (`python -m asyncio ps` / `pstree`) with zero instrumentation, plus the SDK's Prometheus metrics, and use `py-spy dump` to read the exact blocking line.
Slot exhaustion, heartbeat and timeout tuning, and retry policy are general Temporal topics with plenty of existing material; this repo does not teach them.

The repo has three layers.
The root package under `src/temporal_async_debug/` is the frozen-loop reference: a healthy fleet plus the `block` and `cpu` modes, documented lesson by lesson in `README.md`.
`exercises/` holds five hands-on exercises in the Temporal 101/102 course layout (a `README.md`, a `practice/` copy with the bug, a `solution/` copy with the fix), one per common way developers block the loop, so the reader observes the failure, finds it with the tooling, fixes the code, and verifies the fix.
`observability/` holds a Prometheus and Grafana stack that graphs the SDK and dev-server metrics over time, so the effect of a frozen loop is visible as it happens instead of only as one-off `curl` readings.
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
Poller `LastAccessTime` in `temporal task-queue describe` is not a freeze signal, because the pollers live in the Rust core and keep long-polling through a freeze.
Idle and healthy, that age cycles from 0 to about 59 seconds with the 60-second long poll, so a single reading is ambiguous.
During a 30-second freeze the ages read 7 seconds at t+8, 19 seconds at t+20, and 7 to 9 seconds at t+40, all inside that idle cycle.
The activity poller re-polls in the short thaw between the two freezing activities (60 to 570 ms of live loop across the 8 final runs, depending on `get_ip`'s HTTP call; 138 ms in the run that exposed the bystander race).
The workflow poller re-polls when the next workflow task is dispatched to it, even mid-freeze: in the captured run it re-polled 1.3 seconds into the second freeze, for the receipts' workflow task.
The worker never left the Pollers list in any capture, including one taken 75 seconds into a run.
`temporal_worker_task_slots_available` reads 0 during a freeze at t+8 and t+20, while the frozen `get_ip` and the in-flight rollup hold both slots, and 1 at t+40, because the rollup's slot is reclaimed at the first thaw.
A freeze also shows a backlog in `task-queue describe` while no permit is free (one task, 8.9 seconds old, the rollup's retry, at t+20 of a `block` run).
Known tooling gotchas the README must cover: inspector and target must both be Python 3.14+, Linux defaults to Yama `ptrace_scope=1` (failure presents as "Failed to find the PyRuntime section", fixed with sudo or `ptrace_scope=0`), macOS requires sudo, and 3.14's `asyncio ps` can fail transiently and should just be re-run.

Live testing (September 2026) established the mechanics the frozen-loop lessons must respect:

- `time.sleep` and a CPU-bound loop are uncancellable, so they freeze the loop and hold their slot for the full duration.
  `time.sleep` releases the GIL while a CPU-bound loop pins it (a top or py-spy distinguisher, near-zero CPU versus 100 percent).
- A frozen loop also freezes workflow-task processing, so work submitted during a freeze never schedules its activity and only stalls until the loop thaws.
  An activity already in flight when the freeze lands trips `start_to_close`; under the default retry policy its retry cannot finish inside the remaining budget, so it fails with a top-level `ScheduleToClose` timeout whose cause is `StartToClose`.
  Instant activities are not caught by a freeze; activities that do a little work are.
- The metrics endpoint is served by the Rust core off the event loop, so it stays reachable during a freeze and is not the frozen-loop signal (verified: scrapes answered in a few milliseconds throughout both 30-second freezes of a `block` run).
- The SDK's default Core runtime has no public shutdown (temporalio/sdk-python#300); a short-lived starter flushes and `os._exit(0)` to avoid an intermittent teardown hang.

The exercises phase (decided October 31, 2026) started from the owner's definition of the deliverable, in his words:
"If there's nothing to be done, then it's not actually a section. We're not here just teaching and talking. Every single tutorial should have something for the user to do. That is what defines a tutorial. Is that there is actually an achievable goal. So the process of observing the bug, finding the bug, and then fixing the bug should be in every single tutorial present. It actually might even be important for us to set up temporal metrics and use Grafana so we can actually see what's going on."
On how the fixes live in the repo: "Look at our old course content, which has `practice` and `solution` directories per exercise. Temporal 101 and Temporal 102 show this. We should continue to follow this methodology."
The local reference for that layout is `~/Code/Temporal/edu-102-python-code/exercises/debug-activity/`: an exercise `README.md` that opens with "During this exercise, you will" bullets, tells the reader to edit `practice` and peek at `solution`, runs Parts A through E of numbered steps, and ends with "### This is the end of the exercise."; `practice/` is a full standalone copy of the app with `# TODO PART X:` comments at the edit points; `solution/` is the same copy completed.
On the server: "be sure you're using the temporal dev server single binary CLI, not standing up an ENTIRE temporal self hosted cluster."

The scope was narrowed on November 2, 2026, after a first exercise plan covered slot exhaustion, missing heartbeats, and retry policy.
In the owner's words: "There's tons content around regular timeout. This entire tutorial is JUST about the [...] Python async event loop."
And on what the exercises are for: "I want the exercises that show off the most likely things a user would trip on with this issue, how it fails, how to debug it, and what correct looks like."
The exercise set below was picked from the Temporal docs and the community threads in the temporal-docs index, where the same mistakes recur: a synchronous HTTP client (`requests.post`, sync gRPC) inside `async def`, which halts every Workflow on the Worker and shows up as `WorkflowTaskTimeout`s and "only one Workflow runs at a time"; `time.sleep` between heartbeats, where the heartbeats never leave the Worker, the Activity fails its `Heartbeat` timeout, and keeps running because asyncio cancellation cannot interrupt blocking code; CPU-heavy or blocking library work (ML, ffmpeg, `Pool.map`) inside `async def`; and the fix that is not one, where `asyncio.to_thread` or `run_in_executor` frees the loop but cancellation never reaches the thread and the work runs twice, a `def` Activity without an `activity_executor` fails at Worker start, and an executor smaller than `max_concurrent_activities` logs a warning.
Temporal's own guidance for the fixes, from the Python SDK sync-versus-async page: Activities should be synchronous (`def`) by default and run on the Worker's `activity_executor` (a `ThreadPoolExecutor`), because the OS preempts threads where the event loop coordinator does not; `async def` is for call stacks that are async-safe end to end.
Cancellation of a threaded `def` Activity arrives as a `temporalio.exceptions.CancelledError` thrown into the thread, delivered through heartbeats; `async def` cancellation is `asyncio.Task.cancel`, which has no effect on thread-blocking code.
A `ProcessPoolExecutor` is possible but discouraged (pickling, no exception on cancellation), and true CPU parallelism comes from more Worker processes.
Python's asyncio debug mode (`PYTHONASYNCIODEBUG=1` or `asyncio.run(..., debug=True)`) logs any callback or task step slower than `slow_callback_duration` (default 100 ms); a Temporal SDK maintainer points users at it for catching blockers.
`temporal server start-dev` accepts `--metrics-port`, so the dev server's own metrics can be scraped next to the SDK's.
The capture machine has `docker` and `docker-compose` v1 (no `docker compose` v2 plugin) and `ptrace_scope` set to 0.

## Invariants

Rules that hold across every phase of this repo.

- paths: src/temporal_async_debug/**, tests/**, exercises/**, observability/**, docs/**, justfile, pyproject.toml, README.md, CLAUDE.md, .vale.ini, .github/workflows/ci.yml
- Python 3.14+ only; toolchain is uv + ruff + mypy (strict) + pytest, run through `just`; src layout with the hatchling build backend.
- Temporal Python SDK (temporalio) is the only workflow engine; no second orchestration framework.
- The Temporal server is always `temporal server start-dev` (the single-binary CLI); never a self-hosted cluster, never a Temporal server container, never Temporal Cloud. The compose stack under `observability/` holds Prometheus and Grafana and nothing else, and stays `docker-compose` v1 compatible.
- Python: per the python:python skill (strict typing, Google docstrings, no single-letter names, canonical ruff/mypy/pytest config verbatim).
- Prose (README, CLAUDE.md, exercise READMEs, tutorial drafts, comments, commit messages): per the writing hard rules (no em-dash or en-dash, no banned AI-tell vocabulary, straight quotes, one sentence per line in committed Markdown).
- Scope: every lesson, exercise, and draft is about blocking the shared asyncio event loop. No slot-exhaustion, heartbeat-tuning, timeout-tuning, or retry-policy lesson, even as a contrast case.
- Every exercise's bug is an execution failure the reader sees without a dashboard (bystanders fail, attempts fail and retry, the same work runs twice, a bystander is visibly delayed on every run), diagnosed with the Python tooling the reader runs (`asyncio ps`, `pstree`, `py-spy dump`, the CPU reading, asyncio debug mode). A metrics blip alone is not a bug; Grafana corroborates and never teaches. Exercise 05 is the one detection lesson and the only exercise that misbehaves without failing.
- Every deliberate bug, mistuning, or antipattern carries the fixed greppable marker on or immediately above the offending line: `# ANTIPATTERN (deliberate, for teaching): <why it is wrong>. Correct: <the right approach>. Do not copy.` Do not "fix" a marked antipattern in the root package or in a `practice/` copy; it is the demo. A `solution/` copy carries no antipattern and no marker.
- Exercises follow the Temporal 101/102 layout: `exercises/<NN-name>/README.md`, `practice/`, `solution/`; each copy is standalone and runs from its own directory; the edit points in `practice/` carry `# TODO PART X:` comments.
- Every output block in an exercise README, the root README, or a tutorial draft is a capture of that copy (or of the root package for the root README and part 1); no reconstructed output, and no edits beyond the trims the root README discloses.
- No new Python runtime dependency: the fixes use the standard library and the httpx already present (its synchronous `httpx.Client` stands in for `requests`), `py-spy` stays `uvx`, and Prometheus and Grafana run in containers.
- No workflow, activity, or module is named with a role label (victim, villain, culprit). The fleet must read as ordinary so the reader diagnoses from the tooling.
- Tests never require a running Temporal server except through the SDK's own facilities (`temporalio.testing.ActivityEnvironment`, `WorkflowEnvironment.start_time_skipping()`); all network calls are mocked or served by a local stdlib server inside the test.

## Available tooling

Tooling available to the validator and executor during autonomous runs.

**MCPs:**

- temporal-docs (`search_temporal_knowledge_sources`) for authoritative Temporal SDK behavior questions

**Skills:**

- python:python (project standards: strict typing, canonical ruff/mypy/pytest config, uv workflows)
- temporal:temporal-developer (Temporal SDK APIs, worker configuration, testing helpers)
- content-design:tutorial-writing (procedural documentation style for the README, the exercise READMEs, and the tutorial drafts; owns the structure, the code sandwich, and the mechanical canon)
- voice:teaching (Mason's teaching-refined register applied on top of the tutorial-writing canon; invoked after tutorial-writing on every prose step; every draft carries a smell report and open questions)
- content-design:review-content (Vale run plus copy-editor agent; prose review against the writing hard rules)
- content-design:style-linting (the repo .vale.ini, the Std sync rule, and reading Vale output; used by the pre-flight step)

**Notes:** All Python code follows the python:python skill without exception (type hints everywhere, Google docstrings on public interfaces, no single-letter names, canonical config blocks verbatim).
Demo code must stay small and readable; it will be excerpted line-by-line in a tutorial.
Comment density should serve a reader learning the failure mode, not the maintainer.
Every deliberately wrong line, setting, or pattern carries an inline comment on or immediately above the offending line using the fixed marker format below; the validator should flag any antipattern that lacks one, and should flag any marker or antipattern that appears inside a `solution/` copy.
The validator should also flag any lesson, exercise part, or draft section that drifts into slot exhaustion, heartbeat or timeout tuning, or retry policy.
No session skill covers Prometheus or Grafana; the compose file, scrape config, and dashboard JSON are validated by the executor's own config tests (see Test requirements) and by the validator checking that the compose file defines no Temporal server service.
Prose tooling is gated: a repo-root `.vale.ini` applies MasonBase everywhere and MasonBase plus MasonTechnical under `docs/drafts/**` and `exercises/**`, and `just preflight` verifies Vale, the styles, Std, and the plugin files before any prose step runs; the validator reads `just lint-prose` (Vale JSON) and `just lint-keyboard` as declared linters.
voice:teaching's rule that every draft waits for Mason's eyes is satisfied in the autonomous loop by the scaffold-branch commit (only Mason merges) plus a committed `docs/drafts/smell-reports.md` holding each artifact's smell report and open questions; nothing publishes from the loop.

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
- failure-mode-catalog: the cpu, slow_heartbeat, and stuck_no_heartbeat modes, the rollup and quote bystanders, the deterministic freeze and saturation orderings in the starter, every activity timeout shown firing, the seven-lesson README with captured output, and the seven-pass adversarial review and correction (commits through 1ed2541, open as PR #4 against main; .ai-sessions/failure-mode-catalog/).
  The November 2, 2026 rescope retires its saturation, heartbeat, schedule-to-start, and retry-policy material; the freeze machinery and lessons 1 to 3 carry forward.

**Upcoming:**

- event-loop-exercises: trim the root catalog to the frozen-loop reference, then the five practice/solution exercises, the Prometheus and Grafana stack, fresh before-and-after captures, the root README and CLAUDE.md refresh, and the six-part tutorial series drafts.
  This is the current arc (see Architecture, Exercise requirements, Observability requirements, Test requirements, and Documentation requirements below).

**Deferred:** (a lab mode turning the demo into a whodunit; decisions recorded September 2026, build deferred until after the tutorial publishes)

- Fleet generator (`just generate N`): writes real per-workflow source files so every generated activity has its own file and line and stack traces stay genuine clues at any scale. Trigger: scaling past the hand-written workflow types.
- Seeded culprit selection: a `--seed` picks which generated activity misbehaves and how without announcing it; a `reveal` command checks the learner's answer. Trigger: the lab build.
- FastAPI game-master app (async, fully typed): starts and stops scenarios, shows a live fleet status board and symptom feed, and accepts the learner's guess for the reveal flow. Trigger: the lab build; the tutorial-facing v1 stays CLI plus Temporal UI plus metrics.
- Intermittent and load-dependent blockers (a call that only blocks under concurrency, or every Nth call): candidates for the lab, not this arc.

**Deferred:** (adjacent to the exercises phase; sorted October 31, 2026, revised November 2, 2026)

- Alert rules or Alertmanager on the dashboard. Trigger: a reader asks for paging, not graphs.
- A `ProcessPoolExecutor` plus `SharedStateManager` exercise for CPU-bound work. Trigger: demand; the cpu exercise names it in prose and Temporal's docs discourage it.
- A blocking-call-in-Workflow-code exercise (the sandbox and deadlock detector are a separate mechanism). Trigger: a seventh part after the series publishes.
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
  In exercise 01 the code is identical for every run and the input only points the bad run at a slow upstream, because "it worked in dev, the API was fast" is how the real bug ships.
- One mechanism.
  Every lesson and exercise is a way to block the shared asyncio event loop, shown failing, diagnosed from the tooling, and fixed.
  Timeouts appear only as symptoms of a frozen loop, never as the subject.
- The most likely trip-ups first.
  The exercises are the mistakes Temporal users actually report, in order of how often they come up, not a taxonomy.
- Deliberately broken lines carry the greppable antipattern marker, a source-hygiene device that does not spoon-feed the runtime diagnosis.
- Observe, find, fix, verify.
  Every exercise and every tutorial part after the first ends with the reader changing code in `practice/` and re-running the same recipe to see the failure gone.
  A part with nothing for the reader to change is not a part.
- The fix is the one Temporal recommends.
  Blocking and CPU-bound work moves into plain `def` Activities on a `ThreadPoolExecutor` passed as the Worker's `activity_executor`, sized to `max_concurrent_activities`, with heartbeats so cancellation reaches the thread.
  `async def` stays only where the whole call stack is async-safe.
  No fix introduces a dependency or a pattern the docs discourage.
- Each exercise copy is small.
  A copy carries only the code its exercise needs and the bystander fleet, so the reader reads one failure, not the whole catalog.

## Foundation already in place

The failure-mode catalog is built, reviewed, and open as PR #4.
This arc trims it first and builds the exercises beside the trimmed package.
In place under `src/temporal_async_debug/` at the start of the arc:

- `shared.py`: frozen dataclasses for every workflow's input and output, `VALID_MODES` (`block`, `cpu`, `slow`, `slow_heartbeat`, `stuck_no_heartbeat`), and `TASK_QUEUE`.
- `activities.py`: `get_ip` and `get_location` over async httpx with round-robin plus failover; `_apply_mode` with the five modes (`time.sleep` and the busy loop marked; `stuck_no_heartbeat` marked; `slow_heartbeat` correct); `HTTP_TIMEOUT_SECONDS` of 4.0.
- `workflow.py`: `GeoEnrichmentWorkflow` and `geo_activity_options(mode)` (120-second `start_to_close`, 150-second `schedule_to_close`, 10-second `heartbeat_timeout` for the two heartbeating modes, `maximum_attempts=1` marked).
- `receipt.py`, `rollup.py`, `quote.py`: the instant, short-work, and schedule-to-start bystanders (the quote's 5-second `schedule_to_start_timeout` marked).
- `worker.py`: `build_worker(client)` with `max_concurrent_activities=2` (marked), Prometheus on 127.0.0.1:9464, the PID banner.
- `starter.py`: the fleet CLI with the deterministic freeze ordering (gate on `get_location` STARTED plus 1 second) and saturation ordering; `os._exit(0)` teardown.
- 128 tests; `just check` green; CI on actions/checkout v7, setup-uv v7, setup-just v4, with pip-audit clean.
- `README.md`: seven lessons with captured output and a disclosure of every trim; `CLAUDE.md` current.
- `docs/drafts/tutorial-original-draft.md`: the January 2026 draft kept as provenance, with `docs/drafts/README.md` listing its wrong claims.

## Architecture

### Root package: the frozen-loop reference (trimmed in this arc)

The first step of the arc removes everything that is not the frozen loop:

- `shared.py`: `VALID_MODES` becomes `block` and `cpu`; the quote dataclasses go.
- `activities.py`: `_apply_mode` keeps `block` (`time.sleep`, marked) and `cpu` (busy loop, marked); the `slow`, `slow_heartbeat`, and `stuck_no_heartbeat` branches and the heartbeat helper go.
- `workflow.py`: `geo_activity_options` collapses to one fixed set (120-second `start_to_close`, 150-second `schedule_to_close`), with no `heartbeat_timeout` and no `RetryPolicy(maximum_attempts=1)`; the geo activities keep the default retry policy like every other activity.
- `quote.py` is deleted.
- `worker.py`: registration drops the quote; `max_concurrent_activities=2` stays so the slot gauge readings in the freeze lessons stay small and readable, but it loses its antipattern marker and carries a plain comment saying it is small on purpose (decision: confirm at review).
- `starter.py`: the saturation ordering, `SATURATION_MODES`, the concurrent fallback that only served them, and `--quotes` go; the freeze ordering, the `get_location` STARTED gate, and `os._exit(0)` stay.
- `justfile`: `slow`, `slow-heartbeat`, and `stuck` go; `healthy`, `trigger`, `block`, and `cpu` stay.

After the trim the root package is what part 1 of the series baselines, what the root README's three lessons quote, and the source each exercise copy starts from.

### Exercises

```text
exercises/
  01-sync-http-client/          README.md  practice/  solution/
  02-sleep-between-heartbeats/  README.md  practice/  solution/
  03-cpu-bound/                 README.md  practice/  solution/
  04-zombie-thread/             README.md  practice/  solution/
  05-catching-blockers-early/   README.md  practice/  solution/
```

Each `practice/` and `solution/` directory is a flat, standalone copy in the 102 shape: `shared.py`, `activities.py`, `workflow.py`, `receipt.py`, `rollup.py`, `worker.py`, `starter.py`, and `tests/`, plus any file named for that exercise below.
It runs from its own directory with `uv run python worker.py` and `uv run python starter.py ...`, using the root project's virtual environment (the root `pyproject.toml` is the only one; copies are scripts, not packages).
A copy replaces the root's `block`/`cpu` switch with its exercise's bug, keeps the bystander fleet (receipts and rollups), and keeps the starter's freeze ordering so the blast radius is visible the same way in every exercise.
`practice/` keeps the antipattern marker for its bug and adds `# TODO PART X:` comments at every line the README asks the reader to change, including a `TODO` test stub in `tests/`.
`solution/` is the completed copy: no antipattern, no marker, the reader's test implemented and green.

The five exercises, in order of how often Temporal users hit them:

- 01-sync-http-client: `get_location` is an `async def` Activity that calls a synchronous HTTP client (`httpx.Client`, standing in for `requests`).
  Healthy runs hit the real geo providers and finish fast, so the bug hides; the bad run's input points the provider at a local slow endpoint that answers after the configured delay.
  The slow endpoint is a stdlib `http.server` the starter serves on 127.0.0.1 for the duration of the run (decision: served by the starter so the reader needs no extra terminal; confirm at review), in `slow_upstream.py`.
  The fix: `get_ip` and `get_location` become plain `def` Activities on the same sync client, and `worker.py` passes `activity_executor=ThreadPoolExecutor(max_workers=...)` sized to `max_concurrent_activities`.
- 02-sleep-between-heartbeats: `get_location` is an `async def` Activity that polls a slow job in a loop, calling `activity.heartbeat()` and then `time.sleep(...)` between polls, with a `heartbeat_timeout` on the call.
  The heartbeats are recorded but the loop never runs to send them, so the server fails the attempt with a `Heartbeat` timeout while the Worker keeps running the Activity, because asyncio cancellation cannot interrupt `time.sleep`.
  The poll interval is longer than the fixed `heartbeat_timeout` (decision: `heartbeat_timeout` 5 seconds, poll interval 8 seconds, a job of about 20 seconds keyed on the workflow run id so a retry observes the same job; confirm at review), so what the reader sees is a retry storm: the failed attempt keeps polling as a zombie while the default retry policy starts the next attempt beside it, `temporal workflow show` lists attempt after attempt ending in a `Heartbeat` timeout, and the bystanders fail in the same windows until the job finishes and an attempt completes.
  The fix: wait in awaited 1-second ticks with a heartbeat on every tick (`activity.heartbeat()` then `await asyncio.sleep(1)` until the next poll is due), so heartbeats flush on the loop more often than the timeout and cancellation lands at the await (decision: the awaited tick loop replaces the one-line `await asyncio.sleep(poll_interval)`, which would still go 8 seconds without a heartbeat under a 5-second timeout; the Activity stays `async` and the `def` route is named in prose; confirm at review).
- 03-cpu-bound: `get_location` does pure-Python computation inside `async def` (the root `cpu` busy loop, recast as a realistic transform of the provider response), holding the GIL and pinning CPU at 100 percent.
  The fix: the `def` plus executor change from 01; the work runs on a pool thread, the loop stays live while `top` still shows the process near 100 percent, and the README names more Worker processes as the way to get real CPU parallelism.
  The last part starts a second Worker process and re-runs the fleet, showing two CPU-bound runs progressing at once with the combined CPU above 100 percent (decision: confirm at review once captured).
- 04-zombie-thread: the practice copy carries the fix many users ship first, and it looks right: `get_location` stays `async def` and wraps the blocking call in `asyncio.to_thread(...)`, with a `heartbeat_timeout` and no heartbeat.
  The loop stays live, so the bystanders are fine, but when the server times the attempt out the coroutine is cancelled and the thread keeps running, so the work finishes after the Activity has already failed and the retry runs the same work again beside it: the Activity runs twice.
  Part A also walks through the two startup traps on the way to the real fix: a `def` Activity registered without an `activity_executor` fails at Worker construction, and an executor smaller than `max_concurrent_activities` logs the SDK's warning; both messages are captured.
  The fix: a `def` Activity on a `ThreadPoolExecutor` sized to `max_concurrent_activities` that heartbeats from its own thread, so a timeout or cancel arrives as `CancelledError` inside the thread and the work stops.
- 05-catching-blockers-early: the practice copy has a short blocker that ships unnoticed, a synchronous serialization of a large payload in an `async def` Activity that takes a few hundred milliseconds (decision: a pure-Python JSON round trip of a generated payload, sized to take 200 to 500 ms on the capture machine; confirm at review).
  Nothing times out, but every run stalls the loop for that long, and every bystander dispatched into the stall waits it out: a receipt that completes in a few milliseconds in the healthy fleet takes a few hundred milliseconds on every run of this one, visible as the gap between its Activity's started and completed timestamps in `temporal workflow show`.
  This is the one detection lesson in the series and the only exercise that misbehaves without failing.
  Part A runs the healthy fleet and then this one and compares the receipt timings; Part B runs the Worker with asyncio debug mode, captures the slow-callback warning that names the task, and confirms the line with `py-spy`; Part C moves the work off the loop; Part D adds the starvation-probe test over every registered `async def` Activity as the regression guard that would have caught it in CI.

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
The dashboard shows what a frozen loop does to the Worker over time: `temporal_activity_execution_latency`, `temporal_workflow_task_schedule_to_start_latency` and `temporal_workflow_task_execution_latency` (workflow tasks stall during a freeze), activity and workflow task failures and timeouts, `temporal_worker_task_slots_used` by `worker_type`, and the dev server's Task Queue backlog (metric names confirmed against the live `/metrics` output during the build; a panel whose metric the SDK or `start-dev` does not export is dropped and the README says so).
The compose file defines exactly two services, `prometheus` and `grafana`; a test asserts that.

### Documentation

```text
docs/
  drafts/
    README.md                         what each file is, the venue note, the provenance of the original draft
    tutorial-original-draft.md        unchanged, provenance only
    part-1-healthy-worker.md
    part-2-sync-http-client.md
    part-3-sleep-between-heartbeats.md
    part-4-cpu-bound.md
    part-5-zombie-thread.md
    part-6-catching-blockers-early.md
    output/                           the tutorial-writing skill's working files (outline, sections), gitignored
  images/                             Grafana screenshots (PNG), named <exercise>-<state>-<panel>.png
```

The root `README.md` keeps three lessons (healthy, blocking call, CPU bound), recaptured from the trimmed package, and gains an "Exercises" table in the 102 root-README shape (directory, exercise link) and an "Observability" section (what `just metrics` starts, the dashboard, the dev server port).
`CLAUDE.md` describes the trimmed package, the exercises and observability layout, and the solution-copy carve-out.

## Behavior requirements (root package)

Each scenario is a `just` recipe, a README lesson, and a distinct tool signature.
Exact durations are tuned against live runs; the required behavior is what follows.

- Healthy baseline: a fleet of geo and both bystander shapes all complete, with overlapping activity execution.
- Frozen loop, blocking call (`block`, `time.sleep`): the bad geo run freezes the one event loop twice, once in `get_ip` and once in `get_location`, each for the full duration, with a fraction of a second of live loop between the two freezes (60 to 570 ms across the 8 final runs, depending on `get_ip`'s HTTP call).
  A short-work bystander (the rollup) that was already in flight when the first freeze landed trips `start_to_close` and, under the default retry policy, fails with a top-level `ScheduleToClose` timeout whose cause is `StartToClose`; that is the cross-type blast radius.
  The healthy geo completes in under a second before the bad run is submitted, because the starter awaits it.
  The starter then waits until the server reports the bad run's second and last freezing activity (`get_location`) STARTED, adds a 1-second guard, and submits the instant bystanders (receipts).
  They stall through the final freeze and complete at the thaw, about 29 seconds after submission, with zero timeouts.
  The gate waits on the second activity, not the first, because a bystander released into the sub-second thaw between the freezes can be dispatched just as the loop re-freezes and then fails `ScheduleToClose` caused by `StartToClose` (observed once in 16 bystanders gated on `get_ip`).
  `asyncio ps` / `pstree` show the wedged geo task dead-ended at `_ActivityWorker._handle_start_activity_task` with no await beneath it, while every other task sits at a normal await suspension (the in-flight rollup at its `asyncio.sleep`).
  `py-spy dump` names the exact `time.sleep` line in `_apply_mode`, under `get_ip` or `get_location`, with the thread idle.
  CPU stays near zero because `time.sleep` releases the GIL.
  The metrics endpoint stays reachable, answering in a few milliseconds.
  `temporal_worker_task_slots_available` reads 0 while the frozen activity and the in-flight rollup hold both slots, so the slots gauge says the pool is full, not why.
- Frozen loop, CPU-bound (`cpu`): same freeze and same collateral as `block`, but CPU pins at 100 percent because the loop holds the GIL, and `py-spy dump` shows the stack inside the compute loop with the thread active and holding the GIL.
  `asyncio ps` shows the same frozen shape as `block`.
  The CPU contrast, near-zero for `block` versus 100 percent for `cpu`, is the diagnostic that separates them.
- The frozen loop is identified purely from tool output: `asyncio ps` shows one activity task dead-ended at the SDK handler with no await beneath it while the rest sit frozen at awaits; `py-spy` names the line; CPU separates sleeping from computing.
  The metrics endpoint, the slots gauge, and poller `LastAccessTime` do not identify a freeze, and the README says why.
- The blocking and CPU paths are a plain `if` on the mode in the activity body, kept obvious; the tutorial's whole point is that the offending line looks innocent.
- Antipattern marker convention: every deliberate bug is labeled at the offending line with `# ANTIPATTERN (deliberate, for teaching): <why it is wrong>. Correct: <the right approach>. Do not copy.`
  In the trimmed root package this applies to the `time.sleep` call and the CPU-bound loop only.
  The marker string is fixed and greppable; the tutorial references it, and it labels the bad pattern for any human or automated system that ingests the file without the README.
  The README and the GitHub repo description both state that the repo contains deliberately broken code for educational purposes.

## Exercise requirements

Each exercise's `practice/` copy reproduces its failure from its own directory, and each `solution/` copy produces the after-state below.
Both states are captured fresh from the copy (tool output, starter output, Worker log, `temporal workflow show` histories, and Grafana screenshots), so every quoted block in the exercise README and the tutorial draft traces to a file for that exercise.

- 01-sync-http-client.
  Before: the bad run freezes the loop for the slow endpoint's delay; the in-flight rollup fails `ScheduleToClose` caused by `StartToClose`; receipts stall and complete at the thaw; workflow-task latency spikes on the dashboard.
  `asyncio ps` shows the dead-ended task; `py-spy dump` names the `httpx.Client` call in `get_location` (frames down into the socket read); CPU near zero.
  After: the same fleet completes with no timeouts and no stalls; `asyncio ps` shows no task dead-ended; `py-spy dump` shows the main thread idle and the HTTP read on an executor thread.
- 02-sleep-between-heartbeats.
  Before: the history lists attempt after attempt failing with a `Heartbeat` timeout (the retry storm) while the Worker log keeps printing a dead attempt's poll lines after its failure (the zombie); bystanders stall and the in-flight rollup fails as in 01; `py-spy dump` names the `time.sleep` line inside the heartbeat loop; the storm ends when the job finishes and an attempt completes.
  After: heartbeats reach the server (`temporal workflow describe` shows the last heartbeat time advancing every second), the Activity completes on its first attempt, and the bystanders complete normally.
- 03-cpu-bound.
  Before: the root `cpu` signature from this copy (frozen shape, 100 percent CPU, `py-spy` in the compute loop, the rollup failure).
  After: the fleet completes with no timeouts; the loop stays live (bystanders complete while the computation runs); `py-spy dump` shows the computation on an executor thread holding the GIL and the main thread idle; `top` still shows the process near 100 percent.
  With a second Worker process started, two `cpu` runs progress at the same time with the combined CPU above 100 percent (decision: confirm at review from the capture).
- 04-zombie-thread.
  Before: the bystanders complete (the loop is live), but the bad run's first attempt times out, the Worker log shows the thread's work still running and finishing after the server failed the attempt, and the retry's work overlaps it; `py-spy dump` shows the orphaned thread still inside the blocker after the failure.
  The two startup traps are captured verbatim: the error from a `def` Activity with no `activity_executor`, and the warning from an executor smaller than `max_concurrent_activities`.
  After: a forced timeout or cancel stops the work inside the thread (the Worker log shows the `CancelledError` and no work after it), and no attempt's work overlaps another's.
- 05-catching-blockers-early.
  Before: every run completes and nothing times out, yet the receipt Activities take a few hundred milliseconds from started to completed where the healthy fleet takes a few (the stall, read in `temporal workflow show`), asyncio debug mode logs a slow-step warning naming the Activity task at a few hundred milliseconds per run, and `py-spy` confirms the serialization line.
  After: the receipt timings return to milliseconds, debug mode logs no slow step for the Activity, and the probe test passes over every `async def` Activity in the copy.
- Each exercise README follows the 102 structure: title "Exercise N: <Doing the thing>", "During this exercise, you will" bullets, the `practice`/`solution` note, a prerequisites section pointing at the root README's setup and at `just metrics`, Parts A through E (run it; read the failure in the tooling and the dashboard; find the bug; write the test and fix it; redeploy and verify), and the closing "### This is the end of the exercise." line.
- Each reader-written test in Part D:
  01 and 03, the probe test pattern from the root suite (a 50 ms ticker beside the Activity is not starved);
  02, an `ActivityEnvironment` run asserting more than one heartbeat and an unstarved probe during the poll loop;
  04, an `ActivityEnvironment` cancel of the `def` Activity asserting the work stops at the next heartbeat, plus a `build_worker` assertion that the executor's `max_workers` is at least `max_concurrent_activities`;
  05, the probe test parametrized over every registered `async def` Activity.
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

- Root package after the trim: unit tests for `shared.py` dataclasses, starter argument parsing and input construction, and the starter's metrics parser (ActivityWorker gauge, not LocalActivityWorker).
- Activity tests via `temporalio.testing.ActivityEnvironment` with httpx mocked (all providers mocked so rotation is deterministic): `block` calls `time.sleep`; `cpu` spins without awaiting or calling `time.sleep`; healthy applies no delay; provider failover moves to the next provider on error and raises when all fail.
- The event-loop starvation probe test proves the freeze deterministically without Temporal: a probe ticks every 50 ms beside the mode under test; `block` and `cpu` starve the probe, healthy does not.
- Tests for the bystander workflows and activities (instant and short-work), verifying output and no network.
- Workflow tests via `WorkflowEnvironment.start_time_skipping()` for the happy path of each workflow type with mocked-network activities, and confirming an unknown mode raises `ApplicationError(type="InvalidMode")`.
- History-based timeout wiring: workflow tests read the `ActivityTaskScheduled` events from the finished run's history (`tests/history.py`) and assert the timeouts the server actually received.
- `build_worker(client)` coverage: a test builds the worker and asserts `max_concurrent_activities=2` and the full workflow and activity registration.
- Starter tests cover `fleet_from_args` and the freeze submission order.
- Tests for removed modes, the quote, the saturation ordering, and `maximum_attempts=1` are deleted with the code, not skipped.
- Exercise gate: every `exercises/*/solution/` copy passes ruff, ruff format, mypy strict, and its own `tests/` under `just check`, run per directory so the near-identical module names in different copies never share one mypy or pytest invocation (decision: a `just` loop over the solution directories with `uv run mypy <dir>` and `uv run pytest <dir>/tests`, and the root pytest configuration excludes `exercises/`; confirm at review).
  `practice/` copies are excluded from the gate because they carry the deliberate bug and the reader's unimplemented test; a lighter `just check-practice` runs ruff and mypy on them so they at least parse and type-check.
- Solution-copy tests include the reader's Part D test for that exercise; exercise 01's tests serve the slow endpoint from a stdlib server inside the test, never the network.
- Observability config tests assert only the stack's invariants, never that a file parses or a value we chose: `prometheus.yml` names exactly the two scrape targets on ports 9464 and 9465; the compose file defines exactly the services `prometheus` and `grafana` with no image whose name contains `temporal`; every dashboard panel expression references a metric from the allowed list.
- The live failure signatures (cross-type blast radius, CPU pinning, the heartbeat retry storm, the zombie-thread overlap, the debug-mode warning) and the after-fix states are demonstrated live and captured during the build, not asserted in CI.
- The full gate is `just check` (ruff check, ruff format --check, mypy strict, pytest, the solution-copy loop, the observability config tests); pytest alone is the autonomous-run verification command.

## Documentation requirements

- README: what the repo demonstrates (one mechanism, the shared event loop), quickstart (three terminals: `just server`, `just worker`, then a scenario recipe, plus `just metrics` for the dashboard), and three lessons (healthy, frozen loop from a blocking call, frozen loop from CPU-bound code), each with the expected healthy-versus-broken shapes for `asyncio ps` / `pstree`, CPU, `py-spy dump` (the exact blocking line), and the metrics, with the cross-type blast radius called out.
  Lessons 4 to 7, "Which timeout fires, and how to tell", and the timeout-tuning parts of "Realistic timeouts" are removed.
  Every output block in the three lessons is recaptured from the trimmed package.
- README additions for this arc: an "Exercises" table in the 102 root-README shape linking each `exercises/<NN-name>/README.md`, an "Observability" section (what `just metrics` starts, where the dashboard is, the dev server metrics port and why `just server` sets it), and the series title with a `TODO` link.
- The two-tool framing stated plainly: `asyncio ps` / `pstree` identify the frozen loop and which task is wedged with zero instrumentation; `py-spy dump` names the exact file and line, because a task stuck in synchronous code is not at an await and so its frames are off the asyncio stack.
- Platform gotchas (including that `py-spy` and `asyncio ps` both need `ptrace_scope=0` or sudo on Linux) and a tutorial link placeholder.
- Exercise READMEs: five, in the 102 structure described under Exercise requirements, quoting only that exercise's captures, with the Grafana panel named in the observe and verify parts.
- Tutorial drafts: six, under `docs/drafts/`, written with the content-design:tutorial-writing skill from the exercise READMEs and the captures (Title H1, Introduction H3, Prerequisites H2, "Step N: Gerund phrase" H2, Conclusion H2; sentence case; second person; code sandwich; Temporal primitives capitalized), each linking the previous and next parts with `TODO` placeholders, each Vale-clean (MasonBase plus MasonTechnical) and passed through `/review-content`.
  Part 1 covers install, `ptrace_scope`, `just server`, `just worker`, `just metrics`, `just healthy`, and the baseline readings including the dashboard; parts 2 to 6 follow exercises 01 to 05 and end with the reader's fix and its verification.
  The series title is "Debugging blocking calls in Temporal async Activities".
  Drafts carry no frontmatter.
- `docs/drafts/README.md` lists the six drafts, keeps the provenance note on the original draft, and keeps the venue as not yet chosen.
- README and draft prose follows the repo owner's writing rules: no em-dashes, one sentence per line in committed Markdown.
- Update CLAUDE.md to the trimmed package, the three-layer layout (root reference, exercises, observability), the solution-copy carve-out, and the current `just` recipes.
- MIT license (already present).

## Non-goals

- No lesson, exercise, or draft about slot exhaustion, Worker sizing for throughput, heartbeat or timeout tuning, schedule-to-start, or retry policy and idempotency; those are general Temporal topics covered elsewhere.
- No detection library, watchdog, linter, or any maintained tooling; diagnosis uses read-only introspection the reader runs (native `asyncio ps` / `pstree`, `py-spy dump`, asyncio debug mode) and the Prometheus and Grafana stack, never tooling this repo builds or ships.
- No Flask or web front end; the Temporal Web UI, the metrics endpoint, and the Grafana dashboard are the visual layer.
- No CI beyond the canonical application CI workflow (single pinned Python 3.14, `just check`, pip-audit, dependabot); CI does not start containers, run the dev server, or take captures.
- No Temporal server in a container, no self-hosted cluster, and no Temporal Cloud; `temporal server start-dev` is the only server.
- No log shipping or tracing (Loki, OpenTelemetry); the stack is metrics only.
- No `fixed` modes, flags, or patch files in the root package; the fixed code lives only in `solution/` copies.
- No support for Python older than 3.14.
- No lab mode in this arc (see the Deferred list under Roadmap / phase log).

## Component boundaries

- Root trim (`src/temporal_async_debug/`, `tests/`, `justfile`): input is the catalog package; output is the frozen-loop reference with `block` and `cpu` only, its tests green.
- Exercise copies (`exercises/<NN-name>/{practice,solution}/`): input is the trimmed root package; output is a standalone flat copy carrying that exercise's bug, with `TODO PART X` markers in `practice/` and the fix in `solution/`.
  Owns its own `tests/`.
  Depends on nothing outside the root virtual environment.
- Exercise READMEs (`exercises/<NN-name>/README.md`): input is the exercise's captures; output is the 102-structure instructions.
  Depends on the captures existing.
- Observability stack (`observability/`): input is the two metrics endpoints; output is a provisioned dashboard.
  Owns the compose file, scrape config, provisioning, and dashboard JSON, plus their config tests.
  Depends on `just server` exposing port 9465.
- Captures (scratchpad during the build, trimmed into the READMEs, drafts, and `docs/images/`): input is the trimmed root package's three scenarios and each copy's before and after runs with the stack up; output is the quoted blocks and screenshots, with the trims disclosed in the root README's "About the captured output" section.
  Depends on the exercise copies and the stack.
- Tutorial drafts (`docs/drafts/part-N-*.md`): input is the exercise READMEs and the captures; output is the six drafts and the Vale and copy-editor passes.
  Depends on every capture and README being final.
- Root docs (`README.md`, `CLAUDE.md`, `docs/drafts/README.md`): input is the trimmed package, the finished layout, and the root captures; output is the three-lesson README, the exercises table, the observability section, and the architecture refresh.
- Gate (`justfile`, `pyproject.toml`): input is the solution copies and config files; output is `just check` covering them and `just check-practice` covering the practice copies lightly.

## Success criteria

- `just check` is green with the solution-copy loop and the observability config tests included, and `just check-practice` is green.
- `grep -rn "slow_heartbeat\|stuck_no_heartbeat\|PriceQuote\|maximum_attempts" src tests justfile` returns nothing.
- Each exercise runs from its own directory: the `practice/` copy reproduces its failure, and the `solution/` copy produces its after-state, both captured and quoted.
- `just metrics` brings up the dashboard on a machine with `docker-compose` v1, with both scrape targets up and every panel populated during a scenario.
- Five exercise READMEs and six tutorial drafts exist, quote only captures of their own exercise, pass Vale, and have been through `/review-content`.
- The root README has exactly three lessons, all recaptured; the README and CLAUDE.md describe the three-layer layout; and `grep -rn "ANTIPATTERN (deliberate, for teaching)" exercises/*/solution` returns nothing.
- The arc ships as commits on the `scaffold` branch (PR #4 against `main`), with a session summary per commit.
