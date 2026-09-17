# Lessons Learned

## Recent

- Commit a plan or spec immediately after a `/bpe:review` outcome that needs no `/bpe:apply-review` changes; letting it ride uncommitted into `/bpe:goal` trips the pre-flight dirty-tree refusal (2026-09-17)
- When a BPE slash command's arguments don't parse as one of its documented mode keywords, check whether the text is actually a different valid request (a config change, a clarification) before defaulting to the command's default mode (2026-09-17)
- Generated fleet code must be emitted as real per-workflow source files, not factory closures, or every culprit shows the same file:line in `asyncio pstree` and the diagnostic hunt collapses (2026-09-16)
- Antipattern demos need a fixed, greppable line-level marker (`# ANTIPATTERN (deliberate, for teaching): ...`); README-level warnings do not survive snippet extraction by scrapers, completion tools, or training pipelines (2026-09-16)
- A Temporal worker with all activity slots occupied stops polling entirely and disappears from the Temporal UI poller list while remaining healthy; distinguish from a frozen event loop by stack shapes in `asyncio ps` (healthy tasks park on asyncio suspension points) plus `temporal_worker_task_slots_available` (2026-09-15)
- Scaffold repos for `/bpe:goal` by reading the skill's pre-flight first: gitignore `commit-msg.md` and `goal.md`, keep main commit-free, ensure a test-runner manifest exists so the verification command autodetects (2026-09-14)

## Temporal

- `schedule_to_start_timeout` is non-retryable and normally an antipattern; it is useful in demos precisely because it converts slot exhaustion into a fast, visible failure (2026-09-16)

## Workflow

- When a `/bpe:review` unit comment defers to "my other request", do the global comment's research before applying any unit feedback; the units were ruled contingent on it (2026-09-16)
