# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A Temporal Python demo that misbehaves on purpose, built as a teaching companion to a tutorial series on diagnosing blocking calls in `async def` Activities.
Every intentional bug or mistuning is a feature of the demo, not a defect: it must be preserved and must carry the marker comment described below.
Do not "fix" antipatterns you find here unless the task explicitly asks you to change the demo's behavior.

`spec.md` (requirements) and `plan.md`/`todo.md` (the step-by-step execution plan, consumed by `/bpe:execute-plan` or `/bpe:goal`) drive the build.
Read `spec.md` in full before making architectural decisions; `spec.md` is the source of truth for behavior this repository must exhibit.

The whole repository is about one mechanism: blocking the shared asyncio event loop.
The spec's Invariants forbid any slot-exhaustion, heartbeat-tuning, timeout-tuning, or retry-policy lesson.
The failure-mode catalog that preceded this layout lives under `.ai-sessions/failure-mode-catalog/`.

The repository is public.
No committed file (code, prose, `.ai-sessions/` records, commit messages) may name a customer, a real or invented company, a namespace, a ticket number, or a specific field use case.
None may name an internal system, an internal document, or internal training or course material, course codes and runbooks included.
Field evidence is summarized in aggregate only, as in `.ai-sessions/research-20261109-field-evidence.md`, without saying where it was gathered; raw research notes stay outside the repository.
Quoted captures use stand-ins for the capture machine: the user is `ziggy`, the location is `Milky Way Galaxy`, the public IP address is `256.256.256.256`, paths read `/home/ziggy` and `/home/ziggy/temporal-async-debug`, and an identity reads `PID@host`.
A stand-in for any other place or address is fictional too.
The stand-ins belong to prose only: the code obfuscates nothing when a reader runs it.
Saved test fixtures are captures too: every Worker identity in `tests/fixtures/*.json` reads `PID@host`.
No quoted capture, and no prose around one, names the capture machine's hostname, user name, public IP address, or location.
Tooling paths are the one exception: `.vale.ini`, the `justfile`, `spec.md`, `plan.md`, and older `.ai-sessions/` records hold the owner's user name in a path.

## Layout

The repository has four layers:

- Root reference: `src/temporal_async_debug/`, `tests/`, and the three lessons in `README.md`.
  The package is the frozen-loop reference, trimmed to `block` and `cpu` only.
- `exercises/`: six exercises in the Temporal 102 shape, `exercises/<NN-name>/{README.md,practice/,solution/}`.
  The directories are `01-sync-http-client`, `02-sleep-between-heartbeats`, `03-cpu-bound`, `04-zombie-thread`, `05-catching-blockers-early`, and `06-finding-the-frozen-worker`.
  Exercises 01 to 05 teach on one Worker with two Activity slots (exercise 03 adds a second Worker in its last part); exercise 06 runs two Workers at the SDK default of 100 Activity slots under a flood of receipts.
  Each copy is a flat set of modules plus `tests/`, with absolute (flat top-level) imports, and it runs from its own directory under the root virtual environment.
  Practice edit points carry `# TODO PART X:` comments.
- `scripts/`: `receipt_gaps.py`, a standard-library helper that reads `temporal workflow show --output json` for receipt Workflows and prints the first Workflow Task time (WT1) and each Activity's waits.
  `just receipt-gaps` runs it.
  `--by-identity` adds the Worker identity on each Started event to every line and one summary line per identity, and `--summary` (valid only with `--by-identity`) prints the summary lines alone.
  The directory holds that one script, and it reproduces no whole run.
- `observability/`: `docker-compose.yml` (Prometheus and Grafana only, docker-compose v1), `prometheus.yml`, and the provisioned `grafana/` dashboard.
  `prometheus.yml` scrapes three targets: the Worker on 9464, the dev server on 9465, and a second Worker on 9466, which reads as down when none runs.
  The dashboard has seven panels; panel 7, Workflow Task Slots Used Per Worker, draws one line per Worker.

Other directories: `docs/drafts/` holds the seven-part series drafts, the optional unnumbered `event-loop-primer.md` (a Diataxis explanation page read before part 1), `smell-reports.md` (the voice:teaching smell reports, with each older open question closed as a `Build decision:` line), and the provenance draft `tutorial-original-draft.md`; `docs/images/` holds the Grafana captures that a Markdown file references, and no others.
After Step 1 of the plan, the root package stays frozen: new code lands under `exercises/`, `scripts/`, or `observability/`.

## Antipattern marker convention

Every deliberately wrong line, setting, or pattern carries a comment of this exact, greppable form on or immediately above the offending line:

