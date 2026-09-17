# Lessons Learned

## Recent

- `schedule_to_start_timeout` combined with `WorkflowEnvironment.start_time_skipping` is flaky because the skipped clock can cross the deadline while tasks queue; test such workflows under a real-time (`start_local`) environment (2026-09-17)
- An error-path test that asserts only the exception type does not prove a retry policy is disabled; record `activity.info().attempt` per invocation and assert the attempt count (`== [1]` for `maximum_attempts=1`) so the test fails if retries come back (2026-09-17)
- For timing-based probe tests, pick gap thresholds with wide slack in one pass (block 0.5 s against a 0.4 s floor, not 0.45 s); do not re-run the suite to tune thresholds to the edge, which invites flakiness and a hung tuning loop (2026-09-17)
- Test an activity's heartbeat ordering by assigning `ActivityEnvironment.on_heartbeat`; it receives the same `*details` the activity passed to `activity.heartbeat`, so no worker needs to run (2026-09-17)
- pytest exits 5 when it collects no tests, which fails a `just check` gate; give a freshly scaffolded package a single import smoke test rather than loosening the gate (2026-09-17)
- Commit a plan or spec immediately after a `/bpe:review` outcome that needs no `/bpe:apply-review` changes; letting it ride uncommitted into `/bpe:goal` trips the pre-flight dirty-tree refusal (2026-09-17)
- When a BPE slash command's arguments don't parse as one of its documented mode keywords, check whether the text is actually a different valid request (a config change, a clarification) before defaulting to the command's default mode (2026-09-17)
- Generated fleet code must be emitted as real per-workflow source files, not factory closures, or every culprit shows the same file:line in `asyncio pstree` and the diagnostic hunt collapses (2026-09-16)
- Antipattern demos need a fixed, greppable line-level marker (`# ANTIPATTERN (deliberate, for teaching): ...`); README-level warnings do not survive snippet extraction by scrapers, completion tools, or training pipelines (2026-09-16)
- A Temporal worker with all activity slots occupied stops polling entirely and disappears from the Temporal UI poller list while remaining healthy; distinguish from a frozen event loop by stack shapes in `asyncio ps` (healthy tasks park on asyncio suspension points) plus `temporal_worker_task_slots_available` (2026-09-15)

## Testing

- An error-path test that asserts only the exception type does not prove a retry policy is disabled; record `activity.info().attempt` per invocation and assert the attempt count (`== [1]` for `maximum_attempts=1`) so the test fails if retries come back (2026-09-17)
- For timing-based probe tests, pick gap thresholds with wide slack in one pass (block 0.5 s against a 0.4 s floor, not 0.45 s); do not re-run the suite to tune thresholds to the edge, which invites flakiness and a hung tuning loop (2026-09-17)
- pytest exits 5 when it collects no tests, which fails a `just check` gate; give a freshly scaffolded package a single import smoke test rather than loosening the gate (2026-09-17)

## Temporal

- Test an activity's heartbeat ordering by assigning `ActivityEnvironment.on_heartbeat`; it receives the same `*details` the activity passed to `activity.heartbeat`, so no worker needs to run (2026-09-17)
- `schedule_to_start_timeout` is non-retryable and normally an antipattern; it is useful in demos precisely because it converts slot exhaustion into a fast, visible failure (2026-09-16)
- `schedule_to_start_timeout` combined with `WorkflowEnvironment.start_time_skipping` is flaky because the skipped clock can cross the deadline while tasks queue; test such workflows under a real-time (`start_local`) environment (2026-09-17)

## Workflow

- When a `/bpe:review` unit comment defers to "my other request", do the global comment's research before applying any unit feedback; the units were ruled contingent on it (2026-09-16)
- Scaffold repos for `/bpe:goal` by reading the skill's pre-flight first: gitignore `commit-msg.md` and `goal.md`, keep main commit-free, ensure a test-runner manifest exists so the verification command autodetects (2026-09-14)
