# Lessons Learned

## Recent

- Python 3.14 `asyncio ps` / `pstree` do NOT show the blocking line of an async activity wedged in synchronous code (e.g. `time.sleep` or a CPU loop): that task truncates at the SDK frame `_ActivityWorker._handle_start_activity_task` with no await beneath it, because asyncio introspection walks the await chain and synchronous code is not an await, so those frames live on the OS thread stack. Use `py-spy dump` (or faulthandler) for the exact line; use asyncio ps / pstree for the frozen-loop SHAPE (the wedged task dead-ended at the SDK handler while every other task sits parked at a real await) (2026-10-04)
- Concurrent `execute_workflow` calls (`asyncio.gather`) under `WorkflowEnvironment.start_time_skipping()` can race the server's automatic clock advance against real workflow-task dispatch, producing spurious `START_TO_CLOSE` timeouts; wrap the `gather` in `env.auto_time_skipping_disabled()` (synchronous context manager) to remove the race (2026-09-23)
- In a justfile, the FIRST recipe is what bare `just` runs; when a plan step adds recipes, instruct the executor to keep the `default: @just --list` recipe first and verify bare `just` prints the help, or an insertion above it silently changes the CLI's front door (2026-09-21)
- On a BPE plugin upgrade, do not reflexively run `/bpe:retrofit`; read the new plan skill first. 0.7.0's `/bpe:plan` states its new spec sections (`## Invariants`, `## Roadmap / phase log`) are optional for older specs, so a legacy spec plans fine. `--replace` discards a hand-written spec and `--resync` corrects drift, so neither fits a spec that is intentionally ahead of the code; a targeted in-place edit adding the fence sections is the right move (2026-09-20)
- BPE 0.7.0 `/bpe:plan` honors three scope fences: `## Invariants`, `## Non-goals`, and `**Deferred:**` under `## Roadmap / phase log`; keep out-of-scope work under one of those exact headings (not a custom "Future work" section) or the plan writer will not treat it as a mechanical fence (2026-09-20)
- To hold an activity slot for a long cooperative wait, heartbeat every few seconds inside the wait (interval a few times shorter than heartbeat_timeout); otherwise the server cancels the activity at heartbeat_timeout and frees the slot early (2026-09-18)
- To demo slot exhaustion without a race, fill the slots first and confirm it: submit the slot-holders, poll temporal_worker_task_slots_available until the ActivityWorker gauge reads 0, then submit the work that should starve, so it fails on schedule_to_start every run (2026-09-18)
- When a shared helper is called both inside and outside an activity (e.g. reused by a Temporal-free test), guard activity.heartbeat with activity.in_activity() so the bare call does not raise (2026-09-18)
- A cooperative slow-mode Activity that awaits `asyncio.sleep` without heartbeating gets cancelled at its `heartbeat_timeout` (10s here), not at the full sleep duration, so a slot-exhaustion window built on `--block-seconds 30` is really only ~10-14s wide; to hold slots for the full duration, heartbeat periodically during the wait or lengthen the heartbeat timeout (2026-09-18)
- Capture real tool output for a tutorial before writing the prose; the live run produced the genuine `temporal_worker_task_slots_available` 0 line AND exposed the heartbeat-timeout timing that the spec and the first README draft both got wrong (2026-09-18)

## Testing

- Concurrent `execute_workflow` calls (`asyncio.gather`) under `WorkflowEnvironment.start_time_skipping()` can race the server's automatic clock advance against real workflow-task dispatch, producing spurious `START_TO_CLOSE` timeouts; wrap the `gather` in `env.auto_time_skipping_disabled()` (synchronous context manager) to remove the race (2026-09-23)
- An error-path test that asserts only the exception type does not prove a retry policy is disabled; record `activity.info().attempt` per invocation and assert the attempt count (`== [1]` for `maximum_attempts=1`) so the test fails if retries come back (2026-09-17)
- For timing-based probe tests, pick gap thresholds with wide slack in one pass (block 0.5 s against a 0.4 s floor, not 0.45 s); do not re-run the suite to tune thresholds to the edge, which invites flakiness and a hung tuning loop (2026-09-17)
- pytest exits 5 when it collects no tests, which fails a `just check` gate; give a freshly scaffolded package a single import smoke test rather than loosening the gate (2026-09-17)

## Temporal

- The Temporal Python SDK serves its Prometheus metrics endpoint from the Rust core runtime on its own threads, not the Python event loop, so `curl :9464/metrics` stays reachable while a blocking call freezes the loop (verified live). The frozen-loop signal is the `asyncio ps` SHAPE (the wedged task dead-ended at `_ActivityWorker._handle_start_activity_task`, every other task parked at an await) plus CPU, with `py-spy dump` for the exact line, not endpoint reachability (2026-10-04)
- Python 3.14 `asyncio ps` / `pstree` do NOT show an async activity's blocking line when it is wedged in synchronous code; the task truncates at the SDK frame `_ActivityWorker._handle_start_activity_task` because asyncio walks the await chain and sync code is not an await. `py-spy dump` shows the real thread stack down to the `time.sleep` call site; asyncio ps still distinguishes the culprit (dead-ended, no await beneath) from healthy tasks (parked at awaits) (2026-10-04)
- A Temporal worker with all activity slots occupied (or a frozen loop) stops polling, so in `temporal task-queue describe` its poller `LastAccessTime` goes stale and it eventually drops off the poller list while the process stays healthy; the live saturation tell is the activity backlog age, and `temporal_activity_schedule_to_start_latency` only moves once a queued task finally starts (2026-10-04)
- Test an activity's heartbeat ordering by assigning `ActivityEnvironment.on_heartbeat`; it receives the same `*details` the activity passed to `activity.heartbeat`, so no worker needs to run (2026-09-17)
- `schedule_to_start_timeout` is non-retryable and normally an antipattern; it is useful in demos precisely because it converts slot exhaustion into a fast, visible failure (2026-09-16)
- `schedule_to_start_timeout` combined with `WorkflowEnvironment.start_time_skipping` is flaky because the skipped clock can cross the deadline while tasks queue; test such workflows under a real-time (`start_local`) environment (2026-09-17)

## Architecture

- Generated fleet code must be emitted as real per-workflow source files, not factory closures, or every culprit shows the same file:line in `asyncio pstree` and the diagnostic hunt collapses (2026-09-16)
- Antipattern demos need a fixed, greppable line-level marker (`# ANTIPATTERN (deliberate, for teaching): ...`); README-level warnings do not survive snippet extraction by scrapers, completion tools, or training pipelines (2026-09-16)

## Workflow

- Commit a plan or spec immediately after a `/bpe:review` outcome that needs no `/bpe:apply-review` changes; letting it ride uncommitted into `/bpe:goal` trips the pre-flight dirty-tree refusal (2026-09-17)
- When a BPE slash command's arguments don't parse as one of its documented mode keywords, check whether the text is actually a different valid request (a config change, a clarification) before defaulting to the command's default mode (2026-09-17)
- When a `/bpe:review` unit comment defers to "my other request", do the global comment's research before applying any unit feedback; the units were ruled contingent on it (2026-09-16)
- Scaffold repos for `/bpe:goal` by reading the skill's pre-flight first: gitignore `commit-msg.md` and `goal.md`, keep main commit-free, ensure a test-runner manifest exists so the verification command autodetects (2026-09-14)
