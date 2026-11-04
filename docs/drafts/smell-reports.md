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
- Quote: the receipt-gaps block in Part E.
  Rule: the numbers come from a scratch helper script that is not in the repository.
  The README says so.

<CLAUDE_HELP>
Should the repository commit the receipt-gaps helper, or should Part E quote `workflow show` JSON instead?
The same question applies to Exercises 3, 4, and 5.
</CLAUDE_HELP>

## exercises/02-sleep-between-heartbeats/README.md

- Quote: `The SDK uses that task to send a heartbeat to the server.`
  Rule: inference.
  The capture lists Task-45 as `_ActivityWorker._heartbeat_async` with nothing beneath it, and says nothing more.
- Quote: `The Worker throttles outgoing heartbeats against the Heartbeat timeout.`
  Rule: sourced from the facts file, not from a capture.
  The capture shows `lastHeartbeatTime` advancing about every four seconds.
- Quote: `The capture comes from a second run of the same fleet, so its IDs differ from the starter output shown earlier.`
  Rule: mixed runs.
  The describe capture is from run 2, and the starter output, receipt, Worker log, and JSON are from run 1.
- Resolved: Part E now says its heartbeat reads and Event History come from a second run, and the event-count sentence names the `get_location` Activity (events 11 to 13).
- Quote: `The text output of `temporal workflow show` lists no failure for this run`
  Rule: matches FINDINGS, and contradicts the plan's "retry storm" and "attempt after attempt".
  The README describes one Heartbeat timeout, one retry that waits for the thaw, and a zombie.
- Quote: `The Activity heartbeats every second, but the heartbeat time on the server advances about every four seconds.`
  Rule: contradicts spec ("advancing every second").
  The README follows the capture.
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
- Quote: `Optional: add CPU with a second Worker process`
  Rule: not reproducible as shipped.
  The solution Worker binds port 9464, and the captures used scratch copies with one slot each on ports 9466 and 9467.
  The README states both caveats and quotes scratch captures.
- Quote: `Two identical Workers with the default slots did not do this in the capture.`
  Rule: matches FINDINGS (both bad runs landed on one process, 65 to 66 seconds).
  The attempt1-skewed and attempt2 files are not quoted.
- Quote: `The small rise is the GIL contention you read in the receipts.`
  Rule: inference.
  The panel peaks near 68 ms, and FINDINGS attributes the 79 to 110 ms first Workflow Tasks to GIL contention.

<CLAUDE_HELP>
Should the second-Worker extension ship a port setting in the solution copy, or stay a described extension?
</CLAUDE_HELP>

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

## exercises/05-catching-blockers-early/README.md

- Quote: `The loop holds one call for about 350 milliseconds each time a geo run starts.`
  Rule: derived from the 355 to 384 ms warnings and the 298 to 394 ms gaps.
- Quote: `In that mode, the event loop logs a warning for every callback that runs longer than 0.1 seconds.`
  Rule: sourced from Python documentation (linked), not from a capture.
  The captured warnings are all above 0.35 seconds.
- Quote: `The warning does not name your code.`
  Rule: matches FINDINGS, and contradicts spec (get_location).
  The warning names `_ActivityWorker._handle_start_activity_task`.
- Quote: `The capture needed 12 tries before the main thread was inside the blocking call.`
  Rule: matches FINDINGS.
  The README gives no loop command, only "run the dump several times".
- Quote: `This panel is the fleet-wide view of what the tooling found.`
  Rule: weak panel.
  The README says the practice panel reads near 100 ms and the solution about 10 ms.
- Resolved: the humor line now reads `A delay this short does not show up as a failure.`
- Resolved: `Nothing stops a thread that asyncio.to_thread already started.` replaces the claim that contradicted Exercise 4.
- Quote: the receipts-only and practice-fleet gap blocks.
  Rule: helper script output, and the README tells the reader to subtract JSON event times by hand.

<CLAUDE_HELP>
Exercise 5 has no `workflow show` capture, only the helper output.
Should I commit a small script, or should a later capture step add JSON excerpts?
</CLAUDE_HELP>
