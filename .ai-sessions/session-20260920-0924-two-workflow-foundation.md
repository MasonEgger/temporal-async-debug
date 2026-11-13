# Session Summary: Two-Workflow Foundation for the Failure-Mode Catalog

**Date**: 2026-09-20
**Duration**: Part of a long design-and-build session
**Conversation Turns**: multiple design turns plus this commit
**Estimated Cost**: High; a fork implementation plus validator and two live-verification subagents
**Model**: Fable 5 orchestrating; fork (Fable) for the implementation; Sonnet subagents for validation and live runs

## Key Actions

- Rebuilt the demo around two neutrally-named workflow types on one worker, replacing the labeled Greeting/Victim pair so the fleet looks ordinary and the reader diagnoses from the tooling, not from names.
  - GeoEnrichmentWorkflow: get_ip then get_location, real async httpx with round-robin + failover across five IP providers and three geo providers; driven into block or slow mode via input.
  - OrderReceiptWorkflow (new): validate_order, compute_total, format_receipt; fast, no network, ordinary correct code; the unrelated workflow that suffers when the geo workflow misbehaves.
- Dropped all heartbeats and the schedule_to_start_timeout antipattern; geo activities use start_to_close + schedule_to_close with maximum_attempts=1 (the marked antipattern), receipts use a normal retry policy.
- Rewrote the starter into a fleet CLI (--mode, --block-seconds, --bad, --geo, --receipts) that sequences the slot-exhaustion run deterministically, and kept the os._exit teardown workaround.
- Reworked all tests; deleted victim.py and test_victim.py; added receipt.py and test_receipt.py (with a no-network guard) and get_location failover plus all-fail RuntimeError tests. `just check` green, 40 passed.
- Validated the diff with the Fable validator (verdict clean after fixing the two findings it raised) and verified behavior live twice.
- Corrected spec.md's frozen-loop signature earlier this arc: the metrics endpoint stays reachable during a block (Rust-core-served), so the asyncio ps stack shape, not metrics reachability, is the frozen-loop tell.

## Live findings that shaped the next phase

- Slot exhaustion (slow) already fails the unrelated receipts cleanly (cross-type blast radius confirmed: receipts 3/3 failed on schedule_to_close).
- Async slow activities are cancelled at start_to_close (asyncio.sleep is a cancellation point), so slots currently free at ~10s, not the full block; a block (time.sleep) holds its slot the full duration because it is uncancellable.
- A frozen loop also freezes bystanders' workflow-task processing, so brand-new work submitted during a freeze never schedules its activity and only stalls; only work already scheduled or in-flight trips start_to_close / schedule_to_close. Instant bystander activities are not caught by a freeze.

## Deviations from Plan / Deferred

- README.md and CLAUDE.md are intentionally NOT updated in this commit. They are stale relative to this foundation (they still describe Greeting/Victim, heartbeats, and the old flags). They will be rewritten once, against the final live-verified behavior, as part of the failure-mode catalog build, so they are not written twice against tuning that is about to change.

## Next phase (decided with the user)

Build a comprehensive failure-mode catalog on this foundation via /bpe:plan + /bpe:goal. Scope (all of it):
- Misbehavior modes: block (time.sleep), cpu (GIL-pinning compute loop), slow (asyncio.sleep no heartbeat), slow-heartbeat (correct long activity), stuck-no-heartbeat (trips heartbeat timeout).
- Bystander shapes: instant no-network, short-work no-network; plus a sample that sets schedule_to_start to show that timeout and its latency metric.
- Every activity timeout shown firing (start_to_close, schedule_to_close, schedule_to_start, heartbeat), each mapped to a scenario/recipe, with the frozen-loop vs slot-exhaustion diagnostic split and the cross-type blast radius layered on.
- Retune timeouts against live behavior so both lessons reliably fail bystanders via activity timeouts.
This pulls the cpu-bound and heartbeat variants out of v2 future work into scope.

## Suggested Skills for Next Session

- `python:python`, `temporal:temporal-developer`: the catalog adds modes, activities, and tests.
- `content-design:tutorial-writing`, `content-design:review-content`: the comprehensive README.
