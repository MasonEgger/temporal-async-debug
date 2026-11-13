# Review Decisions: Fleet Localization

This record is the review handoff for pull request 4, written at the end of the 15-step fleet-localization build.
Every item is a build decision that the builder made without the owner, and one review comment can overrule any of them.
Line numbers are those of the branch at the commit that adds this file.

## Reading Order

1. `docs/drafts/event-loop-primer.md`: the optional explanation page, read before part 1.
2. `README.md`: the three root lessons, the Exercises table, the recognition section, and Observability.
3. `exercises/01-sync-http-client/README.md`.
4. `exercises/02-sleep-between-heartbeats/README.md`.
5. `exercises/03-cpu-bound/README.md`.
6. `exercises/04-zombie-thread/README.md`.
7. `exercises/05-catching-blockers-early/README.md`.
8. `exercises/06-finding-the-frozen-worker/README.md`: the two-Worker flood, with the two open questions listed under Open CLAUDE_HELP Tags.
9. `docs/drafts/part-1-healthy-worker.md` to `docs/drafts/part-7-finding-the-frozen-worker.md`, in order.
10. `docs/drafts/smell-reports.md`: the `Build decision:` lines, as a reference while you read.

## Eleven Decisions on the Older Open Questions

1. The failures panel stays unchanged, and exercise 02 keeps saying the panel misses a Heartbeat timeout.
   Look at `exercises/02-sleep-between-heartbeats/README.md` lines 452 to 457.
2. The exercise 02 solution panel images are new captures, with a window that starts at the fleet start.
   Look at `docs/images/02-solution-live-workflow-task-latency.png` and `docs/drafts/smell-reports.md` line 89.
3. The near-empty Workflow Task panels in exercise 05 stay, and the README says why.
   Look at `exercises/05-catching-blockers-early/README.md` lines 240 to 248.
4. The primer stays unnumbered.
   Look at `docs/drafts/README.md` and `docs/drafts/smell-reports.md` line 292.
5. The primer's third diagram stays, and its edge for `def` Activities agrees with the Temporal documentation.
   Look at `docs/drafts/event-loop-primer.md` from line 155 and `docs/drafts/smell-reports.md` lines 295 to 296.
6. Part 1 quotes the read-only `sysctl kernel.yama.ptrace_scope` output, the `sudo` write stays a command with no output, and `temporal task-queue describe` stays the reliable backlog reading.
   Look at `docs/drafts/part-1-healthy-worker.md` lines 93 to 112 and line 460.
7. The forced-timeout demo in part 5 stays a described extension, because the repository ships no scratch copy for it.
   Look at `docs/drafts/part-5-zombie-thread.md` from line 556.
8. The root README's list of permitted edits to captured output gains the removal of terminal color codes.
   Look at `README.md` line 183.
9. The latency panel has a new reading from a root `just block` run on 2026-11-11, and the root README states that reading with no cause.
   Look at `README.md` lines 768 to 772 and `docs/drafts/smell-reports.md` lines 586 and 620.
10. Part 1's clone command uses the HTTPS URL.
    Look at `docs/drafts/part-1-healthy-worker.md` line 37.
11. The layer count is four, because `scripts/` is a layer.
    Look at `README.md` line 28.

## Decisions Marked Confirm at Review in the Spec

Each item starts with its line in `spec.md`.

- Line 302: every row of the "Same bug, other library" table is a blocking call on the event loop, and no row gets a capture or an exercise of its own.
  Look at `exercises/01-sync-http-client/README.md` from line 362.
- Line 303: a row names a category and a call shape, and a Python package only where the package name is not also a company name; the LLM row stays generic.
  Look at the same table, and at its copy in `docs/drafts/part-2-sync-http-client.md` from line 362.
- Line 362: the lock's hold starts when the starter submits the bad run, so the freeze is a little shorter than `--block-seconds`.
  Look at `exercises/06-finding-the-frozen-worker/solution/db_lock.py` line 58 and `solution/starter.py` line 319.
- Line 363: `get_ip` keeps the async client, so the `sqlite3` lookup is the only blocker in the exercise 06 practice copy.
  Look at `exercises/06-finding-the-frozen-worker/practice/activities.py` lines 166 to 169.
- Line 368: the exercise 06 copies run the SDK default of 100 Activity slots and 100 Workflow Task slots, where exercises 01 to 05 run two Activity slots.
  Look at `exercises/06-finding-the-frozen-worker/solution/worker.py` lines 53 and 143 to 144.
- Line 383: if the slowest receipt of the healthy flood takes longer than about 1 second, the reader lowers `--rate` before the bad flood, and the README is to say so.
  The README gives the 0.70 second reading and has no sentence about lowering `--rate` yet; look at `exercises/06-finding-the-frozen-worker/README.md` line 126.
