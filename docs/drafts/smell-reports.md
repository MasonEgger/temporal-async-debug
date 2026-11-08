# Smell Reports For The Exercise READMEs

Draft status: every README below waits for Mason's review.
Nothing here publishes.
Each bullet gives the verbatim quote and the rule it may break.
Open questions sit inside CLAUDE_HELP tags.

## Shared across all five READMEs

- Quote: `<!-- vale off -->` and `<!-- vale MasonBase.CodeLineLength = NO -->` around every captured output block.
  Rule: Vale hygiene. Captured output has multi-space columns (`MasonBase.Spaces`, error level) and lines over 80 characters (`MasonBase.CodeLineLength`).
  I wrapped each block rather than edit the output, so the quotes stay verbatim.
- Quote: `## Part A: Run the Workflow`
  Rule: `MasonBase.Headings` wants title-style capitalization.
  The task and the Temporal education rule say sentence case, so I kept sentence case and left the warnings visible.
- Quote: `## Conclusion`
  Rule: not in the 102 shape.
  `MasonTechnical.Conclusion` is an error-level rule that requires a level 2 Conclusion heading, so each README has a short one before the closing line.
- Quote: `### This is the end of the exercise.`
  Rule: `MasonBase.Headings` title-case warning, and an H3 under Conclusion where 102 has it under the last Part.
- Quote: `Your team runs a service that looks up where a request came from.`
  Rule: invented framing.
  Every Part A opens with a short production story that no capture shows.
  The facts in it match the code, and the story is mine.
- Quote: `Do not read the Activity code yet.`
  Rule: voice:teaching, "nothing is hidden from the attendee".
  This follows the 102 pattern of asking the reader to diagnose first, and the code is one click away.
- Quote: `SentenceCapitalization` warnings on lines such as `The Activity in the rollup only had to sleep for five seconds.`
  Rule: Vale false positive.
  The sentence tokenizer splits on possessives and on text near code fences, and a rewording of one line moves the warning to another.
  I stopped chasing them after each README had one pass.
- Quote: `The Worker prints a banner with its PID`
  Rule: temporal-docs MCP unreachable.
  Capitalized primitives (Workflow, Activity, Worker, Task Queue, Workflow Task, Event History, Heartbeat timeout, Activity code) are now cased the same way in all five READMEs, and follow the tutorial-writing list and the facts file, not a live docs check.
- Rule check: the review-content copy-editor agent could not run from the executor context, so a checklist pass took its place.
  The validator also did a skill read of its own.

## exercises/01-sync-http-client/README.md

- Quote: `The Workflows finish and nothing looks wrong.`
  Rule: unquoted claim.
  The practice healthy run (`starter.py --geo 2 --receipts 3`) has no capture in `captures/01-practice`.
  The plan and spec say it completes.
- Quote: `That is part of the problem.`
  Rule: voice:teaching broetry and two-beat contrast, close to "Most people would get angry. I got curious."
- Quote: `The tools told you why.`
  Rule: same two-beat shape.
