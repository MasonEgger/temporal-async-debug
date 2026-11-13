# Smell Reports For The Exercise READMEs

Draft status: every README below waits for Mason's review.
Nothing here publishes.
Each bullet gives the verbatim quote and the rule it may break.
The older open questions now read as "Build decision:" lines for Mason to confirm or overrule.
A tag left in a section marks a question that is still open.

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

Build decision: the failures panel stays as it is.
Exercise 02 keeps saying that the panel misses a Heartbeat timeout, and the server counter `activity_task_timeout{timeout_type="Heartbeat"}` stays out of the dashboard.

- Quote: `The three points near 7.8 seconds at the left edge sit before the solution fleet started, so they are not from the solution run.`
  Rule: weak panel capture.
  The solution panel's window opens at 12:04:40, before the fleet started at 12:05:05, and the scale runs to 8 seconds because of those three points.

Build decision: the exercise 02 solution panel images were recaptured in this build with a window that starts at the fleet start.
The pre-fleet points are gone, and the README and part 3 describe the new image.

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

- Resolved: Part E uses the `--bad 3` capture, so the README describes no lowered `MAX_CONCURRENT_ACTIVITIES` and ships no setting for it.
  This was a build decision; an earlier version of this line called it Mason's ruling, and Mason made no such ruling.
  The spec of November 10, 2026 replaces it: `--bad 2` on one Worker, then `--bad 4` on two, and the README changes in the fleet-localization build.
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
  The slot panel shows 2 then 1 for about 20 seconds in the practice run.
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

Build decision: the exercise 05 Workflow Task panels stay near empty, and one sentence says why.
A stall of about 350 milliseconds is small next to a panel that plots a 30-second rate average, and the fleets last only seconds.
The README and part 6 carry the same sentence.

- Quote: `No 0.35 to 0.40 second warnings appear for the archive.`
  Rule: matches the Step 19 finding that a solution debug run can show one 0.1 second callback (0.107 seconds in the second fleet), so the README does not say zero warnings.
- Quote: `The gap is 1.18 seconds, longer than the 0.35 to 0.40 seconds of the live archive.`
  Rule: matches the measured probe failure (`assert 1.1786633972078562 < 0.2`).
  The probe's own docstring in the solution test may still say 0.6 seconds, which the README does not repeat.
- Resolved: the humor line now reads `A delay this short does not show up as a failure.`
- Resolved: `Nothing stops a thread that asyncio.to_thread already started.` replaces the claim that contradicted Exercise 4.
- Resolved: the receipts-only and practice-fleet gap blocks name `just receipt-gaps <receipt workflow ID> ...`, and the README no longer tells the reader to subtract JSON event times by hand.
  The helper is committed.

## exercises/06-finding-the-frozen-worker/README.md

Where the README follows the capture against spec.md or plan.md:

- Quote: `In each bucket from +15s on, the receipts are slower than 2 seconds, or all but two of them are.`
  Rule: matches the flood B timeline (run 4 of 4), and contradicts the spec's claim that the fleet looks recovered before the thaw.
  The failures stop 20 seconds before the freeze ends.
  Every later bucket is still slow.
  The slowest receipt took 38.65 seconds (spec: 20.7 to 21.5).
- Quote: `The backlog was 39 Workflow Tasks, aged 3.5 seconds.`
  Rule: matches the last mid-freeze pass, and contradicts the spec's backlog of 0 in each single read.
  The README reports each pass as captured: 0 and 0, 0 and 0, 1 Workflow Task at 47 ms, then 39 and 1.
- Quote: `The pollers of the frozen identity were 6 and 8 seconds stale.`
  Rule: matches the last pass, and contradicts the plan's "the Task Queue page does not" separate the Workers.
  The early passes did not separate them, and the README says one run proves nothing.
- Quote: `The frozen Worker answered in 1.8, 1.5, 1.5, and 2.8 milliseconds.`
  Rule: raw files win over FINDINGS.
  FINDINGS lists the last pass as 35.1 and 2.8 ms for the frozen and healthy Workers.
  The raw time files read 2.8 ms for port 9464 (frozen) and 35.1 ms for port 9466 (healthy).
  The README uses the raw order.
- Quote: `Both Workers read 0.0 percent in top at the first reading.`
  Rule: matches the capture (the spec expected 10 to 100 percent while the healthy Worker carries traffic).
