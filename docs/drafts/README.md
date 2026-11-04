# Drafts

Working drafts for the tutorial series that accompanies this repository.
Nothing in this directory is public yet.
Final versions go off-repository, and the venue is not yet chosen (probably not masonegger.com).

## The six series parts

The series title is "Debugging blocking calls in Temporal async Activities".
Each part quotes only captured output.
The captures came from the root package or from the exercise copy the part teaches.

- `part-1-healthy-worker.md`: set up the demo, start a healthy Worker, and record the baseline readings.
- `part-2-sync-http-client.md`: fix a blocking HTTP client in an `async def` Activity (exercise 01).
- `part-3-sleep-between-heartbeats.md`: fix a sleep between heartbeats in an `async def` Activity (exercise 02).
- `part-4-cpu-bound.md`: move CPU-bound work off the event loop (exercise 03).
- `part-5-zombie-thread.md`: stop a thread that outlives its Activity attempt (exercise 04).
- `part-6-catching-blockers-early.md`: catch a short blocking call before it ships, with a probe test (exercise 05).

Each part links to the next with a TODO placeholder until the series has a venue.

## smell-reports.md

`smell-reports.md` is the review file for Mason.
It holds one section per artifact: the five exercise READMEs, the six parts, and the root README.
Each section lists the suspect items with the verbatim quote and the rule it may break, and it holds the open questions inside `CLAUDE_HELP` tags.
Mason reads it before merging the scaffold branch, because nothing here publishes without his review.

## tutorial-original-draft.md

The January 2026 tutorial draft, moved here verbatim from the masonegger.com website repository (branch `async-debug-tutorial`) in October 2026.
It predates this repository and is a structural starting point only.

Known-wrong claims in it, per the October 2026 live captures (see spec.md Starting context):

- It claims `asyncio ps` and `pstree` show the blocking call site.
  They do not.
  A task wedged in synchronous code dead-ends at the SDK frame `_ActivityWorker._handle_start_activity_task`; the frozen-loop SHAPE is the signal, and `py-spy dump` names the exact line.
- It treats the whole worker as frozen.
  Only the Python side freezes, and the Rust core's pollers and the Prometheus endpoint keep running.
- It references a Flask web UI and a `temporal-async-debug` repository layout that were never built.
  The real repository uses the command-line starter and the fleet described in spec.md.
- Its awaiter-chain output examples predate the tooling here.
  Real captures replace them.

## Conclusion

The six parts replace the original draft.
They follow the `block` and `cpu` lessons and the five exercises, and they quote only captured output.