- Resolved: the top command now reads `top -b -d 1 -n 2 -p <PID> | tail -8`, as captured, and the block says it keeps only the column header and the process row (also in 02 and 03).
- Resolved: the idiom now reads `the way a real provider sometimes takes several seconds to answer.`
- Resolved: the Workflow Task block now describes the `WorkflowTaskTimedOut` event and the retried task, and says "stall" instead of "29-second Workflow Task" (also in 02, 03).
- Quote: `uv run python starter.py --block-seconds 30 --bad 1 --geo 1 \`
  Rule: command line continuation.
  The capture shows the command on one line, and the README breaks it for the 80-column code rule.
- Resolved: the receipt-gaps block in Part E names `just receipt-gaps <receipt workflow ID> <receipt workflow ID>` as the command to run, because the helper is committed (`scripts/receipt_gaps.py`, commit 9073b93).
  The printed block was captured on 2026-11-03 by an earlier script with the same output format, before the helper was committed, and the intro now says so rather than claiming `just receipt-gaps` printed it.
  Exercises 3 and 4 carry the same wording for their blocks.
  The Exercise 2 and 5 gap blocks are real `just receipt-gaps` output and are worded as such.

- Resolved: Part D step 4 now says the hinted test fails first at `assert isinstance(executor, ThreadPoolExecutor)`, because practice `build_worker` passes no `activity_executor`, and that a probe over the `async def` fails on a gap about as long as the upstream's wait.
  The ruling is the Step 20 instruction, matching the drafts.

## exercises/02-sleep-between-heartbeats/README.md

- Quote: `The SDK uses that task to send a heartbeat to the server.`
  Rule: inference.
  The capture lists Task-48 as `_ActivityWorker._heartbeat_async` with nothing beneath it, and says nothing more.
- Resolved: the throttling sentence and the 4-second cadence reads are gone from Part E, as the Step 20 ruling keeps the cadence cut.
  Part E now quotes the `LastHeartbeatTime` line from seven describe captures, which never ages past 3 seconds.
- Resolved: Parts A, B, and E draw from one run per copy (practice run 2, solution run 1 of Step 19), and the Web UI screenshots are from that same practice run 2.
  The two Grafana panel images in Part B are the exception: they come from practice run 1 of the same fleet, and the README says "an earlier run of the same fleet".
- Resolved: the README no longer describes one timeout and one retry.
  The ruling is the Step 19 retry-storm capture: the Attempt climbs to 4, the Web UI and `describe` show it, `workflow show` writes no event per retried attempt, and the README says so.
- Quote: `The `TMPRL1101` ... depends on timing.`
  Rule: frequency claim.
  The README says it appeared in all four capture runs, once per run, and may not appear in the reader's run.
  `TMPRL1104` is called the reliable signal and appeared in every run.
- Quote: `The only Activity timeout on the panel is the rollup's ScheduleToClose`
  Rule: dashboard gap, not changed here by instruction.
  The failures panel plots `activity_timeout`, which does not count Heartbeat timeouts, so the retry storm is invisible on it.

<CLAUDE_HELP>
The Grafana failures panel plots `activity_timeout` and misses the Heartbeat timeout storm in Exercise 2.
The server counter `activity_task_timeout{timeout_type="Heartbeat"}` counts it (1, 2, 3 across the run 1 window).
Should the dashboard add that series?
The README says plainly that the panel misses the storm and leaves the dashboard alone.
</CLAUDE_HELP>

- Quote: `The three points near 7.8 seconds at the left edge sit before the solution fleet started, so they are not from the solution run.`
  Rule: weak panel capture.
  The solution panel's window opens at 12:04:40, before the fleet started at 12:05:05, and the scale runs to 8 seconds because of those three points.

<CLAUDE_HELP>
The Exercise 2 solution panel image includes three pre-fleet points near 7.8 seconds, which stretch the scale so the solution lines read as zero.
Should the panel be recaptured with a window that starts at the fleet start?
</CLAUDE_HELP>

- Quote: `temporal workflow list --query 'WorkflowType="GeoEnrichmentWorkflow" AND ExecutionStatus="Running"'`
  Rule: command with no capture.
  It is the standard visibility query and was not run for this README.
- Quote: `That is a wait for a free slot and does not freeze the loop.`
  Rule: matches FINDINGS item 7.
- Part lettering: `TODO PART C` is one line in `get_location`, and the whole edit happens in Part D.
  This matches the README lettering.

## exercises/03-cpu-bound/README.md

- Quote: `The large job takes about 25 to 30 seconds on the machine that made the capture.`
  Rule: machine-dependent figure.
  The starter docstring says about 25 seconds and FINDINGS says about 29.
- Quote: `In Exercise 1 the frozen loop read 0.0 percent, because the Worker waited on a socket.`
  Rule: cross-exercise reference without a quote.
  The reading comes from the Exercise 1 capture and is not quoted here, to keep each block from its own exercise.
- Resolved: the second-Worker section now uses `ASYNC_DEBUG_METRICS_PORT=9466 uv run python worker.py`, with no scratch copy and no `METRICS_BIND_ADDRESS` edit.
  The ruling is the Step 19 capture of the shipped solution (`03-solution-second-worker`).