- Quote: `The healthy Worker had no dead-ended row in the first three readings.`
  Rule: matches the capture.
  The last reading shows one fresh dead-ended row on the healthy Worker, so the README rates `asyncio ps` as a partial separator.
- Quote: `14 of the 21 failed receipts print no Activity.`
  Rule: matches the capture and the raw receipt-gaps file (spec: 13 of 17).
- Quote: the TMPRL1101 sentence in Step 4.
  Rule: no log from these floods holds that code, so the README does not list it as a symptom.
  The sentence only points to exercise 02.
- Quote: the Web UI row of the table.
  Rule: the row reports the rendered pages of two floods run on 2026-11-13, and the README says they are not the capture.
  The two floods are two runs, so the row gives their readings and no rule.
- Quote: `The Worker that freezes can change from run to run, so this part never names one in advance.`
  Rule: every figure names identity 3193283 only after the histories do, as a reading of one capture.
- Quote: the dashboard descriptions.
  Rule: written from opening the committed PNG files, because the capture index lists the image windows and no reading of each image.
  The solution latency panel reads about 7 to 17 ms in the image, where FINDINGS says 6 to 17 ms.
- Quote: `The healthy Worker answered in 1.1, 1.6, 6.0, and 35.1 milliseconds.`
  Rule: matches the capture, which reads up to 35.1 ms and 6.0 ms on the healthy Worker where spec.md says about a millisecond.
  The README rates the metrics endpoints as not separating the Workers, because both answered in milliseconds.
- Quote: `it took about 50 seconds for 523 receipts in the capture.`
  Rule: matches the capture, where `receipt-gaps` took about 50 s for 523 receipts and spec.md says 37.7 s for 518.

Build decisions:

- Build decision: the capture index records the starter flags as `<flags>`.
  The README shows `uv run python starter.py --bad 0` and `uv run python starter.py`, and lists the defaults from the argparse.
  The counts (500 planned receipts, a 30-second lock) match the defaults.
- Build decision: the process tools need a live freeze, and the histories are complete only after the thaw.
  Step 3 says so and uses the mid-freeze readings of the capture.
  It tells the reader to rerun the flood and confirm the match with the by-identity summary.
- Build decision, on Mason's answer of 2026-11-13: the README quotes two events of the saved JSON history, with each identity masked to `PID@host`.
  The `temporal workflow show --output json` command in Step 2 is a reader command that is not in the repository.
- Build decision, on Mason's answer of 2026-11-13: two more bad floods ran to read the rendered Web UI pages.
  The row describes those pages in text, with no image.
  The row covers the Task Queue page and the Pending Activities tab, because Web UI 2.45.3 has no Workers page for the Namespace.
- Build decision: the sentence on which Worker starts the bad run's Workflow Tasks now covers both outcomes.
  In the capture the healthy Worker started all three, and in one of the later floods the Worker that froze started the first two.
- Build decision, on Mason's answer of 2026-11-13: Part A now holds a rate check.
  It tells the reader to lower `--rate` when the slowest receipt of the healthy flood takes longer than about 1 second.
  The example value, `--rate 5`, is valid for the parser, and no capture ran at that rate.
- Build decision: the README gives the inferred cause in one sentence marked as an inference.
  The cause is that a frozen Worker takes a limited number of tasks and the healthy Worker carries the rest.
  It teaches no slot, timeout, heartbeat, or retry-policy lesson.
- Build decision: the solution run's Failures panel read No data, so one sentence says so and the README embeds no image.
- Build decision: a scratch copy outside the repository checked the failing behavior of Part D.
  The hinted solution test fails at the executor assertion on the practice copy.
  A probe test against the practice copy fails with a single 0.67 second gap for a 0.6 second hold.
- Build decision: `content-design:review-content` needs the copy-editor agent, which this run could not launch.
  Vale and a manual checklist replaced it.
- Build decision: the README keeps three SentenceCapitalization warnings.
  Vale splits two of those sentences after a possessive and splits the third in the middle of a line that starts with a capital letter.
  All three are the same false-positive class the other exercise READMEs carry.

Open points for Mason:

