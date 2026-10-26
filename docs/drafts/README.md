# Drafts

Working drafts for the tutorial and blog content that accompany this repo.
Nothing in this directory is published; final versions will be published off-repo (venue TBD, likely not masonegger.com).

## tutorial-original-draft.md

The January 2026 tutorial draft, moved here verbatim from the masonegger.com website repo (branch `async-debug-tutorial`) in October 2026.
It predates this repo actually being built and is kept as a structural starting point only.

Known-wrong claims in it, per the October 2026 live captures (see spec.md Starting context):

- It claims `asyncio ps` / `pstree` show the blocking call site. They do not.
  A task wedged in synchronous code dead-ends at the SDK frame `_ActivityWorker._handle_start_activity_task`; the frozen-loop SHAPE is the signal, and `py-spy dump` names the exact line.
- It treats the whole worker as frozen. Only the Python side freezes; the Rust core's pollers and the Prometheus endpoint keep running.
- It references a Flask web UI and a `temporal-async-debug` repo layout that were never built; the real repo uses the CLI starter and the fleet described in spec.md.
- Its awaiter-chain output examples were written before the tooling existed here and must be replaced with real captures.

Rewrite against the justfile lessons (`block`, `cpu`, `slow`, `slow-heartbeat`, `stuck`) and quote only captured output.
