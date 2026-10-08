# Session Summary: Rewrite the README From Verified Captures

**Date**: 2026-10-07
**Duration**: One README-only correction pass outside the plan (implement, copy-editor pass, two validator iterations with one fix round, finalize)
**Conversation Turns**: Orchestrated; one implement dispatch, one copy-editor fix pass, one validator fix dispatch, two validator dispatches, one finalize dispatch
**Estimated Cost**: Moderate; one large prose file (555 insertions, 193 deletions) diffed block by block against the capture sets, no code changed
**Model**: Implementer Opus 5.5; copy-editor agent pass; validator Fable 5.1 (clean at iteration 2); finalize Opus 5.5

## Key Actions

- The adversarial review found the README's "real captured output" promise had cracks.
  One value was altered, ten quoted starter lines carried a colon the code never prints, four `temporal workflow show` blocks had no capture behind them, one quote was truncated, one trim was undisclosed, and several line numbers were stale.
- Several README claims had also been disproved by later live runs: the poller LastAccessTime going stale, slots_available as a discriminator, a blanket maximum_attempts=1, and the freeze outcome for instant bystanders.
- README.md was rewritten to quote only from the capture sets (temporalio 1.33.0, Python 3.14.3, Temporal CLI 1.6.2 / server 1.30.2).
  Every trim is declared in "About the captured output" and was checked line by line against its source.
- The freeze lesson now matches the measurements: the rollup fails ScheduleToClose caused by StartToClose (8 of 8), the healthy geo is awaited before the bad run, and receipts and quotes are gated on the bad run's second activity STARTED, stall through the final freeze, and complete at the thaw (19 of 19).
- The saturation lesson scopes the ScheduleToStart label and states the healthy geo completes late.
  The latency metric is described as lagging; backlog age is the live tell only together with the healthy `asyncio ps` shape.
- The two-tool story (asyncio ps for the frozen-loop shape, py-spy for the exact line) carries current line numbers.
  The pollers' Rust-core behavior is explained, and maximum_attempts=1 is taught as at-most-one dispatch, not exactly-once.
- A copy-editor agent pass tightened the technical prose; validator Fable 5.1 diffed every fenced block against its capture and returned warn at iteration 1 (disclosure gaps), clean at iteration 2.
- `just check` green: 128 passed.

## Deviations from Plan

- Plan said: Lesson 1 healthy block re-quoted from reverify2/healthy.starter.txt.
- Deviated: quoted all 7 rows from reverify/01-healthy-starter.txt instead, so the rows pair with that run's own metrics file (reverify/01-healthy-metrics-after.txt: sum 1130, count 15). The old "1227 and 15" had no capture.
- Impact: none on accuracy; every row is shown, no trim.

- Plan said: CPU readings from reverify4.
- Deviated: reverify4 only has `ps -o %cpu` (lifetime average: 1.7 SNl for block, 3.0 RNl for cpu). The README quotes those lines, explains the lifetime average, and keeps the earlier `top` rows (block-top.txt 0.0 S; cpu/05.top 100.0 R). The old README added a `top` header line to the cpu row that the capture does not have; it is removed. "80 to 100 percent" became "81.8 to 100 percent in all 24 samples" (cpu/*.top).
- Impact: CPU claims now quote real files only.

- Plan said: poller section rewritten as "not a freeze signal".
- Deviated: also disclosed that reverify4 block-1 t+20 shows an activity backlog (1 task, 8.9s) during a freeze: it is the rollup's queued retry with zero free permits. The README says a backlog appears whenever no slot is free, so backlog age is the saturation tell only together with the healthy `asyncio ps` shape.
- Impact: slightly qualifies spec.md's "backlog age is the live saturation tell"; consistent with the spec's slots reasoning. Spec not edited (README-only pass).

- Plan said: nothing on quotes under a freeze.
- Deviated: added the blockq-1 output to Lesson 7 showing the quote completes at the thaw under a freeze (3 of 3 runs), since a frozen loop never schedules its Activity. The command shown is the starter directly (no recipe submits a quote on the freeze path).
- Impact: new, capture-backed fact; no recipe change.

- Vale: 0 errors. Warnings are code-line length on verbatim captures, the Title Case heading rule (overridden by the sentence-case instruction for Temporal docs), the "Temporal CLI" product name, and Flesch 66. Left as is.
- The maximum_attempts lesson matches the workflow.py marker text; no docs.temporal.io URL is linked because the implement dispatch could not fetch it.

- Copy-editor fix pass (technical flags, README prose only):
  - Lesson 2 "with zero timeouts" became "with no Activity timeouts and no failures"; the later WorkflowTaskTimedOut sentence now says the first Workflow Task expired on the frozen Worker and the retry succeeded at the thaw.
  - Intro: "nothing else on the Worker can run" became "nothing else on that loop can run". The one-loop sentence now names what shares the loop (async def Activities, Python-side Workflow Task handling, poll hand-off tasks) and what does not (Rust core polling, Prometheus endpoint).
  - Lesson 4: dropped "the count drops as the starved tasks time out"; now says ApproximateBacklogCount is approximate and lags.
  - No fenced block, quoted output, figure, timestamp, id, or file:line changed.

- Validator iteration 1 fix (verdict warn, README prose only):
  - Capture-edits list: housekeeping rows named as Task-1 through Task-6 (Task-6 is the `_ActivityWorker.run` exception-queue task; Lesson 2 keeps it, the others drop it).
  - pstree bullet: excerpts show only the branches the text names and omit the housekeeping tree under Task-1.
  - Timestamp-prefix bullet: "Lessons 2 and 3" became "Lessons 2, 3, and 7".
  - Lesson 3: the `3.0 RNl 04:32` ps line is attributed to the snapshot eight seconds into the first cpu run of the final capture session (cpu-1-snap-t08-summary.txt).
  - Lesson 7: "event history JSON" became "Event History JSON".
  - No fenced block, figure, id, or file:line changed; just check exit 0 (128 passed).

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| Fix C implement dispatch | Rewrote README.md quoting only from the capture sets, every trim disclosed | Draft ready for review |
| Copy-editor agent pass | Flagged technical prose overstatements | Three prose fixes, no quoted block touched |
| Validator iteration 1 (Fable 5.1) | Diffed every fenced block against its capture | Warn: disclosure gaps in the capture-edits list and two attributions |
| Fix dispatch | Closed the disclosure gaps | Validator clean at iteration 2 |
| Finalize dispatch | `just check`, session summary, lesson, commit, push | One signed commit on scaffold |

## Efficiency Insights

**What went well:**
- A mechanical quote-vs-capture diff of every fenced block found what two earlier read-throughs missed, and made each fix checkable.

**What could improve:**
- The first README was validated for internal consistency and line numbers only, so an altered value, inserted punctuation, and four reconstructed blocks shipped.

**Course corrections:**
- Lesson 1 switched source captures so its rows pair with a metrics file from the same run.

## Process Improvements

- For any doc that promises verbatim output, make the validator diff each quoted block against a named capture file and check that every trim appears in the disclosure list.
- Name the capture file next to each block in the working notes so the diff is a lookup, not a search.

## Observations

- spec.md still says backlog age is the live saturation tell without the qualifier the README now carries (a freeze can also show a backlog when no permit is free).
  A small spec follow-up would align the two.
- No docs.temporal.io link backs the maximum_attempts lesson in the README yet.

## Suggested Skills for Next Session

- `content-design:review-content`: if the README or spec gets another prose pass.
- `temporal:temporal-developer`: to confirm the backlog-during-freeze qualifier and source a docs link for the maximum_attempts lesson.