- Closed on 2026-11-13: Mason asked for the masked excerpt, and the README now quotes events 3 and 12.
- Closed on 2026-11-13: Mason asked for a rerun described in text, and the Web UI row now reports the rendered pages.
- Build decision: keep the measured figures for the metrics response times and the `receipt-gaps` duration; Mason may ask for the spec.md figures to be revisited.

## docs/drafts/event-loop-primer.md

Draft status: waits for Mason's review.
Nothing here publishes.
The copy-editor agent reviewed the first draft, and its reasoning-gap, overclaim, and diagram findings are applied.

- Quote: `# Understanding the asyncio event loop in a Temporal Worker`
  Rule: Diataxis type.
  The page is an explanation, not a tutorial, so it has no Prerequisites section and no steps.
  `MasonTechnical.Prerequisites` still suggests one, because `.vale.ini` applies `MasonTechnical` to all of `docs/drafts/`.
- Quote: `The [Temporal Python documentation](...) puts it this way: "the event loop can only pass the flow of control when the `await` keyword is executed."`
  Rule: `MasonBase.Passive` and `MasonBase.Modals` fire inside the two direct quotes from Temporal's documentation.
  I left the quotes verbatim.
- Quote: `await asyncio.sleep(work_seconds)` and `time.sleep(block_seconds)`
  Rule: never generate new code.
  Both lines come from the root package, dedented from their source indentation so they read on their own.
- Quote: `Server->>Server: first Workflow Task times out after 10 seconds`
  Rule: captures win.
  The 10 seconds is the gap between `WorkflowTaskStarted` and `WorkflowTaskTimedOut` in the receipt history quoted in README.md (18:11:59 to 18:12:09).
  The diagram simplifies the timing; the prose under it gives the real sequence.
- Quote: `Python hands the GIL between threads every 5 milliseconds by default`
  Rule: name a source.
  `sys.getswitchinterval()` returned 0.005 under the repository's Python 3.14.3.
- Quote: `Every poll result passes through the event loop thread, even when the work then runs somewhere else.`
  Rule: claims checked against source.
  The SDK's `_activity.py` dispatches a `def` Activity with `loop.run_in_executor`, and `_workflow.py` hands each activation to the Workflow Task pool the same way.
  No capture shows a `def` Activity stalling during a freeze, because no exercise runs one next to a blocking `async def` Activity.

Build decision: the primer stays unnumbered.
It is linked from the part 1 introduction and the root README opening, and no list needs an edit.

Build decision: diagram 3 keeps the edge for `def` Activities.
The claim was checked against the Temporal documentation during this build: a synchronous `def` Activity runs on the `activity_executor`, and an `async def` Activity runs on the event loop.

## docs/drafts/part-1-healthy-worker.md

Draft status: waits for Mason's review.
Nothing here publishes.

- Resolved: the four two-sentence prerequisite bullets now put the second sentence on an indented continuation line.
- Resolved: the clone command uses the HTTPS URL of the public repository.
- Resolved: Step 1 quotes the ptrace capture (root-ptrace/): `py-spy dump` and `asyncio ps` refuse to attach at `ptrace_scope` 1, then attach at 0.
  The failure message is no longer an open question.