- Line 387: the flood runs one rollup by default.
  Look at `exercises/06-finding-the-frozen-worker/solution/starter.py` lines 127 to 132.
- Line 389: the flood has one gate, the server-side check that the bad run's `get_location` has STARTED, and no metrics-scrape gate.
  Look at `wait_for_activity_started` in `exercises/06-finding-the-frozen-worker/solution/starter.py`, line 142.
- Line 415: the per-Worker panel's query carries the Task Queue filter, because without it the query also returns six all-zero series from the dev server's own system Workers.
  Look at panel 7 in `observability/grafana/dashboards/async-debug.json`.
- Line 416: the third scrape target, port 9466, is always in the configuration and reads as down whenever no second Worker runs.
  Look at `observability/prometheus.yml` line 15.
- Line 417: the per-Worker view moved out of the Deferred list and into this phase.
  Look at panel 7, Workflow Task Slots Used Per Worker, and the Observability section of `README.md` from line 708.
- Line 441: `--summary`, valid only with `--by-identity`, prints the per-identity summary lines alone.
  Look at `scripts/receipt_gaps.py` and `tests/test_receipt_gaps.py`.
- Line 447: with `--by-identity`, each history's line also reports a Workflow Task timeout with its identity and marks an Activity that timed out or failed; the default output keeps its old form.
  Look at `scripts/receipt_gaps.py` and `tests/test_receipt_gaps.py`.
- Line 617: each capture flood ran against a freshly started dev server, and the healthy flood stays the rate check.
  Look at `exercises/06-finding-the-frozen-worker/README.md` lines 64 to 66 and line 130.

## Exercise 06 Design Decisions

These come from the Architecture Recap in `plan.md`, from line 47.
Paths in this section are relative to `exercises/06-finding-the-frozen-worker/`.

- `GeoEnrichmentInput` carries `location_cache_path` in place of exercise 01's `upstream_url`.
  Look at `solution/shared.py` line 31.
- `get_location` reads the cache first and falls through to the geo providers on a miss; the cache table is empty, and no copy carries a hardcoded fallback city.
  Look at `solution/activities.py` lines 111 to 179.
- `hold_cache_lock` returns a `CacheLock` that is itself the context manager, with an `arm()` method that the starter calls right after it submits the bad run.
  Look at `solution/db_lock.py` lines 33 to 133.
- Both copies read `ASYNC_DEBUG_METRICS_PORT` as exercise 03's solution does, so a second Worker needs no edit.
  Look at `solution/worker.py` from line 47.
- The practice copy passes no `max_concurrent_activities`; the solution sets its constant to 100 only so the thread pool has one thread per slot.
  Look at `practice/worker.py` from line 120 and `solution/worker.py` lines 53 and 143 to 144.
- The flood's pure functions live in `flood.py`, which imports nothing from Temporal; the spec names no module for them, so `flood.py`, `tests/test_flood.py`, and `tests/test_starter.py` are the builder's names.
  Look at `solution/flood.py` and `solution/starter.py`.
- A healthy flood (`--bad 0`) also submits the rollups after the lead, and its timeline counts from the end of the lead.
  Look at `solution/starter.py` lines 14 to 15 and line 291.
- The per-Worker panel is panel 7, at full width under the six older panels.
  Look at `observability/grafana/dashboards/async-debug.json`.
- The practice copy's antipattern marker wraps over three comment lines, and the marker search still finds it.
  Look at `practice/activities.py` lines 166 to 168.

## Open CLAUDE_HELP Tags

The tree holds two tag pairs, both in `exercises/06-finding-the-frozen-worker/README.md`.

- Lines 353 to 357: the bad run's identity comes from the capture's JSON history, which has no masked copy, so the README states the identity and quotes no block.
  Decide whether to add a masked excerpt.
- Lines 531 to 534: the Web UI row reports saved API JSON, because the capture has no rendered Task Queue or Workers page.
  Take a screenshot of both pages during a freeze, or keep the row as it stands.

## Other Build Decisions Worth a Look

Each step's session file under `.ai-sessions/` lists every deviation from the plan in its Deviations from Plan section; these are the ones a reader can see.

- The build read "just run more exercises" as more bad runs in exercise 03: `--bad 2` on one Worker, then `--bad 4` on two.
  Look at `exercises/03-cpu-bound/README.md` lines 467 and 524, and at Steps 10 and 11 of `docs/drafts/part-4-cpu-bound.md`.