<!-- vale off -->
```
# ANTIPATTERN (deliberate, for teaching): <why it is wrong>. Correct: <the right approach>. Do not copy.
```
<!-- vale on -->

Find them all with `grep -rn "ANTIPATTERN (deliberate, for teaching)"`.
The root package has two markers, the `time.sleep` call and the CPU-bound loop, both in `activities.py`.
Each `exercises/*/practice` copy keeps its antipattern and its marker.
Any new deliberate bug or mistuning added to this repository must carry this marker; a validator pass flags one that does not.

Solution-copy carve-out: a `solution/` copy carries no antipattern and no marker.
`grep -rn "ANTIPATTERN (deliberate, for teaching)" exercises/*/solution` must return nothing.
So the marker search over the whole tree finds the root package and the practice copies only.

## Commands

Toolchain is `uv` + `ruff` + `mypy` (strict) + `pytest`, orchestrated through `just`:

<!-- vale off -->
```bash
just check            # root gate (ruff check, ruff format --check, mypy strict, pytest), then check-solutions
just check-solutions  # the solution loop alone
just check-practice   # ruff and mypy on each exercises/*/practice copy
just fmt              # ruff format + ruff check --fix
just test             # pytest on the root package only
```
<!-- vale on -->

Run a single test with `uv run pytest path/to/test_file.py::test_name`.

Per-directory gate: the root gate excludes `exercises/`, because every copy reuses the same flat module names.
`just check` loops over `exercises/*/solution` and runs ruff, ruff format, mypy, and pytest for each.
Each loop iteration runs from inside the copy, so the copy's own directory is first on `sys.path`, and pytest's `pythonpath` is pinned to that same absolute directory.
`just check-practice` runs ruff and mypy only, because a practice copy carries the bug and an unfinished test.
Both loops are no-ops when no copy exists.

Demo-running recipes (require the dev server and the Worker running in separate terminals; the scenario recipes take an optional `seconds` argument, default 30):

<!-- vale off -->
```bash
just server                # temporal server start-dev --metrics-port 9465
just worker                # the demo Worker (prints its PID for asyncio introspection)
just healthy               # healthy fleet (two geo, a rollup, three receipts), all completing
just trigger               # smaller healthy fleet (geo and receipts only), a quick smoke test
just block seconds="30"    # frozen-loop lesson (time.sleep blocks the Worker)
just cpu seconds="30"      # frozen-loop lesson, CPU-pinned (busy loop holds the GIL)
just receipt-gaps ids      # WT1 and Activity gaps for receipt Workflow IDs, or --limit N (needs the Temporal CLI and a server)
just metrics               # Prometheus and Grafana in the background (docker-compose v1)
just metrics-down          # tear the stack down
```
<!-- vale on -->

`just server` passes `--metrics-port 9465` so the dev server exports its own metrics, which Prometheus scrapes beside the worker's port 9464.
In exercises 03 and 06, a second Worker exports on 9466 when it starts with `ASYNC_DEBUG_METRICS_PORT=9466`.
`just metrics` starts Prometheus (9090) and Grafana (3000, anonymous viewer) only, never a Temporal server.

Prose tooling (the README, CLAUDE.md, exercise READMEs, and drafts all go through it):

<!-- vale off -->
```bash
just preflight       # verify Vale 3.20 or newer, .vale.ini, the Mason styles, Std, and the content-design and voice plugin files
just lint-prose      # Vale as JSON for the named files, or for every committed prose file
just lint-keyboard   # flag non-keyboard characters (em-dashes, smart quotes, arrows, emoji)
```
<!-- vale on -->

`.vale.ini` applies `MasonBase` to every Markdown file and adds `MasonTechnical` under `docs/drafts/` and `exercises/`.
`.vale.ini` turns `MasonBase.Headings` off under `docs/drafts/` and `exercises/` only.
In the root `README.md` and `CLAUDE.md` it still fires, and both it and `MasonBase.SentenceCapitalization` are ruled false positives there.
Run `just preflight` before any prose step.
`.vale.ini` sets an absolute Linux `StylesPath` under the owner's home directory, so `just preflight` and `just lint-prose` fail on macOS; lint there with a temporary copy of the config whose `StylesPath` points at the local Mason styles.

## Architecture

Package lives under `src/temporal_async_debug/` (src layout, hatchling build backend, Python 3.14+ required).
The modules are:

- `shared.py`: frozen dataclasses for every Workflow's input and output, `VALID_MODES` (`block`, `cpu`), and the Task Queue name constant.
- `activities.py`: `get_ip` and `get_location` (httpx-based, `HTTP_TIMEOUT_SECONDS` of 4.0).
  Both call `_apply_mode`, a plain function that branches on the two modes.
  `block` calls `time.sleep` and `cpu` spins in a busy loop; both freeze the loop, and each carries a marker.