- Resolved: stack direction is stated once (`asyncio ps` lists a task's calls from the innermost to the outermost), and the rollup paragraph now says the innermost call is `sleep`.
- Quote: `<!-- vale off -->` and `<!-- vale MasonBase.CodeLineLength = NO -->` around every `text` and `python` block in all six drafts.
  Rule: Vale hygiene.
  Captured output has multi-space columns and long lines, and the wrappers keep the quotes verbatim.
- Quote: `<!-- TODO: venue not yet chosen. -->`
  Rule: no frontmatter and no venue.
  A comment holds the placeholder in every draft.
- Quote: `Set the value to 0 for your session with this command:`
  Rule: never generate new code.
  The `sudo sysctl` write is not in any repository file or capture, so it carries no quoted output.
  The read-only `sysctl kernel.yama.ptrace_scope` output comes from a one-line capture, and the draft says it was read after the setting changed to 0.
- Quote: `In the captures of this part, `ziggy`, `256.256.256.256`, `Milky Way Galaxy`, and `host` are stand-ins for the user name, address, location, and hostname of the capture machine.`
  Rule: privacy stand-ins.
  Parts 1 to 6 use the stand-ins Mason named on 2026-11-13, the way the exercise READMEs do, and each part carries one disclosure sentence.
- Quote: `You start the Worker in Step 3, so this first capture comes from an idle Worker started ahead of time.`
  Rule: provenance disclosure.
  The ptrace capture is of an idle root-package Worker, taken before the Step 3 Worker of this draft.
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

Build decision: part 1 quotes the read-only `sysctl kernel.yama.ptrace_scope` output, which a capture read after the setting was changed to 0.
The `sudo sysctl` write stays a command with no quoted output.
The backlog gauge stayed flat in the capture session, so `temporal task-queue describe` is the reliable backlog reading and the dashboard is corroboration.
Part 1 states the one freeze reading (a count of 1 and an age of 4.27 seconds while the gauge read 0) as a single capture.

## docs/drafts/part-2-sync-http-client.md

- Resolved: the stack wording follows the part 1 convention (a stuck task holds only the SDK handler, the outermost call; the top `py-spy` frame is the innermost).
- Resolved: the hinted test now fails first at the missing `activity_executor`, and a probe over the `async def` fails on a gap the length of the wait.
- Resolved: the pstree command block has a sentence before its output block.
- Resolved: the receipt-gaps block names `just receipt-gaps <receipt workflow ID> <receipt workflow ID>` and discloses that the capture came from the prototype script, because the helper is committed (`scripts/receipt_gaps.py`).

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
- Quote: `This block comes from an earlier script with the same output format, run on the two receipts in the solution capture.`
  Rule: provenance.
  The capture (01-solution/receipt-gaps.txt, 2026-11-03) predates `scripts/receipt_gaps.py`, so the draft names `just receipt-gaps` as the command to run and says the block came from the prototype script.
- Quote: `uv run python starter.py --block-seconds 30 --bad 1 --geo 1 \`
  Rule: the capture shows one line, and the draft breaks it for line length.
- Quote: `The test builds the Worker with `build_worker` and takes the executor from its configuration.`
  Rule: describes quoted solution code, not a capture.
- Quote: links to `https://docs.temporal.io/` in every Conclusion.
  Rule: vague pointer.
  The docs MCP was not reachable, so deeper links are unverified.

## docs/drafts/part-3-sleep-between-heartbeats.md

- Resolved: the draft is rebuilt from the Step 19 captures of the reworked exercise (practice run 2, solution run), matching the exercise 02 README.
  Steps 2 to 5 and the Web UI screenshots draw on run 2.
  The two dashboard panels are from run 1, and Step 6 says so.
- Resolved: the Web UI screenshots, the climbing Attempt in `describe`, and the failing rollup and stalled receipts open the diagnosis.
  The draft says that `workflow show` writes no event per retried attempt.
- Resolved: the `TMPRL1101` and `TMPRL1104` warnings appear as frozen-loop clues, with the counts from the captures (one failed Workflow Task in each of four runs, one legacy query each in the two runs with the Web UI open).
- Resolved: Step 6 says the failures panel plots `activity_timeout` and does not show the Heartbeat storm.
- Resolved: the receipt-gaps blocks name `just receipt-gaps`, and both captures were printed by it (02-practice-v2 and 02-solution-v2 postdate the helper).
- Resolved: `WT1` is described as running from the first `WorkflowTaskStarted` to the first `WorkflowTaskCompleted`, so it covers a timeout and its retry.
- Resolved: the 4-second Heartbeat cadence stays cut (Step 20 ruling), and the draft says the Activity records a Heartbeat and the SDK sends it when the loop is free.

- Quote: `The Activity heartbeats before every wait, so you expect it to pass.`
  Rule: invented framing.
  The scenario follows the exercise README.
- Quote: `It ran as a zombie until the cancel finally landed.`
  Rule: voice:teaching, figurative term.
  "Zombie" comes from FINDINGS and the READMEs.
- Quote: `The name suggests a deadlock in your Workflow code.`
  Rule: unquoted claim about how readers read `TMPRL1101`.
- Quote: `The Workflow gives that Activity a Heartbeat timeout of five seconds and no retry limit.`
  Rule: series scope.
  Heartbeats and timeouts appear as scenery and as the symptom, and the draft never asks the reader to tune them.
- Quote: `The receipt line starts near 55 seconds, the rollup line sits near 20 seconds, and the geo line sits between 16 and 18 seconds.`
  Rule: read from the PNG, not from a capture file.
- Quote: Step 8 describes the test in prose and shows no code.
  Rule: never generate new code.
  The solution test excerpt was not quoted.

## docs/drafts/part-4-cpu-bound.md

- Resolved: the hinted test wording matches part 2 (fails first at the missing `activity_executor`).
- Resolved: Steps 10 and 11 follow the exercise 03 README.
  Step 10 runs `--bad 2` on the first Worker alone, and Step 11 starts the second Worker with `ASYNC_DEBUG_METRICS_PORT=9466 uv run python worker.py` and runs `--bad 4`.
  The part never runs `--bad 3` or four bad runs on one Worker, and the README says why.
- Resolved: the receipt-gaps block names `just receipt-gaps` and discloses the prototype-script provenance.
- Resolved: the signature block and the sync client block each have prose around them.
- Resolved: Steps 10 and 11 split each `top`, describe, and placement summary into separate blocks with a sentence between.
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
- Quote: the run times in Steps 10 and 11 (84.47 and 84.43 seconds on one Worker, and 84.41, 84.43, 86.97, and 86.38 seconds on two).
  Rule: derived figures.
  They come from a summary computed over the run histories and not saved tool output, and the draft says so.
- Quote: `Steps 1 to 10 run one Worker with two Activity slots on purpose, as teaching code, so the failure is loud.`
  Rule: step range.
  The exercise README says "Parts A to D", and the draft names its own range, because its second Worker starts in Step 11.
- Quote: the `receipt-gaps.txt` block.
  Rule: provenance.
  The capture (03-solution/receipt-gaps.txt, 2026-11-03) predates `scripts/receipt_gaps.py`, so the draft says it came from the prototype script.

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

Build decision: the part 5 forced-timeout demo stays a described extension.
Step 11 says it needs a scratch copy with `STEP_SECONDS` set to 6.0, and the repository ships no such copy.

## docs/drafts/part-6-catching-blockers-early.md

- Resolved: the draft is rebuilt from the Step 19 captures of the reworked exercise (seeded audit trail), matching the exercise 05 README.
  It describes the trail as generated audit-log lines and says a real archiver would upload the bytes and return a key.
- Resolved: the receipt-gaps blocks name `just receipt-gaps`, and the draft no longer asks the reader to rely on an uncommitted script (the helper is `scripts/receipt_gaps.py`); the `workflow show --output json` subtraction stays as the by-hand route.
- Resolved: Step 9 runs the solution with debug mode on throughout, so the starter, receipt-gaps, and log captures come from one mode.
- Resolved: the intro and Conclusion say the probe catches an `async def` Activity that blocks the loop for 0.2 seconds or more with the network mocked, and drop the production claim.
- Resolved: the two test excerpts have prose between them.

- Quote: `The Worker runs slower than a healthy Worker, and no alert tells you why.`
  Rule: unquoted claim.
  No capture shows an alert state.
- Quote: `The test fails the build when an `async def` Activity blocks the loop for 0.2 seconds or more with the network mocked.`
  Rule: scope of the claim.
  It states only what the probe catches.
- Quote: `The capture needed 9 tries before the main thread was inside the blocking call.`
  Rule: matches INDEX row 627; the loop command is not in the draft.
- Quote: `The `PYTHONASYNCIODEBUG=1` prefix sets an environment variable for this one command.`
  Rule: explanation not tied to a capture.
- Quote: `In that mode, the event loop logs a warning for every callback that runs longer than 0.1 seconds.`
  Rule: sourced from the linked Python documentation, not a capture.
- Quote: `Across the series, you used one mechanism and a small set of tools.`
  Rule: summary sentence in the Conclusion, now followed by a pointer to part 7.
- Quote: `It comes from its own practice run of the same fleet, so its PID differs from the debug-mode run in Step 3.`
  Rule: provenance disclosure.
  The `py-spy` capture (05-practice-v2/pyspy) and the probe capture are separate runs from the fleet captures.
- Quote: `In the three practice fleets from Step 2, receipts read from 351 to 731 milliseconds, and 324 to 330 in the debug-mode practice fleet.`
  Rule: cross-run comparison.
  Each figure traces to a receipt-gaps.txt file in 05-practice-v2 and 05-solution-v2, and the draft names which fleet each range covers.

## docs/drafts/part-7-finding-the-frozen-worker.md

Where the draft follows the exercise 06 README and its captures over spec.md or plan.md:

- Quote: `In this capture, one identity holds every timeout and every failure, and that is the Worker to look at.`
  Rule: reports one run.
  The draft keeps the README hedges ("in this capture", "This is one run") and never presents the run as general.
- Quote: `Here is one inference, and the capture does not measure it.`
  Rule: unmeasured claim, marked as an inference, as in the README.
  It teaches no slot, heartbeat, timeout, or retry-policy lesson.
- Quote: `Only the process you picked from the histories has the lock wait in its dump.`
  Rule: matches the two `py-spy` captures, which read the lock wait on one Worker and an idle loop on the other.
- Quote: `This note is general practice, and it has no capture behind it.`
  Rule: the production note, carried from the README with the same disclosure.
  The Kubernetes sentences stay marked as a documentation claim and an unchecked inference.
- Quote: `The Web UI row comes from those two later floods, which had their own PIDs.`
  Rule: provenance disclosure.
  The row's readings come from two floods run on 2026-11-13 and not from the capture of 2026-11-11.
- Quote: `The next block keeps two events of that JSON from the capture.`
  Rule: provenance disclosure for the bad run identity.
  The block is a masked excerpt, and each identity reads `PID@host`.
- Quote: `The per-Worker panel is the one that separates the Workers.`
  Rule: the panel appears in Step 8, after the histories have named the Worker, and the draft says it does not find the Worker for you.
- Quote: `It plots a 30-second rate average, so read the true lengths from the histories.`
  Rule: matches the root README dashboard facts.
- Quote: `Part 3 covers where it does appear.`
  Rule: the draft names TMPRL1101 once, as the README does, and never leads with it.
- Quote: `Read your own line for the rollup, because this capture does not promise the same outcome for your run.`
  Rule: outcome hedge from the README.

Build decisions:

- Build decision: the draft is the tutorial form of the exercise 06 README, in 13 steps that follow Parts A to E in order.
  Every fenced block comes from that README or from the practice and solution copies.
  None comes from a `.masked` capture file.
  The two probe-test excerpts in Step 11 come from `solution/tests/test_probe.py`.
  The draft quotes no output of a failing probe, because no capture holds one.
- Build decision, on Mason's answer of 2026-11-13: the draft quotes the same masked JSON excerpt as the README.
  The `temporal workflow show --output json` command sits in a fenced command block.
- Build decision, on Mason's answer of 2026-11-13: the Web UI row reports the rendered pages of two later floods.
  It matches the README row and has no image.
- Build decision: the draft runs 1012 lines against the 550 to 800 planned.
  The 39 quoted blocks, the tools table, and nine images account for the difference.
  The prose steps stay short, and the blocks are the README blocks unchanged.
- Build decision: the link to the root README section on blocked event loops is a `TODO` cross-link, in the form parts 1 to 6 use.
  The primer link in the Introduction is a relative link, in the form part 1 uses, where plan.md asked for a `TODO` cross-link.
- Build decision: the Vale run leaves two `MasonBase.SentenceCapitalization` warnings.
  One is the possessive in the quoted `TODO PART C` comment of the practice file, a code comment that cannot change.
  The other moves to a different line each time the prose changes and lands inside a quoted block.
  Both are the false-positive class the exercise 06 README also carries.
- Build decision: in prose, identities such as 3193283@host and PID@hostname carry no backticks, because Vale splits sentences around those code spans.
  The draft also rewords several possessives and uses of the word "shows" for the same reason.
- Build decision: `content-design:review-content` needs the copy-editor agent, which this run could not launch.
  Vale and a manual read replaced it.
- Build decision: the tools table is the README table with five possessives reworded.

## README.md

- Quote: `Series: TODO (add the link when the series goes up).`
  Rule: placeholder.
  The plan asks for a series title with a TODO link, and the venue is not chosen.
- Quote: `The starter took about 62 seconds end to end in the capture.`
  Rule: unexplained number.
  The figure comes from the capture timestamps (`root-block/start.txt` at 17:14:09.5, the starter output last written at 17:15:11.2), and it fits two 30-second freezes plus a short gap.
  An earlier draft said 55 seconds, which the timestamps do not support.
- Resolved: the rollup's `ScheduleToClose` caused by `StartToClose` and the receipt's `WorkflowTaskTimedOut` are now quoted from the Step 19 root `just block` histories (`root-block-histories/show-rollup-8003e351...txt` and `show-receipt-6e4afdb8...txt`).
  The ruling is that every Event History claim needs a root capture behind it, and the pointer to Exercise 1 is gone.
  The histories come from a fourth run (2026-11-08), so their Workflow IDs match no other excerpt, and the README says so.
- Quote: the receipt Event History excerpt, `lines=1-9` of a 26-event history.
  Rule: trimmed capture.
  The README says in one sentence that it keeps the first seven events and drops events 8 through 26 and the Results block, and it lists the trim among the capture edits.
- Quote: `This is what `just receipt-gaps` printed for the two receipts.`
  Rule: command attribution.
  Resolved: the capture came from `just receipt-gaps` (captures/INDEX.md and the capture script agree).
  The file's first line is `just` echoing the command the recipe runs, and the README says so.
- Quote: `so WT1 of 28,816 and 28,834 milliseconds is the two Workflow Tasks together.`
  Rule: figure from a capture.
  Both figures come from `receipt-gaps.txt`, and CLAUDE.md gives the same reading (about 28.8 seconds, first `WorkflowTaskStarted` to first `WorkflowTaskCompleted`).
- Quote: `The Worker log excerpt drops the terminal color codes (ANSI escapes) from the lines it keeps.`
  Rule: disclosure of a capture edit.
  The root README quotes a Worker log in its recognition section, so the list of permitted edits names the ANSI strip.

Build decision: the root README's list of permitted capture edits gains ANSI stripping.
The root documentation refresh applied the edit.

- Quote: `A second scrape about 8 seconds later, still inside the first freeze, read the same.`
  Rule: sampling scope.
  Both root scrapes (17:14:25.4 and 17:14:33.0, about 14 and 22 seconds after the starter began) fall inside the first freeze, so no root capture shows the `get_location` freeze or the slots reading of 1.
- Quote: `The Workflow Task Execution Latency panel drew no line for the receipts in that run.`
  Rule: figure from a capture.
  The readings come from the root `just block` run of 2026-11-11: WT1 of 29,002 and 29,001 milliseconds, no receipt line, and a highest reading of about 5.1 seconds on the rollup line.
  Only the three latency panels plot a 30-second rate average; the failures, slots, and backlog panels use other expressions.

Build decision: the root README states the latency-panel reading of the 2026-11-11 run and gives no cause for it.
The exercise 01 README and draft part 2 still give a cause: the panel averages over 30 seconds.
No capture establishes that cause.

Build decision, on Mason's answer of 2026-11-13: prose uses stand-ins for the capture machine.
The root README, the exercise READMEs, and the drafts all use them.
`ziggy` is the user name, `256.256.256.256` is the public IP address, and `Milky Way Galaxy` is the location.
Paths read `/home/ziggy` and `/home/ziggy/temporal-async-debug`, and `host` stays the stand-in for the hostname.
The exercise 03 digests are new hashes of the `Milky Way Galaxy` text, because the old ones were hashes of the real location text.
The code obfuscates nothing when a reader runs it.

Build decision: the Vale run after the stand-in change reports ten `MasonBase.SentenceCapitalization` warnings that the run before it did not.
The ten sit in parts 2, 4, and 5 and in the exercise 01 and 03 READMEs, on text that did not change.
Vale splits each of those sentences after a possessive or a code span.
The ten belong to the false-positive class the exercise READMEs carry, so the text stays.

Build decision: the Web UI row in the exercise 06 README and in part 7 keeps one `MasonBase.BoldOveruse` suggestion.
The row names Web UI labels, and a label is bold in every file.

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

Build decision: the 29-second panel figure was read again in a fresh run in this build.
The README correction is part of the root documentation refresh.

Build decision: part 1 clones with the HTTPS URL, `https://github.com/MasonEgger/temporal-async-debug.git`, because the repository is public.

Build decision: the layer count is four, because `scripts/` is a layer.
The README line that says three is fixed in the root documentation refresh.
