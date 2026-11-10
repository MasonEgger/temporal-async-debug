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
`exercises/` holds six hands-on exercises in the Temporal 101/102 course layout (a `README.md`, a `practice/` copy with the bug, a `solution/` copy with the fix), five of them one per common way developers block the loop and the sixth on finding the frozen Worker in a fleet, so the reader observes the failure, finds it with the tooling, fixes the code, and verifies the fix.
Exercises 01 to 05 run one Worker with two Activity slots, so one blocking call fails loudly, where the reader can see the mechanism; exercise 06 runs the same kind of bug under steady traffic on two Workers at the SDK's default slot counts, where the second Worker masks most of the damage.
`observability/` holds a Prometheus and Grafana stack that graphs the SDK and dev-server metrics over time, so the effect of a frozen loop is visible as it happens instead of only as one-off `curl` readings.
The repo is the companion to a seven-part tutorial series, "Debugging blocking calls in Temporal async Activities" (part 1 is the setup and healthy baseline, parts 2 to 7 are the six exercises); the publication venue is not yet chosen.
It is a teaching artifact, not a maintained tool, and will never be published to PyPI.
The code is built to teach one mechanism, so parts of it are simplified or altered to make a point, and it is not a template for a production system.

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

The fleet-localization phase (decided November 9, 2026) closes a gap found by checking this work against field evidence.
Every capture here runs one Worker whose PID the banner prints, so the reader never has to work out which process to attach `asyncio ps` or `py-spy` to, while in a production fleet the first job is finding which Worker froze.
After the gap analysis the owner approved a sketch of the fix ("Yes, sketch it") and then had it written into this spec.

The owner then asked for a review of field evidence "so we can make sure these exercises _actually_ reflect what customers are experiencing" (November 9, 2026); the research notes stay outside the repository.
The research found about 50 cases and confirmed the mechanism and the cross-type blast radius in every source.
A synchronous client inside `async def` (LLM SDKs, cloud SDKs, database drivers and ORMs, message producers, in-house packages) was the most common blocker by a wide margin, then CPU-bound work and GIL contention, then logging locks and telemetry export; `time.sleep` appeared once.
The field symptoms were Workflow Task timeouts in nearly every case, `TMPRL1101` on Workflow code that was fine, Workers that stopped picking up work while the process stayed alive, the Worker log line "Task not found when completing", and Activities marked Started minutes before their code ran.
Field diagnosis ran on a code question ("are these `async def`, and what do they call?"), code reading, bisecting from a sample, local reproduction, profiling, and matching failures to one host; asyncio debug mode was suggested and never reported as used, py-spy appeared once, and missing SDK metrics stalled several cases.
Every source independently flagged finding the frozen Worker in a fleet as the missing skill, and the owner ruled it gets its own exercise ("Own exercise") rather than a step inside 01.

The owner then ruled on the review's open items (November 9, 2026): the exercises keep their numbering, one shared recognition block is written once and linked from each exercise's Part B, four fold-ins land in exercises 01, 02, and 03 and in the primer, and the production loop-lag canary is deferred.
On `TMPRL1101`, in the owner's words: "I don't think we need to lead with TMPRL1101 but if it's related we 100% need to mention it somewhere."
A scratch spike of the two-Worker `sqlite3` design ran the same day (five freeze runs and one healthy run) and replaced the capture assumptions with results; see Exercise requirements.