- Quote: `In this capture, a second Worker added CPU only once a third bad run needed a slot that the first Worker no longer had.`
  Rule: matches the Step 19 captures, worded as the capture's result and not as a rule.
  The run times (about 63 seconds each, and 30.14, 73.53, and 73.83) are first and last event times subtracted from `temporal workflow show --output json`; no tool prints them, and the README says so.
  The `describe` excerpts show the Worker identity of each run's `get_location`.
  `--bad 2` put both runs on one Worker (93.0 and 0.0 percent, about 63 seconds each), and `--bad 3` spread them (96.0 and 93.1 percent, about 189 combined; 30.14, 73.53, and 73.83 seconds).
- Quote: `The small rise is the GIL contention you read in the receipts.`
  Rule: inference.
  The panel peaks near 68 ms, and FINDINGS attributes the 79 to 110 ms first Workflow Tasks to GIL contention.

- Resolved: the second Worker needs no code change, because the solution Worker already ships the `ASYNC_DEBUG_METRICS_PORT` setting (commit 33e285b).

- Resolved: Mason ruled that `--bad 3` is the capture Part E uses, so the README describes no lowered `MAX_CONCURRENT_ACTIVITIES` and ships no setting for it.
  The old "two bad runs, one slot each, about 32 seconds" capture cannot be reproduced on the shipped solution, because the Step 19 run put both `--bad 2` runs on one Worker at the shipped two slots.

- Resolved: Part D step 4 now says the hinted test fails first at `assert isinstance(executor, ThreadPoolExecutor)`, because practice `build_worker` passes no `activity_executor`.
  The ruling is the Step 20 instruction, matching Exercise 1.

## exercises/04-zombie-thread/README.md

- Resolved: the downstream-system clause is gone, and the report now reads `its job seems to run more than once.`
- Resolved: the vague attribution is gone, and the teammate now moves the work into `asyncio.to_thread`.
- Resolved: Part C says the cancel arrives about five seconds after the failure, the third-attempt paragraph reads `ScheduleToClose`, caused by `Heartbeat`, and both log blocks now disclose their filters in active voice (the forced-timeout block ends before the Worker shutdown).
- Resolved: every trimmed or filtered capture block in all five READMEs, including every py-spy dump, now says in one active sentence what it keeps.
- Quote: `The thread did not stop, and it printed its last step in the same second.`
  Rule: matches FINDINGS.
  The capture cannot say whether the cancel or the final step came first, and the README says so.
- Quote: `Each overlapping attempt has its own thread.`
  Rule: inference from the run 1 py-spy dump.
  Run 1 has no timestamped log, so the dump time against the attempts is not shown.
- Quote: `The next block is from the second run in the capture, with the Worker output prefixed by the time of day.`
  Rule: mixed runs.
  The starter output, asyncio ps, describe, and py-spy come from run 1, and the timestamped log and the Event History come from run 2.
  The README labels the run for the log and the Event History.
- Quote: `The capture added the time prefix with a small filter`
  Rule: disclosure of a capture-time change.
  The Worker does not print the prefix.
- Quote: the Optional section on a forced timeout.
  Rule: scratch-copy capture.
  The diff is `STEP_SECONDS` 0.5 to 6.0, and the README tells the reader to do it only in a scratch copy.
- Quote: `This panel is a weak signal on its own`
  Rule: honest panel reading.
  The slot panel shows 2 then 1 for about 25 seconds in the practice run.