- `workflow.py`: `GeoEnrichmentWorkflow`, the Workflow that carries the bad modes, and `geo_activity_options`.
  It returns the same 120-second `start_to_close` and 150-second `schedule_to_close` for every valid mode, and raises on an unknown mode.
  There is no heartbeat timeout and no custom retry policy.
- `receipt.py`: `OrderReceiptWorkflow`, an instant in-memory bystander.
- `rollup.py`: `SalesRollupWorkflow`, a short-work bystander (a five-second cooperative pause, then a sum).
- `worker.py`: `build_worker(client)` registers all three Workflow types and all Activities on one Task Queue, with `max_concurrent_activities=2`.
  That setting carries no marker; it only keeps the slot gauge readings short.
  It exposes Prometheus metrics on `localhost:9464` and prints a startup banner with its PID and copy-paste `python -m asyncio ps`/`pstree` commands.
- `starter.py`: fleet CLI (argparse) over the two modes, with `--bad`, `--geo`, `--rollups`, `--receipts`, and `--block-seconds`.
  `fleet_from_args` builds a `Fleet`, and `select_scenario` routes it to the freeze or the concurrent ordering.
  The freeze path puts rollups in flight and awaits the healthy geo before submitting the bad run.
  It then waits until the server reports the bad run's second Activity (`get_location`) STARTED, plus a 1-second guard, before submitting receipts, so they stall through the final freeze and complete at the thaw.
  The geo Workflow freezes twice (`get_ip`, then `get_location`) with a fraction of a second of live loop between (60 to 570 ms across the 8 final runs, depending on `get_ip`'s HTTP call; 138 ms in the run that exposed the race).
  A bystander released into that gap can be dispatched just as the loop re-freezes and time out, which is why the gate waits on the second Activity.
  It exits with `os._exit(0)`.

The core teaching mechanism: every `async def` Activity, the Python side of Workflow Task handling, heartbeat recording, and the Python tasks that hand poll results to user code share **one** asyncio event loop, so a single blocking call freezes them together.
The Rust core's network polling and the Prometheus endpoint run on their own threads and keep going, which is why the server keeps dispatching tasks that then time out and why the metrics endpoint still answers during a freeze.
The three Workflow types are unrelated, yet they share that loop and the same two Activity slots.
A misbehaving geo Activity therefore fails the rollup and stalls the receipts too, even though their code is correct (the cross-type blast radius).

The root cause is a frozen loop (`block`, `cpu`): a single blocking or CPU-bound call starves everything on the loop at once.

- `python -m asyncio ps` and `pstree` show the shape with zero instrumentation.
  The wedged task dead-ends at the SDK handler `_ActivityWorker._handle_start_activity_task` with no await beneath it, and the other tasks sit parked at awaits.
  They do not name the blocking line, because a task stuck in synchronous code is not suspended at an await.
- `py-spy dump` reads the OS thread stack and names the exact line: `activities.py:121` for `block`, `activities.py:127` for `cpu` in the captures quoted in README.md.
- CPU separates the two causes: `top` reads 0.0 in state `S` for `block` (`time.sleep` releases the GIL) and 99.0 in state `R` for `cpu`, where `py-spy` labels the thread `active+gil`.
- The in-flight rollup fails `ScheduleToClose` caused by `StartToClose`.
  Receipts stall: their first Workflow Task goes to the frozen Worker and times out, and a second Workflow Task completes at the thaw.
  Read a `WorkflowTaskTimedOut` plus retry as a stall across two Workflow Tasks, never as one long one.
  The root `just block` histories quoted in README.md show both: the rollup's Activity times out 20 seconds after it is scheduled, and a receipt's WT1 is about 28.8 seconds.
  WT1 runs from the first `WorkflowTaskStarted` to the first `WorkflowTaskCompleted`, so it spans the timeout and its retry.
- The metrics endpoint stays reachable during a freeze, answering in milliseconds (0.014 s in the capture quoted in README.md), so it is not a freeze signal.
  `temporal_worker_task_slots_available` reads 0 whenever both slots are in use, so slots alone do not name the cause.
  The pollers live in the Rust core and keep long-polling through a freeze, so poller `LastAccessTime` is not a freeze signal either.

Dashboard facts from the captures quoted in README.md and the exercise READMEs (they win over earlier prose):

- The SDK reports latency in milliseconds, so the latency panels use `ms`.
- A freeze fails no Activity on the Worker side, so `temporal_activity_execution_failed` never appears; the failures panel plots the dev server's `activity_timeout` by timeout type.
- The dev server's backlog gauge is nearly flat.
  `temporal task-queue describe` is the reliable backlog reading (count 1, age 4.27 s during a `cpu` freeze, while the 9465 scrape read 0).
- Only the three latency panels plot a 30-second rate average.
  Do not read a stall's length from them: in the root `just block` run of 2026-11-11 the receipts' WT1 was 29,002 and 29,001 ms, the Workflow Task Execution Latency panel drew no receipt line, and its highest reading was 5.14 s on the rollup line.
  Exercise 01's capture shows the receipt and rollup lines between 5 and 6 seconds.
  No capture establishes why the panel reads low, so prose states the reading and the run, never a cause.
- The failures panel plots `activity_timeout`, so it misses a Heartbeat timeout.
  Exercise 02's storm is a run of Heartbeat timeouts, so the panel misses the storm.

Exercise facts from the rework captures (the exercise READMEs quote them):

- Exercise 02, the retry storm: the Activity's **Attempt** climbs in the Web UI and in `temporal workflow describe` (to attempt 4 in about 50 seconds), but a retried Activity writes no history event per attempt, so `workflow show` cannot show the storm.
  The Worker log shows each attempt's polls.
  `TMPRL1101` ("Potential deadlock detected") appeared on one failed Workflow Task in each of the four capture runs (runs 1 and 2, with the Web UI open, also failed one legacy Query each), and `TMPRL1104` ("Workflow task duration exceeded 5 seconds") appeared in every run.
  `TMPRL1101` depends on timing, so the README says a reader's run may not show it.
- Exercise 03: `solution/worker.py` reads its Prometheus port from `ASYNC_DEBUG_METRICS_PORT`, so a second Worker runs with `ASYNC_DEBUG_METRICS_PORT=9466 uv run python worker.py` and needs no edit.
  The README runs `--bad 2` on one Worker and `--bad 4` on two.
- Exercise 05: the audit trail is 40,000 generated audit-log lines, about five megabytes, built once at Worker start.
  `get_location` compresses it with `zlib`, which releases the GIL, then throws the bytes away in place of an upload.
  The run completes with no failure, and the receipts only run a little late.
- Exercise 06: two Workers (metrics ports 9464 and 9466) share the Task Queue, and `starter.py` floods them with receipts (default `--rate 10`) around one bad run; the pure plan, summary, and formatting functions live in `flood.py`.
  The practice `get_location` runs a synchronous `sqlite3` lookup against a location cache whose exclusive lock `db_lock.py` holds, so one Worker's loop freezes while the other keeps serving.
  In the flood of record the starter printed `receipts submitted=523 failed=21`, and `just receipt-gaps --limit 600 --by-identity --summary` gave one identity 82 Workflow Task timeouts and a largest WT1 of 29199 ms, and the other 0 timeouts and 977 ms.
  A `WorkflowTaskTimedOut` event carries no identity, so the helper gives it to the identity on the `WorkflowTaskStarted` that shares its scheduled event id.
  `py-spy dump`, the `--by-identity` view, the per-Worker panel, and (after the thaw) the Worker log separated the two Workers; `top`, the metrics endpoints, the `ActivityWorker` slot gauge, and the fleet-wide dashboard panels did not.
  A Workflow Task of the bad run can carry either identity; only the `ActivityTaskStarted` event for `get_location` named the frozen Worker in all three bad floods (the flood of record and two on 2026-11-13).
  The Web UI row comes from the two 2026-11-13 floods, read on the rendered pages of Web UI 2.45.3, which has no Workers page for the Namespace.
  On the Task Queue page the frozen identity's **Last Accessed** time fell behind only late in the freeze (6.1 and 11.8 seconds behind at about 23 and 28 seconds in the later flood).
  The bad run's **Pending Activities** tab named the frozen Worker under **Last Worker Identity** at each of its four readings.
  No capture establishes why **Last Accessed** stops, so prose states the readings and no cause.
  The README holds no open `CLAUDE_HELP` question.

`spec.md`'s Behavior Requirements section spells out what each mode must produce; where the captured output quoted in README.md and the exercise READMEs disagrees with spec.md or plan.md, the captures win.
`README.md` is the tutorial companion with captured output for the three lessons, an Exercises table, a blocked-event-loop recognition section, and an Observability section.

Tests must never require a running Temporal server except through the SDK's own test facilities (`temporalio.testing.ActivityEnvironment`, `WorkflowEnvironment.start_time_skipping()`); all network calls are mocked.