- An older session file still calls the retired `--bad 3` choice a ruling, and the owner made no such ruling.
  Look at `.ai-sessions/session-20261109-0100-goal-step-20-exercise-readmes.md` line 48 and `docs/drafts/smell-reports.md` lines 121 to 123.
- `spec.md` line 63 quotes the owner's scope statement with one word replaced by `[...]`.
  Look at `spec.md` line 63.
- Quoted captures mask the capture machine's public IP address, place name, and paths, and identities read `PID@host`; the `top` USER column stays as captured.
  Look at `README.md` lines 165 to 187 and `docs/drafts/smell-reports.md` line 590.
- The exercise 01 README and part 2 still say the latency panel averages over 30 seconds, so a 29-second stall reads as about 5 to 6 seconds; no capture establishes that cause.
  Look at `exercises/01-sync-http-client/README.md` line 336 and `docs/drafts/part-2-sync-http-client.md` line 319.
- The exercise 06 README and part 7 say "the other four dashboard panels" in a dashboard of seven panels, which is the wording written from the capture.
  Look at `exercises/06-finding-the-frozen-worker/README.md` line 537 and `docs/drafts/part-7-finding-the-frozen-worker.md` line 535.
- Of the 64 PNG files under `docs/images/`, 39 appear in no Markdown file outside `.ai-sessions/`; the build kept them all and deleted none.
  Look at `docs/images/`; the unused files are panel captures from exercises 01 to 05, the healthy baseline, and the root runs.
- Four bad practice floods ran for exercise 06, and only the fourth is the flood of record; the solution flood of record is a rerun after one receipt read 2.01 seconds.
  Look at `.ai-sessions/session-20261111-1113-goal-step-7-exercise-06-captures.md`.
- The solution run's Failures panel read No data, so the exercise 06 README says so in one sentence and embeds no image.
  Look at `docs/drafts/smell-reports.md` line 248.
- The exercise 06 README keeps the measured figures for the metrics response times and the `receipt-gaps` duration where they differ from `spec.md`.
  Look at `docs/drafts/smell-reports.md` lines 260 to 262.
- The recognition sign "An Activity marked Started long before its code runs" has no quoted capture behind it.
  Look at `README.md` line 674.
- Part 7 is 956 lines against a plan of 550 to 800, in 13 steps that follow Parts A to E of the exercise.
  Look at `docs/drafts/smell-reports.md` lines 524 to 547, where line 534 gives the count as 954, taken before Step 14 added two lines.
- Part 1 reads `sysctl kernel.yama.ptrace_scope` after the `sudo` write, as a read-back check.
  Look at `docs/drafts/part-1-healthy-worker.md` lines 93 to 112.
- The series link in the root README and the links between parts are still `TODO` lines, and each part carries a "venue not yet chosen" comment.
  Look at `README.md` line 24 and lines 2 and 18 to 22 of `docs/drafts/part-6-catching-blockers-early.md`.
- With `--by-identity`, an Activity with no `ActivityTaskStarted` event prints `on no Worker`, and a Workflow Task timeout with no Started event gets no identity.
  Look at `scripts/receipt_gaps.py` line 257.
- In the flood summary, a failed receipt counts in `slow>2s`, `p50`, and `max`, and the parser accepts `--rate inf` and `--rate nan`.
  Look at `exercises/06-finding-the-frozen-worker/solution/flood.py` and `solution/starter.py`.
- Exercise 03's `build_telemetry_config` still takes the port two ways, from the environment or from a `port` argument.
  Look at `exercises/03-cpu-bound/solution/worker.py` line 85.
- The observability tests pin the expressions of panels 1 to 6, though the spec says config tests assert no chosen value.
  Look at `tests/test_observability_config.py`.
- The primer came from no plan step.
  Look at `docs/drafts/event-loop-primer.md`.

## Process Notes

- Steps 1 to 4 ran with Opus executors and Fable validators, and Steps 5 to 15 ran with Sonnet executors and Opus validators.
  Each step's session file names the model that ran it.
- The copy-editor agent and the Temporal documentation search were out of reach for the executors and the validators.
  Vale and a manual checklist replaced the copy-editor, and the orchestrator ran the documentation queries.
- Steps 5, 10, 12, and 13 used all three validator iterations, Steps 1 to 4, 6, 9, 11, and 14 used two, and Steps 7 and 8 ran no validator.
  Look at each step's session file under `.ai-sessions/`.
- Steps 12 and 13 went in with `just check` failing on a Python fence in part 7, because the per-step check was `pytest` alone.
  Step 14 fixed the fence, and the full gate ran after it.
- `/init` did not run after each commit.
  The `CLAUDE.md` refresh in Step 14 stands in for it.