- Rule check: the mechanism stays "work outliving its Activity attempt", which sits next to the blocked-loop theme because the fix most readers ship first is the one that removed the freeze.
- Resolved: the startup trap 1 disclosure now reads `This block keeps the four-line tail of the error from the capture, from the `raise ValueError(` line on.`
  The old sentence called a four-line block the last line, and the Step 20 instruction named the fix.

## exercises/05-catching-blockers-early/README.md

- Quote: `The loop holds one call for about 350 to 400 milliseconds each time a geo run starts.`
  Rule: derived from the 0.347 to 0.397 second warnings and the 351 to 368 ms gaps in the shown fleet.
- Quote: `In that mode, the event loop logs a warning for every callback that runs longer than 0.1 seconds.`
  Rule: sourced from Python documentation (linked), not from a capture.
  The captured warnings are all above 0.35 seconds.
- Quote: `The warning does not name your code.`
  Rule: matches FINDINGS, and contradicts spec (get_location).
  The warning names `_ActivityWorker._handle_start_activity_task`.
- Quote: `The capture needed 9 tries before the main thread was inside the blocking call.`
  Rule: matches FINDINGS (looped, hit on try 9).
  The README gives no loop command, only "run the dump several times".
- Quote: `Here the view is almost empty.`
  Rule: weak panel.
  The practice panel has three geo points near 6 ms and no receipt line, and the solution panel has no points in its window.
  The old claim of lines between 20 and 190 ms is gone.

<CLAUDE_HELP>
The Exercise 5 Workflow Task panels have almost no points because the fleets last only a few seconds.
Should the images be recaptured over a longer run, or dropped in favor of the receipt-gaps block?
</CLAUDE_HELP>

- Quote: `No 0.35 to 0.40 second warnings appear for the archive.`
  Rule: matches the Step 19 finding that a solution debug run can show one 0.1 second callback (0.107 seconds in the second fleet), so the README does not say zero warnings.
- Quote: `The gap is 1.18 seconds, longer than the 0.35 to 0.40 seconds of the live archive.`
  Rule: matches the measured probe failure (`assert 1.1786633972078562 < 0.2`).
  The probe's own docstring in the solution test may still say 0.6 seconds, which the README does not repeat.
- Resolved: the humor line now reads `A delay this short does not show up as a failure.`
- Resolved: `Nothing stops a thread that asyncio.to_thread already started.` replaces the claim that contradicted Exercise 4.
- Resolved: the receipts-only and practice-fleet gap blocks name `just receipt-gaps <receipt workflow ID> ...`, and the README no longer tells the reader to subtract JSON event times by hand.
  The helper is committed.

## docs/drafts/part-1-healthy-worker.md

Draft status: waits for Mason's review.
Nothing here publishes.

- Resolved: the four two-sentence prerequisite bullets now put the second sentence on an indented continuation line.
- Resolved: stack direction is stated once (`asyncio ps` lists a task's calls from the innermost to the outermost), and the rollup paragraph now says the innermost call is `sleep`.
- Quote: `<!-- vale off -->` and `<!-- vale MasonBase.CodeLineLength = NO -->` around every `text` and `python` block in all six drafts.
  Rule: Vale hygiene.
  Captured output has multi-space columns and long lines, and the wrappers keep the quotes verbatim.
- Quote: `<!-- TODO: venue not yet chosen. -->`
  Rule: no frontmatter and no venue.
  A comment holds the placeholder in every draft.
- Quote: `The machine that produced the captures in this series reports 0, which allows attaching.`
  Rule: unquoted claim.
  No capture holds `ptrace_scope`; the value comes from spec.md and one live read.
- Quote: `Set the value to 0 for your session with this command:`
  Rule: never generate new code.
  The `sysctl` command is not in any repository file or capture.
- Quote: `Previous: this is the first part.`
  Rule: tutorial-writing structure.
  The line is a navigation note, not an instruction.
- Quote: `Remember this shape.`
  Rule: voice:teaching, short imperative sentences.
  It reads as emphasis and may sit close to broetry.
- Quote: `Both ports read 1, so Prometheus saw the Worker and the server.`
  Rule: derived claim.
  The capture says only that each target reached 1 at some point in three hours.
- Quote: `The lines sit between about 6 and 32 milliseconds.`
  Rule: read from the PNG, not from a capture file.
- Quote: `- **Activity Execution Latency**` (six bold panel names in one list).
  Rule: `MasonBase.BoldOveruse` suggestion.
  The names are UI labels, so bold follows the style guide.
- Quote: `### Introduction` directly under the H1.
  Rule: `MasonBase.HeadingLevelSkip` suggestion.
  The tutorial-writing structure requires H3 here.

<CLAUDE_HELP>
The repository clone URL is missing from part 1.
The ptrace failure message and the `sysctl` command have no capture.
The backlog gauge stayed flat in every capture, so part 1 treats `temporal task-queue describe` as the reliable reading.
Confirm all three.
</CLAUDE_HELP>

## docs/drafts/part-2-sync-http-client.md

- Resolved: the stack wording follows the part 1 convention (a stuck task holds only the SDK handler, the outermost call; the top `py-spy` frame is the innermost).
- Resolved: the hinted test now fails first at the missing `activity_executor`, and a probe over the `async def` fails on a gap the length of the wait.
- Resolved: the pstree command block has a sentence before its output block.

- Quote: `That is part of the problem.`
  Rule: voice:teaching broetry and two-beat contrast.
  It carries over from the exercise README.
- Quote: `The tools told you why.`
  Rule: the same two-beat shape.
- Quote: `A 29-second stall is the mystery to solve.`
  Rule: voice:teaching, possible idiom or drama.
- Quote: `The Workflows finish and nothing looks wrong.`
  Rule: unquoted claim.
  The small healthy run has no capture.
- Quote: the `receipt-gaps.txt` block.
  Rule: the numbers come from a helper script that is not in the repository.
- Quote: `uv run python starter.py --block-seconds 30 --bad 1 --geo 1 \`
  Rule: the capture shows one line, and the draft breaks it for line length.
- Quote: `The test builds the Worker with `build_worker` and takes the executor from its configuration.`
  Rule: describes quoted solution code, not a capture.
- Quote: links to `https://docs.temporal.io/` in every Conclusion.
  Rule: vague pointer.
  The docs MCP was not reachable, so deeper links are unverified.

<CLAUDE_HELP>
Should the repository commit the receipt-gaps helper, or should the drafts quote `workflow show` excerpts?
The same question applies to parts 4 and 6.
</CLAUDE_HELP>

## docs/drafts/part-3-sleep-between-heartbeats.md

- Resolved: Step 10 no longer says the describe capture is from a second run (it is from the first); the receipt-gaps block now says it is from the second run.
- Resolved: the Heartbeat wording says the Activity records a Heartbeat and the SDK sends it when the loop is free, with no claim of one send per tick.
- Resolved: stack wording follows the part 1 convention, and the `asyncio ps` command block has a sentence before its output block.

- Quote: `The Activity heartbeats before every wait, so you expect it to pass.`
  Rule: invented framing.
  The scenario follows the exercise README.
- Quote: `The attempt never stopped, so it ran to the end of the job as a zombie.`
  Rule: voice:teaching, figurative term.
  "Zombie" comes from FINDINGS and the Step 11 READMEs.
- Quote: `The first four lines come from attempt 1.`
  Rule: derived from the log; the grep keeps five poll lines.
- Quote: `These receipts come from a second run of the same fleet, so their IDs differ from the starter output.`
  Rule: provenance claim, checked against the capture index (receipt-gaps.txt is from the second run).
- Quote: `The Workflow gives that Activity a Heartbeat timeout of five seconds.`
  Rule: series scope.
  Heartbeats and timeouts appear as scenery and as the symptom, and the draft never asks the reader to tune them.
- Quote: the `receipt-gaps.txt` block.
  Rule: helper script output, as in part 2.
- Quote: Step 8 describes the test in prose and shows no code.
  Rule: never generate new code.
  The solution test excerpt was not quoted.

<CLAUDE_HELP>
The server-side Heartbeat time advances about every four seconds in the captures, not every second.
The draft leaves that out to stay off heartbeat tuning.
Confirm that cut.
</CLAUDE_HELP>

## docs/drafts/part-4-cpu-bound.md

- Resolved: the hinted test wording matches part 2 (fails first at the missing `activity_executor`).
- Resolved: the signature block and the sync client block each have prose around them.
- Resolved: Step 10 splits each `top` and run-time pair into separate blocks with a sentence between, and the one-Worker reading is now the second `top` frame (91.0 percent), not the first.
- Resolved: stack wording follows the part 1 convention.

- Quote: `A blocking call is not always a call that waits.`
  Rule: voice:teaching opening smell check.
  The sentence is a contrast with the next lines and may read as a two-beat split.
- Quote: `The loop is live, but the GIL is not free.`
  Rule: two-beat contrast.
  It restates the FINDINGS wording.
- Quote: `The time scales with the speed of your CPU, so yours can differ.`
  Rule: unquoted claim.
  FINDINGS says the roughly 29 seconds scales with CPU speed.
- Quote: Step 10 and its two `top` captures.
  Rule: scope and reproducibility.
  The second-Worker demonstration uses scratch copies that are not in the repository.
- Quote: the `receipt-gaps.txt` block.
  Rule: helper script output.

<CLAUDE_HELP>
The shipped solution cannot start a second Worker without a metrics port change.
Should the exercise ship that setting, or should the draft drop Step 10?
</CLAUDE_HELP>

## docs/drafts/part-5-zombie-thread.md

- Resolved: Step 9 now says to add `from temporalio.exceptions import CancelledError` and to remove the unused `import asyncio`.
- Resolved: the signature block and the return line block have prose around them.
- Resolved: the forced-timeout paragraph says each attempt stops at the end of its current step, that a retry can overlap the old attempt by up to one step, and that no attempt runs to step 20; the Conclusion matches.
- Resolved: the slot-busy duration reads about 20 seconds everywhere, and the panel paragraph says it is the second run.
- Resolved: the Activity code is said to heartbeat or record a Heartbeat, not to send one.

- Quote: `Moving blocking work into `asyncio.to_thread` frees the event loop, and it looks like a complete fix.`
  Rule: voice:teaching, possible inflated framing.
- Quote: `A teammate fixed a freeze like the one in part 2`
  Rule: invented framing from the exercise README.
- Quote: `The log cannot tell you which came first.`
  Rule: matches FINDINGS, which says the capture cannot order the cancel and the last step.
- Quote: `Each overlapping attempt has its own thread.`
  Rule: derived from two `py-spy` threads and three attempts.
- Quote: `The filter drops the other log lines from the same seconds, including the traceback you read next.`
  Rule: disclosure sentence at the 25-word edge.
- Quote: Heartbeat use in Step 9.
  Rule: series scope.
  The Heartbeat is the path a cancel takes into the thread, and the draft never tunes it.
- Quote: Step 11 forced-timeout block.
  Rule: scratch copy.
  The capture comes from a modified solution that the repository does not ship.

<CLAUDE_HELP>
Step 11 depends on a scratch copy with `STEP_SECONDS` set to 6.0.
Keep it as a described extension, or cut it from the draft?
</CLAUDE_HELP>

## docs/drafts/part-6-catching-blockers-early.md

- Resolved: the intro and Conclusion say the probe catches an `async def` Activity that blocks the loop for 0.2 seconds or more with the network mocked, and drop the production claim.
- Resolved: the two test excerpts have prose between them.
- Resolved: Step 9 now runs the fix with debug mode off for the starter and receipt-gaps captures, then restarts with debug mode on for the log, and gives the debug-mode receipt range (21 to 55 ms) separately.

- Quote: `The Worker runs slower than a healthy Worker, and no alert tells you why.`
  Rule: unquoted claim.
  No capture shows an alert state.
- Quote: `The test fails the build when an `async def` Activity blocks the loop for 0.2 seconds or more with the network mocked.`
  Rule: scope of the claim.
  It states only what the probe catches.
- Quote: `The capture needed 12 tries before the main thread was inside the blocking call.`
  Rule: matches FINDINGS; the loop command is not in the draft.
- Quote: `The `PYTHONASYNCIODEBUG=1` prefix sets an environment variable for this one command.`
  Rule: explanation not tied to a capture.
- Quote: `In that mode, the event loop logs a warning for every callback that runs longer than 0.1 seconds.`
  Rule: sourced from the linked Python documentation, not a capture.
- Quote: `Across the series, you used one mechanism and a small set of tools.`
  Rule: summary sentence in the last Conclusion.
- Quote: `lines=1-9` blocks of `receipt-gaps-practice-fleet.txt` and `receipt-gaps-solution-fleet.txt`.
  Rule: the source files hold extra lines from other runs.
  The draft keeps only the first nine.

<CLAUDE_HELP>
Part 6 has no `workflow show` capture, only helper script output.
Commit a small script, or add JSON excerpts in a later capture pass?
</CLAUDE_HELP>

## README.md

- Quote: `Series: TODO (add the link when the series goes up).`
  Rule: placeholder.
  The plan asks for a series title with a TODO link, and the venue is not chosen.
- Quote: `The starter took about 62 seconds end to end in the capture.`
  Rule: unexplained number.
  The figure comes from the capture timestamps (`root-block/start.txt` at 17:14:09.5, the starter output last written at 17:15:11.2), and it fits two 30-second freezes plus a short gap.
  An earlier draft said 55 seconds, which the timestamps do not support.
- Quote: `The failure is ` followed by `ScheduleToClose` caused by `StartToClose`.
  Rule: unquoted claim.
  The root captures have no `temporal workflow show` output.
  The README names Exercise 1, whose captures hold both histories for the same kind of freeze, as the source, and it tells the reader to run the command.
- Quote: `That task times out, which the Event History records as `WorkflowTaskTimedOut`.`
  Rule: unquoted claim.
  The README reads it as a stall across two Workflow Tasks, as the exercise captures show, but no root capture holds the receipt history.
- Quote: `A second scrape about 8 seconds later, still inside the first freeze, read the same.`
  Rule: sampling scope.
  Both root scrapes (17:14:25.4 and 17:14:33.0, about 14 and 22 seconds after the starter began) fall inside the first freeze, so no root capture shows the `get_location` freeze or the slots reading of 1.
- Quote: `so a stall of about 29 seconds reads as 5 to 6 seconds on the graph.`
  Rule: figure from other captures.
  FINDINGS gives it for one 29-second stalled Workflow Task, and it is not from a root run.
  The README and CLAUDE.md scope the 30-second rate average to the latency panels, because the failures, slots, and backlog panels use other expressions.
- Quote: `asyncio ps cannot show the blocking line, and that is not a bug in the tool.`
  Rule: negation-first objection countering.
  It denies a bug before saying what the tool does, and Mason may want it to open with the tool's mechanism.
- Quote: `It survives because the starter waits for it, not because of its 120-second `start_to_close`.`
  Rule: negation-first objection countering.
  It states the denial after the cause, and Mason may want only the positive half.
- Quote: the document-level Flesch reading ease of `README.md`.
  Rule: `MasonBase.FleschReadingEase`.
  The `vale off` and `vale on` pairs around every fence hide the warning.
  With the wrappers removed, the README scores 68.39 against a target of 70, and it is not restructured for it.
- Quote: `Grafana corroborates the diagnosis, and the tooling makes it.`
  Rule: voice cadence.
  It is a two-clause aphorism that echoes the plan's "Grafana corroborates rather than teaches", and Mason may want it plainer.
- Quote: `Remember this shape, because the next lesson shows a task that does not have it.`
  Rule: forward reference, kept as a teaching transition.
- Quote: `<!-- vale off -->` around every `text` and `bash` fence.
  Rule: Vale hygiene.
  Captured blocks have long lines and multi-space columns.
  Vale stopped honoring the comment after an unwrapped `bash` fence, so the `bash` fences are wrapped too.
- Quote: `Warning: this repository contains deliberately broken code`
  Rule: `MasonBase.Adverbs` and `MasonBase.Weasel` warn on `deliberately`.
  The sentence is the original warning text and the claim is exact, so it stays.
- Quote: the headings `temporal-async-debug`, `What is in this repository`, `The headline: one Workflow type takes down another`, and `The diagnostic story: two tools for a frozen loop`.
  Rule: `MasonBase.Headings` wants title case.
  The task rules say sentence case, and the warnings are ruled false positives.
- Rule check: the review-content copy-editor agent could not run in this dispatch, because a subagent cannot launch another.
  The Vale run, the keyboard check, and a manual pass against the tutorial-writing checklist stood in for it.

<CLAUDE_HELP>
The root lessons have no `temporal workflow show` capture, so the rollup failure chain and the receipt `WorkflowTaskTimedOut` are stated in prose without a quoted block.
Should a later capture pass add the two histories?
The 29-second panel figure needs a second look against a fresh run.
</CLAUDE_HELP>