That spike also showed that a second Worker turns the loud failure of exercises 01 to 05 into a partial stall, and the owner ruled on the single-Worker shape the same day (November 9, 2026).
In the owner's words: "I think it's totally reasonable to leave single worker for the beginning, then in the final exercise show a real world scenario where the results are hard to figure out."
On how the final exercise opens: "Now if everything in the real world crashed this easy, that would be great. But it doesn't, there are more workers. These errors can mask".
On the code, the owner pointed to the note that the Temporal 101 and 102 course material carries: "this code is for teaching purposes, so things may be incorrect or altered to demonstrate a point".
On the tooling: "We also need to make sure our tools/suggestions work in a multi-worker environment and still give us the results we expect."
On scale: "If we are having issues with placement, just run more exercises. If we need more size to show the issues, flood it.", and "if we need a flood or tsunami to see this at 06 let's architect that out. Because in reality, an issue that only happens at that scale is all the more damaging for customers."
Three more scratch spikes ran that day, and their results are under Architecture and Exercise requirements.
The first checked every tool the series teaches against two Workers, at eight receipts and under a flood.
The second was a design matrix for exercise 06's flood: bursts and steady traffic, two and four Workers, two and 100 Activity slots, ending in six freeze runs and one healthy run of the chosen design.
The third ran exercise 03's solution copy eight times on one and two Workers to settle the second-Worker step.
On November 10, 2026 a check of this spec against the saved spike output found 13 figures that did not match it, three claims with no saved output behind them, and four that the saved output could not settle.
This revision corrects them in place, and a claim with no saved output now says so.
The owner ruled on four points the same day.
The spec correction came first; then the fleet checks that had never run (the dashboard and the Web UI with two Workers, `scripts/receipt_gaps.py` on a fleet's histories, and the after-fix flood) ran as scratch spikes on November 10, 2026, with a second pass at exercise 03's placement.
Their results are under Architecture and Exercise requirements, and the builder reports them to the owner before writing the plan.
Exercise 02 still leads with the climbing Attempt count and names `TMPRL1101` without leading on it.
The owner reviews once, after the build.
The builder decides the open questions left from the earlier arcs and lists each choice in one pull request comment, where the owner can overrule any of them.

## Invariants

Rules that hold across every phase of this repo.

- paths: src/temporal_async_debug/**, tests/**, exercises/**, observability/**, docs/**, justfile, pyproject.toml, README.md, CLAUDE.md, .vale.ini, .github/workflows/ci.yml, spec.md, todo.md, plan.md, .ai-sessions/**, scripts/**
- Python 3.14+ only; toolchain is uv + ruff + mypy (strict) + pytest, run through `just`; src layout with the hatchling build backend.
- Temporal Python SDK (temporalio) is the only workflow engine; no second orchestration framework.
- The Temporal server is always `temporal server start-dev` (the single-binary CLI); never a self-hosted cluster, never a Temporal server container, never Temporal Cloud. The compose stack under `observability/` holds Prometheus and Grafana and nothing else, and stays `docker-compose` v1 compatible.
- Python: per the python:python skill (strict typing, Google docstrings, no single-letter names, canonical ruff/mypy/pytest config verbatim).
- Prose (README, CLAUDE.md, exercise READMEs, tutorial drafts, comments, commit messages): per the writing hard rules (no em-dash or en-dash, no banned AI-tell vocabulary, straight quotes, one sentence per line in committed Markdown).
- Privacy: the repository is public, so no committed file or commit message names a customer, a real or invented company, a namespace, a ticket number, or a specific field use case; none names an internal system, an internal document, or internal training or course material (course codes and runbooks included); research evidence is summarized only in aggregate (blocker categories, symptoms, counts), without saying where it was gathered.
- Scope: every lesson, exercise, and draft is about blocking the shared asyncio event loop. No slot-exhaustion, heartbeat-tuning, timeout-tuning, or retry-policy lesson, even as a contrast case.
- Every exercise's bug is an execution failure the reader sees without a dashboard (bystanders fail, attempts fail and retry, the same work runs twice, a bystander is visibly delayed on every run), diagnosed with the Python tooling the reader runs (`asyncio ps`, `pstree`, `py-spy dump`, the CPU reading, asyncio debug mode). A metrics blip alone is not a bug; Grafana corroborates and never teaches. Exercise 05 is the one detection lesson and the only exercise that misbehaves without failing; exercise 06 adds one step before that tooling, because the Event Histories name which process to attach to.
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
- fleet-localization: teach the skill a production reader needs before any process tooling, finding which Worker in a fleet froze, from the Worker identity in Event Histories.
  A new exercise, 06-finding-the-frozen-worker, runs steady receipt traffic on two Workers at the SDK's default slot counts with a synchronous `sqlite3` lookup blocking one of them, so a few percent of the receipts fail and the rest mostly hide it.
  `scripts/receipt_gaps.py` gains an opt-in identity view, Prometheus gains a third scrape target and the dashboard a per-Worker panel, and a seventh draft carries the exercise plus a short note on production fleets.
  Builds on event-loop-exercises (see the fleet-localization items under Architecture, Exercise requirements, Observability requirements, Test requirements, and Documentation requirements below).
  The phase also carries the rulings of November 9, 2026: the shared recognition block, the fold-ins in exercises 01, 02, and 03 and in the event loop primer, the teaching-code note in the root README, and the single-Worker sentence in exercises 01 to 05.

**Deferred:** (a lab mode turning the demo into a whodunit; decisions recorded September 2026, build deferred until after the tutorial publishes)

- Fleet generator (`just generate N`): writes real per-workflow source files so every generated activity has its own file and line and stack traces stay genuine clues at any scale. Trigger: scaling past the hand-written workflow types.
- Seeded culprit selection: a `--seed` picks which generated activity misbehaves and how without announcing it; a `reveal` command checks the learner's answer. Trigger: the lab build.
- FastAPI game-master app (async, fully typed): starts and stops scenarios, shows a live fleet status board and symptom feed, and accepts the learner's guess for the reveal flow. Trigger: the lab build; the tutorial-facing v1 stays CLI plus Temporal UI plus metrics.
- Intermittent and load-dependent blockers (a call that only blocks under concurrency, or every Nth call): candidates for the lab, not this arc.

**Deferred:** (adjacent to the exercises phase; sorted October 31, 2026, revised November 2, 2026)

- Alert rules or Alertmanager on the dashboard. Trigger: a reader asks for paging, not graphs.
- A `ProcessPoolExecutor` plus `SharedStateManager` exercise for CPU-bound work. Trigger: demand; the cpu exercise names it in prose and Temporal's docs discourage it.
- A blocking-call-in-Workflow-code exercise (the sandbox and deadlock detector are a separate mechanism). Trigger: an eighth part after the series publishes.
- Codespaces or devcontainer setup like the 102 repo. Trigger: the series is taught live.
- A committed capture script under `scripts/` that reproduces whole before-and-after runs and their disclosed trims. Trigger: the captures need re-taking after a dependency bump.
  The small receipt-gap helper `scripts/receipt_gaps.py` (stdlib only) ships now so readers can reproduce every gap figure.
  This read-only helper is not part of the deferred script.
- Temporal Web UI screenshots beyond exercise 02. Trigger: a venue that prefers screenshots to CLI output; the tool story is CLI plus Grafana, with exercise 02's pending-activity screenshots as the one exception.
- Publication venue and frontmatter for the drafts. Trigger: the venue decision; drafts carry no frontmatter and `TODO` cross-links until then.

**Deferred:** (adjacent to the fleet-localization phase; sorted November 9, 2026)

- A registration guard: a short CI test that fails when any Activity registered on the Worker is `async def`, answering a recurring field question and following Temporal's default-to-`def` guidance. Trigger: the owner's ruling after the fleet-localization research; it would sit beside exercise 05's probe test, which already filters registered Activities with `inspect.iscoroutinefunction`.
- A blocking payload codec or data converter as a way to freeze the loop, named in field guidance but never confirmed as a root cause. Trigger: a confirmed field case, or an eighth part after the series publishes.
- A flood on more than two Workers or faster than 10 receipts per second. Trigger: a capture machine that holds a flat healthy baseline at that load; on the spike machine 30 receipts per second overloaded the run, and four Workers at 10 per second cut the failures to 11 of 512, so two Workers at 10 per second is the shape exercise 06 ships.
- A production loop-lag canary: a background task that measures how late the loop wakes it and exports the lag, the production counterpart to exercise 05's CI probe (one team in the field evidence built its own). Trigger: the owner lifts the Non-goal against shipping a watchdog or maintained tooling, or a part after the series publishes covers production monitoring; until then exercise 05 keeps the probe test and asyncio debug mode (owner ruling, November 9, 2026).

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
- The most likely trip-ups, not a taxonomy.
  The exercises are mistakes Temporal users actually report, and exercise 01 is the most common of them by a wide margin.
  The numbering after 01 is a teaching order, not a frequency ranking: field evidence puts CPU-bound work second and a blocking sleep between heartbeats far below it, and the owner ruled against reordering (November 9, 2026).
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
- Loud first, then realistic.
  Exercises 01 to 05 run one Worker with two Activity slots, so a single blocking call fails where the reader can see it.
  Exercise 06 puts the same kind of bug in a two-Worker fleet under steady traffic, where it is partly masked, because that is how it arrives in production.
  The simplification is stated to the reader, never hidden.

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
- `worker.py`: registration drops the quote; `max_concurrent_activities=2` stays so the slot gauge readings in the freeze lessons stay small and readable, but it loses its antipattern marker and carries a plain comment saying it is small on purpose (decision: kept, confirmed against the live captures).
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
  06-finding-the-frozen-worker/ README.md  practice/  solution/
```

Each `practice/` and `solution/` directory is a flat, standalone copy in the 102 shape: `shared.py`, `activities.py`, `workflow.py`, `receipt.py`, `rollup.py`, `worker.py`, `starter.py`, and `tests/`, plus any file named for that exercise below.
It runs from its own directory with `uv run python worker.py` and `uv run python starter.py ...`, using the root project's virtual environment (the root `pyproject.toml` is the only one; copies are scripts, not packages).
A copy replaces the root's `block`/`cpu` switch with its exercise's bug and keeps the bystander fleet (receipts and rollups).
Exercises 01 to 05 keep the starter's freeze ordering, one Worker, and the root's `max_concurrent_activities=2`, so one blocking call takes the whole fleet down and the blast radius is visible the same way in each.
That shape is a teaching choice, and each of those READMEs says so in one sentence (see Documentation requirements); exercise 06 swaps it for steady traffic on two Workers at the SDK's default slot counts.
`practice/` keeps the antipattern marker for its bug and adds `# TODO PART X:` comments at every line the README asks the reader to change, including a `TODO` test stub in `tests/`.
`solution/` is the completed copy: no antipattern, no marker, the reader's test implemented and green.

The six exercises, in teaching order (the Design principles say why the order is not a frequency ranking):

- 01-sync-http-client: `get_location` is an `async def` Activity that calls a synchronous HTTP client (`httpx.Client`, standing in for `requests`).
  Healthy runs hit the real geo providers and finish fast, so the bug hides; the bad run's input points the provider at a local slow endpoint that answers after the configured delay.
  The slow endpoint is a stdlib `http.server` the starter serves on 127.0.0.1 for the duration of the run (decision: served by the starter so the reader needs no extra terminal), in `slow_upstream.py`.
  The fix: `get_ip` and `get_location` become plain `def` Activities on the same sync client, and `worker.py` passes `activity_executor=ThreadPoolExecutor(max_workers=...)` sized to `max_concurrent_activities`.
  Part C ends with a "same bug, other library" table, because a reader's own blocker is rarely an HTTP client: one row per category the field evidence names (database drivers and ORMs, cloud SDKs, LLM SDKs, message producers that flush synchronously), each with the synchronous call shape to look for.
  Decision: every row is a blocking call on the event loop with the diagnosis and fix this exercise teaches, so the table stays inside the one-mechanism invariant; no row gets a capture or an exercise of its own (confirm at review).
  Decision: a row names a category and a call shape, and a Python package only where the package name is not also a company name; the LLM row stays generic (confirm at review).
  Part D, where the executor is introduced, states that `activity_executor` runs only `def` Activities: an `async def` Activity always runs on the event loop, so a thread pool passed to a Worker whose Activities are all `async def` runs nothing, however large it is.
  The event loop primer carries the same point in one sentence under "Getting blocking work off the loop".
- 02-sleep-between-heartbeats: `get_location` is an `async def` Activity that polls a slow job in a loop, with a `heartbeat_timeout` on the call.
  Each poll starts with an awaited async status check (a real `await`, so the loop is live for an instant), then calls `activity.heartbeat()` and a blocking `time.sleep(poll_interval)`.
  The heartbeat is recorded but the loop never runs to send it, so the server fails the attempt with a `Heartbeat` timeout while the Worker keeps running the Activity, because asyncio cancellation cannot interrupt `time.sleep`.
  The poll interval is longer than the fixed `heartbeat_timeout` (decision, proved by a scratch spike: `heartbeat_timeout` 5 seconds, poll interval 8 seconds, a job of 60 seconds keyed on the workflow run id so a retry observes the same job), so what the reader sees is a retry storm.
  The default retry policy starts the next attempt while the failed one is still polling, the `Attempt` counter climbs past 2 in the Web UI's pending-activity view and in `temporal workflow describe`, every attempt fails on `Heartbeat` timeout, and cancels land late so failed attempts keep polling as overlapping zombies.
  The in-flight rollup fails and the receipts stall; the run completes after about 65 seconds.
  The Worker log printed `TMPRL1101 Potential deadlock detected` on one failed Workflow Task in each of the four capture runs, but the line depends on timing, so the README says a reader's run may not show it.
  Temporal writes no history event per retried Activity attempt, so `temporal workflow show` does not list attempt after attempt.
  The storm shows in the Web UI pending-activity view, in `temporal workflow describe`, in the Worker log, and in the dashboard's `activity_timeout` panel.
  The README calls out `TMPRL1101` as a frozen-loop clue: on an `async def` Worker it can mean the event loop is blocked, not that the Workflow code deadlocked.
  Where Part C reads the heartbeat call, the README sharpens one sentence: calling `activity.heartbeat()` is not sending a heartbeat, because the call only records it and the loop has to run before it is sent, so a heartbeat in the code is no proof that the server received one.
  Decision: the retry storm and the exercise's opening stay as they are, and `TMPRL1101` is not the lead; the shared recognition block names it and points here (owner ruling, November 9, 2026; reconfirmed November 10, 2026 against the corrected count of four of four capture runs).
  The fix: wait in awaited 1-second ticks with a heartbeat on every tick (`activity.heartbeat()` then `await asyncio.sleep(1)` until the next poll is due), so heartbeats flush on the loop more often than the timeout and cancellation lands at the await (decision: the awaited tick loop replaces the blocking `time.sleep`, which would still go 8 seconds without a heartbeat under a 5-second timeout; the Activity stays `async` and the `def` route is named in prose).
- 03-cpu-bound: `get_location` does pure-Python computation inside `async def` (the root `cpu` busy loop, recast as a realistic transform of the provider response), holding the GIL and pinning CPU at 100 percent.
  The fix has two required steps.
  The first is the `def` plus executor change from 01: the work runs on a pool thread and the loop stays live, while `top` still shows the process near 100 percent.
  The README says what that step leaves unsolved: the pool thread still holds the GIL while it computes, so the loop is free but the process gains no CPU parallelism.
  The second step shows the GIL as the limit and then lifts it with a second Worker process.
  On one Worker, `--bad 2` runs two CPU-bound `get_location` calls on two pool threads that share one GIL: in the spike one process read 60 to 100 percent CPU and each run took 59 to 60 seconds, about twice the 27 to 31 seconds a run takes with a GIL to itself.
  With a second Worker started, `--bad 4` fills all four Activity slots, two per Worker: in three spike invocations both processes read mostly 90 to 100 percent CPU, and each run took about 65 to 67 seconds (64.82 to 67.35).
  The spike printed two `get_location` calls per identity in all three, but that printout was not saved.
  A rerun on November 10, 2026 saved it: two invocations of `--bad 4`, each with two `get_location` calls per identity, every one completing on its first attempt.
  Those runs took 91.0 to 93.7 seconds each on a busier machine (a load average of 6.8 on four cores), and the build's capture records its own placement and timing.
  Two processes did twice the hashing in well under twice the wall time, because each has its own GIL.
  Four runs on two Workers took about 1.1 times as long as two runs on one Worker on November 9, and 1.3 to 1.4 times as long on the busier machine on November 10.
  Decision: the two-Worker step runs four bad runs, not two, because the placement of two runs across two Workers varies (both on one Worker in the earlier README capture and in two saved invocations on November 10, 2026, at 67.5 and 71.6 seconds a run; in four spike invocations on November 9 the durations of 27.04 to 30.52 seconds fit one per Worker, though the identity printout was not saved), and four runs fill every slot whatever the placement (owner ruling, November 9, 2026, on placement trouble: run more).
  Decision: the single-Worker step never runs `--bad 4`, because the third and fourth runs would wait for a slot and finish close to the 150-second `schedule_to_close` (an estimate of about 120 seconds or more, twice the 59 to 60 seconds two runs took; not run).
  Decision: the second Worker is a step of the main fix path, no longer an optional section, because field evidence shows that moving CPU-bound work to threads alone falls short (owner ruling, November 9, 2026).
  Decision: the step is framed as GIL isolation (one GIL per process) and never as sizing a fleet for throughput, which stays a Non-goal (confirm the framing at review).
  The second Worker needs its own Prometheus port, so `worker.py` in both copies reads an `ASYNC_DEBUG_METRICS_PORT` environment variable (default 9464) and the step runs from the repository.
- 04-zombie-thread: the practice copy carries the fix many users ship first, and it looks right: `get_location` stays `async def` and wraps the blocking call in `asyncio.to_thread(...)`, with a `heartbeat_timeout` and no heartbeat.
  The loop stays live, so the bystanders are fine, but when the server times the attempt out the coroutine is cancelled and the thread keeps running, so the work finishes after the Activity has already failed and the retry runs the same work again beside it: the Activity runs twice.
  Part A also walks through the two startup traps on the way to the real fix: a `def` Activity registered without an `activity_executor` fails at Worker construction, and an executor smaller than `max_concurrent_activities` logs the SDK's warning; both messages are captured.
  The fix: a `def` Activity on a `ThreadPoolExecutor` sized to `max_concurrent_activities` that heartbeats from its own thread, so a timeout or cancel arrives as `CancelledError` inside the thread and the work stops.
- 05-catching-blockers-early: the practice copy has a short blocker that ships unnoticed, one `zlib.compress` at level 9 over generated audit-log lines in an `async def` Activity, taking about 350 ms on the capture machine.
  The records are seeded, realistic JSON-lines audit entries built inside the Worker, so only `str` and `int` cross Temporal boundaries and `get_location(ip: str, payload_records: int) -> str` keeps its signature.
  `zlib.compress` is the blocker because it releases the GIL: after the `asyncio.to_thread` fix the loop and the receipts recover, where a pure-Python JSON blocker kept receipts slow through GIL contention.
  The README notes that a real archiver uploads the compressed bytes to blob storage and returns a key, never the blob.
  Nothing times out, but every run stalls the loop for that long, and every bystander dispatched into the stall waits it out.
  The symptom is the receipts' first Workflow Task gap, from `WorkflowTaskStarted` to `WorkflowTaskCompleted` in `temporal workflow show`: 298 to 394 ms in the captures where the healthy fleet shows 19 to 23 ms.
  This is the one detection lesson in the series and the only exercise that misbehaves without failing.
  Part A runs the healthy fleet and then this one and compares the receipt timings; Part B runs the Worker with asyncio debug mode, captures the slow-callback warning, which names the SDK handler `_ActivityWorker._handle_start_activity_task` rather than `get_location`, and confirms the line with `py-spy`; Part C moves the work off the loop; Part D adds the starvation-probe test over every registered `async def` Activity as the regression guard that would have caught it in CI.
- 06-finding-the-frozen-worker (fleet-localization phase): the real-world shape of the bug the first five exercises teach.
  Exercises 01 to 05 run one Worker with two Activity slots, so one blocking call fails loudly.
  A production fleet has more Workers and far more slots, the healthy Workers absorb most of the work, and the same frozen loop shows up as a few percent of failed Workflows and a band of slow ones.
  The exercise runs steady receipt traffic on two Workers on the one Task Queue, and the reader has to find the frozen Worker from the Event Histories before attaching any process tool, because a production fleet does not hand over the PID that the single Worker's banner prints in exercises 01 to 05.
  Decision: the 06 README opens with that contrast, in the owner's framing (a failure this easy to see would be welcome in production, but more Workers mask it), and exercises 01 to 05 point forward to it (owner ruling, November 9, 2026).
  Decision: this is its own exercise, not a step inside 01, because localization is a distinct skill (reading a partial stall across a fleet and grouping it by Worker identity) that field evidence showed readers need, and folding it into 01 would make 01 carry two lessons (owner ruling, November 9, 2026).
  Decision: the exercise is numbered 06 and appended after 05, so no existing directory, README, or draft is renumbered, and the series is not reordered by field frequency (owner ruling, November 9, 2026).
  The bug: `get_location` is an `async def` Activity that looks up a cached location through the standard library's `sqlite3` driver, a synchronous database call, and the bad run's input makes that lookup wait on a database lock the starter holds for the configured delay.
  Decision: `sqlite3` is the blocker because synchronous database drivers are a common blocker in the field, it adds no dependency, and a lock wait gives the idle-CPU freeze of a call that waits rather than computes.
  Two scratch spikes shaped the design before the plan was written (November 9, 2026).
  The first ran five freeze runs and one healthy run of eight receipts on two Workers with two Activity slots each: the lock wait froze only the Worker that ran the bad run's `get_location`, for 29.4 to 30.0 seconds against a 30-second delay, both Workers read state `S` at all 76 samples and 0.0 percent CPU at 74 of them (the healthy Worker read 10.0 and 9.1 percent once each), and every Workflow completed.
  Nothing failed at that scale, so the second spike varied the load and the slot counts and settled the flood described below; its matrix is under Exercise requirements.
  Which Worker freezes changes from run to run (the second Worker in three of the small runs and the first in two, and it varied across the flood runs as well), so the README never names one in advance.
  The lock lives in `db_lock.py`: a holder thread in the starter opens a temporary database file in rollback-journal mode and holds a `BEGIN EXCLUSIVE` transaction, and `get_location` connects with a `timeout` longer than the hold, so its `SELECT` waits where a shorter timeout would raise `database is locked`.
  Decision: the hold is counted from the moment the starter submits the bad run, so the freeze is a little shorter than `--block-seconds` (confirm at review).
  Decision: `get_ip` keeps the root package's async client, so the `sqlite3` lookup is the copy's only blocker; the spike was built on the 01 practice copy, whose synchronous client blocks the loop for the length of its HTTP call on every run, healthy ones included, and the 06 copy must carry one blocker only (confirm at review).
  No figure is quoted for that delay, because the spike saved the healthy run's results and not its history timings.
  The lock lives only for the bad run, so healthy runs on either Worker finish fast and the bug hides in development, the same "it worked in dev" shape as 01.
  `worker.py` in both copies reads `ASYNC_DEBUG_METRICS_PORT` exactly as exercise 03's does (default 9464), and the second Worker starts with `ASYNC_DEBUG_METRICS_PORT=9466 uv run python worker.py` from the same directory.
  Prometheus scrapes both Workers: `observability/prometheus.yml` gains 127.0.0.1:9466 as a third target (see Observability).
  Decision: the 06 copies run the SDK's default slot counts, 100 Activity slots and 100 Workflow Task slots in temporalio 1.33.0, in place of the root's `max_concurrent_activities=2` (confirm at review).
  The setting of 2 exists only to keep a single Worker's readings short, a real Worker runs the defaults, and the spike needed them: with two Activity slots no receipt failed at any burst size (no steady two-slot run was made), and with the defaults a few percent failed in each of the six steady freeze runs.
  The practice copy passes no `max_concurrent_activities`.
  The solution copy sets its constant to 100, the SDK default, with a plain comment, so its `ThreadPoolExecutor` is sized to it.
  Decision: the 06 starter is a flood, not the freeze ordering (owner ruling, November 9, 2026: "If we need more size to show the issues, flood it."; confirm the shape and the defaults at review).
  It submits receipts at a steady rate for the whole run: `--rate` receipts per second (default 10), for `--lead` seconds before the bad run (default 10), through the freeze of `--block-seconds` (default 30), and for `--tail` seconds after the bad run returns (default 10), about 500 receipts in all.
  After the lead it submits `--rollups` rollups (default 1), waits 1 second, submits `--bad` bad runs (default 1), and waits until the server reports the bad run's `get_location` STARTED.
  That moment is the confirmed freeze, the zero point of the starter's timeline.
  `--bad 0` is the healthy flood: the same stream for the same length with no lock held.
  Decision: steady traffic, not a burst.
  At the default slot counts a burst's result swung with its size: 1 of 8 receipts failed, then 27 of 100, then 0 of 500.
  The burst of 500 overloaded the healthy Worker and hid the effect (nothing failed while the median receipt took 14.0 seconds).
  Ten receipts per second held a flat baseline on the spike machine (healthy flood median 0.36 to 0.38 seconds).
  The only faster run, four Workers at 30 per second, was overloaded before its freeze began (median 32.9 seconds), so no rate above 10 was shown to hold.
  Decision: the healthy flood is the rate check.
  If its slowest receipt takes longer than about 1 second, the reader lowers `--rate` before running the bad flood, and the README says so (confirm at review).
  Decision: the starter prints a closing summary in place of a line per Workflow.
  The summary holds the receipts submitted, how many failed, the first failure's message, the outcome of the rollup and of the bad run, and a timeline by submit time relative to the confirmed freeze, in 5-second buckets with the count, the failed count, the count slower than 2 seconds, and the median and slowest latency for each.
  The flood plan (when each receipt is due, for a rate and a duration) and the summary (the bucketing and the counts, from a list of results) are pure functions, so both are unit tested without a server.
  Decision: the exercise's recipe runs one rollup (confirm at review).
  The rollup failed in two of the six flood freeze runs and completed in the other four, so the README promises neither outcome.
  Decision: the flood has one gate, the server-side check that the bad run's `get_location` has STARTED, which the freeze ordering already uses (confirm at review).
  The inherited bystander gate scrapes port 9464 for a busy Activity slot, and with two Workers it fails open: in one small spike run it waited its full 20 seconds and printed its warning, because the rollup's Activity ran on the other Worker (a second run also waited it out, but that run submitted no rollup, so it says nothing about the gate).
  The flood drops that gate, since its receipts are already in flight when the freeze lands.
  Part A runs the healthy flood and then the bad flood on the two-Worker fleet, and reads the result as an operator meets it: most receipts are fast, a few percent fail with an Activity timeout, a band of receipts submitted around the freeze finishes late, the fleet looks clean again while one Worker is still frozen, and both Workers are still listed among the Task Queue's pollers.
  Part B localizes the freeze with `just receipt-gaps --by-identity --summary`: one identity holds every Workflow Task timeout and every failed Activity.
  The frozen Worker is the identity on the `WorkflowTaskStarted` before each `WorkflowTaskTimedOut`, on the `ActivityTaskStarted` of each timed-out receipt Activity, and on the bad run's `ActivityTaskStarted` for `get_location`.
  The reader takes the PID from that identity (`PID@host`), and only then attaches `asyncio ps` and `py-spy dump` to that process, while the other Worker's `asyncio ps` shows no task dead-ended.
  Part B also reads the two Worker logs: the frozen Worker prints its "Task not found when completing" warnings together at the thaw, and the other Worker prints none.
  Part B then checks the tools from the earlier exercises against the fleet (see "The tools in a fleet" under Exercise requirements) and ends with a short note on production fleets (see Documentation requirements).
  Part C finds the `sqlite3` call; Part D writes the probe test and applies the 01 fix (`def` Activities on a sized `ThreadPoolExecutor`); Part E re-runs the bad flood on the two-Worker fleet and reads the summary and the per-identity view again.

### Observability

```text
observability/
  docker-compose.yml         Prometheus and Grafana only, docker-compose v1 syntax, host networking on Linux
  prometheus.yml             scrapes 127.0.0.1:9464 (SDK), 127.0.0.1:9465 (dev server), and 127.0.0.1:9466 (a second Worker, when one runs)
  grafana/provisioning/      datasource (Prometheus) and dashboard provider
  grafana/dashboards/        one provisioned dashboard JSON
```

`just server` becomes `temporal server start-dev --metrics-port 9465` (decision: 9465 sits next to the SDK's 9464 and collides with nothing the demo uses).
`just metrics` runs `docker-compose -f observability/docker-compose.yml up -d`; `just metrics-down` tears it down.
Grafana serves on `localhost:3000` with anonymous viewer access and the dashboard provisioned at startup; Prometheus serves on `localhost:9090`.
The dashboard shows what a frozen loop does to the Worker over time: `temporal_activity_execution_latency`, `temporal_workflow_task_schedule_to_start_latency` and `temporal_workflow_task_execution_latency` (workflow tasks stall during a freeze), activity and workflow task failures and timeouts, `temporal_worker_task_slots_used` by `worker_type`, and the dev server's Task Queue backlog (metric names confirmed against the live `/metrics` output during the build; a panel whose metric the SDK or `start-dev` does not export is dropped and the README says so).
Fleet-localization phase: Prometheus gains a third scrape target, 127.0.0.1:9466, the port the second Worker takes in exercises 03 and 06, and the dashboard gains one per-Worker panel, `temporal_worker_task_slots_used{worker_type="WorkflowWorker", task_queue="async-debug-task-queue"}`, one line per Prometheus `instance`.
Decision: the panel's query carries the Task Queue filter, because without it the query also returns six all-zero series from the dev server's own system Workers on 127.0.0.1:9465 (checked on November 10, 2026; confirm at review).
Decision: the third target is always configured and reads as down whenever no second Worker runs, which is harmless in exercises 01, 02, 04, and 05; any README that shows the Prometheus targets page says so (confirm at review).
Decision: the per-Worker view moves out of Deferred and into this phase, because the owner asked that the series' tools be checked in a fleet and which Worker freezes varies by run, so a dashboard that scrapes one Worker shows the freeze only when that Worker is the frozen one (confirm at review).
The panel corroborates the histories and does not replace them.
In the flood spike the frozen Worker's line climbed (31 of 100 Workflow Task slots in use 4 seconds into the freeze in one run, 95 of 100 later in another) while the healthy Worker's stayed low (its highest sampled reading was 3 to 6 across five freeze runs, against 95 or 96 on the frozen Worker), and the `ActivityWorker` gauge did not separate the two Workers (at most 2 in use on the frozen one, and up to 3 on the healthy one).
In the fleet check of November 10, 2026, read from Prometheus at a 5-second step, the frozen Worker's line read 2, 5, 31, 59, 95, 95, 95, and then 1 after the thaw, and the healthy Worker's peaked at 5.
The README words the panel as Workflow Tasks handed to a Worker that cannot complete them, and draws no slot-sizing lesson from it.
Decision: the existing panel expressions stay as they are.
The slots panel sums across Workers by `worker_type`, and the latency panels divide rates per series, so with two Workers scraped they draw one line per Worker; the 06 README says how each panel reads with two Workers, from its capture.
In the fleet check of November 10, 2026 the existing panels read as follows.
The slots panel's `WorkflowWorker` sum climbed to 100, and it does not say which Worker holds the tasks.
The failures panel showed `ScheduleToClose` rising to 17, the count of failed receipts, with no Worker-side failure series.
The backlog panel held two samples, both 0.
The latency panels did not pick out the frozen Worker during the freeze; its Workflow Task execution line for receipts stayed near 7 ms and jumped to about 16 seconds only at the thaw.
The compose file defines exactly two services, `prometheus` and `grafana`; a test asserts that.

### Receipt-gap helper identity view (fleet-localization phase)

`scripts/receipt_gaps.py` stays stdlib-only and read-only.
Decision: the identity view is opt-in behind one flag, `--by-identity`, so the default output, which the READMEs already quote, does not change.
With the flag, each history's line also prints the Worker identity from the first `WorkflowTaskStarted`, from the `WorkflowTaskStarted` that completed WT1 when a retry moved it, and from each `ActivityTaskStarted` with its `attempt`.
It also prints the `attempt` recorded on the `WorkflowTaskScheduled` that completed WT1, because the server writes no events for the retries in between: after a `WorkflowTaskTimedOut`, the next scheduled event in history is the attempt that completed (attempt 2 or 3 in the spike).
A timeout is attributed to the identity on the `WorkflowTaskStarted` before it, since `WorkflowTaskTimedOut` carries no identity, and that holds for a later Workflow Task as well as the first (a rollup stalls this way through sticky affinity).
After the per-history lines it prints one summary line per identity: how many first Workflow Tasks it started, how many Workflow Task timeouts it holds, how many Activities failed on it, and the largest WT1.
A failed Activity is attributed to the identity on the `ActivityTaskStarted` that shares its scheduled event with the `ActivityTaskTimedOut` or `ActivityTaskFailed`.
A retried Activity's history keeps only its last attempt's `ActivityTaskStarted`, so an attempt that a frozen Worker swallowed before a retry completed elsewhere is not counted, and the README says so.
Decision: a second flag, `--summary`, used with `--by-identity`, prints the per-identity summary alone, because a flood has about 500 receipt histories and the reader needs the lines at the end (confirm at review).
The helper runs one `temporal workflow show` per history, so a flood's summary takes about 500 CLI calls; the README gives the wall time from its capture, and `--limit` bounds the run.
Decision: the helper stays sequential, because the script as it stands read a flood's 518 receipt histories in 37.7 seconds on November 10, 2026, well under the two minutes that would have called for a thread pool.
That run also showed what the default output leaves out on a fleet.
No line names an identity or marks a failure, and 13 of the 17 failed receipts' lines print no Activity at all, because the helper prints completed Activities only.
Of the 79 receipts with a Workflow Task timeout, 4 show a WT1 of 11 to 20 ms, because the timeout fell on a later Workflow Task.
Decision: with `--by-identity`, each history's line therefore also reports a timeout on any of its Workflow Tasks, with the attributed identity, and marks an Activity that timed out or failed; the default output stays unchanged (confirm at review).
`just receipt-gaps` passes the flag through unchanged.
A rollup or geo history is read the same way when its Workflow ID is named, since the helper reads any history.

### Documentation

```text
docs/
  drafts/
    README.md                         what each file is, the venue note, the provenance of the original draft
    tutorial-original-draft.md        unchanged, provenance only
    event-loop-primer.md              optional explanation page read before part 1, unnumbered
    part-1-healthy-worker.md
    part-2-sync-http-client.md
    part-3-sleep-between-heartbeats.md
    part-4-cpu-bound.md
    part-5-zombie-thread.md
    part-6-catching-blockers-early.md
    part-7-finding-the-frozen-worker.md   fleet-localization phase
    smell-reports.md                  the voice:teaching smell reports and open questions
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
  Before: the `Attempt` counter climbs past 2 in the Web UI pending-activity view and in `temporal workflow describe`, each attempt failing with a `Heartbeat` timeout (the retry storm); the Worker log keeps printing a dead attempt's poll lines after its failure (the zombie) and shows `TMPRL1101 Potential deadlock detected`; bystanders stall and the in-flight rollup fails as in 01; `py-spy dump` names the `time.sleep` line inside the poll loop; the storm ends when the job finishes and an attempt completes.
  `temporal workflow show` writes no event per retried attempt, and the README says so.
  Web UI screenshots of the bad run's pending activity at two attempt counts are committed under `docs/images/` for this exercise only.
  After: heartbeats reach the server (`temporal workflow describe` shows the last heartbeat time advancing about every 4 seconds, because the SDK throttles heartbeats sent every second to about 0.8 of the 5-second `heartbeat_timeout`), the Activity completes on its first attempt, and the bystanders complete normally.
- 03-cpu-bound.
  Before: the root `cpu` signature from this copy (frozen shape, 100 percent CPU, `py-spy` in the compute loop, the rollup failure).
  After: the fleet completes with no timeouts; the loop stays live (bystanders complete while the computation runs); `py-spy dump` shows the computation on an executor thread holding the GIL and the main thread idle; `top` still shows the process near 100 percent.
  The second-Worker step (a required step of the fix) is captured in two runs, and the README quotes its own figures.
  One Worker with `--bad 2`: one process near 100 percent CPU, and each bad run takes about twice as long as a run with a GIL to itself (59 to 60 seconds against 27 to 31 in the spike).
  Two Workers with `--bad 4`: both processes busy (mostly 90 to 100 percent CPU on November 9, and 30 to 100 percent on a busier machine on November 10), two `get_location` calls started by each identity, and each run in well under twice the time the two-run case took.
  The spikes read about 65 to 67 seconds against 59 to 60 on November 9, and 91.0 to 93.7 against 67.5 to 71.6 on November 10, so the fleet did twice the work in 1.1 to 1.4 times the wall time.
  The README states the placement with counts from its capture and does not promise an even split.
- 04-zombie-thread.
  Before: the bystanders complete (the loop is live), but the bad run's first attempt times out, the Worker log shows the thread's work still running and finishing after the server failed the attempt, and the retry's work overlaps it; `py-spy dump` shows the orphaned thread still inside the blocker after the failure.
  The two startup traps are captured verbatim: the error from a `def` Activity with no `activity_executor`, and the warning from an executor smaller than `max_concurrent_activities`.
  After: a forced timeout or cancel stops the work inside the thread (the Worker log shows the `CancelledError` and no work after it), and no attempt's work overlaps another's.
- 05-catching-blockers-early.
  Before: every run completes and nothing times out, yet the receipts' first Workflow Task takes 298 to 394 ms where the healthy fleet takes 19 to 23 ms (the stall, read in `temporal workflow show`), asyncio debug mode logs a slow-callback warning at a few hundred milliseconds per run that names `_ActivityWorker._handle_start_activity_task`, and `py-spy` names the `zlib.compress` line.
  After: the receipts' first Workflow Task returns to milliseconds, debug mode logs no slow callback, and the probe test passes over every `async def` Activity in the copy.
- 06-finding-the-frozen-worker.
  The figures below come from the spikes of November 9 and 10, 2026; the README quotes its own captures, with counts, and never says "always".
  The design matrix, one 30-second freeze per run, with receipts as the bystanders:

  | Workers | Activity slots each | Receipt traffic | Receipts failed | Workflow Task timeouts |
  |---|---|---|---|---|
  | 2 | 2 | burst of 8 (five runs) | 0 | 4 per run |
  | 2 | 2 | burst of 100 | 0 | 53 |
  | 2 | 2 | burst of 500 | 0 | 94; the healthy Worker was overloaded |
  | 2 | 100 | burst of 8 | 1 | 4 |
  | 2 | 100 | burst of 100 | 27 | 52 |
  | 2 | 100 | burst of 500 | 0 | 94; the healthy Worker was overloaded |
  | 2 | 100 | 10 per second (six runs) | 17 to 22 of 512 to 520 | 77 to 84 |
  | 2 | 100 | 10 per second, no bad run | 0 of 521 | 0 |
  | 4 | 100 | 10 per second | 11 of 512 | 55 |

  A four-Worker run at 30 receipts per second overloaded the spike machine and is discarded.
  The chosen design is two Workers, the default slot counts, and 10 receipts per second.
  Healthy flood (`--bad 0`, two Workers): no receipt fails, no Workflow Task times out, and receipts stay fast for the whole run.
  In the spike 0 of 521 failed, the median receipt took 0.36 to 0.38 seconds, the slowest took 0.90 seconds, and neither Worker's log gained a line.
  Before (the bad flood on the practice copy, two Workers): a few percent of the receipts fail, and most of the rest are fast.
  In the six freeze runs 17 to 22 of 512 to 520 receipts failed (3.3 to 4.3 percent), each with "activity ScheduleToClose timeout" caused by "activity StartToClose timeout".
  The mechanism is the one exercises 01 to 03 show, thinned out by the second Worker.
  The frozen Worker's Rust-core pollers keep taking tasks, an Activity task it takes never runs and times out at the receipt's 5-second `start_to_close`, and the retry can go to either Worker, so a receipt fails only when its retry lands on the frozen Worker again and the 10-second `schedule_to_close` runs out.
  One swallowed attempt costs about 6 seconds (the 95th-percentile wait from scheduled to started was 6.04 to 6.05 seconds in three runs), which is why many more receipts are slow than fail.
  The frozen Worker takes Workflow Tasks the same way: 77 to 84 timed out per run at the 10-second default, every one started by the frozen identity.
  The server writes no history events for the retries in between, so a stalled receipt's history holds one `WorkflowTaskTimedOut` and then a `WorkflowTaskScheduled` whose `attempt` is 2 or 3 (in three runs the highest attempt was 1 for 438 to 442 receipts, 2 for 58 to 65, and 3 for 12 to 18).
  The timeline is the shape the reader learns to recognize, and the starter's summary prints it.
  Counted by submit time relative to the confirmed freeze, in three runs with about 50 receipts per 5-second bucket: the failures fall on receipts submitted from 5 seconds before the freeze to 10 seconds after it (1 to 2, then 12 to 13, then 4 to 8 per bucket).
  Of the receipts submitted in the first 10 seconds of the freeze, 44 to 49 of every 50 took longer than 2 seconds; in the next 5 seconds, 39 to 44 of 50; in the 5 after that, 1 or 2; and from 20 seconds on, none, although the Worker stayed frozen for 10 more seconds.
  The slowest receipt took 20.7 to 21.5 seconds, and after the thaw the median was 0.35 to 0.38 seconds.
  So the fleet looks recovered before the freeze ends, which is how a frozen Worker goes unnoticed.
  Decision: the README reports that timeline from its capture and may give the cause in one sentence marked as inferred: a frozen Worker takes only so many tasks before it stops asking for more, and the healthy Worker carries the rest.
  It measures nothing about slots and teaches no slot lesson, per the Scope invariant (confirm the wording at review).
  With four Workers (one run) the failures dropped to 11 of 512, all on receipts submitted in the first 15 seconds of the freeze, while the slow receipts spread across the whole 30 seconds (106 took longer than 2 seconds with no Workflow Task timeout).
  So more Workers mask more; the README may say so in one sentence without a capture of its own.
  `just receipt-gaps --by-identity --summary` over the run's receipts names one identity for every Workflow Task timeout and every failed Activity, and the other identity holds none (all six runs).
  The same identity is on the bad run's `ActivityTaskStarted` for `get_location`.
  The bad run's first Workflow Task is not the signal: the healthy Worker started it in three of the five small runs.
  A retried Activity's history keeps only its last attempt's `ActivityTaskStarted`, so the frozen identity shows on failed Activities and on timed-out Workflow Tasks, and never on a receipt whose swallowed attempt was retried elsewhere.
  Those receipts are late and carry the healthy identity: across the six runs, 77 to 82 receipt Activities per run started on a retry, and 57 to 67 receipts per run took longer than 2 seconds with no Workflow Task timeout in their history.
  The README says so, so the reader does not read a slow receipt on the healthy identity as a second sick Worker.
  The reader takes the PID from the frozen identity (`PID@host`) and attaches `asyncio ps` and `py-spy dump` to that process only; the other Worker's `asyncio ps` shows no task dead-ended.
  `py-spy dump` names the `sqlite3` call in `get_location`, and CPU reads near zero because the call waits on a lock.
  The rollup failed in two of the six flood freeze runs and completed in the other four, so the README quotes its capture and promises neither.
  Sticky affinity, seen in the small runs and quoted only if the capture shows it: a Workflow whose first Workflow Task ran on the Worker that later froze stalls on its next Workflow Task, although its Activity ran on the healthy Worker.
  The frozen Worker's log gains 273 to 277 lines in a flood run (five runs), 95 or 96 of them "Task not found when completing" and 78 to 82 of them `TMPRL1104`.
  Nearly all arrive at the thaw; two runs logged one more line 4 to 5 seconds after it.
  The healthy Worker's log gains none, and a healthy flood adds no line to either log.
  A seventh freeze run on November 10, 2026, made for the fleet checks, fell inside these ranges except in two timeline buckets: 17 of 518 receipts failed, 81 Workflow Tasks timed out on the frozen identity, and the rollup completed.
  It had 3 failures among the receipts submitted 5 to 10 seconds after the freeze, where the three earlier runs had 4 to 8, and no slow receipt among those submitted 15 to 20 seconds after it, where they had 1 or 2.
  `TMPRL1101` appeared in no spike run at either scale, so the 06 README does not list it as a symptom of this exercise.
  The tools in a fleet, checked on two Workers at eight receipts and under the flood; Part B of the 06 README walks through them and quotes its own capture:

  - `python -m asyncio ps` and `pstree` read each process as before.
    The frozen Worker's table has the task dead-ended at `_ActivityWorker._handle_start_activity_task`, the healthy Worker's has none, and both answer in about a tenth of a second.
    Under the flood the frozen Worker's table stays short (9 tasks), because a frozen loop creates no task for the work its pollers keep taking.
  - `py-spy dump` reads each process as before: the frozen Worker's main thread is in `get_location`, and the healthy Worker's is in the selector.
  - `top` shows the frozen Worker in state `S` at 0.0 percent for a lock wait.
    At eight receipts the healthy Worker read the same, and under the flood it read about 10 to 100 percent while it carried the traffic, so the busy Worker is the healthy one and CPU does not pick the frozen Worker.
    It still separates a waiting blocker from a computing one after the Worker is known.
  - `temporal task-queue describe` read a backlog of 0 and an age of 0 in each single mid-freeze read at both scales, because the healthy Worker drains the queue, so the backlog that marks a single-Worker freeze does not mark this one.
    A sampler that read every 2 seconds saw brief backlogs of 1 to 4 tasks, all younger than 0.3 seconds, in three of five flood runs.
    Its poller list shows both Workers polling, and it keeps Workers from earlier runs for some minutes.
  - The metrics endpoints of both Workers answer in about a millisecond, so they are still not a freeze signal.
  - The slot gauges, per Worker: the frozen Worker's `WorkflowWorker` gauge climbs (31 of 100 in use 4 seconds into the freeze, 95 of 100 later in another run) and the healthy Worker's stays low (highest sampled reading 3 to 6 across five freeze runs).
    The `ActivityWorker` gauge reads at most 2 in use on the frozen Worker and up to 3 on the healthy one, so it does not separate them.
  - `scripts/receipt_gaps.py` without flags reads one history at a time and prints no identity, so it cannot say which Worker; `--by-identity` can.
    Run as it stands on a flood's histories on November 10, 2026, it read 518 receipts in 37.7 seconds with `--limit 600`, and eight named IDs in 0.7 seconds.
    Its lines show the stall without naming a Worker: 75 of the 79 receipts with a Workflow Task timeout show a WT1 near 10 or 20 seconds, and 53 lines show an Activity that waited about 6 seconds from scheduled to started, which is the retried attempt.
    No line marks a failure, and 13 of the 17 failed receipts print no Activity.
  - The Web UI, checked about four minutes after the thaw and not during the freeze: the Workflow list filtered to `ExecutionStatus = Failed` shows the 17 failed receipts, and a failed receipt's page shows `Activity task timed out` with both timeout causes.
    The Task Queue page and a Workflow's Workers tab list both Workers with the same last-access second, so neither names the frozen Worker.
    In the stalled receipt opened for the check, the `Workflow Task Timed Out` rows show no identity; the frozen identity is on that receipt's earlier `Workflow Task Completed` rows and in the sticky Task Queue name on its `Workflow Task Scheduled` rows.
  - The dashboard, with both Workers scraped: only the per-Worker panel separates the two Workers, and the other panels read as listed under Observability.
  - The Worker log: only the frozen Worker prints "Task not found when completing" and `TMPRL1104`, at the thaw.

  The order of work changes with a fleet: in exercises 01 to 05 the reader starts at the process, and in exercise 06 the histories come first because they name the process.
  After (the bad flood on the solution copy, two Workers): no receipt fails, no Workflow Task times out, and the lookup waits out the lock on an executor thread.
  A solution-shaped scratch copy ran the bad flood six times on November 10, 2026.
  In five of the runs 0 of 512 or 513 receipts failed, no Workflow Task timed out, the median receipt took 0.33 to 0.40 seconds, and the slowest took 0.55 to 1.25 seconds.
  The rollup completed in all six, and in those five the bad run completed about 41 seconds into the flood, once the lock released.
  `py-spy dump` showed each Worker's main thread idle in the selector and the lookup on a `ThreadPoolExecutor` thread inside `get_location`, and `temporal task-queue describe` read a backlog of 0.
  One run was slow: the fourth of five back-to-back floods on one dev server, with the process tools attached.
  None of its 528 receipts failed, but 260 took longer than 2 seconds (median 1.36 seconds, slowest 23.63) and one Workflow Task timed out.
  The cause was not identified and the result did not recur: the next flood on the same server was clean, and so was a rerun with the tools attached on a fresh server.
  Decision: each capture flood runs against a freshly started dev server, and the healthy flood stays the rate check (confirm at review).
  The README quotes what the capture shows; if a receipt fails or stalls after the fix, the build stops and this spec is corrected before the README is written.
  The README says what the dashboard adds: the per-Worker panel shows one Worker holding Workflow Tasks, after the histories have named it.
  It leads with the histories because after an incident they are often all there is.
- Each exercise README follows the 102 structure: title "Exercise N: <Doing the thing>", "During this exercise, you will" bullets, the `practice`/`solution` note, a prerequisites section pointing at the root README's setup and at `just metrics`, Parts A through E (run it; read the failure in the tooling and the dashboard; find the bug; write the test and fix it; redeploy and verify), and the closing "### This is the end of the exercise." line.
- Each reader-written test in Part D:
  01 and 03, the probe test pattern from the root suite (a 50 ms ticker beside the Activity is not starved);
  02, an `ActivityEnvironment` run asserting more than one heartbeat and an unstarved probe during the poll loop;
  04, an `ActivityEnvironment` cancel of the `def` Activity asserting the work stops at the next heartbeat, plus a `build_worker` assertion that the executor's `max_workers` is at least `max_concurrent_activities`;
  05, the probe test parametrized over every registered `async def` Activity;
  06, the probe test pattern from 01, run against the `sqlite3` lookup with the lock held.
  `practice/tests/` holds the stub with a `TODO PART D` comment; `solution/tests/` holds it implemented.

## Observability requirements

- `just metrics` brings up Prometheus and Grafana with one command on a machine that has `docker` and `docker-compose` v1; `just metrics-down` removes them.
  The compose file defines exactly the two services and no Temporal server.
- Prometheus scrapes the SDK endpoint on 127.0.0.1:9464, the dev server endpoint on 127.0.0.1:9465, and a second Worker's endpoint on 127.0.0.1:9466 every 5 seconds, so a 30-second scenario produces at least six points per series.
  The third target is down whenever no second Worker runs, and that is expected.
- The dashboard is provisioned from the repo at Grafana startup; no manual import.
  Its panels are the ones listed under Architecture, and each exercise README and tutorial part names the panel the reader looks at and what it shows for the before and after states.
  The per-Worker panel is named in the exercise 06 README and in draft part 7 only, as corroboration after the histories have named the Worker.
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
- Exercise gate: every `exercises/*/solution/` copy passes ruff, ruff format, mypy strict, and its own `tests/` under `just check`, run per directory so the near-identical module names in different copies never share one mypy or pytest invocation (decision: a `just` loop over the solution directories with `uv run mypy <dir>` and `uv run pytest <dir>/tests`, and the root pytest configuration excludes `exercises/`).
  `practice/` copies are excluded from the gate because they carry the deliberate bug and the reader's unimplemented test; a lighter `just check-practice` runs ruff and mypy on them so they at least parse and type-check.
- Solution-copy tests include the reader's Part D test for that exercise; exercise 01's tests serve the slow endpoint from a stdlib server inside the test, never the network.
- Fleet localization: exercise 06's port-resolution tests mirror exercise 03's (default 9464, override, invalid values raise) in both copies, and its solution tests hold the lock from inside the test with a temporary database file, never a shared one.
  Its starter tests cover the flood without a server.
  The flood plan is tested as a pure function: the number of submissions and their due times for a rate and for the `--lead`, `--block-seconds`, and `--tail` durations.
  The summary is tested as a pure function: the 5-second bucketing relative to the confirmed freeze, the failed and slow counts, a receipt submitted before the freeze, and a bucket with no receipts.
  Argument parsing is tested for `--rate`, `--lead`, `--tail`, and `--bad 0`, and the freeze gate is tested against a mocked `describe` result (`get_location` STARTED, not yet started, and the timeout path), with no metrics scrape.
  A `build_worker` test in the solution copy asserts the executor's `max_workers` equals its `max_concurrent_activities`.
  `tests/test_receipt_gaps.py` covers the identity view against fixture histories captured from the two-Worker run: the per-line identities of the first `WorkflowTaskStarted` and of each `ActivityTaskStarted`, a retried first Workflow Task whose two attempts carry different identities (when the capture shows one), the `attempt` on the `WorkflowTaskScheduled` that completed WT1, a timeout attributed to the identity on the `WorkflowTaskStarted` before it, a failed receipt whose timed-out Activity is attributed through its scheduled event, the per-identity summary, and `--summary` printing the summary lines alone.
  A test asserts the default output is unchanged byte for byte against the existing `tests/fixtures/receipt-gaps.txt`, so the blocks already quoted in the READMEs stay valid.
- Observability config tests assert only the stack's invariants, never that a file parses or a value we chose: `prometheus.yml` names exactly the three scrape targets on ports 9464, 9465, and 9466; the compose file defines exactly the services `prometheus` and `grafana` with no image whose name contains `temporal`; every dashboard panel expression references a metric from the allowed list.
- The live failure signatures (cross-type blast radius, CPU pinning, the heartbeat retry storm, the zombie-thread overlap, the debug-mode warning, the flood's failed and late receipts) and the after-fix states are demonstrated live and captured during the build, not asserted in CI.
- The full gate is `just check` (ruff check, ruff format --check, mypy strict, pytest, the solution-copy loop, the observability config tests); pytest alone is the autonomous-run verification command.

## Documentation requirements

- README: what the repo demonstrates (one mechanism, the shared event loop), quickstart (three terminals: `just server`, `just worker`, then a scenario recipe, plus `just metrics` for the dashboard), and three lessons (healthy, frozen loop from a blocking call, frozen loop from CPU-bound code), each with the expected healthy-versus-broken shapes for `asyncio ps` / `pstree`, CPU, `py-spy dump` (the exact blocking line), and the metrics, with the cross-type blast radius called out.
  Lessons 4 to 7, "Which timeout fires, and how to tell", and the timeout-tuning parts of "Realistic timeouts" are removed.
  Every output block in the three lessons is recaptured from the trimmed package.
- Teaching-code note (owner ruling, November 9, 2026): the root README says once, in its own words and beside the statement that the repo contains deliberately broken code, that the code is built to teach one mechanism, so parts of it are simplified or altered to make a point, and that it is not a template for a production system.
  Each of the exercise 01 to 05 READMEs carries one sentence: the exercise runs one Worker with two Activity slots so one blocking call fails loudly, a real fleet has more of both and hides the failure, and exercise 06 shows that.
  Draft parts 1 to 6 carry the same sentence, so a draft never disagrees with its exercise.
  Decision: the sentence goes after the "During this exercise, you will" bullets, and nothing else in the five finished READMEs changes for it (confirm the placement at review).
- Fleet localization: the exercise 06 README follows the 102 structure, quoting only its two-Worker captures (the healthy flood, the bad flood, and the bad flood after the fix), and a seventh draft, `docs/drafts/part-7-finding-the-frozen-worker.md`, follows it.
  Both open with the contrast to exercises 01 to 05: those fail loudly on one small Worker, and a real fleet masks the same bug behind its healthy Workers.
  Both give the rate check (run the healthy flood first, and lower `--rate` if its slowest receipt takes longer than about a second) and say the flood is sized to make one failure visible on a laptop.
  Both carry one short paragraph on production fleets, stated as general practice without a capture: after the fact the Event Histories are often all there is, so group Workflow Task and Activity timeouts by time window and by the Worker identity on the Started events; the default identity is `PID@hostname`, and on Kubernetes the hostname is the pod name; attaching `py-spy` or `asyncio ps` inside a pod needs the `SYS_PTRACE` capability.
  The root README's `just receipt-gaps` row names `--by-identity` and `--summary`, its Observability section names the third scrape target and the per-Worker panel, and its Exercises table, CLAUDE.md, and `docs/drafts/README.md` list exercise 06 and part 7.
- README additions for this arc: an "Exercises" table in the 102 root-README shape linking each `exercises/<NN-name>/README.md`, an "Observability" section (what `just metrics` starts, where the dashboard is, the dev server metrics port and why `just server` sets it), and the series title with a `TODO` link.
- The two-tool framing stated plainly: `asyncio ps` / `pstree` identify the frozen loop and which task is wedged with zero instrumentation; `py-spy dump` names the exact file and line, because a task stuck in synchronous code is not at an await and so its frames are off the asyncio stack.
- Platform gotchas (including that `py-spy` and `asyncio ps` both need `ptrace_scope=0` or sudo on Linux) and a tutorial link placeholder.
- Recognition block (owner ruling, November 9, 2026): one shared "recognize it" section, written in the root README and in the event loop primer, tells a reader how a blocked loop looks before any tool is attached.
  It holds the symptom list (Workflow Task timeouts on Workflows whose code is fine, Workers that stay alive and stay listed as pollers but stop completing work, an Activity marked Started long before its code runs, the Worker log line "Task not found when completing", and `TMPRL1101`), then the code question to ask first: are these Activities `async def`, and what do they call?
  The root README quotes the "Task not found when completing" line from its own `just block` Worker log and says the Worker prints it at the thaw.
  It says a healthy run prints none only after a healthy-only root Worker log, taken fresh at the capture step, shows that; the two-Worker spike's healthy run printed none.
  `TMPRL1101` is named in prose, never quoted from a root capture, as a related symptom that depends on timing: on a Worker with `async def` Activities it can mean the event loop is blocked, not that the Workflow code deadlocked; a reader's run may not show it; and the block points to exercise 02, the one place it is captured.
  Each symptom is stated only where a capture of that copy or the documented SDK mechanism supports it.
  The primer carries the same list and question in its "What a frozen loop looks like from outside" section and links to the README's capture.
  Each exercise README links to the block in one line at the top of Part B; the five finished Part Bs otherwise stay as they are.
- Fold-ins (owner ruling, November 9, 2026): the exercise 01 table and `activity_executor` note, the exercise 02 heartbeat sentence, and exercise 03's required second-Worker step (all under Architecture) land in the exercise READMEs and in draft parts 2, 3, and 4 together, so a draft never disagrees with its exercise.
- Exercise READMEs: six (five in the event-loop-exercises arc, and exercise 06 in the fleet-localization phase), in the 102 structure described under Exercise requirements, quoting only that exercise's captures, with the Grafana panel named in the observe and verify parts.
- Tutorial drafts: seven (six in the event-loop-exercises arc, and part 7 in the fleet-localization phase), under `docs/drafts/`, written with the content-design:tutorial-writing skill from the exercise READMEs and the captures (Title H1, Introduction H3, Prerequisites H2, "Step N: Gerund phrase" H2, Conclusion H2; sentence case; second person; code sandwich; Temporal primitives capitalized), each linking the previous and next parts with `TODO` placeholders, each Vale-clean (MasonBase plus MasonTechnical) and passed through `/review-content`.
  Part 1 covers install, `ptrace_scope`, `just server`, `just worker`, `just metrics`, `just healthy`, and the baseline readings including the dashboard; parts 2 to 7 follow exercises 01 to 06 and end with the reader's fix and its verification.
  The series title is "Debugging blocking calls in Temporal async Activities".
  Drafts carry no frontmatter.
- `docs/drafts/README.md` lists the seven drafts, the unnumbered event loop primer, and `smell-reports.md`, keeps the provenance note on the original draft, and keeps the venue as not yet chosen.
- README and draft prose follows the repo owner's writing rules: no em-dashes, one sentence per line in committed Markdown.
- Update CLAUDE.md to the trimmed package, the four-layer layout (root reference, exercises, scripts, observability), the solution-copy carve-out, and the current `just` recipes.
- MIT license (already present).

## Non-goals

- No lesson, exercise, or draft about slot exhaustion, Worker sizing for throughput, heartbeat or timeout tuning, schedule-to-start, or retry policy and idempotency; those are general Temporal topics covered elsewhere.
- No load test or benchmark: exercise 06's flood is sized to make one failure visible on a laptop, and its figures are captures of one machine, never performance claims.
- No detection library, watchdog, linter, or any maintained tooling; diagnosis uses read-only introspection the reader runs (native `asyncio ps` / `pstree`, `py-spy dump`, asyncio debug mode) and the Prometheus and Grafana stack, never tooling this repo builds or ships, apart from the read-only `scripts/receipt_gaps.py` helper that tabulates a history's Workflow Task gaps, and with `--by-identity` the Worker identity behind each (`--summary` trims that view to its per-identity lines), from `temporal workflow show` output.
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
- Observability stack (`observability/`): input is the metrics endpoints (the Worker, the dev server, and a second Worker when one runs); output is a provisioned dashboard.
  Owns the compose file, scrape config, provisioning, and dashboard JSON, plus their config tests.
  Depends on `just server` exposing port 9465.
- Captures (scratchpad during the build, trimmed into the READMEs, drafts, and `docs/images/`): input is the trimmed root package's three scenarios and each copy's before and after runs with the stack up; output is the quoted blocks and screenshots, with the trims disclosed in the root README's "About the captured output" section.
  Depends on the exercise copies and the stack.
- Tutorial drafts (`docs/drafts/part-N-*.md`): input is the exercise READMEs and the captures; output is the drafts (six in the event-loop-exercises arc, part 7 in the fleet-localization phase) and the Vale and copy-editor passes.
  Depends on every capture and README being final.
- Root docs (`README.md`, `CLAUDE.md`, `docs/drafts/README.md`): input is the trimmed package, the finished layout, and the root captures; output is the three-lesson README, the exercises table, the observability section, and the architecture refresh.
- Fleet localization (`exercises/06-finding-the-frozen-worker/`, `scripts/receipt_gaps.py`, `observability/`, `tests/`, draft part 7, root docs): input is the two-Worker flood runs of the 06 copies (healthy, bad, and bad after the fix) and exercise 03's one-Worker and two-Worker runs.
  Output is the two 06 copies with the port setting and the flood starter, the `--by-identity` view with `--summary` and its tests, the third scrape target and the per-Worker panel, the captures, the 06 README with its production note, and the draft.
  It also outputs the recognition block, the fold-ins in exercises 01, 02, and 03, the teaching-code note in the root README, and the single-Worker sentence in exercises 01 to 05 and draft parts 1 to 6.
  Depends on the event-loop-exercises arc being complete; the helper change lands before the captures, and the prose lands after them.
- Gate (`justfile`, `pyproject.toml`): input is the solution copies and config files; output is `just check` covering them and `just check-practice` covering the practice copies lightly.

## Success criteria

- `just check` is green with the solution-copy loop and the observability config tests included, and `just check-practice` is green.
- `grep -rn "slow_heartbeat\|stuck_no_heartbeat\|PriceQuote\|maximum_attempts" src tests justfile` returns nothing.
- Each exercise runs from its own directory: the `practice/` copy reproduces its failure, and the `solution/` copy produces its after-state, both captured and quoted.
- `just metrics` brings up the dashboard on a machine with `docker-compose` v1, with the 9464 and 9465 scrape targets up, the 9466 target up while a second Worker runs, and every panel populated during a scenario.
- Fleet localization: a two-Worker healthy flood of the 06 practice copy shows no failed receipt, and a bad flood shows failed receipts and the timeline in the starter's summary.
  From that bad flood, `just receipt-gaps --by-identity --summary` names the frozen Worker as the one identity holding the Workflow Task timeouts and the failed Activities, and the reader reaches `asyncio ps` and `py-spy dump` on that PID without reading the Worker banner.
  `just receipt-gaps` without the flags prints exactly what it printed before; `grep -rn "ANTIPATTERN (deliberate, for teaching)" exercises/06-finding-the-frozen-worker/solution` returns nothing; the 06 README and draft part 7 quote only those captures and satisfy the Privacy invariant.
- The recognition block exists in the root README and the primer, every exercise README's Part B links to it in one line, and exercise 03's second-Worker step is no longer marked optional.
- The root README carries the teaching-code note, and each of the exercise 01 to 05 READMEs carries the single-Worker sentence that points to exercise 06.
- Six exercise READMEs and seven tutorial drafts exist, quote only captures of their own exercise, pass Vale, and have been through `/review-content`.
- The root README has exactly three lessons, all recaptured; the README and CLAUDE.md describe the four-layer layout; and `grep -rn "ANTIPATTERN (deliberate, for teaching)" exercises/*/solution` returns nothing.
- The arc ships as commits on the `scaffold` branch (PR #4 against `main`), with a session summary per commit.
